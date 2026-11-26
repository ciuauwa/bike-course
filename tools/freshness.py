#!/usr/bin/env python3
"""Freshness check for the bike courses: which stretches does nobody seem to ride any more?

Courses are routed from OpenStreetMap, which only says a road was mapped once. This tool
adds two signals (standard library only):

  1. the Strava global heatmap (rides of the last 12 months), read through the owner's
     signed-in browser by a generated script,
  2. the last-edit date of the OpenStreetMap ways under the route (public Overpass API,
     best effort: when Overpass is down the report simply has no OSM column).

    python3 tools/freshness.py script <slug>                    print the `aside repl` script that reads the heatmap
    python3 tools/freshness.py report <slug> --heat <file> [--no-osm] [--cold N] [--faint N]
                                              [--min-len M] [--out DIR]
    python3 tools/freshness.py --selftest                       offline tests, prints SELFTEST OK

Typical use:

    aside repl "$(python3 tools/freshness.py script <slug>)" > /path/to/heat.txt
    python3 tools/freshness.py report <slug> --heat /path/to/heat.txt

The report is not a gate: it exits 0 whether or not it finds cold stretches, and non-zero only
for bad input. Heatmap data is Strava's, so it is written only under .gstack/ (git-ignored)
or outside the repo, never under courses/ or any other published path.
"""
import argparse
import bisect
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_route as cr  # noqa: E402  (same folder: hav, expand_course, load_course_data, maps_link)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_M = 25            # one sample every 25 m along the route
ZOOM = 15
TILE = 512             # heatmap tiles are 512 x 512 px
RADIUS_PX = 4          # heat of a sample = max red value within this many px (about 9.5 m at 6 deg S)
HEATMAP_PAGE = "https://www.strava.com/maps/global-heatmap?sport=Ride"
TILE_URL = ("https://content-a.strava.com/identified/globalheat/sport_Ride/grayscale/"
            "${z}/${x}/${y}.png?v=20&missing=empty")
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "bike-course-freshness/1.0"
OSM_AROUND_M = 12      # ways within this distance of the route are fetched
OSM_NEAREST_M = 25     # a sample is matched to a way only within this distance
OSM_CHUNK = 60         # at most this many polyline vertices per Overpass query
OSM_RETRIES = 3        # retries after the first attempt
DEFAULT_COLD, DEFAULT_FAINT, DEFAULT_MIN_LEN = 0, 30, 50
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class InputError(Exception):
    """Bad input: reported on stderr, exit code 2."""


# ----------------------------------------------------------- geometry
def cumulative(pts):
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + cr.hav(pts[i - 1], pts[i]))
    return cum


def point_at(pts, cum, d):
    """[lat, lon] at distance d (m) along the polyline, clamped to its ends."""
    if d <= 0 or len(pts) < 2:
        return (pts[0][0], pts[0][1])
    if d >= cum[-1]:
        return (pts[-1][0], pts[-1][1])
    j = max(0, min(len(pts) - 2, bisect.bisect_right(cum, d) - 1))
    span = cum[j + 1] - cum[j]
    t = 0.0 if span <= 0 else (d - cum[j]) / span
    return (pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t)


def resample(points, step=STEP_M):
    """Samples every `step` metres along the line, starting at 0 m: returns (samples, total_m)
    with samples = [(lat, lon, d_m), ...]. There are int(total // step) + 1 of them."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    cum = cumulative(pts)
    total = cum[-1]
    out = []
    for k in range(int(total // step) + 1):
        d = k * step
        lat, lon = point_at(pts, cum, d)
        out.append((lat, lon, float(d)))
    return out, total


def load_course(slug):
    if not SLUG_RE.match(slug or ""):
        raise InputError("bad course slug %r (use a-z, 0-9, -)" % slug)
    path = os.path.join(ROOT, "courses", slug, "course-data.js")
    if not os.path.isfile(path):
        raise InputError("no course-data.js for %r (looked at %s)" % (slug, path))
    pts = cr.expand_course(cr.load_course_data(path))
    if len(pts) < 2:
        raise InputError("course %r has fewer than 2 points" % slug)
    return pts


# ----------------------------------------------------------- tiles
def tile_pixel(lat, lon, zoom=ZOOM):
    """Standard XYZ web-mercator tile of a point and the pixel inside that 512 px tile:
    (tile_x, tile_y, px, py)."""
    n = 2 ** zoom
    lat = max(-85.0511287798, min(85.0511287798, lat))
    xf = (lon + 180.0) / 360.0 * n
    yf = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    tx, ty = int(math.floor(xf)), int(math.floor(yf))
    tx, ty = max(0, min(n - 1, tx)), max(0, min(n - 1, ty))
    px = max(0, min(TILE - 1, int((xf - tx) * TILE)))
    py = max(0, min(TILE - 1, int((yf - ty) * TILE)))
    return tx, ty, px, py


def tile_plan(samples, zoom=ZOOM):
    """{ "x/y": [sample_index, px, py, sample_index, px, py, ...] } in first-seen tile order."""
    plan = {}
    for i, (lat, lon, _d) in enumerate(samples):
        tx, ty, px, py = tile_pixel(lat, lon, zoom)
        plan.setdefault("%d/%d" % (tx, ty), []).extend([i, px, py])
    return plan


# ----------------------------------------------------------- the aside script
SCRIPT_TEMPLATE = r"""// Bike course freshness: heat of __SLUG__ along its route, from the Strava global heatmap.
// Generated by tools/freshness.py. Reads tiles through your signed-in browser; prints HEAT_JSON= or HEAT_ERROR=.
const CFG = __CFG__;
const pg = await openTab(__PAGE__);
try {
  await sleep(6000);
  const res = await pg.evaluate(async (cfg) => {
    const u = new URL(location.href);
    if (u.hostname !== "www.strava.com" || /^\/(login|session|signin|oauth|register)/.test(u.pathname)) {
      return { error: "not signed in (page is at " + u.hostname + u.pathname + ")" };
    }
    const heat = new Array(cfg.n).fill(0);
    const keys = Object.keys(cfg.tiles);
    let err = null;
    let next = 0;
    async function one(key) {
      const [x, y] = key.split("/");
      const url = "https://content-a.strava.com/identified/globalheat/sport_Ride/grayscale/" +
        cfg.zoom + "/" + x + "/" + y + ".png?v=20&missing=empty";
      const r = await fetch(url, { credentials: "include" });
      if (r.redirected && /login|session/.test(new URL(r.url).pathname)) { err = "tile " + key + " redirected to a login page"; return; }
      if (r.status !== 200) { err = "tile " + key + " HTTP " + r.status; return; }
      const bmp = await createImageBitmap(await r.blob());
      if (bmp.width !== 512 || bmp.height !== 512) { err = "tile " + key + " is " + bmp.width + "x" + bmp.height + ", expected 512x512"; return; }
      const cv = new OffscreenCanvas(512, 512);
      const ctx = cv.getContext("2d");
      ctx.drawImage(bmp, 0, 0);
      const px = ctx.getImageData(0, 0, 512, 512).data;
      const s = cfg.tiles[key];
      for (let k = 0; k < s.length; k += 3) {
        const cx = s[k + 1], cy = s[k + 2];
        let m = 0;
        for (let yy = Math.max(0, cy - cfg.radius); yy <= Math.min(511, cy + cfg.radius); yy++) {
          for (let xx = Math.max(0, cx - cfg.radius); xx <= Math.min(511, cx + cfg.radius); xx++) {
            const v = px[(yy * 512 + xx) * 4];
            if (v > m) m = v;
          }
        }
        heat[s[k]] = m;
      }
    }
    async function worker() {
      while (!err && next < keys.length) {
        const key = keys[next++];
        try { await one(key); } catch (e) { err = "tile " + key + " failed: " + String(e && e.message || e); }
      }
    }
    await Promise.all([worker(), worker(), worker(), worker()]);
    if (err) return { error: err };
    return { heat: heat, fetched: new Date().toISOString() };
  }, CFG);
  if (!res || res.error) {
    console.log("HEAT_ERROR=" + (res && res.error ? res.error : "no result from the page"));
  } else {
    console.log("HEAT_JSON=" + JSON.stringify({ slug: CFG.slug, stepM: CFG.stepM, zoom: CFG.zoom, fetched: res.fetched, heat: res.heat }));
  }
} catch (e) {
  console.log("HEAT_ERROR=" + String(e && e.message || e));
} finally {
  await closeTab(pg);
}
console.log("GSTACK_STEP_OK");
"""


def make_script(slug, samples):
    cfg = {"slug": slug, "stepM": STEP_M, "zoom": ZOOM, "radius": RADIUS_PX, "n": len(samples),
           "tiles": tile_plan(samples)}
    cfg_js = json.dumps(cfg, separators=(",", ":"))
    return (SCRIPT_TEMPLATE.replace("__SLUG__", slug)
            .replace("__CFG__", cfg_js)
            .replace("__PAGE__", json.dumps(HEATMAP_PAGE)))


# ----------------------------------------------------------- heat input
def parse_heat(text):
    """Accept the JSON object itself or raw `aside repl` output containing a HEAT_JSON= line."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError as e:
            raise InputError("heat file looks like JSON but does not parse: %s" % e)
    else:
        data, err = None, None
        for line in text.splitlines():
            if "HEAT_ERROR=" in line:
                err = line.split("HEAT_ERROR=", 1)[1].strip()
            m = re.search(r"HEAT_JSON=(\{.*\})\s*$", line)
            if m:
                try:
                    data = json.loads(m.group(1))
                except ValueError as e:
                    raise InputError("HEAT_JSON= line does not parse: %s" % e)
        if data is None:
            if err is not None:
                raise InputError("the browser step reported HEAT_ERROR=%s" % err)
            raise InputError("no HEAT_JSON= line (and no JSON object) found in the heat file")
    if not isinstance(data, dict) or not isinstance(data.get("heat"), list):
        raise InputError("heat data has no \"heat\" list")
    heat = data["heat"]
    if not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in heat):
        raise InputError("heat values must be integers from 0 to 255")
    step = data.get("stepM", STEP_M)
    if not isinstance(step, (int, float)) or step <= 0:
        raise InputError("heat data has a bad stepM")
    return {"slug": data.get("slug"), "stepM": step, "zoom": data.get("zoom", ZOOM),
            "fetched": data.get("fetched"), "heat": heat}


# ----------------------------------------------------------- classification
def classify(h, cold, faint):
    return "cold" if h <= cold else ("faint" if h <= faint else "ridden")


def runs_of(classes):
    out = []
    for i, c in enumerate(classes):
        if out and out[-1][0] == c:
            out[-1][2] = i
        else:
            out.append([c, i, i])
    return out


def merge_stretches(classes, step, min_len):
    """Runs of one class as [class, first_sample, last_sample]. A cold or faint run shorter than
    min_len (count * step metres) is noise (a tile edge, a junction): it takes the class of its
    longer neighbour (the earlier one on a tie), shortest first, until none is left."""
    runs = runs_of(classes)
    while len(runs) > 1:
        cand = [k for k, r in enumerate(runs)
                if r[0] != "ridden" and (r[2] - r[1] + 1) * step < min_len]
        if not cand:
            break
        k = min(cand, key=lambda j: (runs[j][2] - runs[j][1], j))
        nb = [j for j in (k - 1, k + 1) if 0 <= j < len(runs)]
        pick = max(nb, key=lambda j: ((runs[j][2] - runs[j][1]), -j))
        runs[k][0] = runs[pick][0]
        runs = runs_of([r[0] for r in runs for _ in range(r[1], r[2] + 1)])
    return runs


# ----------------------------------------------------------- OSM
class OsmUnavailable(Exception):
    pass


def thin_polyline(samples, tol_m=3.0, max_gap=4):
    """Fewer vertices for the Overpass `around` filter: Douglas-Peucker on the 25 m samples (so
    corners stay within tol_m) plus every max_gap-th sample (so no gap is longer than ~100 m)."""
    n = len(samples)
    if n <= 2:
        return [(s[0], s[1]) for s in samples]
    lat0 = sum(s[0] for s in samples) / n
    ky = cr.R * math.pi / 180.0
    kx = ky * math.cos(math.radians(lat0))
    xy = [((s[1]) * kx, (s[0] - lat0) * ky) for s in samples]
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        best, bi = -1.0, None
        for i in range(a + 1, b):
            dd, _ = cr._seg_dist(xy[i][0], xy[i][1], xy[a][0], xy[a][1], xy[b][0], xy[b][1])
            if dd > best:
                best, bi = dd, i
        if bi is not None and best > tol_m:
            keep.add(bi)
            stack.extend([(a, bi), (bi, b)])
    keep.update(range(0, n, max_gap))
    return [(samples[i][0], samples[i][1]) for i in sorted(keep)]


def chunk_polyline(poly, size=OSM_CHUNK):
    if len(poly) <= size:
        return [poly]
    out, i = [], 0
    while i < len(poly) - 1:
        out.append(poly[i:i + size])
        i += size - 1
    return out


def overpass_query(poly):
    flat = ",".join("%.6f,%.6f" % (p[0], p[1]) for p in poly)
    return '[out:json][timeout:50];way(around:%d,%s)["highway"];out meta geom;' % (OSM_AROUND_M, flat)


def overpass_post(query):
    req = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def fetch_ways(chunks, post=overpass_post, sleep=time.sleep):
    """{way_id: way} for every chunk. Retries with backoff (2, 4, 8 s) on 429/5xx and network
    errors; raises OsmUnavailable with a short reason when it still fails."""
    ways = {}
    for ci, poly in enumerate(chunks):
        query = overpass_query(poly)
        attempt = 0
        while True:
            try:
                data = json.loads(post(query))
                break
            except urllib.error.HTTPError as e:
                retry, why = e.code in (429, 500, 502, 503, 504), "HTTP %d" % e.code
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                retry, why = True, "network error: %s" % getattr(e, "reason", e)
            except ValueError:
                retry, why = True, "answer was not JSON"
            if not retry or attempt >= OSM_RETRIES:
                raise OsmUnavailable("%s (query %d of %d, %d attempt(s))" % (why, ci + 1, len(chunks), attempt + 1))
            sleep(2 ** (attempt + 1))
            attempt += 1
        for el in data.get("elements", []):
            if el.get("type") == "way" and el.get("geometry"):
                ways[el["id"]] = el
        if ci + 1 < len(chunks):
            sleep(1)
    return ways


class WayIndex:
    """Grid over the way segments (local metres) to find the nearest way to a point fast."""
    CELL = 30.0

    def __init__(self, ways, lat0, lon0):
        self.ky = cr.R * math.pi / 180.0
        self.kx = self.ky * math.cos(math.radians(lat0))
        self.lat0, self.lon0 = lat0, lon0
        self.ways = ways
        self.grid = {}
        for wid, w in ways.items():
            g = [self._xy(p["lat"], p["lon"]) for p in w["geometry"]]
            for a, b in zip(g, g[1:]):
                for cx in range(int(min(a[0], b[0]) // self.CELL), int(max(a[0], b[0]) // self.CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // self.CELL), int(max(a[1], b[1]) // self.CELL) + 1):
                        self.grid.setdefault((cx, cy), []).append((wid, a, b))

    def _xy(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)

    def nearest(self, lat, lon, max_m=OSM_NEAREST_M):
        """(way_id, distance_m) of the closest way within max_m, else None."""
        x, y = self._xy(lat, lon)
        cx, cy = int(x // self.CELL), int(y // self.CELL)
        best = None
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for wid, a, b in self.grid.get((gx, gy), ()):
                    dd, _ = cr._seg_dist(x, y, a[0], a[1], b[0], b[1])
                    if dd <= max_m and (best is None or dd < best[1]):
                        best = (wid, dd)
        return best


def way_info(w):
    tags = w.get("tags", {})
    return {"id": w["id"], "highway": tags.get("highway"), "surface": tags.get("surface"),
            "name": tags.get("name"), "lastEdit": (w.get("timestamp") or "")[:10] or None}


def osm_for_samples(samples, ways):
    """For every sample the nearest way id (or None)."""
    lat0 = sum(s[0] for s in samples) / len(samples)
    lon0 = sum(s[1] for s in samples) / len(samples)
    idx = WayIndex(ways, lat0, lon0)
    out = []
    for lat, lon, _d in samples:
        hit = idx.nearest(lat, lon)
        out.append(hit[0] if hit else None)
    return out


def stretch_way(way_ids, ways, i0, i1):
    """The way that is nearest to most samples of the stretch."""
    count = {}
    for i in range(i0, i1 + 1):
        if way_ids[i] is not None:
            count[way_ids[i]] = count.get(way_ids[i], 0) + 1
    if not count:
        return None
    wid = max(count, key=lambda k: (count[k], -k))
    return way_info(ways[wid])


def osm_course_dates(way_ids, ways):
    """Oldest and median last-edit date over the samples that sit on a mapped way."""
    dated = sorted((ways[w].get("timestamp") or "")[:10] for w in way_ids if w is not None and ways[w].get("timestamp"))
    if not dated:
        return None
    oldest_id = next(w for w in way_ids if w is not None and (ways[w].get("timestamp") or "")[:10] == dated[0])
    mid = dated[len(dated) // 2] if len(dated) % 2 else dated[len(dated) // 2 - 1]
    return {"oldest": dated[0], "oldestWay": way_info(ways[oldest_id]), "median": mid,
            "samplesOnWay": len(dated)}


# ----------------------------------------------------------- report
def tags_text(info):
    if not info:
        return "no mapped way within %d m" % OSM_NEAREST_M
    bits = ["highway=%s" % info["highway"]] if info.get("highway") else []
    if info.get("surface"):
        bits.append("surface=%s" % info["surface"])
    if info.get("name"):
        bits.append('name="%s"' % info["name"])
    return " ".join(bits) or "-"


def build_report(slug, pts, heat_data, cold=DEFAULT_COLD, faint=DEFAULT_FAINT, min_len=DEFAULT_MIN_LEN,
                 use_osm=True, post=overpass_post, sleep=time.sleep):
    """Returns (result_dict, text). Raises InputError when the heat does not fit the course."""
    step = heat_data["stepM"]
    samples, total = resample(pts, step)
    heat = heat_data["heat"]
    if len(heat) != len(samples):
        raise InputError(
            "the heat file has %d samples but %s resampled every %g m has %d: the course was rebuilt since "
            "the heat was read. Run `script` again and redo the browser step." % (len(heat), slug, step, len(samples)))
    if heat_data.get("slug") not in (None, slug):
        raise InputError("the heat file is for course %r, not %r" % (heat_data.get("slug"), slug))
    if not (0 <= cold <= faint <= 255):
        raise InputError("need 0 <= --cold <= --faint <= 255")
    classes = [classify(h, cold, faint) for h in heat]
    runs = merge_stretches(classes, step, min_len)
    merged = [c for c, i0, i1 in runs for _ in range(i0, i1 + 1)]
    n = len(merged)
    share = {k: 100.0 * merged.count(k) / n for k in ("ridden", "faint", "cold")}

    osm = {"requested": bool(use_osm), "available": False, "reason": None}
    ways, way_ids = {}, []
    if use_osm:
        try:
            ways = fetch_ways(chunk_polyline(thin_polyline(samples)), post=post, sleep=sleep)
            way_ids = osm_for_samples(samples, ways)
            osm["available"] = True
            osm["ways"] = len(ways)
            osm["course"] = osm_course_dates(way_ids, ways)
        except OsmUnavailable as e:
            osm["reason"] = str(e)
    else:
        osm["reason"] = "skipped (--no-osm)"

    cum = cumulative([(p[0], p[1]) for p in pts])
    stretches = []
    for cls, i0, i1 in runs:
        a, b = i0 * step, min((i1 + 1) * step, total)
        lat, lon = point_at([(p[0], p[1]) for p in pts], cum, (a + b) / 2.0)
        s = {"fromKm": round(a / 1000.0, 3), "toKm": round(b / 1000.0, 3), "lengthM": int(round(b - a)),
             "class": cls, "maxHeat": max(heat[i0:i1 + 1]),
             "lat": round(lat, 6), "lon": round(lon, 6), "link": cr.maps_link(lat, lon)}
        if cls != "ridden" and osm["available"]:
            s["osm"] = stretch_way(way_ids, ways, i0, i1)
        stretches.append(s)

    flagged = [s for s in stretches if s["class"] != "ridden"]
    cold_s = [s for s in stretches if s["class"] == "cold"]
    cold_m = sum(s["lengthM"] for s in cold_s)
    result = {"slug": slug, "stepM": step, "zoom": heat_data.get("zoom"), "fetched": heat_data.get("fetched"),
              "params": {"cold": cold, "faint": faint, "minLenM": min_len},
              "totalKm": round(total / 1000.0, 2),
              "share": {k: round(v, 1) for k, v in share.items()},
              "coldStretches": len(cold_s), "coldM": cold_m, "osm": osm, "stretches": stretches}

    lines = ["%s: %.1f km, %.1f%% ridden, %.1f%% faint, %.1f%% cold"
             % (slug, total / 1000.0, share["ridden"], share["faint"], share["cold"])]
    lines.append("heat: Strava global heatmap, rides of the last 12 months, read %s; cold = heat <= %d, faint = heat <= %d, "
                 "stretches under %g m folded into their neighbours" % (heat_data.get("fetched") or "at an unknown time", cold, faint, min_len))
    if use_osm and not osm["available"]:
        lines.append("OSM: unavailable (%s); the road tag and last-edit columns are left blank" % osm["reason"])
    elif use_osm:
        c = osm.get("course")
        if c:
            lines.append("OSM last edit under the route: oldest %s (%s), median %s, %d mapped way(s)" % (
                c["oldest"], tags_text(c["oldestWay"]) + " way/%d" % c["oldestWay"]["id"], c["median"], osm["ways"]))
        else:
            lines.append("OSM: no mapped way found under the route")
    lines.append("km range | length | class | max heat | road tags | OSM last edit | map")
    for s in flagged:
        info = s.get("osm")
        lines.append("km %.2f-%.2f | %d m | %s | %d | %s | %s | %s" % (
            s["fromKm"], s["toKm"], s["lengthM"], s["class"], s["maxHeat"],
            tags_text(info) if osm["available"] else "-",
            (info or {}).get("lastEdit") or "-" if osm["available"] else "-",
            s["link"]))
    if not flagged:
        lines.append("(no cold or faint stretch)")
    lines.append("FRESHNESS OK" if not cold_s else "FRESHNESS: %d cold stretch(es), total %d m" % (len(cold_s), cold_m))
    return result, "\n".join(lines) + "\n"


def safe_out_dir(out):
    """Heat data is Strava's: refuse any directory inside the repo except under .gstack/."""
    real = os.path.realpath(out)
    root = os.path.realpath(ROOT)
    inside = real == root or real.startswith(root + os.sep)
    if inside and not (real + os.sep).startswith(os.path.join(root, ".gstack") + os.sep):
        raise InputError("refusing to write heatmap-derived data to %s: inside the repo it may only go under "
                         ".gstack/ (git-ignored), because everything else is published" % out)
    return real


# ----------------------------------------------------------- commands
def cmd_script(args):
    samples, _ = resample(load_course(args.slug))
    sys.stdout.write(make_script(args.slug, samples))
    return 0


def cmd_report(args):
    pts = load_course(args.slug)
    out_dir = safe_out_dir(args.out or os.path.join(ROOT, ".gstack", "freshness", args.slug))
    try:
        with open(args.heat, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise InputError("cannot read the heat file: %s" % e)
    heat = parse_heat(text)
    result, report = build_report(args.slug, pts, heat, args.cold, args.faint, args.min_len, use_osm=not args.no_osm)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "freshness.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    with open(os.path.join(out_dir, "freshness.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write(report)
    print("written: %s" % out_dir)
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(description="Flag stretches of a course that nobody seems to ride any more.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("script", help="print the aside repl script that reads the Strava heatmap")
    s.add_argument("slug")
    r = sub.add_parser("report", help="classify the heat and (best effort) add OSM last-edit dates")
    r.add_argument("slug")
    r.add_argument("--heat", required=True, help="heat JSON, or raw aside repl output with a HEAT_JSON= line")
    r.add_argument("--no-osm", action="store_true", help="skip the Overpass query")
    r.add_argument("--cold", type=int, default=DEFAULT_COLD, help="heat <= N is cold (default %d)" % DEFAULT_COLD)
    r.add_argument("--faint", type=int, default=DEFAULT_FAINT, help="heat <= N is faint (default %d)" % DEFAULT_FAINT)
    r.add_argument("--min-len", type=float, default=DEFAULT_MIN_LEN, help="shorter cold/faint stretches are noise (m, default %d)" % DEFAULT_MIN_LEN)
    r.add_argument("--out", help="output directory (default .gstack/freshness/<slug>/)")
    args = ap.parse_args(argv)
    try:
        return cmd_script(args) if args.cmd == "script" else cmd_report(args)
    except InputError as e:
        print("freshness: %s" % e, file=sys.stderr)
        return 2


# ----------------------------------------------------------- selftest
def selftest():
    import tempfile
    fails = []

    def expect(name, cond, detail=""):
        if not cond:
            fails.append("%s %s" % (name, detail))

    # (a) tile and pixel maths. Hand-computed:
    #   lat 0, lon 0, z15: x = 0.5 * 2^15 = 16384 exactly, y = 16384 exactly -> tile 16384/16384, pixel 0,0.
    expect("(a1) origin", tile_pixel(0.0, 0.0, 15) == (16384, 16384, 0, 0), str(tile_pixel(0.0, 0.0, 15)))
    #   lat 45, lon 90, z1: x = (270/360) * 2 = 1.5 -> tile 1, pixel 0.5*512 = 256;
    #   y = (1 - asinh(tan 45deg)/pi)/2 * 2 = (1 - 0.8813736/3.1415927) = 0.719451 -> tile 0, pixel int(0.719451*512) = 368.
    expect("(a2) 45N 90E z1", tile_pixel(45.0, 90.0, 1) == (1, 0, 256, 368), str(tile_pixel(45.0, 90.0, 1)))
    #   lat 0, lon 90, z2: x = 0.75 * 4 = 3.0 -> tile 3 pixel 0; y = 0.5 * 4 = 2.0 -> tile 2 pixel 0.
    expect("(a3) 0N 90E z2", tile_pixel(0.0, 90.0, 2) == (3, 2, 0, 0), str(tile_pixel(0.0, 90.0, 2)))
    #   lon 180 (and beyond the pole) is clamped into the last tile / the first row, never out of range.
    tx, ty, px, py = tile_pixel(89.0, 180.0, 3)
    expect("(a4) clamped", (tx, ty, px) == (7, 0, 511) and 0 <= py < 512, str((tx, ty, px, py)))

    # (b) resampling a straight 1 km line at 25 m: 41 samples at 0, 25, ..., 1000 m
    line = [cr._ll(x, 0) for x in range(0, 1001, 10)]
    samples, total = resample(line, 25)
    expect("(b1) total ~1000 m", abs(total - 1000) < 1.0, str(total))
    expect("(b2) 41 samples", len(samples) == 41, str(len(samples)))
    gaps = [cr.hav(samples[i][:2], samples[i + 1][:2]) for i in range(40)]
    expect("(b3) 25 m apart", all(abs(g - 25) < 0.2 for g in gaps), str((min(gaps), max(gaps))))
    expect("(b4) distances", samples[0][2] == 0 and samples[40][2] == 1000.0)
    short, _ = resample(line[:11], 25)   # 100 m line: 0, 25, 50, 75, 100
    expect("(b5) 100 m line has 5 samples", len(short) == 5, str(len(short)))

    # (c) classification and merging
    expect("(c1) classes", [classify(h, 0, 30) for h in (0, 1, 30, 31, 255)] == ["cold", "faint", "faint", "ridden", "ridden"])
    classes = ["ridden"] * 10 + ["cold"] * 12 + ["ridden"] * 10 + ["cold"] * 1 + ["ridden"] * 10
    runs = merge_stretches(classes, 25, 50)
    expect("(c2) 300 m cold kept, 25 m cold absorbed", [(r[0], r[1], r[2]) for r in runs]
           == [("ridden", 0, 9), ("cold", 10, 21), ("ridden", 22, 42)], str(runs))
    runs = merge_stretches(["ridden"] * 5 + ["cold"] * 2 + ["ridden"] * 5, 25, 50)
    expect("(c3) 50 m is not shorter than 50 m: kept", [r[0] for r in runs] == ["ridden", "cold", "ridden"], str(runs))
    runs = merge_stretches(["ridden"] * 5 + ["cold"] * 2 + ["ridden"] * 5, 25, 51)
    expect("(c4) min-len 51: absorbed", [r[0] for r in runs] == ["ridden"], str(runs))
    runs = merge_stretches(["cold"] * 1 + ["ridden"] * 8, 25, 50)
    expect("(c5) short stretch at the start takes its only neighbour", [r[0] for r in runs] == ["ridden"], str(runs))
    runs = merge_stretches(["cold"] * 10 + ["faint"] * 1 + ["ridden"] * 4, 25, 50)
    expect("(c6) short faint between cold and ridden joins the longer (cold)", [(r[0], r[2]) for r in runs]
           == [("cold", 10), ("ridden", 14)], str(runs))
    runs = merge_stretches(["cold"] * 1 + ["faint"] * 1 + ["cold"] * 1 + ["ridden"] * 10, 25, 50)
    expect("(c7) cascading absorption ends with no short stretch",
           all(r[0] == "ridden" or (r[2] - r[1] + 1) * 25 >= 50 for r in runs) and len(runs) <= 2, str(runs))

    # (d) parsing both heat input forms, and bad input
    obj = {"slug": "x", "stepM": 25, "zoom": 15, "fetched": "2026-11-26T10:00:00Z", "heat": [0, 5, 80]}
    p1 = parse_heat(json.dumps(obj))
    raw = "noise line\nHEAT_JSON=" + json.dumps(obj, separators=(",", ":")) + "\nGSTACK_STEP_OK\n"
    p2 = parse_heat(raw)
    expect("(d1) JSON form", p1["heat"] == [0, 5, 80] and p1["slug"] == "x" and p1["stepM"] == 25, str(p1))
    expect("(d2) aside repl form", p2 == p1, str(p2))
    for name, txt, frag in (("(d3) HEAT_ERROR", "HEAT_ERROR=not signed in\nGSTACK_STEP_OK", "not signed in"),
                            ("(d4) nothing", "hello", "no HEAT_JSON"),
                            ("(d5) bad value", json.dumps({"heat": [0, 300]}), "0 to 255"),
                            ("(d6) not json", "{oops", "does not parse")):
        try:
            parse_heat(txt)
            expect(name, False, "no error raised")
        except InputError as e:
            expect(name, frag in str(e), str(e))

    # (e) sample-count mismatch, slug mismatch, and a full report on a synthetic course (no network)
    pts = [cr._ll(x, 0) for x in range(0, 2001, 20)]          # 2 km straight line, 81 samples at 25 m
    n = len(resample(pts)[0])
    heat = [80] * n
    for i in range(20, 32):                                    # 12 samples = 300 m cold (km 0.50-0.80)
        heat[i] = 0
    heat[50] = 0                                               # 25 m cold: noise
    heat[60:64] = [20, 20, 20, 20]                             # 100 m faint
    hd = {"slug": "syn", "stepM": 25, "zoom": 15, "fetched": "T", "heat": heat}
    res, text = build_report("syn", pts, hd, use_osm=False)
    kinds = [(s["class"], s["lengthM"], s["fromKm"]) for s in res["stretches"]]
    expect("(e1) report stretches", kinds == [("ridden", 500, 0.0), ("cold", 300, 0.5), ("ridden", 700, 0.8),
                                              ("faint", 100, 1.5), ("ridden", 400, 1.6)], str(kinds))
    expect("(e2) summary line", text.splitlines()[0] == "syn: 2.0 km, 80.2% ridden, 4.9% faint, 14.8% cold", text.splitlines()[0])
    expect("(e3) cold verdict", text.rstrip().splitlines()[-1] == "FRESHNESS: 1 cold stretch(es), total 300 m", text)
    expect("(e4) flagged lines", sum(1 for l in text.splitlines() if l.startswith("km ") and not l.startswith("km range")) == 2, text)
    expect("(e5) map link in the middle", "https://www.google.com/maps?q=" in text)
    hd_ok = dict(hd, heat=[80] * n)
    expect("(e6) FRESHNESS OK", build_report("syn", pts, hd_ok, use_osm=False)[1].rstrip().endswith("FRESHNESS OK"))
    try:
        build_report("syn", pts, dict(hd, heat=[80] * (n - 1)), use_osm=False)
        expect("(e7) count mismatch", False, "no error raised")
    except InputError as e:
        expect("(e7) count mismatch names the cause", "rebuilt" in str(e) and str(n - 1) in str(e), str(e))
    try:
        build_report("other", pts, hd, use_osm=False)
        expect("(e8) slug mismatch", False, "no error raised")
    except InputError as e:
        expect("(e8) slug mismatch", "not 'other'" in str(e), str(e))

    # (f) the generated script: every expected tile exactly once, every sample exactly once
    tiny = [(-6.3293, 106.6367), (-6.3293, 106.6367 + 0.012)]  # ~1.3 km east: crosses tile edges at z15
    sm, _ = resample(tiny)
    plan = tile_plan(sm)
    expected = []
    for lat, lon, _d in sm:
        t = tile_pixel(lat, lon)[:2]
        if "%d/%d" % t not in expected:
            expected.append("%d/%d" % t)
    script = make_script("tiny", sm)
    expect("(f1) tiles in plan", list(plan) == expected and len(expected) >= 2, str((list(plan), expected)))
    expect("(f2) every tile exactly once", all(script.count('"%s":[' % k) == 1 for k in expected), str(expected))
    ids = sorted(plan[k][j] for k in plan for j in range(0, len(plan[k]), 3))
    expect("(f3) every sample exactly once", ids == list(range(len(sm))), str(ids))
    expect("(f4) contract strings", all(s in script for s in ("HEAT_JSON=", "HEAT_ERROR=", "GSTACK_STEP_OK", HEATMAP_PAGE,
                                                                "credentials: \"include\"", "createImageBitmap", "OffscreenCanvas")))
    expect("(f5) no cookie access", "document.cookie" not in script and "localStorage" not in script)

    # (g) OSM: thinning, retry, graceful failure, nearest-way logic (all with fake transports)
    thinned = thin_polyline(sm)
    expect("(g1) thinning keeps the ends", thinned[0] == sm[0][:2] and thinned[-1] == sm[-1][:2])
    longpoly = [(0.0, i * 0.001) for i in range(130)]
    ch = chunk_polyline(longpoly)
    expect("(g2) chunks overlap by one point and cover all", len(ch) == 3 and ch[0][-1] == ch[1][0]
           and ch[-1][-1] == longpoly[-1] and all(len(c) <= OSM_CHUNK for c in ch), str([len(c) for c in ch]))
    calls, naps = [], []

    def flaky(query):
        calls.append(query)
        if len(calls) <= 2:
            raise urllib.error.HTTPError(OVERPASS_URL, 504, "Gateway Timeout", {}, None)
        return json.dumps({"elements": []})
    fetch_ways([longpoly[:5]], post=flaky, sleep=naps.append)
    expect("(g3) retries 504 twice then succeeds", len(calls) == 3 and naps == [2, 4], str((len(calls), naps)))
    calls.clear()
    naps.clear()

    def down(query):
        calls.append(query)
        raise urllib.error.HTTPError(OVERPASS_URL, 502, "Bad Gateway", {}, None)
    try:
        fetch_ways([longpoly[:5]], post=down, sleep=naps.append)
        expect("(g4) gives up", False, "no error raised")
    except OsmUnavailable as e:
        expect("(g4) gives up after 1 + 3 attempts", len(calls) == 4 and naps == [2, 4, 8] and "HTTP 502" in str(e), str((len(calls), naps, e)))
    calls.clear()

    def refused(query):
        calls.append(query)
        raise urllib.error.HTTPError(OVERPASS_URL, 406, "Not Acceptable", {}, None)
    try:
        fetch_ways([longpoly[:5]], post=refused, sleep=naps.append)
        expect("(g5) 406 is not retried", False, "no error raised")
    except OsmUnavailable:
        expect("(g5) 406 is not retried", len(calls) == 1, str(len(calls)))
    expect("(g6) query shape", overpass_query([(1.0, 2.0), (3.0, 4.0)]) ==
           '[out:json][timeout:50];way(around:12,1.000000,2.000000,3.000000,4.000000)["highway"];out meta geom;')

    def fake_overpass(query):
        def way(i, y, ts, tags):
            return {"type": "way", "id": i, "timestamp": ts, "tags": tags,
                    "geometry": [{"lat": cr._ll(x, y)[0], "lon": cr._ll(x, y)[1]} for x in range(-20, 2041, 20)]}
        return json.dumps({"elements": [
            way(1, 4, "2019-03-02T10:00:00Z", {"highway": "residential", "surface": "asphalt", "name": "Jl Contoh"}),
            way(2, 60, "2024-05-06T10:00:00Z", {"highway": "track"})]})
    res, text = build_report("syn", pts, hd, use_osm=True, post=fake_overpass, sleep=lambda s: None)
    cold = [s for s in res["stretches"] if s["class"] == "cold"][0]
    expect("(g7) nearest way tags", cold["osm"] and cold["osm"]["highway"] == "residential" and cold["osm"]["lastEdit"] == "2019-03-02"
           and cold["osm"]["name"] == "Jl Contoh", str(cold))
    expect("(g8) course dates", res["osm"]["course"]["oldest"] == "2019-03-02" and res["osm"]["course"]["median"] == "2019-03-02", str(res["osm"]))
    expect("(g9) tags in the text", 'highway=residential surface=asphalt name="Jl Contoh" | 2019-03-02' in text, text)
    res, text = build_report("syn", pts, hd, use_osm=True, post=down, sleep=lambda s: None)
    expect("(g10) OSM down is not fatal", not res["osm"]["available"] and "OSM: unavailable" in text
           and text.rstrip().splitlines()[-1].startswith("FRESHNESS: 1 cold"), text)

    # (h) heatmap data never goes under a published path
    for bad in (os.path.join(ROOT, "courses", "x"), ROOT, os.path.join(ROOT, "tools")):
        try:
            safe_out_dir(bad)
            expect("(h1) refuse %s" % bad, False, "no error raised")
        except InputError:
            pass
    expect("(h2) .gstack and outside the repo are fine",
           safe_out_dir(os.path.join(ROOT, ".gstack", "freshness", "x")) and safe_out_dir(tempfile.gettempdir()))

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
