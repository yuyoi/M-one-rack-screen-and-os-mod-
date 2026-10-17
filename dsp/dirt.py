"""DIRT: the dirt-pedal engine, effect id 17 (PEDAL board). Writes dirt.hex (P:$0E00). Every dirt pedal (TS808, SD-1,
Klon, RAT, DS-1, Big Muff, Metal Muff, Metal Zone, Fuzz Face, Funeral, Iron Man, amp RADIO) is a set of param words
and curve tables for this one program. Reference model: model/dirt_ref.py (same steps, same scaling); circuit models:
model/dirt_model.py; test: model/sim_dirt.py (bit-exact).

fx_dirt: sample in X1 -> out in X1, like every effect. First call: clears its state, copies the 4x FIR coefficients
from AMP's SRAM table (loaded at boot) into Y:$0D00. Params and curves come from the ESP (a pedal = writes); with
NST = 0 (nothing written yet) it passes the input through.
Uses R0-R6 / M1-M3, M6 and puts the M registers back to linear before it returns.

Memory (PROPOSED to the FX lab, not agreed yet): P $0E00-$0FFF, X $0900-$0D03, Y $0D00-$0D5F.
  X:$0900 params (64, layout in dirt_ref.py)   X:$0940 state   X:$0980 upsampler ring (mod 16)
  X:$0990 dry delay ring (mod 16)               X:$09C0 decimator ring (mod 64)   X:$0A00-$0D02 3 x 257 curves
Cycles: sim56 instructions per frame printed by model/sim_dirt.py (1 stage ~300, 3 stages ~600).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, ea, encode  # noqa: E402
from asmh import H, MAC, MPY  # noqa: E402
from dis56k import listing  # noqa: E402
import dirt_ref as DR  # noqa: E402

BASE, END = 0x0E00, 0x0FFF
AMP_FIR = 0x031C00 + 512                       # AMP's SRAM table: IR (512), then 48 + 48 FIR words
PAR, ST, UPX, DNX, FIRY = DR.PAR, DR.ST, DR.UPX, DR.DNX, DR.FIRY
DRYX = 0x0990
DCX, DCY, S_PRE, RUP, RDN, RDRY, DRYD = ST + 0, ST + 1, ST + 2, ST + 6, ST + 7, ST + 8, ST + 9
S_STG, S_TONE, INITF = ST + 12, ST + 24, ST + 63      # stages 3 x 4 (HPX HPY LPY ENV), tone 3 x 4 (x1 x2 y1 y2)
MAGIC = 0x2D1D7E
P_NST, P_NT, P_DC, P_PG, P_BL, P_LV = (PAR + DR.P_NST, PAR + DR.P_NT, PAR + DR.P_DC, PAR + DR.P_PG, PAR + DR.P_BL,
                                       PAR + DR.P_LV)
P_PRE, P_PRED, P_STG, P_TONE = PAR + DR.P_PRE, PAR + DR.P_PRED, PAR + DR.P_STG, PAR + DR.P_TONE
DRY_N = (16 - 11) % 16                          # dry ring read offset: 11 samples back (the FIRs' group delay)

a = Asm(BASE)
h = H(a)


def X(e, reg, W=1):                            # X:ea <-> reg as a parallel move
    return ('Movex_ea', dict(W=W, d=R5[reg], **ea(e)))


def alu_mac(s1, s2, d, k=0, r=False):
    n, f = MAC(s1, s2, d, k)
    return ('Macr_S1S2' if r else n, f)


def do_reg(reg, end):                          # DO reg,end
    a.word(encode('Do_S', D=R6[reg]))
    a.fix.append((len(a.w), end, 'do'))
    a.w.append(0)


def fir(n, acc='A', xreg=2, yreg=0):           # n taps: X:(Rx)- newest first, Y:(Ry)+ coefficients, rounded
    xy = dict(W=1, w=1, e=0, f=0, M=2, R=xreg, m=3, r=yreg)
    a.par(alu=('Clr', dict(d='AB'.index(acc))), move=('Movexy', xy))
    h.rep(n - 1)
    a.par(alu=MAC('X0', 'Y0', acc), move=('Movexy', xy))
    a.par(alu=('Macr_S1S2', MAC('X0', 'Y0', acc)[1]))


# ======================================================================== fx_dirt
a.label('fx_dirt')
h.ldl(INITF, 'A'); h.cmpi(MAGIC, 'A'); h.j('EQ', 'go')
a.jsr('init')
a.label('go')
h.ldl(P_NST, 'A'); h.tst('A'); h.j('NE', 'run')
h.rts()                                        # nothing written yet: X1 passes through
a.label('run')
# ---- input DC blocker: y = x - xprev + R*yprev (x in X1); dcy = sat(y) = the dry signal
h.mv('X1', 'A')
h.ldl(DCX, 'X0'); h.sub('X0', 'A')
h.stl('X1', DCX)
h.ldl(DCY, 'X0'); h.ldl(P_DC, 'Y0'); h.mac('X0', 'Y0', 'A')
h.stl('A', DCY)
# ---- dry delay: write at (R3), read 11 back (R3+N3, modulo 16)
h.movec('M3', 15)
h.ldl(RDRY, 'R3')
h.li('N3', DRY_N)
h.nop()
h.stxi('A', '(R3)')
h.ldxi('(R3+N3)', 'X0')
h.ldxi('(R3)+', 'Y0')                          # dummy read: post-increment wraps with M3
h.stl('X0', DRYD)
h.stl('R3', RDRY)
h.movec('M3', 0xFFFFFF)
# ---- pre-EQ biquad + PREDRY * x
h.mv('A', 'X0')
h.li('R5', P_PRE); h.li('R0', S_PRE)
a.jsr('bq')
h.ldl(DCY, 'X1'); h.ldl(P_PRED, 'Y0'); h.mac('X1', 'Y0', 'A')
h.mv('A', 'X0')
# ---- 4x upsample (newest at (R1)), stages at 4x, decimator history (R6)
h.movec('M1', 15); h.movec('M2', 15); h.movec('M6', 63)
h.ldl(RUP, 'R1')
h.ldl(RDN, 'R6')
h.ldl(P_NST, 'N0')
h.li('R4', FIRY)
h.stxi('X0', '(R1)')
a.do(4, 'os_end')
h.mv('R1', 'R2')
h.li('R0', S_STG)
fir(12)
h.li('R5', P_STG)
do_reg('N0', 'st_end')
# stage: params (R5)+ HPK HPP C1 C2N BIAS KB EC TAB, state (R0)+ HPX HPY LPY ENV; A = input (full accumulator)
a.par(alu=('Tfr', dict(J=0, d=1)), move=X('(R0)', 'X0'))                    # tfr a,b      x:(r0),x0   (hpx)
h.ldxi('(R5)+', 'Y0')                                                       # hpk
a.par(alu=MAC('X0', 'Y0', 'A', k=1), move=X('(R0)+', 'B', W=0))             # a -= hpk hpx ; hpx = sat(in)
h.ldxi('(R0)', 'X0')                                                        # hpy
h.ldxi('(R5)+', 'Y0')                                                       # hpp
a.par(alu=alu_mac('X0', 'Y0', 'A', r=True), move=X('(R5)+', 'Y1'))          # v = rnd(a + hpp hpy) ; y1 = c1
h.mv('A', 'X0')
a.par(alu=MPY('X0', 'Y1', 'A'), move=X('(R0)+', 'A', W=0))                  # hpy = sat(v) ; a = c1 v
h.asl(8, 'A')
h.ldxi('(R0)', 'X0')                                                        # lpy
h.ldxi('(R5)+', 'Y0')                                                       # c2n
a.par(alu=alu_mac('X0', 'Y0', 'A', r=True), move=X('(R5)+', 'X1'))          # a = rnd(c1 v 256 + c2n lpy) ; bias
h.stxi('A', '(R0)+')                                                        # lpy = sat(a)
a.par(alu=('Add_SD', dict(J=6, d=0)), move=X('(R0)', 'X1'))                 # a += bias ; x1 = env
h.ldxi('(R5)+', 'Y0')                                                       # kb
a.par(alu=MAC('X1', 'Y0', 'A', k=1), move=X('(R5)+', 'Y1'))                 # a -= kb env ; y1 = ec
h.mv('A', 'X0')                                                             # u = sat
h.mv('X0', 'B'); h.abs_('B')
h.sub('X1', 'B')                                                            # |u| - env
h.mv('B', 'Y0')
h.mpy('Y0', 'Y1', 'B')
a.par(alu=('Add_SD', dict(J=6, d=1)), move=X('(R5)+', 'R3'))                # env' ; r3 = curve
h.stxi('B', '(R0)+')                                                        # env = sat
h.mv('X0', 'B')                                                             # curve: index = top 8 bits of u + 1
h.eori(0x800000, 'B')
h.lsr(16, 'B')
h.mv('B1', 'N3')
h.mv('X0', 'A')
h.andi(0x00FFFF, 'A')
h.lsl(7, 'A')                                                               # A1 = frac
h.lua(3, 'R3')                                                              # r3 = curve + index
h.mv('A1', 'X1')
h.ldxi('(R3)+', 'Y0')                                                       # t0
h.ldxi('(R3)', 'B')                                                         # t1
h.sub('Y0', 'B')
h.mv('B', 'Y1')                                                             # d = sat(t1 - t0)
h.mpy('X1', 'Y1', 'A')
h.add('Y0', 'A')                                                            # a = t0 + frac d
a.label('st_end')
h.stxi('A', '(R6)+')
a.label('os_end')
h.ldxi('(R1)+', 'X0')                          # next write slot (dummy read, wraps with M1)
h.stl('R1', RUP)
h.stl('R6', RDN)
# ---- decimate: 48 taps over the newest 4x samples
h.movec('M2', 63)
h.mv('R6', 'R2')
h.nop()
h.ldxi('(R2)-', 'X0')                          # newest = the slot before the write pointer
h.li('R4', FIRY + 48)
h.nop()
fir(48)
# ---- PG * clipped + BL * dry, tone sections, level
h.mv('A', 'X0'); h.ldl(P_PG, 'Y0'); h.mpy('X0', 'Y0', 'A')
h.ldl(DRYD, 'X1'); h.ldl(P_BL, 'Y0'); h.mac('X1', 'Y0', 'A')
h.mv('A', 'X0')
h.li('R5', P_TONE); h.li('R0', S_TONE)
h.ldl(P_NT, 'N0')
h.nop()
do_reg('N0', 't_end')
a.jsr('bq')
h.nop()                                        # a JSR can't end a DO loop
a.label('t_end')
h.ldl(P_LV, 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(DR.LV_SHIFT, 'A')
h.mv('A', 'X1')
for m in ('M1', 'M2', 'M6'):
    h.movec(m, 0xFFFFFF)
h.rts()

# ======================================================================== bq: biquad /2, DF1, rounded
# X0 = x in; coefficients (R5)+ b0 b1 b2 -a1 -a2; state (R0)+ x1 x2 y1 y2. Out: A = full, X0 = sat, R0/R5 advanced.
a.label('bq')
h.ldxi('(R5)+', 'Y0')                                                       # b0
a.par(alu=MPY('X0', 'Y0', 'A'), move=X('(R0)+', 'X1'))                      # a = b0 x ; x1 = x1s
h.ldxi('(R5)+', 'Y0')                                                       # b1
a.par(alu=MAC('X1', 'Y0', 'A'), move=X('(R0)-', 'Y1'))                      # += b1 x1s ; y1 = x2s
h.ldxi('(R5)+', 'Y0')                                                       # b2
a.par(alu=MAC('Y1', 'Y0', 'A'), move=X('(R0)+', 'X0', W=0))                 # += b2 x2s ; x1 slot = x
h.stxi('X1', '(R0)+')                                                       # x2 slot = x1s
h.ldxi('(R0)+', 'X1')                                                       # x1 = y1s
h.ldxi('(R5)+', 'Y0')                                                       # -a1
a.par(alu=MAC('X1', 'Y0', 'A'), move=X('(R0)-', 'Y1'))                      # += -a1 y1s ; y1 = y2s
h.ldxi('(R5)+', 'Y0')                                                       # -a2
a.par(alu=alu_mac('Y1', 'Y0', 'A', r=True))                                 # += -a2 y2s, rounded
h.asl1('A')
h.stxi('A', '(R0)+')                                                        # y1 slot = sat(y)
h.stxi('X1', '(R0)+')                                                       # y2 slot = y1s
h.mv('A', 'X0')
h.rts()

# ======================================================================== init (first call)
a.label('init')
h.li('R1', ST); h.clr('A')
h.rep(0x0A00 - ST)                             # state + rings: X:$0940-$09FF
h.stxi('A', '(R1)+')
h.li('R1', AMP_FIR); h.li('R4', FIRY)
a.do(96, 'cp_end')
h.ldxi('(R1)+', 'A')
h.styi('A', '(R4)+')
a.label('cp_end')
h.li('A', UPX); h.stl('A', RUP)
h.li('A', DNX); h.stl('A', RDN)
h.li('A', DRYX); h.stl('A', RDRY)
h.li('A', MAGIC); h.stl('A', INITF)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'DIRT runs past its P space: %X' % end
FX_DIRT = a.labels['fx_dirt']

if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d  end=P:%04X  labels=%s' % (len(words), end, {k: '%04X' % v for k, v in a.labels.items()}))
    a.hexfile(os.path.join(HERE, 'dirt.hex'))
