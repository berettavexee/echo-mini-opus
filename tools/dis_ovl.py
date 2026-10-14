# dis.py IMG ovl_idx start end  (exec addresses)
import struct,sys,capstone
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); e=struct.unpack_from('<8I',c,8+32*int(sys.argv[2]))
s,t=int(sys.argv[3],16),int(sys.argv[4],16)
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS); md.skipdata=True
o=e[0]-B+(s-e[1])
for x in md.disasm(c[o:o+(t-s)],s):
    extra=''
    if x.mnemonic.startswith('ldr') and '[pc' in x.op_str:
        try:
            imm=int(x.op_str.split('#')[-1].rstrip(']'),0); a=((x.address+4)&~3)+imm
            extra='  ; =0x%08x'%struct.unpack_from('<I',c,e[0]-B+(a-e[1]))[0]
        except Exception: pass
    print('%08x  %-8s %s%s'%(x.address,x.mnemonic,x.op_str,extra))
