# Worst-case stack depth from OpusCodec: .su files + call graph from objdump of the linked ELF
import re,subprocess,sys,glob,collections,functools
elf,build=sys.argv[1],sys.argv[2]
su={}
for f in glob.glob(build+'/**/*.su',recursive=True):
    for l in open(f):
        m=re.match(r'.*:\d+:\d+:(\S+)\t(\d+)\t(\S+)',l)
        if m: su[m.group(1)]=max(su.get(m.group(1),0),int(m.group(2))) ; 
dyn={}
for f in glob.glob(build+'/**/*.su',recursive=True):
    for l in open(f):
        m=re.match(r'.*:\d+:\d+:(\S+)\t(\d+)\t(\S+)',l)
        if m and 'dynamic' in m.group(3): dyn[m.group(1)]=m.group(3)
dis=subprocess.run(['arm-none-eabi-objdump','-d',elf],capture_output=True,text=True).stdout
g=collections.defaultdict(set); cur=None; indirect=set()
for l in dis.splitlines():
    m=re.match(r'^[0-9a-f]+ <([^>]+)>:',l)
    if m: cur=m.group(1); continue
    m=re.search(r'\t(bl|b\.w|b)\s+[0-9a-f]+ <([^+>]+)',l)
    if m and cur and m.group(2)!=cur: g[cur].add(m.group(2))
    if re.search(r'\tblx\s+r',l) and cur: indirect.add(cur)
sys.setrecursionlimit(10000)
@functools.lru_cache(None)
def depth(f,stack=()):
    if f in stack: return (0,[f+'(recursion)'])
    best=(0,[])
    for c in g.get(f,()):
        d=depth(c,stack+(f,))
        if d[0]>best[0]: best=d
    return (su.get(f,0)+best[0],[f]+best[1])
d,path=depth('OpusCodec')
print('worst-case stack from OpusCodec: %d bytes'%d)
print(' path:',' -> '.join('%s(%d)'%(p,su.get(p.split('(')[0],0)) for p in path))
print(' dynamic-stack functions:',dyn or 'none')
print(' functions with indirect calls:',sorted(indirect)[:15])
rec=[f for f in g if f in g[f]]
print(' self-recursive:',rec)
