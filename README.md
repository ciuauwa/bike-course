# Bike courses

A plain static site (no framework, no build step) for riding bike courses virtually in Google Street View. `index.html` lists the courses, `viewer.html?course=<slug>` plays one, and each course has a downloadable GPX. It works when hosted (Vercel) and when opened from disk (file://).

On a phone the viewer fits the screen without scrolling: Street View on top, the turn instruction as a strip directly under the image (never over it), the map below, and the controls in a dock at the bottom within thumb reach. Speed, section jumps, the Google Maps link, the GPX link and the blank-view note sit behind the "More" button, which opens a sheet above the dock. On a desktop-width window the controls stay in the top bar and the turn banner sits over the Street View.

## Layout

```
index.html                     course list
viewer.html                    viewer, chosen with ?course=<slug> (defaults to the first course)
courses/index.js               generated list of courses (window.COURSES)
courses/<slug>/course.json     the course definition (you write this)
courses/<slug>/course-data.js  generated route + turns (window.COURSE)
courses/<slug>/<gpx>           generated GPX file
tools/make_course.py           builds a course from course.json
tools/check_site.mjs           acceptance check: node tools/check_site.mjs
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
| `stops` | no | Labelled points on the map: `[label, lat, lon]` |
| `roundabouts` | no | `[lat, lon]` of roundabouts, so turns there are described as roundabout moves |

## Notes

- Turn directions are computed from the route geometry (bearing changes along the line), not from map instructions, so check them on a new course.
- Routing uses the public BRouter service (https://brouter.de). It needs internet when you run the tool and may be slow or rate limited; the site itself does not call it.
