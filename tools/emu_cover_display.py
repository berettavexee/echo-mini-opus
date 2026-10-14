# emu_cover_display.py IMG file : real content sniffer (uninitialised ext buffer) -> overlay-18 cover
# extraction sub_030814de -> image open/JPEG header (sub_03081b06, overlay 19). File I/O emulated.
import sys,struct
from unicorn import *
from unicorn.arm_const import *
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); E=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
data=open(sys.argv[2],'rb').read(); EXT=sys.argv[3].encode() if len(sys.argv)>3 else b'OPU'
IN,OUTH,TMP=5,7,6; pos={IN:0,OUTH:0,TMP:0}; files={OUTH:bytearray()}; log=[]
mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
mu.mem_map(0x03000000,0x00200000); mu.mem_map(0xe0000000,0x00100000); mu.mem_map(0x40000000,0x01000000)
mu.mem_map(0x60000000,0x01000000)
for i in (0,18,19):
    cl,ce,cn,dl,de,dn,be,bn=E[i]
    mu.mem_write(ce,c[cl-B:cl-B+cn]); mu.mem_write(de,c[dl-B:dl-B+dn])
def R(r): return mu.reg_read(r)
def ret(v): mu.reg_write(UC_ARM_REG_R0,v&0xffffffff); mu.reg_write(UC_ARM_REG_PC,R(UC_ARM_REG_LR))
def src(h): return data if h==IN else files[OUTH]
calls={}
def hk(mu,a,size,u):
    if a==0x0305999a:
        buf,nb,h=R(UC_ARM_REG_R0),R(UC_ARM_REG_R1),R(UC_ARM_REG_R2)&0xff
        ch=bytes(src(h)[pos[h]:pos[h]+nb]); mu.mem_write(buf,ch); pos[h]+=len(ch); ret(len(ch))
        if h==TMP: log.append('rd tmp %d'%nb)
    elif a==0x03059e92:
        off=struct.unpack('<i',struct.pack('<I',R(UC_ARM_REG_R0)))[0]; wh,h=R(UC_ARM_REG_R1),R(UC_ARM_REG_R2)&0xff
        pos[h]={0:0,1:pos[h],2:len(src(h))}[wh]+off; ret(0)
        if h==TMP: log.append('seek tmp %d,%d'%(off,wh))
    elif a==0x0305d212: log.append('create'); pos[OUTH]=0; files[OUTH]=bytearray(); ret(OUTH)
    elif a==0x0305d25a: log.append('delete'); ret(0)
    elif a==0x03059880: log.append('close %d'%(R(UC_ARM_REG_R0)&0xff)); ret(0)
    elif a==0x030596ba: log.append('open tmp'); pos[TMP]=0; ret(TMP)
    elif a==0x0305d40c:
        buf,ln=R(UC_ARM_REG_R0),R(UC_ARM_REG_R2); files[OUTH]+=bytes(mu.mem_read(buf,ln)); ret(ln)
    elif a in (0x03061da8,0x0306edbc,0x0306913c): ret(0)
    elif a==0x030814fc: mu.mem_write(R(UC_ARM_REG_SP)+0x20c,b'\xa5\x5a\xc3\x00')   # uninitialised stack
    elif a==0x03081504: print('  sniffer ->',bytes(mu.mem_read(R(UC_ARM_REG_SP)+0x20c,3)))
    elif a in (RDP,SKP):
        h=R(UC_ARM_REG_R2)&0xff
        if a==RDP:
            buf,nb=R(UC_ARM_REG_R0),R(UC_ARM_REG_R1); ch=bytes(src(h)[pos[h]:pos[h]+nb]); mu.mem_write(buf,ch); pos[h]+=len(ch); ret(len(ch))
        else: pos[h]=R(UC_ARM_REG_R0); ret(0)
    elif a==0x03000000: mu.emu_stop()
    if 0x3083d20<=a<0x3086650 or a in (0x3081b06,0x3081bc0,0x3081bca,0x3081bdc,0x3081c4c):
        if a in (0x3084604,0x3084080,0x3081bc0,0x3081bca,0x3081bdc,0x3081c4c,0x3081b06): print('  at',hex(a),'r0',hex(R(UC_ARM_REG_R0)))
def bad(mu,acc,a,sz,v,u): print('unmapped',hex(a),'pc',hex(R(UC_ARM_REG_PC))); return False
RDP,SKP=0x03100000,0x03100010
mu.mem_write(RDP,b'\x70\x47'); mu.mem_write(SKP,b'\x70\x47')
mu.mem_write(0x03004538,struct.pack('<I',RDP|1)); mu.mem_write(0x0300453c,struct.pack('<I',SKP|1)); mu.mem_write(0x0304af7c,struct.pack('<I',1))
mu.hook_add(UC_HOOK_CODE,hk); mu.hook_add(UC_HOOK_MEM_UNMAPPED,bad)
OUT=0x03180000; mu.mem_write(OUT,b'\xff'*8)
for fn,args in ((0x030814de,(IN,OUT)),(0x03081b06,(IN,None))):
    mu.reg_write(UC_ARM_REG_SP,0x031f0000); mu.reg_write(UC_ARM_REG_LR,0x03000001)
    if args and args[1] is None: args=(IN,struct.unpack('<i',mu.mem_read(OUT,4))[0])
    for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1),args): mu.reg_write(r,v&0xffffffff)
    try: mu.emu_start(fn|1,0x03000000,count=500000000)
    except UcError as e: print('error',e,hex(R(UC_ARM_REG_PC)))
    print(hex(fn),'->',hex(R(UC_ARM_REG_R0)))
print(log[:30])
for a in (0x03024840,0x030247ae): print(hex(a),struct.unpack('<h',mu.mem_read(a,2))[0])
