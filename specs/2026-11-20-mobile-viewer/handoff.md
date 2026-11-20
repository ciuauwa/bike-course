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
