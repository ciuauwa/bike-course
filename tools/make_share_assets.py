# Generates favicon.ico, favicon.svg, apple-touch-icon.png, icon-192.png and og-image.png. Usage: python tools/make_share_assets.py <repo root> (needs Pillow, macOS Helvetica).
import json, math, sys
from PIL import Image, ImageDraw, ImageFont
root = sys.argv[1]
RED, BLUE, YEL, INK = (217,56,30), (30,111,217), (255,210,63), (29,35,41)
# loop-shaped route used by the icon, in a 64-unit box (same path as favicon.svg)
ICON = [(18,46),(18,26),(26,17),(38,17),(46,25),(46,36),(38,46),(28,46)]
def icon(size, ss=8):
    n = size*ss; k = n/64
    im = Image.new("RGBA", (n,n), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0,0,n-1,n-1], radius=int(14*k), fill=RED)
    pts = [(x*k,y*k) for x,y in ICON]
    d.line(pts, fill="white", width=int(7*k), joint="curve")
    for x,y in (pts[0],pts[-1]):
        d.ellipse([x-3.5*k,y-3.5*k,x+3.5*k,y+3.5*k], fill="white")
    x,y = pts[0]; r = 7*k
    d.ellipse([x-r,y-r,x+r,y+r], fill=YEL, outline=INK, width=int(2*k))
    return im.resize((size,size), Image.LANCZOS)
icon(256).save(root+"/favicon.ico", sizes=[(16,16),(32,32),(48,48)])
icon(180).save(root+"/apple-touch-icon.png")
icon(192).save(root+"/icon-192.png")
open(root+"/favicon.svg","w").write(
 '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#d9381e"/>'
 '<polyline points="'+" ".join(f"{x},{y}" for x,y in ICON)+'" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>'
 '<circle cx="18" cy="46" r="6" fill="#ffd23f" stroke="#1d2329" stroke-width="2"/></svg>\n')

# ---- share image 1200x630 ----
W,H,ss = 1200,630,2
im = Image.new("RGB",(W*ss,H*ss),(245,246,247)); d = ImageDraw.Draw(im)
def F(sz,bold=False):
    return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz*ss, index=1 if bold else 0)
# right panel with the real route shape
px0,py0,px1,py1 = 640*ss,50*ss,1150*ss,580*ss
d.rounded_rectangle([px0,py0,px1,py1], radius=28*ss, fill="white", outline=(213,217,221), width=2*ss)
s = open(root+"/courses/aeris-3-laps-lake/course-data.js").read()
C = json.loads(s[s.index("{"):s.rindex("}")+1])
segs = [sg["points"] for sg in C["segments"]]
allp = [p for sg in segs for p in sg]
la0,la1 = min(p[0] for p in allp), max(p[0] for p in allp); lo0,lo1 = min(p[1] for p in allp), max(p[1] for p in allp)
cosl = math.cos(math.radians((la0+la1)/2)); gw,gh = (lo1-lo0)*cosl, (la1-la0)
pad = 60*ss; sc = min((px1-px0-2*pad)/gw, (py1-py0-2*pad)/gh)
ox = (px0+px1)/2 - gw*sc/2; oy = (py0+py1)/2 - gh*sc/2
T = lambda p: (ox+(p[1]-lo0)*cosl*sc, oy+(la1-p[0])*sc)
for i,sg in reversed(list(enumerate(segs))):
    d.line([T(p) for p in sg], fill=BLUE if i==0 else RED, width=9*ss, joint="curve")
for n,st in enumerate(C["stops"],1):
    x,y = T((st[1],st[2])); r = 17*ss
    d.ellipse([x-r,y-r,x+r,y+r], fill=YEL, outline=INK, width=3*ss)
    d.text((x,y), str(n), font=F(20,True), fill=INK, anchor="mm")
# left text
ic = icon(96, ss=8).resize((96*ss,96*ss), Image.LANCZOS); im.paste(ic,(70*ss,70*ss),ic)
d.text((70*ss,200*ss), "Bike courses", font=F(84,True), fill=INK)
y = 312*ss
for line in ["Gravel routes around", "Cisauk and BSD.", "Preview every turn in", "Street View, then download", "the GPX for your Garmin."]:
    d.text((72*ss,y), line, font=F(34), fill=(91,102,112)); y += 42*ss
d.text((72*ss,578*ss), "bike.davidyosuanto.com", font=F(26,True), fill=RED, anchor="ls")
im.resize((W,H), Image.LANCZOS).save(root+"/og-image.png", optimize=True)
