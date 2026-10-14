import sys,re,bisect,collections
log,syms=sys.argv[1:]
S=[(int(a,16),n) for a,n in (l.split() for l in open(syms))]; A=[a for a,_ in S]
def cnt(h):
    b=bytes.fromhex(h); i=n=0
    while i+1<len(b):
        hw=b[i]|b[i+1]<<8; i+= 4 if (hw>>11) in (0x1d,0x1e,0x1f) else 2; n+=1
    return n
ninsn={}; pend=None; execs=collections.Counter()
for l in open(log,errors='replace'):
    m=re.match(r'0x([0-9a-f]{8}):',l)
    if m: pend=int(m.group(1),16); ninsn.setdefault(pend,0); continue
    if l.startswith('OBJD-T:') and pend is not None: ninsn[pend]+=cnt(l.split()[1]); continue
    if l.startswith('Trace'):
        m=re.search(r'/([0-9a-f]{16})/',l)
        if m: execs[int(m.group(1),16)]+=1
f=collections.Counter()
for pc,c in execs.items():
    i=bisect.bisect_right(A,pc)-1
    f[S[i][1] if i>=0 else '?']+=c*ninsn.get(pc,0)
tot=sum(f.values())
print("total",tot)
for n,c in f.most_common(): print(f"{c:12d} {100*c/tot:6.2f}% {n}")
