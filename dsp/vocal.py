"""Vocal effects for the M-One OS (P:$0100-$03FF). Writes vocal.hex. Mirrors dsp/model/vox_model.py.

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
import radio_model as rm  # noqa: E402

BASE, END = 0x100, 0x3FF                                 # above the vector table (interrupts are masked)
XS, YC, SLAP = 0x0100, 0x0100, 0x032000
ENV, G, LP, LPD, W, PK = range(0x1A, 0x20)
q = vm.q23
# RADIO: X state at RS (via R3 + displacement), Y mode table at YR (via R5), wobble ring X:$1300, params X:$0210
RS, YR, RRING, RTAB, RP = 0x0140, 0x0140, 0x1300, 0x03C000, 0x0210
(R_EIN, R_G, R_ENV, R_DCL, R_PH, R_HELD, R_W, R_S1, R_C1, R_S2, R_C2, R_LF, R_HL, R_CLK, R_BT, R_POPEN, R_CUR,
 R_DRY, R_TZ, R_TN1, R_TNZ, R_TS) = range(20, 42)
RSN = 42
RP_DEFAULT = [0, 0x7FFFFF, 0x400000, 0x400000]           # X:$0210 mode, wet, drive trim, noise trim
TI = rm.SI
VTAB = RTAB + len(rm.MODES) * rm.NTAB                    # VOX coefficients, right after RADIO's mode tables

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
def xr(reg, off, W=1, R=3): a.op('Movex_Rnxxx', a=off & 127, R=R, W=W, D=R5[reg])    # X:(Rn+off)
def xw(reg, off, R=3): xr(reg, off, W=0, R=R)
def yr(reg, off, R=5): a.op('Movey_Rnxxx', a=off & 127, R=R, W=1, D=R5[reg])         # Y:(Rn+off)
def ldl(addr, reg): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], M=6, R=0)), ext=addr)  # X:$long
def lsl1(d): a.par(alu=('Lsl_D', dict(D=D(d))))
def lsr(n, d): a.op('Lsr_ii', i=n, D=D(d))
def lsl(n, d): a.op('Lsl_ii', i=n, D=D(d))
def eori(v, d): a.op('Eor_xxxx', ext=v, d=D(d))
def andr(s, d): a.par(alu=('And_SD', dict(J=QI[s], d=D(d))))
def mac(s1, s2, d, k=0): a.par(alu=MAC(s1, s2, d, k))
def add(s, d): a.par(alu=('Add_SD', dict(J=J12[src(s)], d=D(d))))
def tst(d): a.par(alu=('Tst', dict(d=D(d))))

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
clr('A'); li('R0', RS)                              # RADIO state + wobble ring
a.op('Rep_xxx', i=RSN, h=0)
stxi('A', '(R0)+')
li('R1', RRING)
a.op('Rep_xxx', i=0, h=1)                           # 256
stxi('A', '(R1)+')
li('R3', RS); li('A', 0x7FFFFF); nop()
xw('A', R_G); xw('A', R_C1); xw('A', R_C2)
li('A', 0x5A5A5A); xw('A', R_LF)
li('A', 0xFFFFFF); xw('A1', R_CUR)                  # no mode loaded yet: the first sample loads one
for k, v in enumerate(RP_DEFAULT):                  # RADIO params: TELEPHONE, wet 1.0, trims as voiced
    li('A', v); a.par(move=('Movex_ea', dict(W=0, d=R5['A'], M=6, R=0)), ext=RP + k)
li('R0', VTAB)                                      # VOX coefficients: external SRAM -> Y
li('R4', YC); li('B', len(vm.coef_words()))
a.label('vi_co')
ldxi('(R0)+', 'X0')
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

# ============================================================ fx_radio (X1 in -> X1 out), mirrors radio_model.py
a.label('fx_radio')
li('R3', RS); li('R5', YR)
xw('X1', R_DRY)
ldl(RP, 'A')                                              # mode, clamped 0..5
tst('A'); j('GE', 'r_m0'); clr('A')
a.label('r_m0')
a.op('Cmp_xxS2', i=len(rm.MODES) - 1, d=0); j('LE', 'r_m1'); li('A', len(rm.MODES) - 1)
a.label('r_m1')
xr('B', R_CUR); cmp('A', 'B'); j('EQ', 'r_same')
xw('A1', R_CUR)                                           # new mode: copy its table to Y, clear the filters
tfr('A', 'B'); asl(5, 'B'); asl(4, 'A'); add('B', 'A'); ori(RTAB, 'A'); mv('A1', 'R2')
li('R4', YR)
a.do(rm.NTAB, 'r_cp')
ldxi('(R2)+', 'X0'); styi('X0', '(R4)+')
a.label('r_cp')
clr('A'); li('R0', RS); nop()
a.op('Rep_xxx', i=20, h=0)
stxi('A', '(R0)+')
a.label('r_same')
mv('X1', 'B'); abs_('B'); xr('Y1', R_EIN); mpyi(q(rm.DSQ), 'Y1', 'A')      # squelch detector
cmp('B', 'A'); j('GE', 'r_e'); tfr('B', 'A')
a.label('r_e')
xw('A', R_EIN)
mv('X1', 'X0'); li('R0', RS); li('R4', YR)                # HP1 HP2 PK
for _ in range(3):
    a.jsr('bq')
xr('Y0', R_G); mpy('X0', 'Y0', 'A'); mv('A', 'X1')       # leveler
tfr('A', 'B'); abs_('B'); xr('Y1', R_ENV); mpyi(q(vm.DEC), 'Y1', 'A')
cmp('B', 'A'); j('GE', 'r_l'); tfr('B', 'A')
a.label('r_l')
xw('A', R_ENV); xr('Y1', R_G); yr('X0', TI['T']); cmp('X0', 'A'); j('GT', 'r_ov')
mpyi(q(1 - vm.R), 'Y1', 'B'); addi(q(vm.R), 'B'); j('T', 'r_g')
a.label('r_ov')
mpyi(q(vm.ATT), 'Y1', 'B')
a.label('r_g')
xw('B', R_G)
yr('Y0', TI['MK']); mpy('X1', 'Y0', 'A'); asl(2, 'A'); mv('A', 'X1')       # makeup
yr('Y0', TI['DRV']); ldl(RP + 2, 'X0'); mpy('X0', 'Y0', 'A'); mv('A', 'Y0')  # drive
mpy('X1', 'Y0', 'A'); asl(4, 'A'); mv('A', 'X0')
yr('Y0', TI['BIAS']); mv('X0', 'A'); add('Y0', 'A'); mv('A', 'X0')
mpy('X0', 'X0', 'A'); mv('A', 'Y0'); mpy('X0', 'Y0', 'A'); mv('A', 'Y1')
mpyi(q(0.75), 'X0', 'A'); maci(q(0.25), 'Y1', 'A', k=1); asl1('A'); mv('A', 'X0')
xr('Y0', R_DCL); mv('X0', 'A'); sub('Y0', 'A'); mv('A', 'X0')               # DC block
xr('B', R_DCL); maci(q(vm.KDC), 'X0', 'B'); xw('B', R_DCL)
yr('B', TI['INC']); tst('B'); j('EQ', 'r_take')                             # crush: sample-and-hold
yr('Y0', TI['INC']); xr('A', R_PH); add('Y0', 'A')
a.op('Jclr_S', D=R6['A1'], b=23, label='r_noov')
andi(0x7FFFFF, 'A'); xw('A1', R_PH); j('T', 'r_take')
a.label('r_noov')
xw('A1', R_PH); j('T', 'r_hold')
a.label('r_take')
xw('X0', R_HELD)
a.label('r_hold')
xr('A', R_HELD); yr('Y0', TI['MASK']); andr('Y0', 'A'); xw('A1', R_TZ)     # bit mask
xr('A', R_LF); lsl1('A'); j('CC', 'r_n1'); eori(0xC20001, 'A')            # noise: LFSR, two steps
a.label('r_n1')
xw('A1', R_TN1); lsl1('A'); j('CC', 'r_n2'); eori(0xC20001, 'A')
a.label('r_n2')
xw('A1', R_LF); xw('A1', R_TNZ)
ldl(RP + 3, 'X1'); yr('Y0', TI['HISS']); mpy('X1', 'Y0', 'A'); asl1('A'); mv('A', 'Y0')   # hiss
xr('X0', R_TNZ); mpy('X0', 'Y0', 'A'); xr('Y0', R_HL); sub('Y0', 'A'); mv('A', 'X1')
yr('Y0', TI['HK']); xr('B', R_HL); mac('X1', 'Y0', 'B'); xw('B', R_HL)
yr('B', TI['SQ']); tst('B'); j('EQ', 'r_open')                              # squelch gate
xr('A', R_EIN); yr('Y0', TI['SQT']); cmp('Y0', 'A'); j('GT', 'r_sqo')
xr('B', R_POPEN); tst('B'); j('EQ', 'r_c0')
yr('B', TI['BN']); xw('B1', R_BT)
a.label('r_c0')
clr('B'); xw('B', R_POPEN); clr('A'); j('T', 'r_gd')
a.label('r_sqo')
li('B', 1); xw('B1', R_POPEN)
a.label('r_open')
xr('A', R_TZ); xr('Y0', R_HL); add('Y0', 'A')
a.label('r_gd')
mv('A', 'X1')
xr('B', R_BT); tst('B'); j('LE', 'r_nb')                                    # squelch burst
subi(1, 'B'); xw('B1', R_BT)
ldl(RP + 3, 'X0'); yr('Y0', TI['BLEV']); mpy('X0', 'Y0', 'A'); asl1('A'); mv('A', 'Y0')
xr('X0', R_TNZ); mv('X1', 'A'); mac('X0', 'Y0', 'A'); mv('A', 'X1')
a.label('r_nb')
mv('X1', 'X0')                                            # LP1 LP2 (r0/r4 are already at stage 4)
a.jsr('bq'); a.jsr('bq')
xr('A', R_W); ori(RRING, 'A'); mv('A1', 'R1'); nop()     # wobble delay: write
stxi('X0', '(R1)'); xw('X0', R_TS)
for s_, c_, k_ in ((R_S1, R_C1, 'KW'), (R_S2, R_C2, 'KF')):   # LFOs (magic circle)
    yr('Y0', TI[k_]); xr('X1', c_); xr('A', s_); mac('X1', 'Y0', 'A'); xw('A', s_)
    mv('A', 'X1'); xr('A', c_); mac('X1', 'Y0', 'A', k=1); xw('A', c_)
yr('A', TI['D0']); xr('X1', R_S1); yr('Y0', TI['DW']); mac('X1', 'Y0', 'A')
xr('X1', R_S2); yr('Y0', TI['DF']); mac('X1', 'Y0', 'A'); mv('A', 'X1')    # dd
mv('X1', 'A'); lsr(15, 'A')                                                 # di
xr('B', R_W); sub('A', 'B'); andi(rm.RING - 1, 'B'); ori(RRING, 'B'); mv('B1', 'R1')
mv('X1', 'A'); andi(0x7FFF, 'A'); lsl(8, 'A'); mv('A1', 'Y1')              # frac
ldxi('(R1)', 'X0')                                                          # b0
subi(1, 'B'); andi(rm.RING - 1, 'B'); ori(RRING, 'B'); mv('B1', 'R1'); nop()
ldxi('(R1)', 'A'); sub('X0', 'A'); mv('A', 'X1'); mpy('X1', 'Y1', 'A'); add('X0', 'A'); mv('A', 'Y0')   # dv
xr('B', R_W); addi(1, 'B'); andi(rm.RING - 1, 'B'); xw('B1', R_W)
yr('X1', TI['DLY']); mpy('X1', 'Y0', 'A'); yr('Y1', TI['DMIX']); xr('X0', R_TS); mac('X0', 'Y1', 'A'); mv('A', 'X1')
clr('A'); xr('A1', R_TN1); andi(0x7FFFFF, 'A'); yr('Y0', TI['CTH']); cmp('Y0', 'A'); j('GE', 'r_nc')   # crackle
ldl(RP + 3, 'X0'); yr('Y0', TI['CAMP']); mpy('X0', 'Y0', 'A'); asl1('A'); mv('A', 'Y0')
xr('X0', R_TNZ); mpy('X0', 'Y0', 'A'); xw('A', R_CLK); j('T', 'r_ck')
a.label('r_nc')
xr('X0', R_CLK); yr('Y0', TI['CDEC']); mpy('X0', 'Y0', 'A'); xw('A', R_CLK)
a.label('r_ck')
mv('X1', 'A'); xr('Y0', R_CLK); add('Y0', 'A'); mv('A', 'X1')
yr('Y0', TI['OUTG']); mpy('X1', 'Y0', 'A'); asl1('A'); mv('A', 'X1')      # out gain
xr('X0', R_DRY); mv('X1', 'A'); sub('X0', 'A'); mv('A', 'Y0')              # wet / dry
ldl(RP + 1, 'Y1'); mv('X0', 'B'); mac('Y0', 'Y1', 'B'); mv('B', 'X1')
rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal.py runs past P:%04X: %X' % (END, end)
VOX_INIT, FX_VOX, FX_RADIO = a.labels['vox_init'], a.labels['fx_vox'], a.labels['fx_radio']
# external SRAM tables (vocal_tab.hex, loaded by `boot`): RADIO's 6 mode tables, then VOX's coefficients
TAB = [w for m in range(len(rm.MODES)) for w in rm.mode_table(m)] + [w & 0xFFFFFF for w in vm.coef_words()]
assert RTAB + len(TAB) <= 0x03D000
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  vox_init=%04X fx_vox=%04X' % (len(words), end, VOX_INIT, FX_VOX))
    a.hexfile(os.path.join(HERE, 'vocal.hex'))
    _t = os.path.join(HERE, 'vocal_tab.hex')                               # atomic, like Asm.hexfile
    open(_t + '.%d' % os.getpid(), 'w').write('%X\n%s\n' % (RTAB, ' '.join('%06X' % w for w in TAB)))
    os.replace(_t + '.%d' % os.getpid(), _t)
    print('vocal_tab.hex: %d words at X:%06X  fx_radio=%04X' % (len(TAB), RTAB, FX_RADIO))
