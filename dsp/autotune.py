"""Autotune for the M-One DSP56362 (mirrors dsp/model/autotune_model.py). Writes autotune.hex.

fx_tune: X1 in -> X1 out (drop-in FX module). tune_init: clears buffers/state.
  shifter : 4096-word ring X:$030000 (SRAM), 2 heads W/2 apart over W=2048, triangle crossfade, linear interp
  detector: 4x decimation into X:/Y:$0400-$07FF (mirrored ring, modulo M=$3FF), AMDF NWIN=256 over lags 8..140,
            one lag per frame, YIN-style threshold on cumulative D, parabolic refine (restoring division)
  snap    : period -> nearest note (table, MIDI 36..88), then the ESP's scale snap map X:$23-$2E (semitone offset per
            pitch class, 0 = chromatic), ratio error e = (P - Pt)/Pt, retune smoothing, shifter rate = -e/W
Params (X short): $0B retune speed (Q23, per frame), $23-$2E snap map. Readouts: $0D period (Q23 of /256), $0E note.
"""
import os
import sys
import math
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, EA_ABS, EA_IMM, ea  # noqa: E402
from dis56k import listing  # noqa: E402

BASE = 0x400
FS, DEC = 44100, 4
FSD = FS // DEC
NWIN, TMIN, TMAX, HOPN = 256, 8, 140, 128
K = TMAX - TMIN + 1
TH = int(0.25 * (1 << 23))
MINCUM = int(0.0005 * (1 << 23))
N_HI, N_LO = 88, 36
NN = N_HI - N_LO + 1
SPEED = int(0.002 * (1 << 23))       # retune per frame (~11 ms): robotic-ish; 0.0002 = natural
RING, DARR, SHBUF = 0x0400, 0x0800, 0x030000

# X short state
W_, D_, ACC, PH, IDX, ST, HOP, TAU, BS, ET, ES, SPD, _, PF, NOTE, _V, CUM, FOUND, BK, BD, LOCK, OUT, T1, DT, T2 = range(25)
SNAP = 0x23

a = Asm(BASE)
J12 = {'other': 1, 'X': 2, 'Y': 3, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}      # ADD/SUB (table 12-13)
J16 = {'other': 0, 'X0': 4, 'Y0': 5, 'X1': 6, 'Y1': 7}                       # CMP (table 12-16)
QQQ = ['X0,X0', 'Y0,Y0', 'X1,X0', 'Y1,Y0', 'X0,Y1', 'Y0,X0', 'X1,Y0', 'Y1,X1']
QI = {'X0': 0, 'Y0': 1, 'X1': 2, 'Y1': 3}


def D(acc): return 'AB'.index(acc)
def src(s, acc): return 'other' if s in ('A', 'B') else s
def mv(s, d): a.par(move=('Mover', dict(e=R5[s], d=R5[d])))
def ldx(aa, reg): a.par(move=('Movex_aa', dict(W=1, a=aa, d=R5[reg])))
def stx(reg, aa): a.par(move=('Movex_aa', dict(W=0, a=aa, d=R5[reg])))
def li(reg, v): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **EA_IMM)), ext=v)
def ldxi(e, reg): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **ea(e))))
def stxi(reg, e): a.par(move=('Movex_ea', dict(W=0, d=R5[reg], **ea(e))))
def styi(reg, e): a.par(move=('Movey_ea', dict(W=0, d=R5[reg], **ea(e))))
def add(s, d): a.par(alu=('Add_SD', dict(J=J12[src(s, d)], d=D(d))))
def sub(s, d): a.par(alu=('Sub_SD', dict(J=J12[src(s, d)], d=D(d))))
def cmp(s, d): a.par(alu=('Cmp_S1S2', dict(J=J16[src(s, d)], d=D(d))))   # flags of d - s
def tst(d): a.par(alu=('Tst', dict(d=D(d))))
def clr(d): a.par(alu=('Clr', dict(d=D(d))))
def neg(d): a.par(alu=('Neg', dict(d=D(d))))
def abs_(d): a.par(alu=('Abs', dict(d=D(d))))
def asl1(d): a.par(alu=('Asl_D', dict(d=D(d))))
def andr(s, d): a.par(alu=('And_SD', dict(J=QI[s], d=D(d))))
def mpy(s1, s2, d, k=0):
    q = QQQ.index('%s,%s' % (s1, s2)) if '%s,%s' % (s1, s2) in QQQ else QQQ.index('%s,%s' % (s2, s1))
    a.par(alu=('Mpy_S1S2D', dict(Q=q, d=D(d), k=k)))
def mpyi(v, s, d, k=0): a.op('Mpyi', ext=v, q=QI[s], d=D(d), k=k)
def addi(v, d):
    if 0 <= v < 64: a.op('Add_xx', i=v, d=D(d))
    else: a.op('Add_xxxx', ext=v, d=D(d))
def subi(v, d):
    if 0 <= v < 64: a.op('Sub_xx', i=v, d=D(d))
    else: a.op('Sub_xxxx', ext=v, d=D(d))
def cmpi(v, d):
    if 0 <= v < 64: a.op('Cmp_xxS2', i=v, d=D(d))
    else: a.op('Cmp_xxxxS2', ext=v, d=D(d))
def andi(v, d): a.op('And_xxxx', ext=v, d=D(d))
def ori(v, d): a.op('Or_xxxx', ext=v, d=D(d))
def asl(n, d): a.op('Asl_ii', S=D(d), i=n, D=D(d))
def asr(n, d): a.op('Asr_ii', S=D(d), i=n, D=D(d))
def lsl(n, d): a.op('Lsl_ii', i=n, D=D(d))
def lsr(n, d): a.op('Lsr_ii', i=n, D=D(d))
def movec(ctrl, v): a.op('Movec_ea', ext=v, W=1, S=0, D=C5[ctrl], **EA_IMM)
def movem_ld(e, reg): a.op('Movem_ea', W=1, d=R6[reg], **ea(e))
def nop(): a.word(0)
def rts(): a.word(0x00000C)
def j(c, lbl): a.jshort(c, lbl)


# ============================================================ tables (P memory, read with MOVEM)
def q23(x): return max(-(1 << 23), min((1 << 23) - 1, int(round(x * (1 << 23))))) & 0xFFFFFF
notes = list(range(N_HI, N_LO - 1, -1))                 # i = 0 -> highest note (smallest period)
per = [FSD / (440 * 2 ** ((n - 69) / 12)) for n in notes]
TAB_U = [q23(p * 2 ** (1 / 24) / 256) for p in per]      # upper bound of each note's period band
TAB_P = [q23(p / 256) for p in per]
TAB_R = [q23(8 / p) for p in per]                        # 8/Pt (< 1 for Pt > 8)
TAB_PC = [n % 12 for n in notes]

# ============================================================ test harness main (standalone)
a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)
a.op('Movec_xx', i=0, D=C5['SP'])
for m in range(8):
    movec('M%d' % m, 0xFFFFFF)
a.jsr('tune_init')
a.label('main')
a.op('Jclr_qq', label='main', q=0x33, S=0, b=8)                 # wait RDF
a.op('Movep_SXqq', W=0, d=R6['X1'], q=0x29)                     # x1 = RX1
a.op('Jset_qq', label='m_left', q=0x33, S=0, b=6)                # RFS -> left slot
ldx(0x30, 'A'); add('X1', 'A'); mv('A', 'X1')                    # mono = L + R
a.jsr('fx_tune')
stx('X1', 0x31)
a.op('Movep_SXqq', W=1, d=R6['X1'], q=0x21)
a.jmp('main')
a.label('m_left')
stx('X1', 0x30); ldx(0x31, 'X1')
a.op('Movep_SXqq', W=1, d=R6['X1'], q=0x21)
a.jmp('main')

# ============================================================ tune_init
a.label('tune_init')
clr('A')
for v in range(0x00, 0x20): stx('A', v)
for v in range(SNAP, SNAP + 12): stx('A', v)
li('A', SPEED); stx('A', SPD)
clr('A')
li('R1', RING); li('B', 1024)
a.label('ti_ring')
stxi('A', '(R1)'); styi('A', '(R1)+'); subi(1, 'B'); j('NE', 'ti_ring')
li('R1', SHBUF); li('B', 4096)
a.label('ti_buf')
stxi('A', '(R1)+'); subi(1, 'B'); j('NE', 'ti_buf')
li('N2', 2)
rts()

# ============================================================ fx_tune (X1 in -> X1 out)
a.label('fx_tune')
# --- shifter write: buf[w] = x
ldx(W_, 'A'); ori(SHBUF, 'A'); mv('A1', 'R5'); nop(); stxi('X1', '(R5)')
# --- decimation: acc += x >> 11 ; every 4th sample -> ring
mv('X1', 'B'); asr(11, 'B'); ldx(ACC, 'A'); add('B', 'A'); stx('A', ACC)
ldx(PH, 'A'); addi(1, 'A'); cmpi(4, 'A'); j('NE', 'dec_ph')
ldx(IDX, 'A'); ori(RING, 'A'); mv('A1', 'R1'); nop()
ldx(ACC, 'X0'); stxi('X0', '(R1)'); styi('X0', '(R1)')
ldx(IDX, 'A'); addi(1, 'A'); andi(0x3FF, 'A'); stx('A1', IDX)
clr('A'); stx('A', ACC); stx('A', PH)
ldx(HOP, 'A'); addi(1, 'A'); stx('A1', HOP)
j('T', 'dec_done')
a.label('dec_ph')
stx('A1', PH)
a.label('dec_done')

# --- detector state machine
ldx(ST, 'A'); tst('A'); j('NE', 'st_nz')
ldx(HOP, 'A'); cmpi(HOPN, 'A'); j('LT', 'det_done')       # state 0: wait for a hop
clr('B'); stx('B', HOP); stx('B', CUM); stx('B', FOUND); stx('B', LOCK)
ldx(IDX, 'A'); subi(NWIN + TMAX, 'A'); andi(0x3FF, 'A'); stx('A1', BS)
li('A', TMIN); stx('A1', TAU)
li('A', 1); stx('A1', ST)
j('T', 'det_done')

a.label('st_nz')
cmpi(1, 'A'); j('NE', 'st_eval')
# state 1: one AMDF lag per frame
ldx(BS, 'A'); ori(RING, 'A'); mv('A1', 'R0')
ldx(BS, 'A'); ldx(TAU, 'X0'); add('X0', 'A'); andi(0x3FF, 'A'); ori(RING, 'A'); mv('A1', 'R4')
movec('M0', 0x3FF); movec('M4', 0x3FF)
clr('A')
a.do(NWIN, 'amdf_end')
a.par(move=('Movexy', dict(W=1, w=1, e=3, f=0, M=3, R=0, m=3, r=0)))   # B = X:(R0)+ ; Y0 = Y:(R4)+
sub('Y0', 'B')
abs_('B')
add('B', 'A')
a.label('amdf_end')
movec('M0', 0xFFFFFF); movec('M4', 0xFFFFFF)
ldx(TAU, 'B'); subi(TMIN, 'B'); ori(DARR, 'B'); mv('B1', 'R2'); nop()
stxi('A', '(R2)')                                   # D[k]
mv('A', 'X0')
mv('X0', 'B'); asr(8, 'B'); ldx(CUM, 'Y1'); add('Y1', 'B'); stx('B', CUM)
ldx(FOUND, 'A'); tst('A'); j('NE', 'sw_found')
ldx(TAU, 'A'); subi(TMIN - 1, 'A'); asl(15, 'A'); mv('A1', 'Y0')   # (k+1)/256
mpy('X0', 'Y0', 'A')                                 # lhs = D*(k+1)/256
ldx(CUM, 'Y1'); mpyi(TH, 'Y1', 'B')                  # rhs = th*cum/256
cmp('A', 'B'); j('LE', 'sw_next')                    # rhs - lhs <= 0 -> not below threshold
li('A', 1); stx('A1', FOUND); ldx(TAU, 'A'); stx('A1', BK); stx('X0', BD)
j('T', 'sw_next')
a.label('sw_found')
ldx(LOCK, 'A'); tst('A'); j('NE', 'sw_next')
ldx(BD, 'A'); mv('X0', 'B'); cmp('A', 'B'); j('GE', 'sw_lock')      # D >= best -> lock
ldx(TAU, 'A'); stx('A1', BK); stx('X0', BD)
j('T', 'sw_next')
a.label('sw_lock')
li('A', 1); stx('A1', LOCK)
a.label('sw_next')
ldx(TAU, 'A'); addi(1, 'A'); stx('A1', TAU); cmpi(TMAX, 'A'); j('LE', 'det_done')
li('A', 2); stx('A1', ST)
j('T', 'det_done')

# state 2: evaluate
a.label('st_eval')
clr('B'); stx('B', ST)
ldx(FOUND, 'A'); tst('A'); j('EQ', 'det_done')
ldx(CUM, 'A'); cmpi(MINCUM, 'A'); j('LT', 'det_done')
ldx(BK, 'A'); subi(TMIN, 'A'); ori(DARR, 'A'); mv('A1', 'R2'); nop()
ldxi('(R2)-', 'Y0'); ldxi('(R2)', 'X0'); ldxi('(R2+N2)', 'X1')     # b = D[k], a = D[k-1], c = D[k+1]
mv('X0', 'A'); sub('X1', 'A')                                       # num = a - c
mv('X0', 'B'); add('X1', 'B'); sub('Y0', 'B'); sub('Y0', 'B')       # den = a - 2b + c
tst('B'); j('LE', 'off_zero')
asr(3, 'A'); asr(2, 'B'); mv('B', 'X1')                             # num/8, den/4
stx('A', T1); abs_('A')
cmp('X1', 'A'); j('GE', 'off_zero')                                 # |num/8| >= den/4 -> no refine
clr('B')
a.do(23, 'div_end')
asl1('A'); asl1('B')
cmp('X1', 'A'); j('LT', 'div_skip')
sub('X1', 'A'); addi(1, 'B')
a.label('div_skip')
nop()
a.label('div_end')
ldx(T1, 'A'); tst('A'); j('GE', 'off_pos')
neg('B')
a.label('off_pos')
asr(8, 'B')                                                          # off/256
ldx(BK, 'A'); asl(15, 'A'); add('B', 'A'); stx('A1', PF)
j('T', 'snap')
a.label('off_zero')
ldx(BK, 'A'); asl(15, 'A'); stx('A1', PF)
a.label('snap')
li('R3', 0); a.w[-1] = 0                                            # placeholder replaced below
a.w.pop(); a.w.pop()
a.op('Movex_ea', label='tab_u', W=1, d=R5['R3'], **EA_IMM)          # r3 = tab_u
ldx(PF, 'X0')
a.label('scan')
movem_ld('(R3)+', 'A'); cmp('X0', 'A'); j('GE', 'scan_hit')        # U[i] >= Pf -> note i
mv('R3', 'B'); a.op('Cmp_xxxxS2', label='tab_u_end', d=1); j('LT', 'scan')
a.label('scan_hit')
mv('R3', 'A'); a.op('Sub_xxxx', label='tab_u1', d=0)               # i = r3 - (tab_u + 1)
tst('A'); j('GE', 'i_ok')
clr('A')
a.label('i_ok')
cmpi(NN - 1, 'A'); j('LE', 'i_ok2')
li('A', NN - 1)
a.label('i_ok2')
stx('A1', T2)
# scale: off = snap[pc(i)], i_sel = i - off
a.op('Add_xxxx', label='tab_pc', d=0); mv('A1', 'R3'); nop()
movem_ld('(R3)', 'A'); addi(SNAP, 'A'); mv('A1', 'R3'); nop()
ldxi('(R3)', 'X0')
ldx(T2, 'A'); sub('X0', 'A')
tst('A'); j('GE', 's_ok'); clr('A')
a.label('s_ok')
cmpi(NN - 1, 'A'); j('LE', 's_ok2'); li('A', NN - 1)
a.label('s_ok2')
stx('A1', T2)
# note readout = N_HI - i
li('B', N_HI); sub('A', 'B'); stx('B1', NOTE)
# Pt and 8/Pt
ldx(T2, 'A'); a.op('Add_xxxx', label='tab_p', d=0); mv('A1', 'R3'); nop()
movem_ld('(R3)', 'X0')
ldx(T2, 'A'); a.op('Add_xxxx', label='tab_r', d=0); mv('A1', 'R3'); nop()
movem_ld('(R3)', 'Y0')
ldx(PF, 'A'); sub('X0', 'A'); mv('A', 'X1')                          # Pf - Pt
mpy('X1', 'Y0', 'A'); asl(5, 'A')                                    # e = (Pf-Pt)*(8/Pt)*32
cmpi(0x200000, 'A'); j('LE', 'e_hi'); li('A', 0x200000)
a.label('e_hi')
a.op('Cmp_xxxxS2', ext=0xE00000, d=0); j('GE', 'e_lo'); li('A', 0xE00000)
a.label('e_lo')
stx('A', ET)
a.label('det_done')

# --- retune: es += spd*(et - es)
ldx(ET, 'A'); ldx(ES, 'X0'); sub('X0', 'A'); mv('A', 'X1')
ldx(SPD, 'Y1'); mpy('X1', 'Y1', 'A'); add('X0', 'A'); stx('A', ES)
# --- d += -es/W
neg('A'); asr(11, 'A'); ldx(D_, 'B'); add('A', 'B'); andi(0x7FFFFF, 'B'); stx('B1', D_)
clr('A'); stx('A', OUT)


def head():
    ldx(DT, 'A'); lsr(12, 'A')                                          # di
    ldx(W_, 'B'); sub('A', 'B'); andi(0xFFF, 'B'); ori(SHBUF, 'B'); mv('B1', 'R5')
    ldx(DT, 'A'); andi(0xFFF, 'A'); lsl(11, 'A'); mv('A1', 'Y1')        # df
    ldxi('(R5)', 'X0')                                                  # b0
    subi(1, 'B'); andi(0xFFF, 'B'); ori(SHBUF, 'B'); mv('B1', 'R5'); nop()
    ldxi('(R5)', 'X1')                                                  # b1
    mv('X1', 'A'); sub('X0', 'A'); mv('A', 'X1')
    mpy('X1', 'Y1', 'A'); add('X0', 'A'); mv('A', 'X1')                 # s
    ldx(DT, 'A'); subi(0x400000, 'A'); abs_('A'); neg('A'); addi(0x400000, 'A'); asl1('A'); mv('A', 'Y0')  # g
    mpy('X1', 'Y0', 'A'); ldx(OUT, 'X0'); add('X0', 'A'); stx('A', OUT)


ldx(D_, 'A'); stx('A1', DT); head()
ldx(D_, 'A'); addi(0x400000, 'A'); andi(0x7FFFFF, 'A'); stx('A1', DT); head()
ldx(W_, 'A'); addi(1, 'A'); andi(0xFFF, 'A'); stx('A1', W_)
ldx(OUT, 'X1')
rts()

# ============================================================ tables
a.label('tab_u')
for v in TAB_U: a.word(v, note='data')
a.label('tab_u_end')
a.label('tab_p')
for v in TAB_P: a.word(v, note='data')
a.label('tab_r')
for v in TAB_R: a.word(v, note='data')
a.label('tab_pc')
for v in TAB_PC: a.word(v, note='data')
a.labels['tab_u1'] = a.labels['tab_u'] + 1

words = a.link()
end = BASE + len(words) - 1
assert end <= 0xBFF, 'past internal P RAM: %X' % end
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  fx_tune=%04X tune_init=%04X tables=%04X' % (
        len(words), end, a.labels['fx_tune'], a.labels['tune_init'], a.labels['tab_u']))
    a.hexfile(os.path.join(HERE, 'autotune.hex'))
