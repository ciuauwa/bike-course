# Bike courses

A plain static site (no framework, no build step) for riding bike courses virtually in Google Street View. `index.html` lists the courses, `viewer.html?course=<slug>` plays one, and each course has a downloadable GPX. It works when hosted (Vercel) and when opened from disk (file://).

On a phone the viewer fits the screen without scrolling: Street View on top, the turn instruction as a strip directly under the image (never over it), the map below, and the controls in a dock at the bottom within thumb reach. Speed, section jumps, the Google Maps link, the GPX link and the blank-view note sit behind the "More" button, which opens a sheet above the dock. On a desktop-width window the controls stay in the top bar and the turn banner sits over the Street View.

The turn banner is a button: tap or click it (or press Enter or Space) to jump to the turn it shows, and playback carries on from there. The header status line opens the **Course outline** (a sheet on phones, a 380 px panel on desktop) that lists every turn by lap, where tapping a turn or a lap header jumps there; test cases are in `docs/testcases/course-outline.md`.

The course list shows each course as a card with a small map of the route (stops as numbered dots), distance, climb, the highest point, the steepest gradient, the unpaved share, the main-road share, ride time at 15 km/h, turn count, an elevation profile chart, the surface and difficulty chips, the route sections and the stops. Test cases for the card are in `docs/testcases/course-card.md`. All of it comes from `courses/index.js` (`window.COURSES`), which `tools/make_course.py` regenerates from every course folder. The list shows the newest course first: entries are sorted by `added` (see course.json fields), newest first, and courses without `added` come last, ordered by name. Each entry has `slug`, `name`, `description`, `km`, `gpx`, the optional `added`, `ascentM` (total climb in metres: the sum of the rises of 2 m or more along the elevation profile of the whole course, repeats included, which is close to what Garmin Connect reports), `unpavedM` (metres of unpaved route, counting every repeat; a section is unpaved when its `surface` tag is a loose or natural one such as gravel, dirt, grass or sand, or when it has no surface tag and is a `highway=track` or `highway=path`, so roads with no surface tag count as paved), `maxEleM` and `minEleM` (the highest and lowest point of the course, in whole metres), `maxGradePct` (the steepest uphill gradient in percent, measured over a stretch of at least 100 m so a short bump cannot read as a wall; downhill is not counted), `mainRoadM` (metres of the route on main roads, counting every repeat; a main road is a way tagged `highway` trunk, primary or secondary, links included, so residential streets and tracks do not count), `profile` (the elevation chart as at most 120 `[km, metres]` points, evenly spaced along the route and always including the start, the finish, the highest and the lowest point), `turns`, `stops`, `sections` (`{label, repeat, km}`, with km for one repetition), `preview` (the outline as simplified `[lat, lon]` points, at most 250) and the optional `surface` and `difficulty`. The five elevation and main-road fields are optional, and the card leaves out whatever an older entry lacks (no `profile` means no chart). All elevation figures come from the elevation data BRouter returns along the route, which is terrain data (not a GPS barometer), so short ramps such as a bridge or an underpass are smoothed out and the steepest gradient will read lower than a bike computer might show.

## Layout

```
index.html                     course list
viewer.html                    viewer, chosen with ?course=<slug> (defaults to the first course, which is now the newest)
courses/index.js               generated list of courses (window.COURSES)
courses/<slug>/course.json     the course definition (you write this)
courses/<slug>/course-data.js  generated route + turns (window.COURSE)
courses/<slug>/<gpx>           generated GPX file
tools/make_course.py           builds a course from course.json
tools/check_route.py           offline route checker (spurs, tiny loops, stray U-turns)
tools/freshness.py             flags stretches nobody rides any more (Strava heatmap + OSM edit dates)
tools/check_site.mjs           acceptance check: node tools/check_site.mjs (also runs check_route.py)
```

## Add a course

1. Create `courses/<slug>/course.json` (slug uses only `a-z`, `0-9`, `-`, and matches the folder name). Set `added` to today's date as `YYYY-MM-DD` (or `YYYY-MM-DDTHH:MM` to order two courses added on the same day), so the course appears at the top of the list.
2. Run `python3 tools/make_course.py courses/<slug>/course.json`.
3. Open `index.html` and check the course.
4. Run `node tools/check_site.mjs`, then commit and push.

## course.json fields

| Field | Required | Meaning |
|---|---|---|
| `slug` | yes | Folder name and URL id |
| `added` | no | When the course was added: `YYYY-MM-DD`, or `YYYY-MM-DDTHH:MM` (24 h) to order two courses added on the same day. A date without a time counts as `T00:00`. The course list shows the newest first, and visitors never see the time |
| `name` | yes | Display name |
| `description` | no | One or two sentences for the course list |
| `gpx` | yes | GPX file name written into the course folder |
| `activity` | yes | GPX track type, for example `gravel_cycling` |
| `profile` | yes | BRouter profile, for example `trekking` |
| `segments` | yes | List of `{label, repeat, waypoints: [[lat, lon], ...]}`. Each segment is routed, then repeated `repeat` times in order |
| `surface` | no | Short text shown as a chip on the course list, for example `Mostly paved` |
| `difficulty` | no | Short text shown as a chip on the course list, for example `Easy, flat` |
| `stops` | no | Labelled points on the map: `[label, lat, lon]` |
| `roundabouts` | no | `[lat, lon]` of roundabouts, so turns there are described as roundabout moves |
| `outAndBack` | no | `[lat, lon]` of intended turn-around points, where the route is meant to ride out and come back the same way (see Route checks) |
| `hairpins` | no | `[lat, lon]` of mountain hairpins whose two legs run side by side (within about 8 m), so the route check does not report them as a tiny loop (see Route checks) |
| `uTurns` | no | `[lat, lon]` of intended U-turns at a gap in the median of a divided road, so the route check allows them and the turn reads "U-turn at the gap in the median" (see Route checks) |

## Route checks

`python3 tools/check_route.py` reads each course's `course-data.js` (no network) and fails with `ROUTE CHECK FAILED` (exit 1) on routing accidents. It prints one line per finding with the km position, `lat,lon` and a Google Maps link, and ends with `ROUTE OK` when there are no errors. Pass `courses/<slug>/course.json` to check one course.

| Rule | Level | Catches |
|---|---|---|
| `spur` | error | The route rides out and back along the same way (a dead-end detour of 10 m or more), found from the geometry, not from the turn list. Laps and the opposite carriageway are not spurs, only a reversal at a tip is |
| `loop` | error | A tiny closed loop: the route returns within 8 m of a point it passed 30 to 250 m earlier, and it is not within 45 m of a declared `hairpins` point |
| `uturn-turn` | error | A U-turn instruction in `turns` that is not at an allowed spur, a roundabout or within 60 m of a declared `uTurns` point |
| `waypoint-off-route` | warn | A waypoint more than 15 m from the routed line (the router snapped it to another way) |
| `outAndBack` | warn | A declared turn-around that matches no spur (stale) |
| `hairpins` | warn | A declared hairpin that matches no tiny loop (stale) |
| `uTurns` | warn | A declared U-turn point that matches no U-turn instruction (stale) |

A spur is allowed (printed as `ALLOWED`) when its tip is within 45 m of a `roundabouts` point or within 40 m of a point in the optional `outAndBack` list in `course.json`. Declare the point where you really turn around, for example `"outAndBack": [[-6.3363876, 106.6247291]]`. If a spur is unintended, move the waypoint onto the road instead.

A tiny loop is allowed (printed as `ALLOWED hairpin`) when it is within 45 m of a point in `hairpins`, for example `"hairpins": [[-6.384184, 106.58515]]`: use it for a real mountain hairpin, never to hide a routing accident. A U-turn instruction is allowed (printed as `ALLOWED u-turn`) when it is within 60 m of a point in `uTurns`, for example `"uTurns": [[-6.339759, 106.62623]]`: use it where the route really turns around at a median gap (turn left onto the boulevard, ride on, U-turn). `make_course.py` then words that turn "U-turn at the gap in the median". A declared point that matches nothing gives a `warn` so stale declarations get removed. Both fields must be lists of `[lat, lon]` number pairs.

- `python3 tools/make_course.py courses/<slug>/course.json` runs the same check on the fresh route before it writes anything. On errors it prints them and exits 1 without writing. Add `--force` as a second argument to write anyway (the findings are still printed).
- `python3 tools/check_route.py --selftest` runs synthetic cases (side spur, declared spur, repeated laps, out and back, tiny loop, far waypoint, declared hairpin, declared U-turn and their stale warnings) and prints `SELFTEST OK`.
- `node tools/check_site.mjs` also runs the route check and fails if it does.
- In the browser, `window.__viewer.lineCheck()` returns `{ maxDevM, worstIndex }`: for every view point it measures how far the blue ridden line (its vertices and segment midpoints) is from the true route polyline. It should be below 1 m. It only reads; it does not move the map or the current position.

## Is the road still there?

OpenStreetMap only says a road was mapped once. `python3 tools/freshness.py` flags stretches of a course that nobody seems to ride any more, from two signals: the Strava global heatmap (rides of the last 12 months) and the last-edit date of the OpenStreetMap ways under the route. Standard library only; the heatmap is read through your own signed-in browser, so there is no Strava login in the tool.

1. `python3 tools/freshness.py script <slug>` prints a script for `aside repl` (you must be signed in to Strava in that browser). The script samples the route every 25 m, reads the heatmap tiles it needs (zoom 15, one fetch per tile) and prints one `HEAT_JSON=` line, or `HEAT_ERROR=<reason>` (not signed in, a tile that did not load). Run it as `aside repl "$(python3 tools/freshness.py script <slug>)" > heat.txt`. It prints no cookies or tokens.
2. `python3 tools/freshness.py report <slug> --heat heat.txt` reads that output (or the bare JSON object). It refuses a file whose sample count no longer matches the course (the course was rebuilt since: redo step 1). Options: `--no-osm` skips the Overpass query, `--cold N` (default 0) and `--faint N` (default 30) set the heat limits, `--min-len M` (default 50) folds shorter cold or faint stretches into their neighbours as noise (a tile edge, a junction), `--out DIR` sets the output folder.
3. Read the report: a summary line (`km, % ridden, % faint, % cold`), then one line per cold and per faint stretch with the km range, length, maximum heat, the nearest OSM way (`highway`, `surface`, `name`), its last-edit date and a Google Maps link to the middle of the stretch, ending with `FRESHNESS OK` or `FRESHNESS: n cold stretch(es), total m m`. It always exits 0 (it is a report, not a gate); it exits 2 only for bad input. If Overpass is down or busy after 3 retries, the report is still produced, without the road and last-edit columns, and says so.

Cold means no rides on the heatmap there in the last 12 months (heat 0); faint means a trace (heat 1 to 30 of 255); everything else is ridden. An out-and-back course rides the same road twice, so a stretch is listed once per pass. `python3 tools/freshness.py --selftest` runs the offline tests and prints `SELFTEST OK`.

Limits: the heatmap covers the last 12 months and only Strava users, so a quiet village path can be cold and still exist, and a popular road can stay bright after it is closed to bikes. The OSM date is the last edit of the way itself, which says someone touched it, not that it was surveyed. A cold stretch is a prompt to look (the map link, Street View), not proof.

The heatmap is Strava's data and is not ours to republish. The report goes to `.gstack/freshness/<slug>/` (`freshness.json`, `freshness.txt`), which is git-ignored, and the tool refuses any `--out` inside the repo outside `.gstack/`. Never copy heatmap-derived numbers into `courses/` or any other published path.

## Where am I

The viewer has a **Where am I** button (a crosshair icon) on the map, under the zoom control. Tap it to follow your position: a green dot (with a translucent circle for the GPS accuracy) shows where you are, and a box at the bottom of the map (a strip across the bottom on phones) says how far you are from the route. On the route it reads "You are on the route, at km X of Y". More than 30 m off, it asks the public BRouter service for a road route back and draws it as a solid green line to the course, with the distance by road and the km where you rejoin. Until the route arrives, or if BRouter cannot be reached, it shows a dashed straight line and the compass direction instead. Two routes are tried, to the nearest course point and to the point 400 m further along, and the shorter one is used. More than 20 km away it only says how far, and does not route. The first route zooms the map to show you and the course; later fixes never move the map. "Next turn from here" moves the viewer to the point where the green line meets the route (or to the nearest point when there is no road route), so the turn strip shows your real next turn. Tap the button again, or the x in the strip, to stop.

- It needs HTTPS (or `localhost` / `file://`) and a GPS or network fix. Indoors or on a desktop the fix can be tens or hundreds of metres out; the box warns when accuracy is worse than 100 m.
- The route passes the same road on every lap. When more than one lap is about equally close, it picks the first one at or after where the viewer is now (with 50 m of slack), otherwise the earliest.
- Privacy: the position is sent to brouter.de (public BRouter service) only while Where am I is on and you are more than 30 m, and at most 20 km, off the route, to find the road back. After the first request it is sent again at most every 15 s, and only after you move more than 40 m. Nothing is stored (no localStorage), and nothing goes anywhere else. The More sheet / note under the Street View says so too.
- Test hook in the browser console: `window.__viewer.locate` has `nearest(lat, lon)` (returns `{ distM, alongM, lat, lon, bearing }` using the viewer's current distance for the lap choice), `setFix(lat, lon, accuracyM)` (turns Where am I on without asking the browser for location and handles the point as a real fix, including routing), `stop()`, `isOn()` and `getState()` (`{ on, distM, alongM, roadM, targetAlongM, routePoints, message, requests }`; `roadM` is null and `routePoints` 0 when no road route is shown). Test cases are in `docs/testcases/where-am-i.md`.

## Notes

- Turn directions are computed from the route geometry (bearing changes along the line), not from map instructions, so check them on a new course.
- Routing uses the public BRouter service (https://brouter.de). It needs internet when you run the tool and may be slow or rate limited. The site calls it only from Where am I (see above).
