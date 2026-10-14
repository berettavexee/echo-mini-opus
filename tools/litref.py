# litref.py IMG value_hex -> code sites (all overlays) loading this literal via ldr pc-rel
import struct,sys,capstone
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); ents=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
val=int(sys.argv[2],16)
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS); md.skipdata=True
for i,(cl,ce,cs,*_) in enumerate(ents):
    if not cs or ce==0: continue
    code=c[cl-B:cl-B+cs]
    pos=[k for k in range(0,cs-3,4) if struct.unpack_from('<I',code,k)[0]==val]
    if not pos: continue
    for x in md.disasm(code,ce):
        if x.mnemonic.startswith('ldr') and '[pc' in x.op_str:
            try: imm=int(x.op_str.split('#')[-1].rstrip(']'),0)
            except: continue
            a=((x.address+4)&~3)+imm-ce
            if a in pos: print('ovl%d'%i,hex(x.address),x.mnemonic,x.op_str)
