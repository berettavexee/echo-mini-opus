# emu_tags.py IMG EXT file... : run the resident tag dispatcher sub_0306df9c(handle, out, ext)
# with the real code; only file read (0x0305999a) and seek (0x03059e92) are emulated in Python.
import sys,struct
from unicorn import *
from unicorn.arm_const import *
d=open(sys.argv[1],'rb').read(); c=d[0x200:0x200+0x187c14]
B,n=struct.unpack_from('<2I',c,0); E=[struct.unpack_from('<8I',c,8+32*i) for i in range(n)]
ext=sys.argv[2].encode()
STUBS={0x03061da8}             # watchdog kick (peripheral write)
FIELDS={0x60:'TITLE?',0x15e:'ARTIST?',0x25c:'ALBUM?',0x35a:'f4',0x458:'GENRE?',0x0:'TRACK?',0x8:'f5'}
for path in sys.argv[3:]:
    data=open(path,'rb').read(); pos=[0]
    mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    mu.mem_map(0x03000000,0x00200000); mu.mem_map(0xe0000000,0x00100000); mu.mem_map(0x40000000,0x01000000)
    cl,ce,cn,dl,de,dn,be,bn=E[0]
    mu.mem_write(ce,c[cl-B:cl-B+cn]); mu.mem_write(de,c[dl-B:dl-B+dn])
    OUT=0x03180000; EXT=0x03181000; mu.mem_write(EXT,ext+b'\0')
    sp=0x031f0000; mu.reg_write(UC_ARM_REG_SP,sp); mu.reg_write(UC_ARM_REG_LR,0x03000001)
    mu.reg_write(UC_ARM_REG_R0,0x55); mu.reg_write(UC_ARM_REG_R1,OUT); mu.reg_write(UC_ARM_REG_R2,EXT)
    calls={}
    def ret(v):
        mu.reg_write(UC_ARM_REG_R0,v&0xffffffff); mu.reg_write(UC_ARM_REG_PC,mu.reg_read(UC_ARM_REG_LR))
    def hk(mu,a,size,u):
        if a==0x0305999a:                       # read(buf, n, handle)
            buf,nb=mu.reg_read(UC_ARM_REG_R0),mu.reg_read(UC_ARM_REG_R1)
            chunk=data[pos[0]:pos[0]+nb]; mu.mem_write(buf,chunk); pos[0]+=len(chunk); ret(len(chunk))
        elif a==0x03059e92:                     # seek(off, whence, handle)
            off=struct.unpack('<i',struct.pack('<I',mu.reg_read(UC_ARM_REG_R0)))[0]; wh=mu.reg_read(UC_ARM_REG_R1)
            pos[0]={0:0,1:pos[0],2:len(data)}[wh]+off; calls['seek']=calls.get('seek',0)+1; ret(0)
        elif a==0x03069196: print('  drv call from',hex(mu.reg_read(UC_ARM_REG_LR)),[hex(mu.reg_read(r)) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]); mu.emu_stop()
        elif a==0x03069df4:                     # codepage -> UTF-16 (tables in flash): latin-1 stand-in
            src,dst,ln=mu.reg_read(UC_ARM_REG_R0),mu.reg_read(UC_ARM_REG_R1),mu.reg_read(UC_ARM_REG_R2)
            s=bytes(mu.mem_read(src,ln)).split(b'\x00')[0].decode('latin-1'); mu.mem_write(dst,s.encode('utf-16le')+b'\x00\x00'); ret(len(s))
        elif a in STUBS: ret(0)
        elif a==0x03000000: mu.emu_stop()
    mu.hook_add(UC_HOOK_CODE,hk)
    trail=[]
    mu.hook_add(UC_HOOK_BLOCK,lambda mu,a,s,u:(trail.append(a),trail.__delitem__(0) if len(trail)>40 else None))
    try: mu.emu_start(0x0306df9c|1,0x03000000,count=20000000)
    except UcError as e: print('  error',e,'pc',hex(mu.reg_read(UC_ARM_REG_PC)),'trail',[hex(x) for x in trail[-40:]])
    o=bytes(mu.mem_read(OUT,0x600))
    res={}
    for off,nm in FIELDS.items():
        s=o[off:off+0xfe].decode('utf-16le','replace').split('\0')[0]
        if s: res[nm]=s[:40]
    print(path.split('/')[-1][:40],'->',res,'end pos',pos[0])
