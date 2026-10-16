"""Vocal effects for the M-One OS (P:$0700-$08FF). Writes vocal.hex. Mirrors dsp/model/vox_model.py.

fx_vox: X1 in -> X1 out. VOX = vocal chain for a crystal ham mic: 4-biquad EQ (HPF 80 | +5 dB 180 | -4 dB 1k |
  -4 dB 3.5k), leveler (threshold T), light tube (2nd + 3rd harmonic, DC block), exciter (HPF 3k -> soft clip, mixed
  in), 110 ms slap with low-passed repeats.
vox_init: clears the state and the slap buffer, copies the biquad coefficients from P to Y.
Memory: X short $1A-$1F (env, g, dc lp, slap lp, slap index, input peak) | X:$0100-$0113 biquad states |
  Y:$0100-$0118 coefficients | X:$032000-$033FFF slap buffer (external SRAM). Regs used: A B X0 X1 Y0 Y1 R0 R1 R2 R4.
Debug: X:$1F = peak |input| since boot (never decays): read it to set the gain staging.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools', 'model'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, EA_IMM, ea  # noqa: E402
from dis56k import listing  # noqa: E402
import vox_model as vm  # noqa: E402

BASE, END = 0x700, 0x8FF
XS, YC, SLAP = 0x0100, 0x0100, 0x032000
ENV, G, LP, LPD, W, PK = range(0x1A, 0x20)
q = vm.q23

a = Asm(BASE)
J12 = {'other': 1, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}
J16 = {'other': 0, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}
QQQ = ['X0,X0', 'Y0,Y0', 'X1,X0', 'Y1,Y0', 'X0,Y1', 'Y0,X0', 'X1,Y0', 'Y1,X1']
QI = {'X0': 0, 'Y0': 1, 'X1': 2, 'Y1': 3}
def D(acc): return 'AB'.index(acc)
def src(s): return 'other' if s in ('A', 'B') else s
def mv(s, d): a.par(move=('Mover', dict(e=R5[s], d=R5[d])))
def ldx(aa, reg): a.par(move=('Movex_aa', dict(W=1, a=aa, d=R5[reg])))
def stx(reg, aa): a.par(move=('Movex_aa', dict(W=0, a=aa, d=R5[reg])))
def li(reg, v): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **EA_IMM)), ext=v)
def ldxi(e, reg, alu=None): a.par(alu=alu, move=('Movex_ea', dict(W=1, d=R5[reg], **ea(e))))
def stxi(reg, e, alu=None): a.par(alu=alu, move=('Movex_ea', dict(W=0, d=R5[reg], **ea(e))))
def ldyi(e, reg): a.par(move=('Movey_ea', dict(W=1, d=R5[reg], **ea(e))))
def styi(reg, e): a.par(move=('Movey_ea', dict(W=0, d=R5[reg], **ea(e))))
def sub(s, d): a.par(alu=('Sub_SD', dict(J=J12[src(s)], d=D(d))))
def cmp(s, d): a.par(alu=('Cmp_S1S2', dict(J=J16[src(s)], d=D(d))))     # flags of d - s
def clr(d): a.par(alu=('Clr', dict(d=D(d))))
def abs_(d): a.par(alu=('Abs', dict(d=D(d))))
def tfr(s, d): a.par(alu=('Tfr', dict(J=J16[src(s)], d=D(d))))
def asl1(d): a.par(alu=('Asl_D', dict(d=D(d))))
def MPY(s1, s2, d, k=0):
    p = '%s,%s' % (s1, s2)
    return ('Mpy_S1S2D', dict(Q=QQQ.index(p) if p in QQQ else QQQ.index('%s,%s' % (s2, s1)), d=D(d), k=k))
def MAC(s1, s2, d, k=0):
    n, f = MPY(s1, s2, d, k)
    return ('Mac_S1S2', f)
def mpy(s1, s2, d, k=0): a.par(alu=MPY(s1, s2, d, k))
def mpyi(v, s, d, k=0): a.op('Mpyi', ext=v, q=QI[s], d=D(d), k=k)
def maci(v, s, d, k=0): a.op('Maci_xxxx', ext=v, q=QI[s], d=D(d), k=k)
def addi(v, d):
    if 0 <= v < 64: a.op('Add_xx', i=v, d=D(d))
    else: a.op('Add_xxxx', ext=v, d=D(d))
def subi(v, d):
    if 0 <= v < 64: a.op('Sub_xx', i=v, d=D(d))
    else: a.op('Sub_xxxx', ext=v, d=D(d))
def cmpi(v, d): a.op('Cmp_xxxxS2', ext=v, d=D(d))
def andi(v, d): a.op('And_xxxx', ext=v, d=D(d))
def ori(v, d): a.op('Or_xxxx', ext=v, d=D(d))
def asl(n, d): a.op('Asl_ii', S=D(d), i=n, D=D(d))
def nop(): a.word(0)
def rts(): a.word(0x00000C)
def j(c, lbl): a.jshort(c, lbl)

# ============================================================ vox_init
a.label('vox_init')
clr('A')
li('R0', XS); li('B', 20)
a.label('vi_st')
stxi('A', '(R0)+'); subi(1, 'B'); j('NE', 'vi_st')
for c in (ENV, LP, LPD, W, PK):
    stx('A', c)
li('R1', SLAP); li('B', vm.SLAPN)
a.label('vi_buf')
stxi('A', '(R1)+'); subi(1, 'B'); j('NE', 'vi_buf')
li('A', 0x7FFFFF); stx('A', G)                     # g = 1.0
li('R0', 0); a.fix.append((len(a.w) - 1, 'vox_tab', 'abs'))   # r0 = vox_tab (P)
li('R4', YC); li('B', len(vm.coef_words()))
a.label('vi_co')
a.op('Movem_ea', W=1, d=R6['X0'], **ea('(R0)+'))
styi('X0', '(R4)+'); subi(1, 'B'); j('NE', 'vi_co')
rts()

# ============================================================ bq: one DF1 biquad
# in X0, out X0. R0 -> X state [x1, x2, y1, y2], R4 -> Y coefs [b0, b1, b2, -a1, -a2] / 2; both advance to the next
a.label('bq')
ldyi('(R4)+', 'Y0')                                 # b0
ldxi('(R0)', 'X1', alu=MPY('X0', 'Y0', 'A'))         # a = b0 x ; x1 = xs1
ldyi('(R4)+', 'Y0')                                 # b1
stxi('X0', '(R0)+', alu=MAC('X1', 'Y0', 'A'))        # a += b1 xs1 ; xs1 = x
ldxi('(R0)', 'X0')                                  # x0 = xs2
ldyi('(R4)+', 'Y0')                                 # b2
stxi('X1', '(R0)+', alu=MAC('X0', 'Y0', 'A'))        # a += b2 xs2 ; xs2 = old xs1
ldxi('(R0)+', 'X1')                                 # x1 = ys1
ldyi('(R4)+', 'Y0')                                 # -a1
ldxi('(R0)', 'X0', alu=MAC('X1', 'Y0', 'A'))         # a += -a1 ys1 ; x0 = ys2
ldyi('(R4)+', 'Y0')                                 # -a2
stxi('X1', '(R0)-', alu=MAC('X0', 'Y0', 'A'))        # a += -a2 ys2 ; ys2 = ys1
asl1('A')                                           # coefficients were halved
stxi('A', '(R0)+')                                  # ys1 = y (saturated)
mv('A', 'X0')
a.op('Lua_ea', M=3, R=0, d=R5['R0'])                # r0++ : past ys2 to the next stage
rts()

# ============================================================ fx_vox (X1 in -> X1 out)
a.label('fx_vox')
mv('X1', 'A'); abs_('A'); ldx(PK, 'B'); cmp('B', 'A')    # debug: input peak
j('LE', 'vx_pk')
stx('A', PK)
a.label('vx_pk')
mv('X1', 'X0')
li('R0', XS); li('R4', YC)
for _ in range(4):
    a.jsr('bq')
# --- leveler
ldx(G, 'Y0'); mpy('X0', 'Y0', 'A'); mv('A', 'X1')        # y = x g
tfr('A', 'B'); abs_('B')                                  # b = |y|
ldx(ENV, 'Y1'); mpyi(q(vm.DEC), 'Y1', 'A')                # a = env * decay
cmp('B', 'A')                                             # a - b
j('GE', 'vx_env')
tfr('B', 'A')
a.label('vx_env')
stx('A', ENV); ldx(G, 'Y1')
cmpi(q(vm.T), 'A')
j('GT', 'vx_over')
mpyi(q(1 - vm.R), 'Y1', 'B'); addi(q(vm.R), 'B')
j('T', 'vx_g')
a.label('vx_over')
mpyi(q(vm.ATT), 'Y1', 'B')
a.label('vx_g')
stx('B', G)
# --- tube: u = sat(2y) ; t = u + C2 u^2 - C3 u^3 ; DC block
mv('X1', 'A'); asl1('A'); mv('A', 'X0')
mpy('X0', 'X0', 'A'); mv('A', 'Y0')                       # u^2
mpy('X0', 'Y0', 'B'); mv('B', 'Y1')                       # u^3
mv('X0', 'A')
maci(q(vm.C2), 'Y0', 'A'); maci(q(vm.C3), 'Y1', 'A', k=1)
ldx(LP, 'X0'); sub('X0', 'A'); mv('A', 'X0')              # hp = t - lp
ldx(LP, 'B'); maci(q(vm.KDC), 'X0', 'B'); stx('B', LP)    # lp += kdc hp
# --- exciter
mv('X0', 'Y1')                                            # keep the tube out (bq leaves Y1 alone)
a.jsr('bq')                                               # h = HPF 3 kHz (r0/r4 are already at stage 5)
mv('X0', 'A'); asl(2, 'A'); mv('A', 'X0')                 # v = sat(4h)
mpy('X0', 'X0', 'A'); mv('A', 'X1')                       # v^2
mpy('X1', 'X0', 'A'); mv('A', 'X1')                       # v^3
mpyi(q(0.75), 'X0', 'A'); maci(q(0.25), 'X1', 'A', k=1); mv('A', 'X0')
mv('Y1', 'A'); maci(q(vm.MX2), 'X0', 'A'); mv('A', 'X1')  # ex = tube + mx2 f
# --- slap
ldx(W, 'A'); subi(vm.DLY, 'A'); andi(vm.SLAPN - 1, 'A'); ori(SLAP, 'A'); mv('A1', 'R1')
nop()
ldxi('(R1)', 'A')                                         # a = d
ldx(LPD, 'Y0'); sub('Y0', 'A'); mv('A', 'X0')             # d - lpd
ldx(LPD, 'B'); maci(q(vm.KS), 'X0', 'B'); stx('B', LPD); mv('B', 'Y0')   # lpd
mv('X1', 'A'); maci(q(vm.FB), 'Y0', 'A')                  # write = ex + fb lpd
ldx(W, 'B'); ori(SLAP, 'B'); mv('B1', 'R2')
nop()
stxi('A', '(R2)')
mv('X1', 'A'); maci(q(vm.MIXS), 'Y0', 'A'); mv('A', 'X1')  # out = ex + mixs lpd
ldx(W, 'B'); addi(1, 'B'); andi(vm.SLAPN - 1, 'B'); stx('B1', W)
rts()

# ============================================================ coefficient table (P, copied to Y at init)
a.label('vox_tab')
for v in vm.coef_words():
    a.word(v, note='data')

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal.py runs past P:%04X: %X' % (END, end)
VOX_INIT, FX_VOX = a.labels['vox_init'], a.labels['fx_vox']
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  vox_init=%04X fx_vox=%04X' % (len(words), end, VOX_INIT, FX_VOX))
    a.hexfile(os.path.join(HERE, 'vocal.hex'))
