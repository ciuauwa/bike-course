# Changelog

- 2026-11-22: In the Street View viewer, tapping the turn banner now goes to the turn it shows, and the header status line (section, km, turn counter) opens a Course outline sheet listing every turn by lap, where tapping a row jumps to that turn.
- 2026-11-22: Where am I now draws a road route back to the course (from the public BRouter service, straight dashed line as fallback), is an icon button, and shows as a compact strip with a close button on phones. Your position is sent to brouter.de only while you are off the route.
- 2026-11-22: Street View viewer has a Where am I button on the map: it shows your position, how far you are from the route and which way to head to rejoin it, and can jump the viewer to your next turn. The position stays in the browser.
- 2026-11-22: Route checker (tools/check_route.py) catches unintended spurs, tiny loops and stray U-turns, and make_course.py refuses to write a course that fails it. Fixed the stray 44 m dead-end detour at the Lapangan stop (course is now 19.9 km), and the blue ridden line on the map now follows the road instead of cutting corners.
- 2026-11-20: Course list cards show a route map thumbnail, distance, climb, ride time, turns, surface, difficulty, route breakdown and stops.
- 2026-11-20: Favicon and link-preview (WhatsApp) title, description and image. Regenerate the images with tools/make_share_assets.py (needs Pillow).
- 2026-11-20: On phones the map is now the larger pane and the Street View the smaller one.
- 2026-11-20: Stops on the map are numbered, and a Stops list in the map legend names each one.
- 2026-11-20: Phone layout for the Street View viewer: controls in a bottom dock, turn instruction as a strip under the image, extras behind a More button, and a ridden / ahead legend on the map.
- 2026-11-20: Added Warung Bu Endi Jabon as a rest stop on the Aeris lake loop (course is now 19.9 km).
