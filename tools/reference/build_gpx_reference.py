import json,math,collections,sys
def hav(a,b):
    R=6371000;p=math.radians
    dl=p(b[1]-a[1]);dn=p(b[0]-a[0])
    h=math.sin(dl/2)**2+math.cos(p(a[1]))*math.cos(p(b[1]))*math.sin(dn/2)**2
    return 2*R*math.asin(math.sqrt(h))
def load(f):
    d=json.load(open(f))['features'][0]
    pr=d['properties']; m=pr['messages']; h=m[0]
    st=collections.Counter()
    for r in m[1:]:
        row=dict(zip(h,r)); t=row['WayTags']
        tags=dict(x.split('=',1) for x in t.split())
        st[(tags.get('highway'),tags.get('surface','?'),tags.get('access','-'),tags.get('tracktype','-'))]+=int(row['Distance'])
    print(f,pr['track-length'],'m');
    for k,v in st.most_common(): print('  ',k,v)
    return d['geometry']['coordinates']
lap=load('lap.json'); lake=load('lake.json')
pts=lap+lap[1:]+lap[1:]+lake[1:]
dist=sum(hav(pts[i],pts[i+1]) for i in range(len(pts)-1))
print('gap lap end->start',hav(lap[0],lap[-1]),'lake start',hav(lap[-1],lake[0]),'lake end',hav(lake[-1],lap[0]))
print('max step',max(hav(pts[i],pts[i+1]) for i in range(len(pts)-1)))
print('total',round(dist),'m',len(pts),'pts')
out=sys.argv[1]
with open(out,'w') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="gravel-route-builder">\n <metadata><name>Aeris 3 Laps + Lake Gravel Loop</name></metadata>\n <trk>\n  <name>Aeris 3 Laps + Lake Gravel Loop</name>\n  <type>gravel_cycling</type>\n  <trkseg>\n')
    for p in pts:
        f.write(f'   <trkpt lat="{p[1]:.6f}" lon="{p[0]:.6f}"><ele>{p[2] if len(p)>2 else 0:.1f}</ele></trkpt>\n')
    f.write('  </trkseg>\n </trk>\n</gpx>\n')
# plot
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
osm=json.load(open('osm.json'))['elements']
fig,ax=plt.subplots(figsize=(11,13))
for e in osm:
    g=e['geometry']; ax.plot([q['lon'] for q in g],[q['lat'] for q in g],color='#ccc',lw=.6)
ax.plot([p[0] for p in lake],[p[1] for p in lake],color='red',lw=2.2,label='lake loop')
ax.plot([p[0] for p in lap],[p[1] for p in lap],color='blue',lw=1.4,label='lap x3')
for n,(lo,la) in {'Aeris':(106.6362204,-6.3291635),'Resort Club':(106.6283002,-6.3387649),'Chloe':(106.6340874,-6.3341),'Jabon':(106.6250627,-6.3410515),'RD2':(106.6221287,-6.3490381),'Lapangan':(106.622487,-6.3453937),'Pertamina':(106.6371917,-6.3418708)}.items():
    ax.plot(lo,la,'ko'); ax.annotate(n,(lo,la),fontsize=11)
ax.set_aspect(1); ax.legend(); fig.savefig('route.png',dpi=80,bbox_inches='tight')
