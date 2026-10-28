"""Design: contact sheets of the C63 LA-day swaps (LA night texture | donor day texture). Reads the discs via inputs.py."""
import sys, os, json, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chicago"))
import numpy as np
from PIL import Image, ImageDraw
import inputs, polish_laday as L
from levfile import Lev

def to_img(t):
    name,pg,k,x,y,w,h,clut,idx=t
    pal=np.array([L._rgb(c)+(0 if c==0 else 255,) for c in clut],np.uint8)
    return Image.fromarray(pal[idx],"RGBA")
def fit(im,s=80):
    bg=Image.new("RGB",(s,s),(255,0,255)); r=min(s/im.width,s/im.height); im=im.resize((max(1,int(im.width*r)),max(1,int(im.height*r))),Image.NEAREST)
    bg.paste(im,(0,0),im); return bg
def main():
    T=json.load(open(os.path.join(inputs.WORK,"polish_la_day_table.json")))["swaps"]
    la=Lev.parse(open(inputs.path("d1_LA.lev"),"rb").read()); _,lat=L.textures(la)
    lamap={(t[1],t[2]):t for t in lat}
    dmap={}
    for dn in L.DONORS:
        dl=Lev.parse(open(inputs.path(dn),"rb").read()); _,tx=L.textures(dl)
        for t in tx: dmap[(dn,t[1],t[2])]=t
    per=36
    for si in range(0,len(T),per):
        ch=T[si:si+per]; cols=3; rows=(len(ch)+cols-1)//cols
        sh=Image.new("RGB",(cols*190,rows*104),(30,30,30)); d=ImageDraw.Draw(sh)
        for i,s in enumerate(ch):
            a=lamap[(s["page"],s["k"])]; b=dmap[(s["donor"],s["donor_page"],s["donor_k"])]
            ox,oy=(i%cols)*190,(i//cols)*104
            sh.paste(fit(to_img(a)),(ox,oy)); sh.paste(fit(to_img(b)),(ox+85,oy))
            d.text((ox,oy+82),"%d %s"%(si+i,a[0][:14]),fill=(255,255,0)); d.text((ox,oy+92),"> %s %s"%(s["donor"][3:5],b[0][:12]),fill=(160,255,160))
        sh.save(os.path.join(os.path.dirname(os.path.abspath(__file__)),"out","laday","swaps_%d.png"%(si//per)))
main()
