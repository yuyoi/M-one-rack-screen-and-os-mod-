"""Shared assembler helpers for the effect modules: H(a) binds them to one Asm (dsp56300 parallel-move style).

    from asmh import H
    h = H(Asm(0x700))
    h.mpy('X0', 'Y0', 'A'); h.xr('A', 5)        # X:(R3+5) -> A
"""
from asm56 import R5, R6, C5, EA_IMM, ea

QQQ = ['X0,X0', 'Y0,Y0', 'X1,X0', 'Y1,Y0', 'X0,Y1', 'Y0,X0', 'X1,Y0', 'Y1,X1']
QI = {'X0': 0, 'Y0': 1, 'X1': 2, 'Y1': 3}
J12 = {'other': 1, 'X': 2, 'Y': 3, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}
J16 = {'other': 0, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}


def D(acc): return 'AB'.index(acc)
def src(s): return 'other' if s in ('A', 'B') else s


def MPY(s1, s2, d, k=0):
    p = '%s,%s' % (s1, s2)
    return ('Mpy_S1S2D', dict(Q=QQQ.index(p) if p in QQQ else QQQ.index('%s,%s' % (s2, s1)), d=D(d), k=k))


def MAC(s1, s2, d, k=0):
    return ('Mac_S1S2', MPY(s1, s2, d, k)[1])


class H:
    def __init__(self, a, long_jumps=None):
        self.a = a
        self.long = a.base >= 0x1000 if long_jumps is None else long_jumps   # short jumps reach P:$0FFF only

    # moves
    def mv(self, s, d): self.a.par(move=('Mover', dict(e=R5[s], d=R5[d])))
    def ldx(self, aa, reg): self.a.par(move=('Movex_aa', dict(W=1, a=aa, d=R5[reg])))
    def stx(self, reg, aa): self.a.par(move=('Movex_aa', dict(W=0, a=aa, d=R5[reg])))
    def li(self, reg, v): self.a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **EA_IMM)), ext=v)
    def ldl(self, addr, reg): self.a.par(move=('Movex_ea', dict(W=1, d=R5[reg], M=6, R=0)), ext=addr)
    def stl(self, reg, addr): self.a.par(move=('Movex_ea', dict(W=0, d=R5[reg], M=6, R=0)), ext=addr)
    def ldxi(self, e, reg, alu=None): self.a.par(alu=alu, move=('Movex_ea', dict(W=1, d=R5[reg], **ea(e))))
    def stxi(self, reg, e, alu=None): self.a.par(alu=alu, move=('Movex_ea', dict(W=0, d=R5[reg], **ea(e))))
    def ldyi(self, e, reg): self.a.par(move=('Movey_ea', dict(W=1, d=R5[reg], **ea(e))))
    def styi(self, reg, e): self.a.par(move=('Movey_ea', dict(W=0, d=R5[reg], **ea(e))))
    def xr(self, reg, off, R=3): self.a.op('Movex_Rnxxx', a=off & 127, R=R, W=1, D=R5[reg])     # X:(Rn+off) -> reg
    def xw(self, reg, off, R=3): self.a.op('Movex_Rnxxx', a=off & 127, R=R, W=0, D=R5[reg])     # reg -> X:(Rn+off)
    def lua(self, R, d, M=1): self.a.op('Lua_ea', M=M, R=R, d=R5[d])                           # d = Rn + Nn (M=1)
    # ALU
    def alu(self, n, **f): self.a.par(alu=(n, f))
    def add(self, s, d): self.alu('Add_SD', J=J12[src(s)], d=D(d))
    def sub(self, s, d): self.alu('Sub_SD', J=J12[src(s)], d=D(d))
    def cmp(self, s, d): self.alu('Cmp_S1S2', J=J16[src(s)], d=D(d))      # flags of d - s
    def tfr(self, s, d): self.alu('Tfr', J=J16[src(s)], d=D(d))
    def clr(self, d): self.alu('Clr', d=D(d))
    def tst(self, d): self.alu('Tst', d=D(d))
    def abs_(self, d): self.alu('Abs', d=D(d))
    def neg(self, d): self.alu('Neg', d=D(d))
    def asl1(self, d): self.alu('Asl_D', d=D(d))
    def lsl1(self, d): self.alu('Lsl_D', D=D(d))
    def orr(self, s, d): self.alu('Or_SD', J=QI[s], d=D(d))
    def andr(self, s, d): self.alu('And_SD', J=QI[s], d=D(d))
    def mpy(self, s1, s2, d, k=0): self.a.par(alu=MPY(s1, s2, d, k))
    def mac(self, s1, s2, d, k=0): self.a.par(alu=MAC(s1, s2, d, k))
    def mpyi(self, v, s, d, k=0): self.a.op('Mpyi', ext=v, q=QI[s], d=D(d), k=k)
    def maci(self, v, s, d, k=0): self.a.op('Maci_xxxx', ext=v, q=QI[s], d=D(d), k=k)
    def addi(self, v, d):
        if 0 <= v < 64: self.a.op('Add_xx', i=v, d=D(d))
        else: self.a.op('Add_xxxx', ext=v, d=D(d))
    def subi(self, v, d):
        if 0 <= v < 64: self.a.op('Sub_xx', i=v, d=D(d))
        else: self.a.op('Sub_xxxx', ext=v, d=D(d))
    def cmpi(self, v, d):
        if 0 <= v < 64: self.a.op('Cmp_xxS2', i=v, d=D(d))
        else: self.a.op('Cmp_xxxxS2', ext=v, d=D(d))
    def andi(self, v, d): self.a.op('And_xxxx', ext=v, d=D(d))
    def ori(self, v, d): self.a.op('Or_xxxx', ext=v, d=D(d))
    def eori(self, v, d): self.a.op('Eor_xxxx', ext=v, d=D(d))
    def asl(self, n, d): self.a.op('Asl_ii', S=D(d), i=n, D=D(d))
    def asr(self, n, d): self.a.op('Asr_ii', S=D(d), i=n, D=D(d))
    def lsl(self, n, d): self.a.op('Lsl_ii', i=n, D=D(d))
    def lsr(self, n, d): self.a.op('Lsr_ii', i=n, D=D(d))
    # flow
    def nop(self): self.a.word(0)
    def rts(self): self.a.word(0x00000C)
    def j(self, c, lbl): self.a.jlong(c, lbl) if self.long else self.a.jshort(c, lbl)
    def rep(self, n): self.a.op('Rep_xxx', i=n & 0xFF, h=n >> 8)
    def movec(self, ctrl, v): self.a.op('Movec_ea', ext=v, W=1, S=0, D=C5[ctrl], **EA_IMM)
