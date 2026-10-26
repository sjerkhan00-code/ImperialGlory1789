import numpy as np, json, sys
from PIL import Image, ImageDraw
sys.path.insert(0, '.')
f=np.load('../build/sea/zone_labels.npy'); keys=json.load(open('../build/sea/zone_keys.json'))
g=np.load('../build/sea/grid.npz'); land=g['land']; lon=g['lon']; lat=g['lat']
lo0,lo1,la0,la1,name=float(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),sys.argv[5]
m=(lon>=lo0)&(lon<=lo1)&(lat>=la0)&(lat<=la1)
ys,xs=np.nonzero(m); r0,r1,c0,c1=ys.min(),ys.max()+1,xs.min(),xs.max()+1
sub=f[r0:r1,c0:c1]; L=land[r0:r1,c0:c1]
rng=np.random.default_rng(3); pal=rng.integers(60,255,(len(keys),3))
img=np.zeros(sub.shape+(3,),np.uint8); img[:]=(40,40,40); img[L]=(220,210,180); mm=sub>=0; img[mm]=pal[sub[mm]]
S=4
im=Image.fromarray(img).resize((img.shape[1]*S,img.shape[0]*S),Image.NEAREST); dr=ImageDraw.Draw(im)
for k in np.unique(sub[mm]):
    yy,xx=np.nonzero(sub==k); dr.text((xx.mean()*S,yy.mean()*S),keys[k],fill=(0,0,0))
im.save('../build/sea/dbg_%s.png'%name); print(im.size)
