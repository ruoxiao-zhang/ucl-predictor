#!/usr/bin/env python3
"""Refresh the UCL simulator: fixtures, results and odds from ESPN, ratings from
ClubElo (falls back to our own Elo), then simulate the season and write data.json.
Standard library only.  Usage: python -X utf8 update.py [--sims 10000]
"""
import csv, datetime as dt, io, json, math, os, random, sys, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TEAMS_FILE = os.path.join(ROOT, "teams.json")
DATA_FILE = os.path.join(ROOT, "data.json")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard?dates={}"
CLUBELO = ["http://api.clubelo.com/{}", "https://api.clubelo.com/{}"]
MONTHS = ["202609", "202610", "202611", "202612", "202701"]  # league phase
LEAGUE_END = "2027-01-28"
POLYMARKET = "https://gamma-api.polymarket.com/events?slug={}"
PM_ALIAS = {"Inter Milan": "Inter"}

# Goal model: rating gap -> expected goals.  SCALE=1050 matches the Elo logistic
# (expected score 0.64 at +100, 0.76 at +200), so ClubElo ratings plug in directly.
HFA, BASE, SCALE = 65, 1.38, 1050
SIMS = 50000
LOG = []


def log(kind, msg):
    line = f"{kind:5} {msg}"
    print(line)
    LOG.append(line)


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ucl-simulator/1.0 (personal project)", "Accept": "application/json, text/csv, */*"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            err = e
            time.sleep(2 + 3 * i)
    raise err


# ---------- model ----------
def lambdas(d):
    return BASE * 10 ** (d / SCALE), BASE * 10 ** (-d / SCALE)


def pmf(l, k):
    return math.exp(-l) * l ** k / math.factorial(k)


def probs_d(d):
    lh, la = lambdas(d)
    ph = [pmf(lh, k) for k in range(12)]
    pa = [pmf(la, k) for k in range(12)]
    H = D = A = 0.0
    for i in range(12):
        for j in range(12):
            q = ph[i] * pa[j]
            if i > j: H += q
            elif i == j: D += q
            else: A += q
    s = H + D + A
    return H / s, D / s, A / s


def implied_d(market):
    """Rating gap (home advantage included) whose model H-A matches the market's."""
    target = market[0] - market[2]
    lo, hi = -1200.0, 1200.0
    for _ in range(50):
        mid = (lo + hi) / 2
        h, _, a = probs_d(mid)
        if h - a < target: lo = mid
        else: hi = mid
    return (lo + hi) / 2


def american(s):
    try:
        v = float(str(s).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if v == 0: return None
    return 100 / (v + 100) if v > 0 else -v / (-v + 100)


# ---------- sources ----------
def load_espn(by_espn):
    matches = []
    for m in MONTHS:
        try:
            d = json.loads(fetch(ESPN.format(m)))
        except Exception as e:
            log("FAIL", f"ESPN {m}: {e}")
            return None
        for ev in d.get("events", []):
            c = ev["competitions"][0]
            side = {x["homeAway"]: x for x in c["competitors"]}
            h, a = by_espn.get(side["home"]["team"]["id"]), by_espn.get(side["away"]["team"]["id"])
            if not h or not a:
                continue
            st = ev["status"]["type"]
            state = "post" if st.get("completed") else st.get("state", "pre")
            if st.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"): state = "pre"
            score = None
            if state == "post":
                score = [int(side["home"].get("score") or 0), int(side["away"].get("score") or 0)]
            market = None
            o = (c.get("odds") or [None])[0]
            if o and state == "pre":
                ml = o.get("moneyline") or {}
                def pick(x):
                    x = x or {}
                    return (x.get("close") or {}).get("odds") or (x.get("open") or {}).get("odds")
                ph, pa = american(pick(ml.get("home"))), american(pick(ml.get("away")))
                pd = american((o.get("drawOdds") or {}).get("moneyLine")) or american(pick(ml.get("draw")))
                if ph and pa and pd:
                    s = ph + pd + pa
                    market = {"p": [round(ph / s, 4), round(pd / s, 4), round(pa / s, 4)], "src": (o.get("provider") or {}).get("name", "")}
            matches.append({"id": ev["id"], "date": ev["date"], "h": h, "a": a, "state": state, "score": score, "market": market})
    return matches


def load_clubelo(teams):
    day = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
    text = None
    for u in CLUBELO:
        try:
            text = fetch(u.format(day), tries=2)
            if "Club" in text[:200]: break
            text = None
        except Exception as e:
            log("WARN", f"ClubElo {u.format(day)}: {e}")
    if not text:
        return None, day
    rows = {r["Club"].strip().lower(): float(r["Elo"]) for r in csv.DictReader(io.StringIO(text)) if r.get("Elo")}
    out = {}
    for t in teams:
        for n in t["clubelo"]:
            if n.lower() in rows:
                out[t["key"]] = round(rows[n.lower()]); break
        else:
            log("WARN", f"ClubElo has no match for {t['en']} (tried {t['clubelo']})")
    return out, day


def load_outright(teams, slug):
    """Polymarket title market: mid price per team, rescaled so the 36 teams sum to 1."""
    try:
        ev = json.loads(fetch(POLYMARKET.format(slug)))[0]
    except Exception as e:
        log("WARN", f"Polymarket: {e}")
        return None
    by_name = {t["en"].lower(): t["key"] for t in teams}
    raw = {}
    for m in ev.get("markets", []):
        if not m.get("active") or m.get("closed"):
            continue
        name = PM_ALIAS.get(m.get("groupItemTitle", ""), m.get("groupItemTitle", ""))
        k = by_name.get(name.lower())
        if not k:
            continue
        try:
            bid, ask = float(m.get("bestBid") or 0), float(m.get("bestAsk") or 0)
            p = (bid + ask) / 2 if 0 < bid <= ask else float(json.loads(m["outcomePrices"])[0])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        raw[k] = p
    if len(raw) < 30:
        log("WARN", f"Polymarket: only {len(raw)} teams matched")
        return None
    s = sum(raw.values())
    log("OK", f"Polymarket title market: {len(raw)} teams, prices sum {s:.3f}, volume ${float(ev.get('volume') or 0):,.0f}")
    return {"src": "Polymarket", "t": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z",
            "volume": round(float(ev.get("volume") or 0)), "p": {k: round(v / s, 4) for k, v in raw.items()}}


# ---------- ratings ----------
def gd_mult(gd):
    gd = abs(gd)
    return 1 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8


def walk_elo(base, base_date, matches):
    """Apply Elo updates for completed matches on/after base_date. Returns current ratings and pre-match ratings per match id."""
    r = dict(base)
    pre = {}
    for m in sorted(matches, key=lambda m: m["date"]):
        if m["state"] != "post":
            continue
        pre[m["id"]] = (r[m["h"]], r[m["a"]])
        if m["date"][:10] < base_date:
            continue
        H, D, _ = probs_d(r[m["h"]] - r[m["a"]] + HFA)
        e = H + 0.5 * D
        x, y = m["score"]
        w = 1 if x > y else 0.5 if x == y else 0
        k = 20 * gd_mult(x - y)
        r[m["h"]] += k * (w - e)
        r[m["a"]] -= k * (w - e)
    return r, pre


def active_adjustments(adjs, day):
    out = {}
    for a in adjs:
        if a.get("from", "0000") <= day <= a.get("until", "9999"):
            out[a["team"]] = out.get(a["team"], 0) + a["delta"]
    return out


# ---------- simulation ----------
def pois(rng, l):
    L, k, p = math.exp(-l), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L: return k
        k += 1


def simulate(keys, elo, matches, gap, n, seed):
    rng = random.Random(seed)
    idx = {k: i for i, k in enumerate(keys)}
    N = len(keys)
    E = [elo[k] for k in keys]
    bp, bgd, bgf = [0] * N, [0] * N, [0] * N
    remain = []
    for m in matches:
        h, a = idx[m["h"]], idx[m["a"]]
        if m["state"] == "post":
            x, y = m["score"]
            add(bp, bgd, bgf, h, a, x, y)
        else:
            remain.append((h, a, lambdas(gap[m["id"]])))

    def play(h, a, neutral=False, f=1.0):
        lh, la = lambdas(E[h] - E[a] + (0 if neutral else HFA))
        return pois(rng, lh * f), pois(rng, la * f)

    def tie(lo, hi):  # lo hosts leg 1, hi hosts leg 2
        g1, g2 = play(lo, hi), play(hi, lo)
        al, ah = g1[0] + g2[1], g1[1] + g2[0]
        if al != ah: return lo if al > ah else hi
        et = play(hi, lo, f=1 / 3)
        if et[0] != et[1]: return hi if et[0] > et[1] else lo
        return lo if rng.random() < .5 else hi

    def final(a, b):
        g = play(a, b, True)
        if g[0] != g[1]: return a if g[0] > g[1] else b
        g = play(a, b, True, 1 / 3)
        if g[0] != g[1]: return a if g[0] > g[1] else b
        return a if rng.random() < .5 else b

    def sh(x, y):
        return (x, y) if rng.random() < .5 else (y, x)

    C = {k: [0.0] * N for k in ("top8", "top24", "r16", "qf", "sf", "fin", "win", "pts", "pos")}
    for _ in range(n):
        pts, gd, gf = bp[:], bgd[:], bgf[:]
        for h, a, (lh, la) in remain:
            add(pts, gd, gf, h, a, pois(rng, lh), pois(rng, la))
        R = sorted(range(N), key=lambda t: (-pts[t], -gd[t], -gf[t], rng.random()))
        rank = [0] * N
        for i, t in enumerate(R):
            rank[t] = i
            C["pts"][t] += pts[t]; C["pos"][t] += i + 1
            if i < 8: C["top8"][t] += 1
            if i < 24: C["top24"][t] += 1
        pw = []
        for u, l in ((8, 22), (10, 20), (12, 18), (14, 16)):
            lo = sh(R[l], R[l + 1])
            pw.append((tie(lo[0], R[u]), tie(lo[1], R[u + 1])))
        r16 = []
        for k in range(4):
            w = sh(*pw[3 - k])
            r16 += [(R[2 * k], w[0]), (R[2 * k + 1], w[1])]
        W = []
        for hi, lo in r16:
            C["r16"][hi] += 1; C["r16"][lo] += 1
            W.append(tie(lo, hi))
        ko = lambda a, b: tie(b, a) if rank[a] < rank[b] else tie(a, b)
        p78, p34, p56 = sh(W[6], W[7]), sh(W[2], W[3]), sh(W[4], W[5])
        qw = []
        for a, b in ((W[0], p78[0]), (p34[0], p56[0]), (W[1], p78[1]), (p34[1], p56[1])):
            C["qf"][a] += 1; C["qf"][b] += 1; qw.append(ko(a, b))
        sw = []
        for a, b in ((qw[0], qw[1]), (qw[2], qw[3])):
            C["sf"][a] += 1; C["sf"][b] += 1; sw.append(ko(a, b))
        C["fin"][sw[0]] += 1; C["fin"][sw[1]] += 1
        C["win"][final(*sw)] += 1
    out = {}
    for k, v in C.items():
        out[k] = {keys[i]: round(v[i] / n, 5 if k not in ("pts", "pos") else 2) for i in range(N)}
    return out


def add(pts, gd, gf, h, a, x, y):
    gf[h] += x; gf[a] += y; gd[h] += x - y; gd[a] += y - x
    if x > y: pts[h] += 3
    elif x < y: pts[a] += 3
    else: pts[h] += 1; pts[a] += 1


# ---------- main ----------
def main():
    n = SIMS
    if "--sims" in sys.argv: n = int(sys.argv[sys.argv.index("--sims") + 1])
    cfg = json.load(open(TEAMS_FILE, encoding="utf-8"))
    teams = cfg["teams"]
    keys = [t["key"] for t in teams]
    by_espn = {t["espn"]: t["key"] for t in teams}
    old = json.load(open(DATA_FILE, encoding="utf-8")) if os.path.exists(DATA_FILE) else {}
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # fixtures & results
    matches = load_espn(by_espn)
    if matches is None:
        if not old.get("matches"):
            sys.exit("ESPN unavailable and no previous data.json")
        log("WARN", "keeping previous fixtures/results")
        matches = old["matches"]
    elif old.get("matches"):
        # never lose a result we already had
        prev = {m["id"]: m for m in old["matches"]}
        for m in matches:
            p = prev.get(m["id"])
            if p and p["state"] == "post" and m["state"] != "post":
                log("WARN", f"ESPN lost result for {m['h']}-{m['a']}; kept {p['score']}")
                m.update(state="post", score=p["score"])
    league = [m for m in matches if m["date"][:10] < LEAGUE_END]
    if len(league) != 144:
        log("CHECK", f"expected 144 league-phase matches, ESPN gave {len(league)}")
    cnt = {k: 0 for k in keys}
    for m in sorted(league, key=lambda m: m["date"]):
        cnt[m["h"]] += 1; cnt[m["a"]] += 1
        m["md"] = max(cnt[m["h"]], cnt[m["a"]])

    # ratings: ClubElo base when available, else previous base; plus our Elo walk since base_date
    rs = old.get("ratings") or {"base": {t["key"]: t["elo0"] for t in teams}, "base_date": "2026-09-07", "base_source": "estimate"}
    ce, ce_day = load_clubelo(teams)
    if ce and len(ce) >= 30:
        cur_prev, _ = walk_elo(rs["base"], rs["base_date"], league)
        base = {k: ce.get(k, round(cur_prev[k])) for k in keys}
        rs = {"base": base, "base_date": ce_day, "base_source": "clubelo"}
        log("OK", f"ClubElo ratings for {len(ce)}/36 teams")
    else:
        log("WARN", f"ClubElo unavailable; using {rs['base_source']} ratings from {rs['base_date']} + own Elo updates")
    elo, pre = walk_elo(rs["base"], rs["base_date"], league)
    adj = active_adjustments(cfg.get("adjustments", []), today)
    eff = {k: elo[k] + adj.get(k, 0) for k in keys}

    # per-match predictions (frozen once a match starts)
    pred = old.get("pred", {})
    gap = {}
    for m in league:
        mid = m["id"]
        if m["state"] == "pre":
            d = eff[m["h"]] - eff[m["a"]] + HFA
            p = pred.get(mid, {})
            market = m["market"] or p.get("market")
            pred[mid] = {"model": [round(x, 4) for x in probs_d(d)], "market": market, "t": now.isoformat() + "Z", "rh": round(eff[m["h"]]), "ra": round(eff[m["a"]])}
            gap[mid] = implied_d(market["p"]) if market else d
        elif m["state"] == "in":
            gap[mid] = eff[m["h"]] - eff[m["a"]] + HFA
            if mid in pred and pred[mid].get("market"): gap[mid] = implied_d(pred[mid]["market"]["p"])
        elif mid not in pred:
            rh, ra = pre[mid]
            pred[mid] = {"model": [round(x, 4) for x in probs_d(rh - ra + HFA)], "market": None, "t": None, "backfill": True, "rh": round(rh), "ra": round(ra)}
        m.pop("market", None)

    outright = load_outright(teams, cfg["polymarket_slug"]) or old.get("outright")

    t0 = time.time()
    sim = simulate(keys, eff, league, gap, n, seed=today)
    log("OK", f"{n} simulations in {time.time() - t0:.1f}s")

    hist = [h for h in old.get("history", []) if h["t"][:10] != today]
    if not hist:  # pre-season starting point: same model, elo0 ratings, nothing played
        e0 = {t["key"]: t["elo0"] for t in teams}
        blank = [dict(m, state="pre", score=None) for m in league]
        g0 = {m["id"]: e0[m["h"]] - e0[m["a"]] + HFA for m in blank}
        s0 = simulate(keys, e0, blank, g0, n, seed="preseason")
        hist.append({"t": "2026-09-07T12:00:00Z", "played": 0, "preseason": True,
                     "win": {k: round(s0["win"][k], 4) for k in keys}, "r16": {k: round(s0["r16"][k], 4) for k in keys}, "elo": e0})
    hist.append({"t": now.isoformat() + "Z", "played": sum(m["state"] == "post" for m in league),
                 "win": {k: round(sim["win"][k], 4) for k in keys}, "r16": {k: round(sim["r16"][k], 4) for k in keys},
                 "elo": {k: round(eff[k]) for k in keys},
                 "mwin": (outright or {}).get("p")})

    out = {
        "updated": now.isoformat() + "Z",
        "model": {"hfa": HFA, "base": BASE, "scale": SCALE, "sims": n},
        "teams": [dict(key=t["key"], en=t["en"], zh=t["zh"], short=t["short"], pot=t["pot"], elo=round(eff[t["key"]]), elo0=t["elo0"], adj=adj.get(t["key"], 0)) for t in teams],
        "ratings": rs,
        "adjustments": [a for a in cfg.get("adjustments", []) if a.get("from", "0000") <= today <= a.get("until", "9999")],
        "matches": league,
        "pred": pred,
        "sim": sim,
        "outright": outright,
        "history": hist,
        "log": LOG,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    played = sum(m["state"] == "post" for m in league)
    nm = sum(1 for m in league if m["state"] == "pre" and pred[m["id"]].get("market"))
    log("OK", f"wrote data.json: {played}/{len(league)} played, {nm} upcoming matches with market odds")


if __name__ == "__main__":
    main()
