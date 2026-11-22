#!/usr/bin/env python3
"""Offline route checker for the bike courses (no network, standard library only).

    python3 tools/check_route.py                              check every courses/*/course.json that has course-data.js
    python3 tools/check_route.py courses/<slug>/course.json   check one course
    python3 tools/check_route.py --selftest                   run the built-in synthetic cases

It expands the full course from course-data.js exactly as make_course.py and
viewer.html do (segments x repeat, skipping the duplicated join point) and looks
for routing accidents:

  spur                (error) the route rides out and back along the same way
  loop                (error) a tiny closed loop (comes back within 8 m of a point passed 30-250 m earlier)
  uturn-turn          (error) a turns[] U-turn that is not at an allowed spur or roundabout
  waypoint-off-route  (warn)  a waypoint more than 15 m from the routed line
  outAndBack          (warn)  a declared turn-around point that matches no spur (stale)

A spur is allowed when its tip is within 45 m of a course.json "roundabouts"
point or within 40 m of a course.json "outAndBack" point (intended turn-arounds).

Importable: check(cfg, latlon_points, turns=None) -> list of finding dicts with
keys rule, level, message, lat, lon, d (metres from the start).
"""
import glob
import json
import math
import os
import sys

R = 6371000.0
STEP = 2.0              # resampling step in metres
SPUR_TOL = 6.0          # retraced points must stay this close (m)
SPUR_MIN = 10.0         # one-way length that counts as a spur (m)
ROUNDABOUT_R = 45.0     # spur tip / loop this close to a roundabout is fine
OUTBACK_R = 40.0        # spur tip this close to an outAndBack point is intended
UTURN_R = 60.0          # a uturn turn this close to an allowed tip / roundabout is fine
LOOP_NEAR = 8.0
LOOP_MIN, LOOP_MAX = 30.0, 250.0
WAYPOINT_MAX = 15.0


def hav(a, b):
    p = math.radians
    h = (math.sin(p(b[0] - a[0]) / 2) ** 2
         + math.cos(p(a[0])) * math.cos(p(b[0])) * math.sin(p(b[1] - a[1]) / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def maps_link(lat, lon):
    return "https://www.google.com/maps?q=%.6f,%.6f" % (lat, lon)


def _finding(rule, level, message, lat, lon, d):
    return {"rule": rule, "level": level, "message": message,
            "lat": round(lat, 6), "lon": round(lon, 6), "d": round(d, 1)}


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def analyze(cfg, latlon_points, turns=None):
    """Return (findings, allowed): findings are errors/warnings, allowed are the spurs
    that were let through by roundabouts / outAndBack."""
    pts = [(float(p[0]), float(p[1])) for p in latlon_points]
    findings, allowed = [], []
    if len(pts) < 2:
        return findings, allowed
    roundabouts = [tuple(r) for r in cfg.get("roundabouts", [])]
    outback = [tuple(r) for r in cfg.get("outAndBack", [])]

    lat0 = sum(p[0] for p in pts) / len(pts)
    lon0 = sum(p[1] for p in pts) / len(pts)
    ky = R * math.pi / 180.0
    kx = ky * math.cos(math.radians(lat0))

    def proj(p):
        return ((p[1] - lon0) * kx, (p[0] - lat0) * ky)

    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + hav(pts[i - 1], pts[i]))
    total = cum[-1]
    xy = [proj(p) for p in pts]

    # ---- resample every STEP metres along the route
    n = int(total // STEP) + 1
    rs_ll, rs = [], []
    j = 0
    for k in range(n):
        d = k * STEP
        while j < len(pts) - 2 and cum[j + 1] < d:
            j += 1
        span = cum[j + 1] - cum[j]
        t = 0.0 if span <= 0 else max(0.0, min(1.0, (d - cum[j]) / span))
        ll = (pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t)
        rs_ll.append(ll)
        rs.append(proj(ll))

    def dir_at(i):
        a, b = rs[max(i - 2, 0)], rs[min(i + 2, n - 1)]
        return (b[0] - a[0], b[1] - a[1])

    def reversed_at(i, k):
        v1, v2 = dir_at(i - k), dir_at(i + k)
        m = math.hypot(*v1) * math.hypot(*v2)
        return m > 0 and (v1[0] * v2[0] + v1[1] * v2[1]) / m < -0.3

    # ---- spurs: reversal points where the route after the tip retraces the route before it
    tol2 = SPUR_TOL * SPUR_TOL
    cand = []
    for t in range(1, n - 1):
        k = 0
        while t - k - 1 >= 0 and t + k + 1 < n:
            a, b = rs[t - k - 1], rs[t + k + 1]
            if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 > tol2:
                break
            k += 1
        while k > 3 and not reversed_at(t, k):  # drop the part beyond the junction, where both legs run the same way
            k -= 1
        if k * STEP >= SPUR_MIN:
            cand.append((t, k))
    spurs = []
    cluster = []
    for c in cand + [None]:
        if c is not None and (not cluster or c[0] - cluster[-1][0] <= 10):
            cluster.append(c)
            continue
        if cluster:
            best = max(k for _, k in cluster)
            tied = [t for t, k in cluster if k == best]
            t = tied[len(tied) // 2]
            spurs.append({"t": t, "k": best, "len": best * STEP, "ll": rs_ll[t], "d": t * STEP})
        cluster = [c] if c is not None else []

    def near(ll, plist, r):
        return any(hav(ll, q) <= r for q in plist)

    for sp in spurs:
        ll = sp["ll"]
        sp["ok"] = near(ll, roundabouts, ROUNDABOUT_R) or near(ll, outback, OUTBACK_R)
        msg = "Route rides out %d m and back along the same way (tip here)" % round(sp["len"])
        (allowed if sp["ok"] else findings).append(
            _finding("spur", "error", msg, ll[0], ll[1], sp["d"]))
    for q in outback:
        if not any(hav(sp["ll"], q) <= OUTBACK_R for sp in spurs):
            near_i = min(range(len(pts)), key=lambda i: hav(pts[i], q))
            findings.append(_finding("outAndBack", "warn",
                                     "Declared out-and-back point matches no spur (stale declaration)",
                                     q[0], q[1], cum[near_i]))

    # ---- tiny closed loops
    spur_zone = [(sp["d"] - sp["len"] - 10, sp["d"] + sp["len"] + 10) for sp in spurs]

    def in_spur(i):
        d = i * STEP
        return any(a <= d <= b for a, b in spur_zone)

    rb_xy = [proj(r) for r in roundabouts]

    def near_rb(i):
        x, y = rs[i]
        return any((x - a) ** 2 + (y - b) ** 2 <= ROUNDABOUT_R ** 2 for a, b in rb_xy)

    cell = LOOP_NEAR
    grid = {}
    for i, (x, y) in enumerate(rs):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(i)
    lo_k, hi_k = int(LOOP_MIN / STEP), int(LOOP_MAX / STEP)
    skip_until = -1
    for i in range(n):
        if i <= skip_until or in_spur(i) or near_rb(i):
            continue
        x, y = rs[i]
        cx, cy = int(x // cell), int(y // cell)
        hit = None
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for jj in grid.get((gx, gy), ()):
                    if lo_k <= i - jj <= hi_k and not in_spur(jj) and not near_rb(jj):
                        if (x - rs[jj][0]) ** 2 + (y - rs[jj][1]) ** 2 <= LOOP_NEAR ** 2:
                            hit = jj if hit is None else max(hit, jj)
        if hit is not None:
            findings.append(_finding(
                "loop", "error",
                "Tiny closed loop: the route comes back to a point it passed %d m earlier" % round((i - hit) * STEP),
                rs_ll[i][0], rs_ll[i][1], i * STEP))
            skip_until = i + int(60 / STEP)

    # ---- waypoints far from the routed line
    seen = set()
    for s in cfg.get("segments", []):
        for w in s.get("waypoints", []):
            key = (round(w[0], 7), round(w[1], 7))
            if key in seen:
                continue
            seen.add(key)
            wx, wy = proj(w)
            best, bd = 1e18, 0.0
            for i in range(len(pts) - 1):
                dd, t = _seg_dist(wx, wy, xy[i][0], xy[i][1], xy[i + 1][0], xy[i + 1][1])
                if dd < best:
                    best, bd = dd, cum[i] + t * (cum[i + 1] - cum[i])
            if best > WAYPOINT_MAX:
                findings.append(_finding(
                    "waypoint-off-route", "warn",
                    "Waypoint is %d m from the routed line (the router snapped it to another way)" % round(best),
                    w[0], w[1], bd))

    # ---- U-turn instructions that are not at an allowed spur or a roundabout
    ok_places = [sp["ll"] for sp in spurs if sp["ok"]] + roundabouts
    for t in turns or []:
        if t.get("type") != "uturn":
            continue
        ll = (t["lat"], t["lon"])
        if not near(ll, ok_places, UTURN_R):
            findings.append(_finding("uturn-turn", "error",
                                     "U-turn instruction (%s) that is not at an allowed spur or roundabout" % t.get("text", ""),
                                     ll[0], ll[1], t.get("d", 0)))

    findings.sort(key=lambda f: f["d"])
    allowed.sort(key=lambda f: f["d"])
    return findings, allowed


def check(cfg, latlon_points, turns=None):
    return analyze(cfg, latlon_points, turns)[0]


# ------------------------------------------------------------------ files
def expand_course(data):
    """Full course as [lat, lon] points: segments x repeat, skipping the duplicated join point."""
    full = []
    for s in data["segments"]:
        for _ in range(int(s.get("repeat", 1))):
            full.extend(s["points"] if not full else s["points"][1:])
    return full


def load_course_data(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return json.loads(src[src.index("{"):src.rindex("}") + 1])


def format_finding(f, tag=None):
    return "%s %s: %s | km %.2f | %.6f,%.6f | %s" % (
        tag or f["level"].upper(), f["rule"], f["message"], f["d"] / 1000.0, f["lat"], f["lon"],
        maps_link(f["lat"], f["lon"]))


def print_report(slug, findings, allowed, out=sys.stdout):
    for f in allowed:
        print(format_finding(f, "ALLOWED"), file=out)
    for f in findings:
        print(format_finding(f), file=out)
    errs = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    print("%s: %d error(s), %d warning(s), %d allowed spur(s)" % (slug, errs, warns, len(allowed)), file=out)
    return errs


# --------------------------------------------------------------- selftest
def _ll(x, y, lat0=-6.34, lon0=106.62):
    return [lat0 + y / 111194.9, lon0 + x / (111194.9 * math.cos(math.radians(lat0)))]


def _line(a, b, step=10.0):
    (x0, y0), (x1, y1) = a, b
    L = math.hypot(x1 - x0, y1 - y0)
    m = max(1, int(round(L / step)))
    return [(x0 + (x1 - x0) * i / m, y0 + (y1 - y0) * i / m) for i in range(m + 1)]


def _path(*legs):
    out = []
    for leg in legs:
        out.extend(leg if not out else leg[1:])
    return [_ll(x, y) for x, y in out]


def selftest():
    fails = []

    def expect(name, cond, detail=""):
        if not cond:
            fails.append("%s %s" % (name, detail))

    def rules(fs, level=None):
        return [f["rule"] for f in fs if level is None or f["level"] == level]

    # (a) straight road with a 22 m side spur
    spur_pts = _path(_line((0, 0), (500, 0)), _line((500, 0), (500, 22), 4), _line((500, 22), (500, 0), 4),
                     _line((500, 0), (1000, 0)))
    tip = _ll(500, 22)
    fs, al = analyze({}, spur_pts)
    sp = [f for f in fs if f["rule"] == "spur"]
    expect("(a) one spur error", len(sp) == 1 and rules(fs, "error") == ["spur"], str(fs))
    if sp:
        ln = int(sp[0]["message"].split("out ")[1].split(" m")[0])
        expect("(a) length 22+-3", abs(ln - 22) <= 3, "got %s" % ln)
        expect("(a) tip position", hav((sp[0]["lat"], sp[0]["lon"]), tip) <= 4, str(sp[0]))
        expect("(a) km position", abs(sp[0]["d"] - 522) <= 6, str(sp[0]["d"]))

    # (b) same, tip declared in outAndBack
    fs, al = analyze({"outAndBack": [tip]}, spur_pts)
    expect("(b) no error when declared", not rules(fs, "error") and not rules(fs, "warn") and len(al) == 1, str((fs, al)))
    # (b2) same, tip near a roundabout
    fs, al = analyze({"roundabouts": [_ll(500, 40)]}, spur_pts)
    expect("(b2) allowed at a roundabout", not rules(fs) and len(al) == 1, str((fs, al)))
    # (b3) stale declaration is a warning
    fs, al = analyze({"outAndBack": [_ll(100, 300)]}, _path(_line((0, 0), (1000, 0))))
    expect("(b3) stale outAndBack warns", rules(fs) == ["outAndBack"] and fs[0]["level"] == "warn", str(fs))

    # (c) square circuit ridden 3 times in the same direction
    sq = _line((0, 0), (500, 0)) + _line((500, 0), (500, 500))[1:] + _line((500, 500), (0, 500))[1:] + _line((0, 500), (0, 0))[1:]
    lap = [_ll(x, y) for x, y in sq]
    full = list(lap)
    for _ in range(2):
        full.extend(lap[1:])
    fs, al = analyze({"segments": [{"waypoints": [lap[0], _ll(500, 0), _ll(500, 500), lap[0]]}]}, full)
    expect("(c) laps give no findings", not fs and not al, str((fs, al)))

    # (d) straight out, straight back the whole way, tip not declared
    oab = _path(_line((0, 0), (800, 0)), _line((800, 0), (0, 0)))
    fs, al = analyze({}, oab)
    sp = [f for f in fs if f["rule"] == "spur"]
    expect("(d) out-and-back is one spur", len(sp) == 1, str(fs))
    if sp:
        ln = int(sp[0]["message"].split("out ")[1].split(" m")[0])
        expect("(d) length ~800", abs(ln - 800) <= 6, "got %s" % ln)
        expect("(d) tip at the far end", hav((sp[0]["lat"], sp[0]["lon"]), _ll(800, 0)) <= 6, str(sp[0]))

    # (e) a small 100 m closed loop off a straight road
    r = 100 / (2 * math.pi)
    circle = [(500 + r * math.cos(math.radians(a - 90)), r + r * math.sin(math.radians(a - 90))) for a in range(0, 361, 10)]
    loop_pts = _path(_line((0, 0), (500, 0)), circle, _line((500, 0), (1000, 0)))
    fs, al = analyze({}, loop_pts)
    expect("(e) small loop is a loop error", "loop" in rules(fs, "error") and "spur" not in rules(fs), str(fs))

    # (f) waypoint 30 m off the line
    straight = _path(_line((0, 0), (1000, 0)))
    cfg = {"segments": [{"waypoints": [_ll(0, 0), _ll(500, 30), _ll(1000, 0)]}]}
    fs, al = analyze(cfg, straight)
    expect("(f) waypoint 30 m off is a warn", rules(fs) == ["waypoint-off-route"] and fs[0]["level"] == "warn", str(fs))

    # (g) a uturn turn that is not at a spur or roundabout is an error; at an allowed tip it is fine
    t = {"type": "uturn", "text": "U-turn", "lat": tip[0], "lon": tip[1], "d": 522}
    fs, _ = analyze({}, straight, [t])
    expect("(g) stray uturn is an error", rules(fs, "error") == ["uturn-turn"], str(fs))
    fs, _ = analyze({"outAndBack": [tip]}, spur_pts, [t])
    expect("(g) uturn at an allowed spur is fine", not rules(fs, "error"), str(fs))

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print(" - " + f)
        return 1
    print("SELFTEST OK")
    return 0


# ------------------------------------------------------------------- main
def main(argv):
    if "--selftest" in argv:
        return selftest()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = [a for a in argv if not a.startswith("--")]
    paths = [os.path.abspath(a) for a in args] or sorted(glob.glob(os.path.join(root, "courses", "*", "course.json")))
    explicit = bool(args)
    total_errors = 0
    checked = 0
    for cj in paths:
        folder = os.path.dirname(cj)
        data_file = os.path.join(folder, "course-data.js")
        if not os.path.isfile(cj):
            print("ERROR: not found: " + cj)
            total_errors += 1
            continue
        if not os.path.isfile(data_file):
            if explicit:
                print("ERROR: no course-data.js next to " + cj)
                total_errors += 1
            continue
        with open(cj, encoding="utf-8") as f:
            cfg = json.load(f)
        data = load_course_data(data_file)
        pts = expand_course(data)
        findings, allowed = analyze(cfg, pts, data.get("turns", []))
        slug = cfg.get("slug", os.path.basename(folder))
        print("== %s: %d points, %.2f km" % (slug, len(pts), data.get("totalM", 0) / 1000.0))
        total_errors += print_report(slug, findings, allowed)
        checked += 1
    if total_errors:
        print("ROUTE CHECK FAILED")
        return 1
    if not checked:
        print("ROUTE CHECK FAILED: no course to check")
        return 1
    print("ROUTE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
