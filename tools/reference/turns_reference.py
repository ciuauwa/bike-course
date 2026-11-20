import json,math,re
src=open('/Users/david/Documents/app/gravel/course-data.js').read()
C=json.loads(src[src.index('{'):src.rindex('}')+1])
C.pop('turns',None)
def hav(a,b):
    p=math.radians;h=math.sin(p(b[0]-a[0])/2)**2+math.cos(p(a[0]))*math.cos(p(b[0]))*math.sin(p(b[1]-a[1])/2)**2
    return 2*6371000*math.asin(math.sqrt(h))
def brg(a,b): return math.degrees(math.atan2((b[1]-a[1])*math.cos(math.radians(a[0])),b[0]-a[0]))%360
def sd(a,b): return (b-a+180)%360-180
pts=list(C['lap'])
for _ in range(C['lapCount']-1): pts+=C['lap'][1:]
pts+=C['lake'][1:]
cum=[0]
for i in range(1,len(pts)): cum.append(cum[-1]+hav(pts[i-1],pts[i]))
total=cum[-1]
def at(d):
    d=max(0,min(total,d))
    import bisect
    i=min(max(bisect.bisect_right(cum,d)-1,0),len(pts)-2)
    t=0 if cum[i+1]==cum[i] else (d-cum[i])/(cum[i+1]-cum[i])
    return [pts[i][0]+(pts[i+1][0]-pts[i][0])*t, pts[i][1]+(pts[i+1][1]-pts[i][1])*t]
STEP=5;B=20
n=int(total//STEP)
delta=[]
for k in range(n+1):
    d=k*STEP
    if d<B or d>total-B: delta.append(0);continue
    delta.append(sd(brg(at(d-B),at(d)),brg(at(d),at(d+B))))
RB=[(-6.32954,106.63673),(-6.33927,106.63126),(-6.34072,106.62991),(-6.34456,106.62936),(-6.3499,106.62811)]
turns=[];k=0
while k<=n:
    if abs(delta[k])>=40:
        s=k
        while k<=n and (abs(delta[k])>=40 or (k+1<=n and abs(delta[k+1])>=40) or (k+2<=n and abs(delta[k+2])>=40)): k+=1
        e=k-1
        ds,de=s*STEP,e*STEP
        net=sd(brg(at(ds-B-5),at(ds-5)) if ds-B-5>=0 else brg(at(0),at(5)), brg(at(de+5),at(min(total,de+B+5))))
        # accumulate signed rotation to tell 180 left from right and full circles
        rot=sum(sd(brg(at(j*STEP-STEP),at(j*STEP)),brg(at(j*STEP),at(j*STEP+STEP))) for j in range(max(1,s-4),min(n-1,e+5)))
        peak=max(range(s,e+1),key=lambda j:abs(delta[j]))
        mid=at((ds+de)/2)
        rb=any(hav(mid,r)<45 for r in RB)
        a=abs(rot)
        side='left' if rot<0 else 'right'
        if rb:
            if a<35: typ,text='roundabout','At the roundabout, go straight on'
            elif a>300: typ,text='roundabout','Go all the way around the roundabout'
            elif a>150: typ,text='uturn','Go around the roundabout and head back'
            else: typ,text='roundabout-'+side,'At the roundabout, turn '+side
        elif a>150:
            c=(ds+de)/2
            if a>300 or hav(at(c-40),at(c+40))<15: typ,text='uturn','U-turn (dead end, ride back the same way)'
            else: typ,text='sharp-'+side,'Hairpin '+side+' turn'
        elif a<30: k+=0; continue
        elif a<60: typ,text='slight-'+side,'Bear '+side
        elif a>120: typ,text='sharp-'+side,'Sharp '+side+' turn'
        else: typ,text=side,'Turn '+side
        dd=ds if (de-ds)>30 else peak*STEP
        if dd<60: typ,text='start','Start: follow the roundabout onto the boulevard'
        if dd>total-60: typ,text='finish','Finish on the roundabout'
        p=at(dd)
        turns.append({'d':round(dd),'lat':round(p[0],6),'lon':round(p[1],6),'type':typ,'text':text,'rot':round(rot)})
    else: k+=1
C['turns']=turns
open('/Users/david/Documents/app/gravel/course-data.js','w').write('// Generated from aeris-3-laps-lake-gravel.gpx. Points are [lat, lon]. turns[].d is metres from the start along the full course.\nwindow.COURSE = '+json.dumps(C,separators=(',',':'))+';\n')
print(round(total),len(turns))
for t in turns: print(t['d'],t['type'],t['rot'],t['text'],t['lat'],t['lon'])
