#!/usr/bin/env python3
"""Build one course: python3 tools/make_course.py courses/<slug>/course.json [--force]

Routes each segment with the public BRouter service, then writes the GPX,
courses/<slug>/course-data.js (with computed turns) and courses/index.js.
Before writing anything it runs the route checker (tools/check_route.py) on the
fresh route; on errors it prints them and exits 1 without writing, unless --force.
Python 3 standard library only.
"""
import bisect
import datetime
import glob
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_route  # noqa: E402

BROUTER = "https://brouter.de/brouter"


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def hav(a, b):
    p = math.radians
    h = (math.sin(p(b[0] - a[0]) / 2) ** 2
         + math.cos(p(a[0])) * math.cos(p(b[0])) * math.sin(p(b[1] - a[1]) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


def brg(a, b):
    return math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])), b[0] - a[0])) % 360


def sd(a, b):
    return (b - a + 180) % 360 - 180


# ------------------------------------------------- climb and surface
def climb_m(elevations, threshold_m=2.0):
    """Total climb in metres from an elevation profile (hysteresis sum).

    A rise only counts once it reaches threshold_m above the reference height;
    the reference then moves up to that point. A drop of threshold_m or more
    moves the reference down without counting. Missing (None) values are skipped.
    """
    vals = [v for v in elevations if v is not None]
    if len(vals) < 2:
        return 0.0
    ref = vals[0]
    total = 0.0
    for x in vals[1:]:
        if x - ref >= threshold_m:
            total += x - ref
            ref = x
        elif ref - x >= threshold_m:
            ref = x
    return float(total)


UNPAVED_SURFACES = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth", "ground",
                    "grass", "sand", "mud", "pebblestone", "rock", "woodchips"}


def is_unpaved(tags):
    """True when a way (dict of OSM tags) counts as unpaved.

    An explicit surface tag decides. With no surface tag only highway=track and
    highway=path count as unpaved; any other untagged road counts as paved.
    """
    surface = tags.get("surface")
    if surface:
        return surface in UNPAVED_SURFACES
    return tags.get("highway") in ("track", "path")


def unpaved_m(messages):
    """Metres of unpaved route in BRouter's geojson "messages" table.

    The first row is the header; columns are looked up by name. An empty or
    missing table gives 0.0.
    """
    if not messages:
        return 0.0
    header = messages[0]
    if "Distance" not in header or "WayTags" not in header:
        fail("BRouter messages table has no Distance/WayTags columns (header: %s)" % (header,))
    di, wi = header.index("Distance"), header.index("WayTags")
    total = 0.0
    for row in messages[1:]:
        tags = {}
        for pair in str(row[wi]).split():
            k, _, v = pair.partition("=")
            tags[k] = v
        if is_unpaved(tags):
            try:
                total += float(row[di])
            except (TypeError, ValueError):
                fail("BRouter messages row has a bad Distance value: %r" % (row[di],))
    return total


# ---------------------------------------------------------------- routing
def route(waypoints, profile):
    lonlats = "%7C".join("%s,%s" % (w[1], w[0]) for w in waypoints)
    url = "%s?lonlats=%s&profile=%s&alternativeidx=0&format=geojson" % (
        BROUTER, lonlats, urllib.parse.quote(profile))
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        coords = data["features"][0]["geometry"]["coordinates"]
        props = data["features"][0].get("properties", {})
        messages = props.get("messages")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        fail("BRouter returned HTTP %s for %s: %s" % (e.code, url, body))
    except Exception as e:  # network, timeout, bad JSON
        fail("BRouter request failed (%s: %s) for %s" % (type(e).__name__, e, url))
    if len(coords) < 2:
        fail("BRouter returned an empty route for %s" % url)
    # coords are [lon, lat, ele]; unpaved is the metres of unpaved sections for one pass
    return coords, unpaved_m(messages)


def build_pieces(cfg):
    """Return (pieces, full, ascent_m, unpaved_metres) where pieces are per-segment
    [lon,lat,ele] lists, full is the expanded course (repeats applied, duplicate joins
    skipped), ascent_m is the climb of the elevation profile of full, and unpaved_metres
    is the unpaved distance summed over segments times their repeat."""
    pieces = []
    unpaved = 0.0
    for s in cfg["segments"]:
        coords, u = route(s["waypoints"], cfg["profile"])
        pieces.append(coords)
        unpaved += u * int(s.get("repeat", 1))
    full = []
    for s, pts in zip(cfg["segments"], pieces):
        for _ in range(int(s.get("repeat", 1))):
            full.extend(pts if not full else pts[1:])
    elevations = [p[2] for p in full if len(p) > 2 and p[2] is not None]
    if not elevations:
        fail("BRouter returned no elevation values for this route; cannot compute the climb")
    return pieces, full, int(round(climb_m(elevations))), int(round(unpaved))


# -------------------------------------------------------------------- GPX
def write_gpx(path, cfg, full):
    name = cfg["name"]
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="gravel-route-builder">\n'
                ' <metadata><name>%s</name></metadata>\n <trk>\n  <name>%s</name>\n  <type>%s</type>\n  <trkseg>\n'
                % (esc(name), esc(name), esc(cfg["activity"])))
        for p in full:
            ele = p[2] if len(p) > 2 else 0
            f.write('   <trkpt lat="%.6f" lon="%.6f"><ele>%.1f</ele></trkpt>\n' % (p[1], p[0], ele))
        f.write("  </trkseg>\n </trk>\n</gpx>\n")


# ------------------------------------------------------------------ turns
def compute_turns(pts, RB):
    cum = [0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + hav(pts[i - 1], pts[i]))
    total = cum[-1]

    def at(d):
        d = max(0, min(total, d))
        i = min(max(bisect.bisect_right(cum, d) - 1, 0), len(pts) - 2)
        t = 0 if cum[i + 1] == cum[i] else (d - cum[i]) / (cum[i + 1] - cum[i])
        return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t]

    STEP = 5
    B = 20
    n = int(total // STEP)
    delta = []
    for k in range(n + 1):
        d = k * STEP
        if d < B or d > total - B:
            delta.append(0)
            continue
        delta.append(sd(brg(at(d - B), at(d)), brg(at(d), at(d + B))))
    turns = []
    k = 0
    while k <= n:
        if abs(delta[k]) >= 40:
            s = k
            while k <= n and (abs(delta[k]) >= 40 or (k + 1 <= n and abs(delta[k + 1]) >= 40)
                              or (k + 2 <= n and abs(delta[k + 2]) >= 40)):
                k += 1
            e = k - 1
            ds, de = s * STEP, e * STEP
            rot = sum(sd(brg(at(j * STEP - STEP), at(j * STEP)), brg(at(j * STEP), at(j * STEP + STEP)))
                      for j in range(max(1, s - 4), min(n - 1, e + 5)))
            peak = max(range(s, e + 1), key=lambda j: abs(delta[j]))
            mid = at((ds + de) / 2)
            rb = any(hav(mid, r) < 45 for r in RB)
            a = abs(rot)
            side = 'left' if rot < 0 else 'right'
            if rb:
                if a < 35:
                    typ, text = 'roundabout', 'At the roundabout, go straight on'
                elif a > 300:
                    typ, text = 'roundabout', 'Go all the way around the roundabout'
                elif a > 150:
                    typ, text = 'uturn', 'Go around the roundabout and head back'
                else:
                    typ, text = 'roundabout-' + side, 'At the roundabout, turn ' + side
            elif a > 150:
                c = (ds + de) / 2
                if a > 300 or hav(at(c - 40), at(c + 40)) < 15:
                    typ, text = 'uturn', 'U-turn (dead end, ride back the same way)'
                else:
                    typ, text = 'sharp-' + side, 'Hairpin ' + side + ' turn'
            elif a < 30:
                continue
            elif a < 60:
                typ, text = 'slight-' + side, 'Bear ' + side
            elif a > 120:
                typ, text = 'sharp-' + side, 'Sharp ' + side + ' turn'
            else:
                typ, text = side, 'Turn ' + side
            dd = ds if (de - ds) > 30 else peak * STEP
            if dd < 60:
                typ, text = 'start', 'Start: follow the roundabout onto the boulevard'
            if dd > total - 60:
                typ, text = 'finish', 'Finish on the roundabout'
            p = at(dd)
            turns.append({'d': round(dd), 'lat': round(p[0], 6), 'lon': round(p[1], 6),
                          'type': typ, 'text': text, 'rot': round(rot)})
        else:
            k += 1
    return total, turns


# ------------------------------------------------------------- index.js
def simplify(pts, tol_m):
    """Iterative Douglas-Peucker on [lat, lon] points; tolerance in metres."""
    n = len(pts)
    if n < 3:
        return list(pts)
    lat0 = math.radians(pts[0][0])
    xy = [(math.radians(p[1]) * math.cos(lat0) * 6371000, math.radians(p[0]) * 6371000) for p in pts]

    def dist(i, a, b):
        (px, py), (ax, ay), (bx, by) = xy[i], xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        best, idx = -1, -1
        for i in range(a + 1, b):
            d = dist(i, a, b)
            if d > best:
                best, idx = d, i
        if idx >= 0 and best > tol_m:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(pts, keep) if k]


def make_preview(segments, tol_m=8, cap=250):
    pts = []
    for s in segments:
        for p in s["points"]:
            q = [round(p[0], 5), round(p[1], 5)]
            if not pts or pts[-1] != q:
                pts.append(q)
    tol = tol_m
    out = simplify(pts, tol)
    while len(out) > cap:  # widen the tolerance until it fits the cap
        tol *= 1.25
        out = simplify(pts, tol)
    return out


def write_index(root):
    entries = []
    for cj in glob.glob(os.path.join(root, "courses", "*", "course.json")):
        folder = os.path.dirname(cj)
        data_file = os.path.join(folder, "course-data.js")
        if not os.path.exists(data_file):
            continue
        with open(cj, encoding="utf-8") as f:
            cfg = json.load(f)
        with open(data_file, encoding="utf-8") as f:
            src = f.read()
        data = json.loads(src[src.index("{"):src.rindex("}") + 1])
        slug = os.path.basename(folder)
        entry = {
            "slug": slug,
            "name": cfg["name"],
            "description": cfg.get("description", ""),
            "km": round(data["totalM"] / 1000, 1),
            "gpx": "courses/%s/%s" % (slug, cfg["gpx"]),
        }
        if "added" in cfg:
            added = cfg["added"]
            ok = isinstance(added, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", added) is not None
            if ok:
                try:
                    datetime.date.fromisoformat(added)
                except ValueError:
                    ok = False
            if not ok:
                fail("%s: 'added' must be a calendar date written YYYY-MM-DD, got %r" % (folder, added))
            entry["added"] = added
        if "ascentM" in data:  # stored in course-data.js so the index needs no re-routing
            entry["ascentM"] = int(data["ascentM"])
        if "unpavedM" in data:
            entry["unpavedM"] = int(data["unpavedM"])
        entry["turns"] = len(data.get("turns", []))
        entry["stops"] = cfg.get("stops", [])
        entry["sections"] = [
            {"label": sg["label"], "repeat": int(sg.get("repeat", 1)),
             "km": round(sum(hav(a, b) for a, b in zip(sg["points"], sg["points"][1:])) / 1000, 1)}
            for sg in data["segments"]
        ]
        entry["preview"] = make_preview(data["segments"])
        for k in ("surface", "difficulty"):
            if cfg.get(k):
                entry[k] = cfg[k]
        entries.append(entry)
    # Newest first by `added`; ties and courses without `added` by name. Undated courses come last.
    entries.sort(key=lambda e: e["name"].lower())
    dated = sorted((e for e in entries if "added" in e), key=lambda e: e["added"], reverse=True)
    entries = dated + [e for e in entries if "added" not in e]
    with open(os.path.join(root, "courses", "index.js"), "w", encoding="utf-8") as f:
        f.write("// Generated by tools/make_course.py. Do not edit.\nwindow.COURSES = "
                + json.dumps(entries, indent=2, ensure_ascii=False) + ";\n")


# ------------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if len(args) != 1 or len(sys.argv) - 1 - len(args) > 1:
        fail("usage: python3 tools/make_course.py courses/<slug>/course.json [--force]")
    cj = os.path.abspath(args[0])
    if not os.path.isfile(cj):
        fail("not found: " + cj)
    folder = os.path.dirname(cj)
    root = os.path.dirname(os.path.dirname(folder))
    with open(cj, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("slug", "name", "gpx", "activity", "profile", "segments"):
        if key not in cfg:
            fail("course.json is missing '%s'" % key)
    if cfg["slug"] != os.path.basename(folder):
        fail("slug '%s' does not match folder '%s'" % (cfg["slug"], os.path.basename(folder)))

    pieces, full, ascent_m, unpaved_metres = build_pieces(cfg)

    latlon = [[p[1], p[0]] for p in full]
    RB = [tuple(r) for r in cfg.get("roundabouts", [])]
    total, turns = compute_turns(latlon, RB)

    findings, allowed = check_route.analyze(cfg, latlon, turns)
    for f in allowed:
        print(check_route.format_finding(f, "ALLOWED"))
    for f in findings:
        print(check_route.format_finding(f))
    errors = [f for f in findings if f["level"] == "error"]
    if errors and not force:
        print("ROUTE CHECK FAILED: %d error(s); nothing was written. Fix the waypoints, declare an intended "
              "turn-around in course.json \"outAndBack\", or rerun with --force." % len(errors), file=sys.stderr)
        sys.exit(1)
    if errors:
        print("WARNING: --force given, writing despite %d route error(s)" % len(errors))

    write_gpx(os.path.join(folder, cfg["gpx"]), cfg, full)

    data = {
        "slug": cfg["slug"],
        "name": cfg["name"],
        "description": cfg.get("description", ""),
        "gpx": cfg["gpx"],
        "totalM": round(total),
        "ascentM": ascent_m,
        "unpavedM": unpaved_metres,
        "segments": [
            {"label": s["label"], "repeat": int(s.get("repeat", 1)),
             "points": [[round(p[1], 6), round(p[0], 6)] for p in pts]}
            for s, pts in zip(cfg["segments"], pieces)
        ],
        "stops": cfg.get("stops", []),
        "turns": turns,
    }
    with open(os.path.join(folder, "course-data.js"), "w", encoding="utf-8") as f:
        f.write("// Generated by tools/make_course.py from course.json. Points are [lat, lon]. "
                "turns[].d is metres from the start along the full course.\n"
                "window.COURSE = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    write_index(root)
    print("%s: %d m, %d points, %d turns, %d m climb, %d m unpaved"
          % (cfg["slug"], round(total), len(full), len(turns), ascent_m, unpaved_metres))


if __name__ == "__main__":
    main()
