---
type: Requirement
title: Phone-friendly Street View viewer
description: Acceptance criteria for the mobile layout of viewer.html and index.html
spec: 2026-11-20-mobile-viewer
track: T
risk: R0
status: draft
lifecycle: draft
generated: { by: claude-fable-5-2, at: 2026-11-20T20:15:00+07:00 }
---

# Source

Written during `/ds-design` because no requirement existed. Derived from the owner's request
("improve the UIUX so its also mobile phone friendly") and their phone screenshot of 2026-11-20,
where five rows of controls sat above the Street View and the map was a thin strip at the bottom.

# Acceptance criteria

Phone means a viewport 360 to 430 px wide, portrait. Reference size: 390 x 844.

- AC1. No horizontal scroll at 360, 390 and 430 px wide (`documentElement.scrollWidth <= innerWidth`).
- AC2. The viewer fits the screen: the page does not scroll vertically at 390 x 844 and 360 x 640.
- AC3. At 390 x 844 the Street View is at least 38% of the viewport height and the map at least 22%.
- AC4. Previous, Play, Next, Prev turn and Next turn are each at least 44 x 44 px and sit in the bottom 35% of the screen.
- AC5. On a phone the turn instruction never covers the Street View image: it is a strip directly below it. It still shows distance, instruction and the "Then:" hint, and turns amber for NOW.
- AC6. Speed, section jumps, "Open this spot in Google Maps", "Download GPX" and the blank-view note are behind one "More" button, closed by default on a phone; it opens and closes.
- AC7. A legend on the map says blue is ridden and red is ahead (all sizes).
- AC8. At 1280 x 800 the desktop layout is unchanged in structure: panes side by side, banner over the Street View, every control visible without "More".
- AC9. index.html: the primary action is at least 44 px tall and nothing scrolls sideways at 360 px.

# Invariants

- INV1. `node tools/check_site.mjs` prints `SITE OK`.
- INV2. `window.__viewer` keeps `course, points, getIndex, setIndex, turns, nextTurn`.
- INV3. Keyboard keys (Left, Right, Up, Down, Space) keep working.
- INV4. No build step, no new dependency, no API key.
