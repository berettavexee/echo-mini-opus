# emu_label.py IMG codec freq bitrate bps : run overlay-27 label builders, print the UTF-16 text they build
import sys,struct
from unicorn import *
from unicorn.arm_const import *
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); E=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
codec,freq,br,bps=[int(x) for x in sys.argv[2:6]]
for fn in (0x307af7e,0x307bca8):
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    mu.mem_map(0x03000000,0x00200000)
    for i in (0,27):
        cl,ce,cn,dl,de,dn,be,bn=E[i]
        mu.mem_write(ce,c[cl-B:cl-B+cn]); mu.mem_write(de,c[dl-B:dl-B+dn])
    mu.mem_write(0x0304af7c,struct.pack('<I',codec))
    sp=0x03100000-0x100; mu.reg_write(UC_ARM_REG_SP,sp)
    mu.reg_write(UC_ARM_REG_R0,freq); mu.reg_write(UC_ARM_REG_R1,br); mu.reg_write(UC_ARM_REG_R2,bps)
    mu.reg_write(UC_ARM_REG_LR,0x03000001)
    out={}
    def hk(mu,addr,size,u):
        if addr<0x03079000 or addr==0x03000000:
            r5=mu.reg_read(UC_ARM_REG_R5); b=mu.mem_read(r5,64)
            out['s']=bytes(b).decode('utf-16le').split('\0')[0]; out['call']=addr; mu.emu_stop()
    mu.hook_add(UC_HOOK_CODE,hk)
    mu.emu_start(fn|1,0x03000000,count=5000)
    print(hex(fn),repr(out.get('s')),'first call ->',hex(out.get('call',0)))
