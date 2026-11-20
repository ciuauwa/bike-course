// Acceptance check for the site. Usage: node tools/check_site.mjs
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const errors = [];
const lines = [];
const err = (m) => errors.push(m);

function runData(file, key) {
  const win = {};
  try {
    vm.runInNewContext(fs.readFileSync(file, 'utf8'), { window: win }, { filename: file });
  } catch (e) { err(`${file}: ${e.message}`); return null; }
  if (win[key] === undefined) { err(`${file}: does not define window.${key}`); return null; }
  return win[key];
}
function hav(a, b) {
  const r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(s)));
}
const isPair = (p) => Array.isArray(p) && p.length === 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);
const TYPES = new Set(['left', 'right', 'slight-left', 'slight-right', 'sharp-left', 'sharp-right', 'uturn',
  'roundabout', 'roundabout-left', 'roundabout-right', 'start', 'finish']);

const courses = runData(path.join(root, 'courses/index.js'), 'COURSES');
if (courses !== null && (!Array.isArray(courses) || !courses.length)) err('courses/index.js: COURSES is empty or not an array');

for (const entry of Array.isArray(courses) ? courses : []) {
  const slug = entry.slug, tag = `[${slug}]`;
  const dataFile = path.join(root, 'courses', slug, 'course-data.js');
  const gpxFile = path.join(root, entry.gpx || '');
  if (!fs.existsSync(dataFile)) { err(`${tag} missing ${dataFile}`); continue; }
  if (!entry.gpx || !fs.existsSync(gpxFile)) { err(`${tag} missing gpx ${entry.gpx}`); continue; }
  const C = runData(dataFile, 'COURSE');
  if (!C) continue;
  if (C.slug !== slug) err(`${tag} COURSE.slug is "${C.slug}"`);
  if (!Array.isArray(C.segments) || !C.segments.length) { err(`${tag} segments empty`); continue; }
  let bad = false;
  const full = [];
  for (const s of C.segments) {
    if (!Array.isArray(s.points) || !s.points.length || !s.points.every(isPair)) { err(`${tag} segment "${s.label}" has invalid points`); bad = true; continue; }
    for (let r = 0; r < (s.repeat || 1); r++) for (const p of (full.length ? s.points.slice(1) : s.points)) full.push(p);
  }
  if (bad) continue;
  let len = 0;
  for (let i = 1; i < full.length; i++) len += hav(full[i - 1], full[i]);
  if (!(Math.abs(C.totalM - len) <= len * 0.01)) err(`${tag} totalM ${C.totalM} is not within 1% of computed ${Math.round(len)}`);
  const turns = Array.isArray(C.turns) ? C.turns : [];
  if (!Array.isArray(C.turns)) err(`${tag} turns is not an array`);
  turns.forEach((t, i) => {
    if (i && t.d < turns[i - 1].d) err(`${tag} turns not sorted at index ${i}`);
    if (!(t.d >= 0 && t.d <= C.totalM)) err(`${tag} turn ${i} d=${t.d} outside 0..${C.totalM}`);
    if (typeof t.text !== 'string' || !t.text) err(`${tag} turn ${i} has no text`);
    if (!TYPES.has(t.type)) err(`${tag} turn ${i} has unknown type "${t.type}"`);
  });
  const trkpts = (fs.readFileSync(gpxFile, 'utf8').match(/<trkpt\b/g) || []).length;
  if (trkpts !== full.length) err(`${tag} GPX has ${trkpts} trkpt, expected ${full.length}`);
  if (entry.km !== Math.round(C.totalM / 100) / 10) err(`${tag} index km ${entry.km} != totalM/1000 (${(C.totalM / 1000).toFixed(1)})`);
  lines.push(`${slug}: ${C.totalM} m, ${full.length} points, ${turns.length} turns, ${entry.km} km`);
}

function checkHtml(name, required, forbidden) {
  const file = path.join(root, name);
  if (!fs.existsSync(file)) { err(`missing ${name}`); return; }
  const html = fs.readFileSync(file, 'utf8');
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, n = 0;
  while ((m = re.exec(html))) {
    if (/\bsrc\s*=/.test(m[1]) || !m[2].trim()) continue;
    n++;
    try { new vm.Script(m[2], { filename: `${name}#script${n}` }); } catch (e) { err(`${name} inline script ${n}: ${e.message}`); }
  }
  for (const s of required) if (!html.includes(s)) err(`${name} must contain "${s}"`);
  for (const s of forbidden) if (html.includes(s)) err(`${name} must not contain "${s}"`);
}
checkHtml('index.html', [], []);
checkHtml('viewer.html', ['turn-banner', 'tile.openstreetmap.org', 'server.arcgisonline.com', 'maps/embed?origin=mfe', 'URLSearchParams',
  'id="more"', 'id="morePanel"', 'id="legend"', '100dvh', 'safe-area-inset-bottom', 'viewport-fit=cover'],
  ['basemaps.cartocdn.com', 'src="course-data.js"']);

if (errors.length) {
  console.error('SITE CHECK FAILED');
  for (const e of errors) console.error(' - ' + e);
  process.exit(1);
}
console.log('SITE OK');
for (const l of lines) console.log(l);
