# Reachability split of module 74 (HiFi WMA): runtime vs WMA library, code + data refs
import re,struct,collections,sys
IMG=sys.argv[1]
d=open(IMG,'rb').read(); c=d[0x200:]
B=0x03050000; e=struct.unpack_from('<8I',c,8+32*74)
code=c[e[0]-B:e[0]-B+e[2]]; CS=len(code)
import capstone
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB|capstone.CS_MODE_MCLASS); md.detail=False
def lit(a):
    return struct.unpack_from('<I',code,a)[0] if 0<=a<=CS-4 else None
def walk(entry):
    """recursive-descent disasm of one function from entry; returns (calls, datarefs, code_bytes_set, litpool)"""
    seen=set(); todo=[entry]; calls=set(); drefs=set(); ranges=set(); lits=set()
    while todo:
        a=todo.pop()
        while 0<=a<CS and a not in seen:
            ins=next(md.disasm(code[a:a+4],a),None)
            if ins is None: break
            seen.add(a); ranges.update(range(a,a+ins.size))
            mn,op=ins.mnemonic,ins.op_str
            nxt=a+ins.size
            # pc-relative literal
            m=re.search(r'\[pc, #(-?0x[0-9a-f]+|\d+)\]',op)
            if m and mn.startswith('ldr'):
                la=((a+4)&~3)+int(m.group(1),0); v=lit(la)
                if v is not None:
                    lits.update(range(la,la+(8 if mn=='ldrd' else 4)))
                    if v&1 and 0x80<v<CS: calls.add(v&~1)       # function pointer
                    elif 0x01020000<=v<0x01060000: drefs.add(v)
            m=re.match(r'(adr|addw|subw)',mn)
            if m and 'pc' in op or mn=='adr':
                mm=re.search(r'#(-?0x[0-9a-f]+|\d+)',op)
                if mm:
                    off=int(mm.group(1),0); base=(a+4)&~3
                    t=base-off if mn=='subw' else base+off
                    if t&1 and t<CS: calls.add(t&~1)
            if mn in ('bl',):
                calls.add(int(op[1:],16))
            elif mn in('b','b.w') :
                t=int(op[1:],16) if op.startswith('#') else None
                if t is not None: todo.append(t)
                break
            elif mn.startswith('b') and op.startswith('#') and mn not in('bic','bics','bfc','bfi','bx','blx'):
                todo.append(int(op[1:],16))       # conditional branch
            elif mn in('cbz','cbnz'):
                todo.append(int(op.split('#')[-1],16))
            elif mn in('tbb','tbh'):
                n=None
                # assume up to 64 entries; stop when target goes backwards before table
                tb=a+4
                for i in range(64):
                    off=code[tb+i] if mn=='tbb' else struct.unpack_from('<H',code,tb+2*i)[0]
                    t=tb+2*off
                    if t<tb+ (i+1)*(1 if mn=='tbb' else 2): break
                    todo.append(t)
                break
            if mn=='bx' and op=='lr': break
            if mn.startswith('pop') and 'pc' in op and not re.match(r'pop(eq|ne|hs|lo|hi|ls|ge|lt|gt|le|mi|pl|cs|cc)',mn): break
            if mn=='ldr' and op.startswith('pc'): break
            a=nxt
    return calls,drefs,ranges,lits
def closure(roots,stop=set()):
    funcs={}; todo=list(roots)
    while todo:
        f=todo.pop()
        if f in funcs or f in stop or not(0<=f<CS): continue
        r=walk(f); funcs[f]=r
        todo.extend(r[0])
    return funcs
RT_ROOTS=[0x2aa8,0x15b6,0x139c,0x142c,0x9a]   # reset, main, mailbox ISRs, default handler
rt=closure(RT_ROOTS,stop={0x2ec4})
lib=closure([0x2ec4],stop=set(rt))
def span(fs):
    s=set()
    for f,(c_,d_,r,l) in fs.items(): s|=r; s|=l
    return s
rs,ls=span(rt),span(lib)
def runs(s):
    s=sorted(s); out=[]; st=pv=None
    for x in s:
        if st is None: st=pv=x
        elif x<=pv+8: pv=x
        else: out.append((st,pv+1)); st=pv=x
    if st is not None: out.append((st,pv+1))
    return out
print('runtime funcs',len(rt),'bytes',len(rs)); print(' runs:',' '.join('%x-%x'%r for r in runs(rs)))
print('lib funcs',len(lib),'bytes',len(ls)); print(' runs:',' '.join('%x-%x'%r for r in runs(ls)[:40]))
both=[f for f in lib if f in rt]
sh=[f for f in rt if any(f in lib[g][0] for g in lib)]
print('runtime funcs called by lib:',' '.join('%x'%f for f in sorted(sh)))
rd=set(); ld=set()
for f,(c_,dr,r,l) in rt.items(): rd|=dr
for f,(c_,dr,r,l) in lib.items(): ld|=dr
print('data refs runtime-only:',len(rd-ld),'lib-only:',len(ld-rd),'shared:',' '.join('%x'%x for x in sorted(rd&ld)))
print(' runtime data:',' '.join('%x'%x for x in sorted(rd)))
print(' lib data range: %x..%x'%(min(ld-rd),max(ld-rd)))
print(' lib data (sorted):',' '.join('%x'%x for x in sorted(ld-rd)))
