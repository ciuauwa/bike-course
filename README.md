# Bike courses

A plain static site (no framework, no build step) for riding bike courses virtually in Google Street View. `index.html` lists the courses, `viewer.html?course=<slug>` plays one, and each course has a downloadable GPX. It works when hosted (Vercel) and when opened from disk (file://).

On a phone the viewer fits the screen without scrolling: Street View on top, the turn instruction as a strip directly under the image (never over it), the map below, and the controls in a dock at the bottom within thumb reach. Speed, section jumps, the Google Maps link, the GPX link and the blank-view note sit behind the "More" button, which opens a sheet above the dock. On a desktop-width window the controls stay in the top bar and the turn banner sits over the Street View.

The course list shows each course as a card with a small map of the route (stops as numbered dots), distance, climb, ride time at 15 km/h, turn count, the surface and difficulty chips, the route sections and the stops. All of it comes from `courses/index.js` (`window.COURSES`), which `tools/make_course.py` regenerates from every course folder. Each entry has `slug`, `name`, `description`, `km`, `gpx`, `ascentM` (total climb in metres, from BRouter's "filtered ascend"), `turns`, `stops`, `sections` (`{label, repeat, km}`, with km for one repetition), `preview` (the outline as simplified `[lat, lon]` points, at most 250) and the optional `surface` and `difficulty`.

## Layout

```
index.html                     course list
viewer.html                    viewer, chosen with ?course=<slug> (defaults to the first course)
courses/index.js               generated list of courses (window.COURSES)
courses/<slug>/course.json     the course definition (you write this)
courses/<slug>/course-data.js  generated route + turns (window.COURSE)
courses/<slug>/<gpx>           generated GPX file
tools/make_course.py           builds a course from course.json
tools/check_route.py           offline route checker (spurs, tiny loops, stray U-turns)
tools/check_site.mjs           acceptance check: node tools/check_site.mjs (also runs check_route.py)
```

## Add a course

1. Create `courses/<slug>/course.json` (slug uses only `a-z`, `0-9`, `-`, and matches the folder name).
2. Run `python3 tools/make_course.py courses/<slug>/course.json`.
3. Open `index.html` and check the course.
4. Run `node tools/check_site.mjs`, then commit and push.

## course.json fields

| Field | Required | Meaning |
|---|---|---|
| `slug` | yes | Folder name and URL id |
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

## Route checks

`python3 tools/check_route.py` reads each course's `course-data.js` (no network) and fails with `ROUTE CHECK FAILED` (exit 1) on routing accidents. It prints one line per finding with the km position, `lat,lon` and a Google Maps link, and ends with `ROUTE OK` when there are no errors. Pass `courses/<slug>/course.json` to check one course.

| Rule | Level | Catches |
|---|---|---|
| `spur` | error | The route rides out and back along the same way (a dead-end detour of 10 m or more), found from the geometry, not from the turn list. Laps and the opposite carriageway are not spurs, only a reversal at a tip is |
| `loop` | error | A tiny closed loop: the route returns within 8 m of a point it passed 30 to 250 m earlier |
| `uturn-turn` | error | A U-turn instruction in `turns` that is not at an allowed spur or a roundabout |
| `waypoint-off-route` | warn | A waypoint more than 15 m from the routed line (the router snapped it to another way) |
| `outAndBack` | warn | A declared turn-around that matches no spur (stale) |

A spur is allowed (printed as `ALLOWED`) when its tip is within 45 m of a `roundabouts` point or within 40 m of a point in the optional `outAndBack` list in `course.json`. Declare the point where you really turn around, for example `"outAndBack": [[-6.3363876, 106.6247291]]`. If a spur is unintended, move the waypoint onto the road instead.

- `python3 tools/make_course.py courses/<slug>/course.json` runs the same check on the fresh route before it writes anything. On errors it prints them and exits 1 without writing. Add `--force` as a second argument to write anyway (the findings are still printed).
- `python3 tools/check_route.py --selftest` runs synthetic cases (side spur, declared spur, repeated laps, out and back, tiny loop, far waypoint) and prints `SELFTEST OK`.
- `node tools/check_site.mjs` also runs the route check and fails if it does.
- In the browser, `window.__viewer.lineCheck()` returns `{ maxDevM, worstIndex }`: for every view point it measures how far the blue ridden line (its vertices and segment midpoints) is from the true route polyline. It should be below 1 m. It only reads; it does not move the map or the current position.

## Where am I

The viewer has a **Where am I** button (a crosshair icon) on the map, under the zoom control. Tap it to follow your position: a green dot (with a translucent circle for the GPS accuracy) shows where you are, and a box at the bottom of the map (a strip across the bottom on phones) says how far you are from the route. On the route it reads "You are on the route, at km X of Y". More than 30 m off, it asks the public BRouter service for a road route back and draws it as a solid green line to the course, with the distance by road and the km where you rejoin. Until the route arrives, or if BRouter cannot be reached, it shows a dashed straight line and the compass direction instead. Two routes are tried, to the nearest course point and to the point 400 m further along, and the shorter one is used. More than 20 km away it only says how far, and does not route. The first route zooms the map to show you and the course; later fixes never move the map. "Next turn from here" moves the viewer to the point where the green line meets the route (or to the nearest point when there is no road route), so the turn strip shows your real next turn. Tap the button again, or the x in the strip, to stop.

- It needs HTTPS (or `localhost` / `file://`) and a GPS or network fix. Indoors or on a desktop the fix can be tens or hundreds of metres out; the box warns when accuracy is worse than 100 m.
- The route passes the same road on every lap. When more than one lap is about equally close, it picks the first one at or after where the viewer is now (with 50 m of slack), otherwise the earliest.
- Privacy: the position is sent to brouter.de (public BRouter service) only while Where am I is on and you are more than 30 m, and at most 20 km, off the route, to find the road back. After the first request it is sent again at most every 15 s, and only after you move more than 40 m. Nothing is stored (no localStorage), and nothing goes anywhere else. The More sheet / note under the Street View says so too.
- Test hook in the browser console: `window.__viewer.locate` has `nearest(lat, lon)` (returns `{ distM, alongM, lat, lon, bearing }` using the viewer's current distance for the lap choice), `setFix(lat, lon, accuracyM)` (turns Where am I on without asking the browser for location and handles the point as a real fix, including routing), `stop()`, `isOn()` and `getState()` (`{ on, distM, alongM, roadM, targetAlongM, routePoints, message, requests }`; `roadM` is null and `routePoints` 0 when no road route is shown). Test cases are in `docs/testcases/where-am-i.md`.

## Notes

- Turn directions are computed from the route geometry (bearing changes along the line), not from map instructions, so check them on a new course.
- Routing uses the public BRouter service (https://brouter.de). It needs internet when you run the tool and may be slow or rate limited. The site calls it only from Where am I (see above).
