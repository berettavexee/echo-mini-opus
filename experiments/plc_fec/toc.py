import sys,struct
def pkts(f):
    d=open(f,'rb').read(); i=0; cur=b''
    while i<len(d):
        assert d[i:i+4]==b'OggS'; ns=d[i+26]; lace=d[i+27:i+27+ns]; p=i+27+ns
        for l in lace:
            cur+=d[p:p+l]; p+=l
            if l<255: yield cur; cur=b''
        i=p
for f in sys.argv[1:]:
    modes=[]
    for k,pk in enumerate(pkts(f)):
        if k<2 or not pk: continue
        c=pk[0]>>3; modes.append('S' if c<12 else 'H' if c<16 else 'C')
    tr=sum(1 for a,b in zip(modes,modes[1:]) if (a=='C')!=(b=='C'))
    print(f, {m:modes.count(m) for m in 'SHC'}, "CELT<->SILK/hybrid transitions:", tr)
