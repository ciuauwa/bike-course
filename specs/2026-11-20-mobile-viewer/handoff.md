---
type: Handoff Ledger
spec: 2026-11-20-mobile-viewer
---

--- handoff ---
from: ds-design
at: 2026-11-20T20:15:00+07:00
artifact: design.md
status: draft
lifecycle: draft
risk: R0
provides: [acceptance_criteria, design, rollback]
decisions:
  - acceptance_criteria written here in requirement.md because none existed; derived from the owner's request and screenshot, not from /ds-requirements
  - Bottom control dock over shrinking the top bar, because of thumb reach and screen share
  - Turn strip under the image on phones over an overlay, because the overlay hid Google's own arrows
  - Rollback: git revert of one commit, Vercel redeploys
open_questions: []
next: [ds-tweak]
blocked_on: []
--- end handoff ---

--- handoff ---
from: ds-tweak
at: 2026-11-20T20:45:00+07:00
artifact: viewer.html, index.html
status: stable
lifecycle: shipped
risk: R0
provides: [build, verification]
decisions:
  - Builder: Claude Sonnet subagent. Navigator edit: legend moved from bottom-left to top-left of the map, because it overlapped the Leaflet attribution at 360 px.
  - Phone breakpoint also covers landscape phones wider than 800 px (max-height 480 px, landscape).
  - Measured in a browser on localhost at 360x640, 390x844, 430x932, 844x390, 1280x800: no page scroll in either direction; at 390x844 Street View 377 px (45%), map 259 px (31%), dock buttons 48 px tall at y=788; turn strip starts where the image ends; More opens and closes; next / next turn / prev turn / Left key change the index; __viewer keys unchanged.
  - Outcome metric: Street View plus map share of a 390x844 screen went from about 56% to 75%.
  - Review: no other-vendor review run (R0).
open_questions: []
next: []
blocked_on: []
--- end handoff ---
