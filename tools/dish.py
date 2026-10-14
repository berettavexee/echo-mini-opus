# dish.py IMG ovl start end : disassemble HiFi codec overlay at base 0 (data at 0x01020000)
import struct,sys,capstone
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B=0x03050000; e=struct.unpack_from('<8I',c,8+32*int(sys.argv[2]))
code=c[e[0]-B:e[0]-B+e[2]]
s,t=int(sys.argv[3],16),int(sys.argv[4],16)
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS); md.skipdata=True
for x in md.disasm(code[s:t],s):
    extra=''
    if x.mnemonic.startswith('ldr') and '[pc' in x.op_str:
        try:
            a=((x.address+4)&~3)+int(x.op_str.split('#')[-1].rstrip(']'),0); v=struct.unpack_from('<I',code,a)[0]
            extra='  ; =0x%08x'%v
            if v<len(code):
                st=code[v:v+40].split(b'\0')[0]
                if len(st)>4 and all(32<=b<127 for b in st): extra+=' "%s"'%st.decode()
        except Exception: pass
    print('%06x  %-8s %s%s'%(x.address,x.mnemonic,x.op_str,extra))
