import struct,sys,capstone
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); ents=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
tg=set(int(x,16) for x in sys.argv[2].split(','))
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS); md.skipdata=True
for i,(cl,ce,cs,*_) in enumerate(ents):
    if not cs or ce==0: continue
    for x in md.disasm(c[cl-B:cl-B+cs],ce):
        if x.mnemonic in('bl','b.w','b') and x.op_str.startswith('#') and int(x.op_str[1:],16) in tg:
            print('ovl%d'%i,hex(x.address),x.mnemonic,x.op_str)
