# emu_cover.py IMG file OUTPREFIX : run overlay-18 cover extraction sub_030814de(handle, out) with the
# real code (resident + overlay 18); file I/O emulated in Python, the extracted file is captured.
import sys,struct
from unicorn import *
from unicorn.arm_const import *
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); E=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
data=open(sys.argv[2],'rb').read(); EXT=sys.argv[4].encode() if len(sys.argv)>4 else b'OPU'
IN,OUTH=5,7; pos={IN:0,OUTH:0}; files={OUTH:bytearray()}; log=[]
mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
mu.mem_map(0x03000000,0x00200000); mu.mem_map(0xe0000000,0x00100000); mu.mem_map(0x40000000,0x01000000)
for i in (0,18):
    cl,ce,cn,dl,de,dn,be,bn=E[i]
    mu.mem_write(ce,c[cl-B:cl-B+cn]); mu.mem_write(de,c[dl-B:dl-B+dn])
def R(r): return mu.reg_read(r)
def ret(v): mu.reg_write(UC_ARM_REG_R0,v&0xffffffff); mu.reg_write(UC_ARM_REG_PC,R(UC_ARM_REG_LR))
def src(h): return data if h==IN else files[h]
def hk(mu,a,size,u):
    if a==0x0305999a:                                   # read(buf, n, h)
        buf,nb,h=R(UC_ARM_REG_R0),R(UC_ARM_REG_R1),R(UC_ARM_REG_R2)&0xff
        ch=bytes(src(h)[pos[h]:pos[h]+nb]); mu.mem_write(buf,ch); pos[h]+=len(ch); ret(len(ch))
    elif a==0x03059e92:                                 # seek(off, whence, h)
        off=struct.unpack('<i',struct.pack('<I',R(UC_ARM_REG_R0)))[0]; wh,h=R(UC_ARM_REG_R1),R(UC_ARM_REG_R2)&0xff
        pos[h]={0:0,1:pos[h],2:len(src(h))}[wh]+off; ret(0)
    elif a==0x0305d212: log.append('create'); pos[OUTH]=0; files[OUTH]=bytearray(); ret(OUTH)
    elif a==0x0305d25a: log.append('delete'); ret(0)
    elif a==0x03059880: log.append('close %d'%(R(UC_ARM_REG_R0)&0xff)); ret(0)
    elif a==0x0305d40c:                                 # write(buf, ?, len, h)
        buf,ln=R(UC_ARM_REG_R0),R(UC_ARM_REG_R2); files[OUTH]+=bytes(mu.mem_read(buf,ln)); ret(ln)
    elif a in (0x03061da8,0x0306edbc): ret(0)           # watchdog, debug printf
    elif a==0x03081500: mu.mem_write(R(UC_ARM_REG_SP)+0x20c,EXT+b'\x00')   # sniffer result (see emu_sniff.py)
    elif a in (0x03081504,0x03081512,0x030819b8,0x03081a72,0x03080f3a,0x03081aac): print('  at',hex(a),'r0',hex(R(UC_ARM_REG_R0)), bytes(mu.mem_read(R(UC_ARM_REG_SP)+0x20c,4)) if a==0x03081504 else '')
    elif a==0x03000000: mu.emu_stop()
mu.hook_add(UC_HOOK_CODE,hk)
OUT=0x03180000
for fn,args in ((0x03055184,()),(0x030814de,(IN,OUT))):
    mu.reg_write(UC_ARM_REG_SP,0x031f0000); mu.reg_write(UC_ARM_REG_LR,0x03000001)
    for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1),args): mu.reg_write(r,v)
    try: mu.emu_start(fn|1,0x03000000,count=200000000)
    except UcError as e: print('error',e,hex(R(UC_ARM_REG_PC)))
print(sys.argv[2].split('/')[-1][:40],'ret',hex(R(UC_ARM_REG_R0)),log,'extracted',len(files[OUTH]),'bytes',bytes(files[OUTH][:4]).hex(),'out',bytes(mu.mem_read(OUT,8)).hex())
open(sys.argv[3]+'.bin','wb').write(files[OUTH])
