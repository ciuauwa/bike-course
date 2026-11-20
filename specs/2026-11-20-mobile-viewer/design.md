---
type: Design
title: Phone-friendly Street View viewer
description: Layout and control design for viewer.html and index.html on phones
spec: 2026-11-20-mobile-viewer
track: T
risk: R0
status: draft
lifecycle: draft
generated: { by: claude-fable-5-2, at: 2026-11-20T20:15:00+07:00 }
---

# Overview

On a phone the viewer spends the top third of the screen on controls, puts the turn banner over
Google's own on-image arrows, and leaves the map a thin strip. This change reorders the phone layout
around what the rider looks at (the street, then the map) and moves the controls to a thumb-reach
dock at the bottom. Desktop keeps its structure. CSS and markup only, plus a small "More" toggle.

# Architecture

## Components

Phone layout (viewport width <= 800 px), top to bottom:

| Region | Content | Size |
|---|---|---|
| Header | back arrow, course name on one line (ellipsis), status as one muted line: section, km x of y, turn n / N | about 52 px |
| Street View | the iframe only, nothing drawn on top | flex 5 |
| Turn strip | arrow, distance, instruction, "Then:" hint; dark, amber when NOW | about 52 px, hidden when no turn |
| Map | Leaflet map, legend bottom-left, zoom control top-right | flex 3 |
| Dock | slider (full width), then one row of five buttons: Prev turn, Previous, Play, Next, Next turn, plus More | about 110 px + safe area |
| More panel | Speed, section jumps, Open in Google Maps, Download GPX, the blank-view note | sheet above the dock, closed by default |

Desktop (> 800 px): unchanged structure. The same DOM is restyled; the More panel's content is laid
out inline in the bar and the More button is hidden. The only visible desktop change is the legend.

## Data Flow

No change. `render()` keeps writing the same elements; the turn banner keeps its `data-state`. The
More button only toggles a class on `#app`. `map.invalidateSize()` runs after layout changes.

# Technical Decisions

## Approach

One HTML file, one DOM, CSS media queries. `height:100dvh` with a `100%` fallback so the mobile
browser's address bar does not push the dock off screen. `viewport-fit=cover` plus
`env(safe-area-inset-bottom)` padding on the dock for phones with a home indicator.

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Controls in a bottom dock, Street View first | Thumb reach; the street gets the top of the screen; matches map and navigation apps | Dock takes about 110 px | Selected |
| Keep controls on top, just shrink them | Smallest diff | Still a reach to the top on a tall phone; buttons below 44 px | Rejected |
| Turn banner stays over the image, smaller | Reads as an annotation on the street | Covers Google's forward arrows and address box; Google's own controls cannot be moved | Rejected on phones, kept on desktop where there is room |
| Turn strip directly under the image | Never hides imagery; full width so text can be large | Not literally on the picture | Selected for phones |
| Tabs: Street View or map, one at a time | Each gets the full screen | Loses the point of the app, which is seeing both together | Rejected |
| Draggable split between Street View and map | Rider chooses | Touch-drag code next to an iframe and a map that both capture gestures; not worth it at this size | Rejected |
| Separate mobile page | Free hand in the design | Two files to keep in sync for every later change | Rejected |
| Speed and section jumps always visible | One tap less | Two more rows on screen all the time for controls used once per session | Rejected: behind More |

# Implementation

## Files to Create

None.

## Files to Modify

- `viewer.html`: markup regrouping (status into the header on phones, dock, More panel, legend), CSS, More toggle, `invalidateSize` after toggle and on `orientationchange`.
- `index.html`: 44 px tap targets, primary action full width under 480 px.
- `tools/check_site.mjs`: require the new markers in viewer.html (`id="more"`, `id="legend"`, `100dvh`, `safe-area-inset-bottom`).
- `README.md`: two lines on the phone layout.

## Database Changes / API Changes

None.

# Threat Model

Not required (R0: static layout change, no data, no new egress).

# Error Handling

Unchanged. The error box still replaces `#app`. If `100dvh` is unsupported the `100%` fallback applies.

# Testing Strategy

- INV1: `node tools/check_site.mjs` (syntax of inline scripts plus required markers).
- AC1 to AC9, INV2, INV3: measured in a real browser by the navigator with element rectangles at
  360 x 640, 390 x 844, 430 x 932 and 1280 x 800, on the local file and again on the deployed site.
  There is no browser test runner in this repo and adding one would break INV4, so these stay a
  scripted manual check; the measurements are recorded in `handoff.md`.

# Rollback

`git revert <commit>` and push; Vercel redeploys in under a minute. One commit, no data or config
side effect. Detection: the owner opens the site on their phone.

# Observability

None needed beyond the above. Outcome metric: on a 390 x 844 screen, the share of height given to
Street View plus map. Baseline from the screenshot of 2026-11-20: about 56% (Street View 33%, map
23%), with 36% spent on controls above the fold. Target: at least 70%.

# Pinned Versions

Leaflet 1.9.4 from unpkg (unchanged).
