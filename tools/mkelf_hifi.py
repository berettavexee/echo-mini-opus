# mkelf2.py IMG OUT idx,... [names.txt]  -> ELF with section headers + symtab seeded by BL targets/vectors
import struct,sys,re
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0)
ents=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
segs=[]
for i in map(int,sys.argv[3].split(',')):
    cl,ce,cs,dl,de,ds,be,bs=ents[i]
    if cs: segs.append((".text%d"%i,(0 if 0x01000000<=ce<0x01020000 else ce),c[cl-B:cl-B+cs],5,0))
    if ds: segs.append(('.data%d'%i,de,c[dl-B:dl-B+ds],6,0))
    if bs: segs.append(('.bss%d'%i,be,b'',6,bs))
code=[(va,data) for nm,va,data,fl,x in segs if fl==5]
def inrange(a): return any(va<=a<va+len(dt) for va,dt in code)
funcs={}
for va,dt in code:
    # vector tables
    for o in range(0,len(dt)-8,4):
        pass
    for o in range(0,len(dt)-4,2):
        h1,h2=struct.unpack_from('<HH',dt,o)
        if (h1&0xf800)==0xf000 and (h2&0xd000)==0xd000:
            S=(h1>>10)&1; imm10=h1&0x3ff; J1=(h2>>13)&1; J2=(h2>>11)&1; imm11=h2&0x7ff
            I1=1-(J1^S); I2=1-(J2^S)
            off=(S<<24)|(I1<<23)|(I2<<22)|(imm10<<12)|(imm11<<1)
            if S: off-=1<<25
            t=va+o+4+off
            if inrange(t) and t%2==0:
                funcs[t]=funcs.get(t,0)+1
    # push {.., lr} prologues
    for o in range(0,len(dt)-4,2):
        h=struct.unpack_from('<H',dt,o)[0]
        if (h&0xff00)==0xb500: funcs.setdefault(va+o,0)
        h2=struct.unpack_from('<H',dt,o+2)[0]
        if h==0xe92d and (h2&0x4000): funcs.setdefault(va+o,0)
# vector table at start of first code seg
va0,dt0=code[0]
for nm,va,dt,fl,x in segs:
  if len(dt)>=256 and struct.unpack_from('<I',dt,0)[0]&0xff000000==0x03000000:
    for k in range(1,64):
        v=struct.unpack_from('<I',dt,4*k)[0]
        if v&1 and inrange(v&~1): funcs[v&~1]=funcs.get(v&~1,0)+1
    # also words in data that are thumb pointers into code (function pointer tables)
  if fl==6:
    for k in range(0,len(dt)-3,4):
        v=struct.unpack_from('<I',dt,k)[0]
        if v&1 and inrange(v&~1): funcs[v&~1]=funcs.get(v&~1,0)+1
names={}
if len(sys.argv)>4:
    for l in open(sys.argv[4]):
        if l.strip() and not l.startswith('#'):
            a,nm=l.split()[:2]; names[int(a,16)]=nm
for a in names: funcs.setdefault(a,0)
# keep BL-targets (count>=1) plus prologues
syms=sorted(funcs)
# build ELF
shstr=b'\0'
shnames={}
for nm in ['.shstrtab','.symtab','.strtab']+[s[0] for s in segs]:
    shnames[nm]=len(shstr); shstr+=nm.encode()+b'\0'
strtab=b'\0'; symtab=b'\0'*16
def secidx(a):
    for k,(nm,va,dt,fl,x) in enumerate(segs):
        if va<=a<va+len(dt)+x: return k+1
    return 0
for a in syms:
    nm=names.get(a,'sub_%08x'%a)
    o=len(strtab); strtab+=nm.encode()+b'\0'
    symtab+=struct.pack('<IIIBBH',o,a|1,0,0x12,0,secidx(a))
phn=len(segs); off=52+32*phn; body=b''; phdrs=b''; secoffs=[]
for nm,va,data,fl,extra in segs:
    while (off+len(body))%4: body+=b'\0'
    o=off+len(body); secoffs.append(o)
    phdrs+=struct.pack('<8I',1,o,va,va,len(data),len(data)+extra,fl,4); body+=data
blobs={}
for nm,b in [('.symtab',symtab),('.strtab',strtab),('.shstrtab',shstr)]:
    while (off+len(body))%4: body+=b'\0'
    blobs[nm]=(off+len(body),len(b)); body+=b
while (off+len(body))%4: body+=b'\0'
shoff=off+len(body)
nsh=1+len(segs)+3
strndx=len(segs)+2; symndx=len(segs)+1
sh=b'\0'*40
for k,(nm,va,data,fl,extra) in enumerate(segs):
    if fl==5: typ,flags=1,6
    elif nm.startswith('.bss'): typ,flags=8,3
    else: typ,flags=1,3
    sh+=struct.pack('<10I',shnames[nm],typ,flags,va,secoffs[k],len(data)+extra if typ==8 else len(data),0,0,4,0)
o,l=blobs['.symtab']; sh+=struct.pack('<10I',shnames['.symtab'],2,0,0,o,l,strndx+1-1+0 if False else len(segs)+2,1,4,16)
o,l=blobs['.strtab']; sh+=struct.pack('<10I',shnames['.strtab'],3,0,0,o,l,0,0,1,0)
o,l=blobs['.shstrtab']; sh+=struct.pack('<10I',shnames['.shstrtab'],3,0,0,o,l,0,0,1,0)
entry=struct.unpack_from('<I',dt0,4)[0]
eh=b'\x7fELF\x01\x01\x01'+b'\0'*9+struct.pack('<HHIIIIIHHHHHH',2,40,1,entry,52,shoff,0x05000200,52,32,phn,40,nsh,len(segs)+3)
open(sys.argv[2],'wb').write(eh+phdrs+body+sh)
print(sys.argv[2],'symbols',len(syms),'bl-targets',sum(1 for v in funcs.values() if v))
