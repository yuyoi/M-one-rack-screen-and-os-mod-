"""SPRING: two-spring reverb tank, effect id 21 (PEDAL board). Writes spring.hex. Reference: model/spring_ref.py
(same steps); test: model/sim_spring.py (bit-exact).

fx_spring: sample in X1 -> out in X1. First call: clears its state and both rings. The ESP writes the params when the
pedal is picked (nothing written: MIX = DRY = 0, silence).
Uses R0, R2, R4, R5, M2 (put back to linear).
Memory (PROPOSED, NOT agreed with the FX lab): P $0960-$09FF (the test-program area: cycprobe / ms_on would move),
X $0888-$08DF, rings X:$038000-$038FFF (REVERB's buffer: never in one chain with REVERB).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, ea  # noqa: E402
from asmh import H, MAC  # noqa: E402
from dis56k import listing  # noqa: E402
import spring_ref as SR  # noqa: E402

BASE, END = 0x0960, 0x09FF
PS, SS = SR.PS, SR.SS
S_X, S_U, S_ACC, INITF = SS + 4, SS + 5, SS + 6, SS + 7
MAGIC = 0x5B0196

a = Asm(BASE)
h = H(a)


def macr(s1, s2, d, k=0):
    return ('Macr_S1S2', MAC(s1, s2, d, k)[1])


a.label('fx_spring')
h.ldl(INITF, 'A'); h.cmpi(MAGIC, 'A'); h.j('EQ', 'go')
a.jsr('init')
a.label('go')
# ---- dwell: u = sat(x DWELL 8), u = u + (u - u^3) / 2
h.stl('X1', S_X)
h.mv('X1', 'X0'); h.ldl(PS + 0, 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(3, 'A')
h.mv('A', 'X0')
h.mpy('X0', 'X0', 'A'); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A')
h.mv('X0', 'B'); h.sub('A', 'B'); h.asr(1, 'B'); h.add('X0', 'B')
h.stl('B', S_U)
h.clr('A'); h.stl('A', S_ACC)
h.movec('M2', SR.RLEN - 1)
h.li('R5', PS + 8); h.li('R4', SS + 2); h.li('R0', SS + 8)
h.li('N0', 4); h.li('N5', 4)
a.do(2, 'sp_end')
# ring: r2 = base + WP, z = (r2 - L)
h.xr('A', 2, R=5); h.ldl(SS + 0, 'X0'); h.add('X0', 'A'); h.mv('A', 'R2')
h.xr('B', 0, R=5); h.neg('B'); h.mv('B1', 'N2')
h.nop()
h.ldxi('(R2+N2)', 'B')                                            # z
h.ldl(S_ACC, 'X0'); h.add('X0', 'B'); h.stl('B', S_ACC)           # acc += z (sat after spring 1: z alone)
h.ldxi('(R2+N2)', 'B')
h.ldxi('(R4)', 'X1'); h.sub('X1', 'B'); h.mv('B', 'Y0')           # sat(z - lp)
h.mv('X1', 'A'); h.ldl(PS + 2, 'X0'); a.par(alu=macr('X0', 'Y0', 'A'))
h.stxi('A', '(R4)+')                                              # lp = rnd(lp + KD sat(z - lp))
h.mv('A', 'X0'); h.ldl(S_U, 'A'); h.ldl(PS + 1, 'Y0'); h.mac('X0', 'Y0', 'A')
h.mv('A', 'X1')                                                   # v = sat(u + FB lp)
h.xr('Y1', 1, R=5)                                                # a
a.do(SR.NAP, 'ap_end')
h.mv('X1', 'B'); h.xr('Y0', 3, R=0); h.sub('Y0', 'B'); h.mv('B', 'Y0')   # sat(v - y2)
h.xr('A', 1, R=0); a.par(alu=macr('Y1', 'Y0', 'A'))               # y = rnd(x2 + a sat(v - y2))
h.xr('X0', 0, R=0); h.xw('X0', 1, R=0)                            # x2 = x1
h.xw('X1', 0, R=0)                                                # x1 = v
h.xr('X0', 2, R=0); h.xw('X0', 3, R=0)                            # y2 = y1
h.xw('A', 2, R=0)                                                 # y1 = sat(y)
h.mv('A', 'X1')                                                   # v = sat(y)
h.lua(0, 'R0')                                                    # next stage: r0 += 4
a.label('ap_end')
h.stxi('X1', '(R2)')                                              # ring in
h.lua(5, 'R5')                                                    # next spring's params (n5 = 4)
a.label('sp_end')
h.movec('M2', 0xFFFFFF)
h.ldl(SS + 0, 'A'); h.addi(1, 'A'); h.andi(SR.RLEN - 1, 'A'); h.stl('A1', SS + 0)   # WP += 1 (mod 2048)
# ---- tone LP, out = DRY x + MIX tone
h.ldl(S_ACC, 'B'); h.ldl(SS + 1, 'X1'); h.sub('X1', 'B'); h.mv('B', 'Y0')
h.mv('X1', 'A'); h.ldl(PS + 3, 'X0'); a.par(alu=macr('X0', 'Y0', 'A'))
h.stl('A', SS + 1)
h.ldl(SS + 1, 'X0'); h.ldl(PS + 4, 'Y0'); h.mpy('X0', 'Y0', 'A')
h.ldl(S_X, 'X0'); h.ldl(PS + 5, 'Y0'); h.mac('X0', 'Y0', 'A')
h.mv('A', 'X1')
h.rts()

a.label('init')
h.clr('A')
h.li('R0', SS)
h.rep(8 + 64)
h.stxi('A', '(R0)+')
h.li('R0', SR.RINGS[0]); h.li('R2', SR.RINGS[1])
a.do(SR.RLEN, 'clr_end')
h.stxi('A', '(R0)+')
h.stxi('A', '(R2)+')
a.label('clr_end')
h.li('A', MAGIC); h.stl('A', INITF)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'SPRING runs past its P space: %X' % end
FX_SPRING = a.labels['fx_spring']

if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d  end=P:%04X  labels=%s' % (len(words), end, {k: '%04X' % v for k, v in a.labels.items()}))
    a.hexfile(os.path.join(HERE, 'spring.hex'))
