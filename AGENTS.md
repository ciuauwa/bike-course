# Bike courses: rules for agents

Read `README.md` for the layout, the `course.json` fields and the route checks.

## Push when the work is done

When a piece of work is finished, commit it and push to `main` without asking first. The owner reviews on the live site, not locally.

1. Run `node tools/check_site.mjs`. It must print `SITE OK` and `ROUTE OK`. Do not push if it fails.
2. Commit and push to `main`.
3. Confirm the live site shows the change by fetching the changed file from `https://bike.davidyosuanto.com` (for a course: `courses/index.js` or `courses/<slug>/course-data.js`). Report the result.

Notes on step 3:

- Vercel deploys from pushes to `main` but posts no deployment record to GitHub, so `ci-wait` exits 2 ("nothing started") here. That exit is not a failure in this repo. Check the live file instead.
- A deploy normally lands within a minute. If the live site still serves the old file after 5 minutes, Vercel skipped the push (this happened on 2026-11-25). Push an empty commit to trigger it again and say so.

This rule does not cover force pushes, history rewrites or deleting a course. Ask before those.
