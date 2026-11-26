# Test cases: course card elevation profile and stats

Page used: `index.html`, served over http or opened from disk. Courses: `citragarden-situ-cisawang` (31.6 km), `citragarden-3-laps-danau-abah` (18.5 km) and `aeris-3-laps-lake` (19.9 km). "Chart" is the `Elevation` block with the small area graph in each card. "Phone" means a window 375 px wide. The data comes from `window.COURSES` in `courses/index.js`.

| ID | Steps | Expected |
|---|---|---|
| CC-01 chart renders | Open `index.html` at 1280x800 and look at each of the three cards. | Each card shows an `Elevation` label and a blue area chart about 64 px tall between the stats and the chips. The line is the same blue as the route on the map thumbnail. |
| CC-02 labels match the stats | Read the two small elevation labels and the distance label under the chart, then the `Highest point` stat and the card distance. | The top label equals the `Highest point` value (Cisawang: 70 m). The bottom label is the lowest point (Cisawang: 22 m). The distance label equals the `Distance` stat (31.6 km). |
| CC-03 chart is not zero based | Look at the Danau Abah card (42 m to 57 m). | The chart fills the height of the box. The baseline is the lowest point, not 0 m. |
| CC-04 accessibility | Inspect the chart `svg`. | `role="img"` and an `aria-label` like `Elevation profile: 22 m to 70 m over 31.6 km`. The small text labels are hidden from screen readers. |
| CC-05 desktop stats grid | At 1280x800 count the stats on the Cisawang card. | Eight stats in two rows of four: Distance, Climb, Highest point, Steepest (100 m), then Unpaved, Main roads, Ride time at 15 km/h, Turns. No stat sits alone on a row. |
| CC-06 stat values | Compare the stats with the course entry in `courses/index.js`. | Highest point is `maxEleM` in m. Steepest is `maxGradePct` rounded to a whole percent. Main roads is `mainRoadM` over the distance as a whole percent (Cisawang about 14%, the other two 0%). |
| CC-07 phone layout | At 375x812 open the page and scroll through the cards. | Two stats per row, four rows, no orphan. The chart spans the card width with readable labels. `document.documentElement.scrollWidth <= window.innerWidth` (no sideways scroll). |
| CC-08 chart scales | Drag the window from 1280 px to 375 px wide. | The chart keeps its 64 px height and stays inside the card; the line stays 1.5 px thick and the labels are not stretched. |
| CC-09 entry without a profile | Make a copy of the site, delete the `profile` field from one entry in the copy of `courses/index.js`, and open the copy. | That card has no `Elevation` label and no chart, and the browser console shows no errors. Its stats and chips still show. |
| CC-10 older entry | In the same copy, remove `maxEleM`, `minEleM`, `maxGradePct` and `mainRoadM` from one entry. | The card shows only the stats that remain and no error appears in the console. |
| CC-11 site check | Run `node tools/check_site.mjs`. | Prints `SITE OK` and `ROUTE OK`. It checks `maxEleM`, `minEleM`, `maxGradePct`, `mainRoadM` and `profile` when an entry has them. |
