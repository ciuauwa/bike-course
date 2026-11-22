# Test cases: tappable turn banner and Course outline

Course used: `viewer.html?course=aeris-3-laps-lake` (19.9 km, Lap 1 of 3, Lap 2 of 3, Lap 3 of 3, then Lake loop). "Phone" means a window of 800 px wide or less, or 480 px high or less in landscape. "Banner" is `#turn-banner`, "toggle" is the header status button `#outlineToggle`, "sheet" is `#outline`. In the console, `__viewer.outline` has `open()`, `close()`, `isOpen()` and `rows()`; `__viewer.getIndex()` and `__viewer.points[i]._d` give the position in metres.

| ID | Steps | Expected |
|---|---|---|
| TB-01 tap jumps to the turn | At index 0 click the banner. Note the turn text it showed ("Go to next turn: ..." is its `aria-label`). | The index moves to the last view point at or before that turn's distance minus 20 m (`points[i]._d <= d - 20`, the next point is later). The banner now shows that same turn, "In 20 m" to "In 60 m". |
| TB-02 never backwards | Go to a point 5 m before a turn (the banner says NOW) and click the banner. | The index does not decrease. It moves forward to the first view point at or after the turn, or one view point on when that is the current one. |
| TB-03 last turn | Go to the last view point, so the banner is hidden (`data-state="none"`). | The banner is not shown and cannot be tapped. Pressing Enter does nothing. |
| TB-04 keyboard | Tab to the banner (a visible blue outline appears). Press Enter, then Space. | Each press jumps as in TB-01. Space does not start or stop playback. |
| TB-05 accessibility | Inspect the banner. | `role="button"`, `tabindex="0"`, `aria-label="Go to next turn: <text>"` with the turn text, pointer cursor. |
| TB-06 desktop pointer | At 1280x800 hover and click the banner. | Pointer cursor, click jumps (TB-01). Look and position are unchanged: centred at the top of the Street View, same size. |
| TB-07 phone chevron | At 390x844 look at the strip under the Street View. | A "›" sits at the right end of the strip. The strip height and the pane sizes are unchanged. |
| TB-08 playback | Press Play, then click the banner. | The index jumps, the button still says "Pause", and the position keeps advancing every step after the jump. |
| OL-01 open | Click the status line in the header. | The sheet opens (`__viewer.outline.isOpen()` is `true`), the toggle has `aria-expanded="true"`, focus is on the close button. The title row says "Course outline". |
| OL-02 content | Count rows and read the sheet. | Four sticky section headers in ride order (Lap 1 of 3, Lap 2 of 3, Lap 3 of 3, Lake loop), each with "km X.XX" (its start). Under each, one row per turn with the turn arrow, text and "km X.XX". `__viewer.outline.rows()` equals `__viewer.turns.length`. No stops are listed. |
| OL-03 current turn | Open the sheet at index 0, then close, jump to km 7 and open again. | The row of the current next turn (the one the banner shows) has `aria-current="true"`, a pale amber background, and is scrolled to the middle of the list each time it opens. |
| OL-04 stays updated | With the sheet open, press Next (or let Play run) past a turn. | `aria-current` and the highlight move to the next turn's row. |
| OL-05 turn row | Tap a turn row. | The index becomes the last view point at or before that turn's distance minus 20 m (0 at most), even when that is behind the current index. The sheet closes and focus returns to the toggle. |
| OL-06 section header | Tap "Lap 2 of 3". | The viewer moves to the first view point of lap 2 (the status says Lap 2 of 3), the sheet closes. |
| OL-07 close | Open the sheet and close it with: the x button; Escape; the toggle again. | Each closes it, sets `aria-expanded="false"` and returns focus to the toggle. |
| OL-08 More sheet | On a phone open More, then open the outline. Then open More again. | Opening the outline closes More, and opening More closes the outline. Both are never open together. |
| OL-09 arrow keys | With the sheet open press the Up, Down, Left and Right arrows and Space. | The viewer index does not change and playback does not toggle. |
| OL-10 phone layout | At 360x640, 390x844 and 844x390 open the sheet. | It covers the Street View and map between the header and the dock; the dock stays visible and usable. Close button is 44x44. The toggle is at least 44 px tall and the header is at most 4 px taller than before (52 px portrait, 48 px landscape). |
| OL-11 desktop layout | At 1280x800 open the sheet. | A 380 px wide panel on the left under the status row, at most 70% of the window height, list scrolls, section headers stick to the top while scrolling. |
| OL-12 no side scroll | At 360x640, 390x844, 844x390 and 1280x800, with the sheet open and closed. | `document.documentElement.scrollWidth <= window.innerWidth`. |
| OL-13 unchanged | Run `__viewer.lineCheck()`. Open Where am I, the Stops list and the More sheet. | `maxDevM` is below 1. The other controls behave as before. |
| OL-14 site check | Run `node tools/check_site.mjs`. | Prints `SITE OK`; viewer.html contains `id="outlineToggle"`, `id="outline"`, `id="outlineList"` and `id="outlineClose"`. |
