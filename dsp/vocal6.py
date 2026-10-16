"""Vocal effects, part 6 (P:$0060-$00FF, in the unused interrupt vector area): GRAIN (id 16). Writes vocal6.hex.
Mirrors dsp/model/grain_model.py. Ring: REVERSE's buffer X:$020000-$02FFFF (never chain GRAIN with REVERSE).
State X:$03E0 (R3), voice blocks (R2: +0 PH, +1 POS, +2 RATE), params X:$02C0 (R5).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R6  # noqa: E402
from dis56k import listing  # noqa: E402
from asmh import H  # noqa: E402
import grain_model as gm  # noqa: E402

BASE, END = 0x0060, 0x00FF                      # unused vector area (interrupts masked; $0000-$005F left alone)
GBUF, GS, GP = 0x020000, 0x03E0, 0x02C0
(G_W, G_LF, G_ACC, G_DRY) = range(4)
VOICE = (4, 8)

a = Asm(BASE)
h = H(a)
j = h.j

a.label('vocal6_init')
h.clr('A'); h.li('R0', GS); h.rep(12); h.stxi('A', '(R0)+')
h.li('A', 0x3C3C3C); h.stl('A', GS + G_LF)
h.li('A', 0x400000); h.stl('A', GS + VOICE[1])
h.li('A', 1); h.stl('A', GS + VOICE[0] + 2); h.stl('A', GS + VOICE[1] + 2)
for k, v in enumerate(gm.params()):
    h.li('A', v); h.stl('A', GP + k)
h.rts()

# g_voice: R2 = voice block. acc (X:G_ACC) += window * buf[POS]; new grain when the phase wraps
a.label('g_voice')
h.xr('A', 0, R=2); h.xr('Y0', 0, R=5); h.add('Y0', 'A')                    # PH += DPH
a.op('Jclr_S', D=R6['A1'], b=23, label='g_nw')
h.andi(0x7FFFFF, 'A'); h.xw('A1', 0, R=2)
h.xr('A', G_LF); h.lsl1('A'); j('CC', 'g_r'); h.eori(0xC20001, 'A')
a.label('g_r')
h.xw('A1', G_LF); h.mv('A1', 'X0')                                        # r
h.xr('Y0', 2, R=5); h.mv('X0', 'A'); h.andr('Y0', 'A'); h.mv('A1', 'Y0')   # r & RANGE
h.xr('A', G_W); h.xr('X1', 1, R=5); h.sub('X1', 'A'); h.sub('X1', 'A'); h.sub('Y0', 'A')
h.andi(0xFFFF, 'A'); h.xw('A1', 1, R=2)                                    # POS = w - 2L - (r & RANGE)
h.clr('A'); h.xr('B', 3, R=5); h.tst('B'); j('EQ', 'g_r1')
h.mv('X0', 'A'); h.lsr(20, 'A'); h.andi(1, 'A')
a.label('g_r1')
h.addi(1, 'A'); h.xw('A1', 2, R=2); j('T', 'g_go')                        # rate 1, or 2 on a coin flip
a.label('g_nw')
h.xw('A1', 0, R=2)
a.label('g_go')
h.xr('X0', 0, R=2); h.li('A', 0x7FFFFF); h.sub('X0', 'A'); h.sub('X0', 'A'); h.abs_('A')   # g = 1 - |1 - 2 ph|
h.li('B', 0x7FFFFF); h.sub('A', 'B'); h.mv('B', 'Y0')
h.xr('A', 1, R=2); h.andi(0xFFFF, 'A'); h.ori(GBUF, 'A'); h.mv('A1', 'R1')
h.xr('B', 1, R=2); h.xr('X1', 2, R=2); h.add('X1', 'B'); h.xw('B1', 1, R=2)   # POS += RATE
h.ldxi('(R1)', 'X0'); h.xr('A', G_ACC); h.mac('X0', 'Y0', 'A'); h.xw('A', G_ACC)
h.rts()

a.label('fx_grain')
h.li('R3', GS); h.li('R5', GP)
h.xw('X1', G_DRY)
h.xr('A', G_W); h.ori(GBUF, 'A'); h.mv('A1', 'R1'); h.clr('B'); h.xw('B', G_ACC); h.nop()
h.stxi('X1', '(R1)')                                                       # ring write
for o in VOICE:
    h.li('R2', GS + o); a.jsr('g_voice')
h.xr('A', G_W); h.addi(1, 'A'); h.andi(0xFFFF, 'A'); h.xw('A1', G_W)
h.xr('X0', G_DRY); h.xr('Y0', 5, R=5); h.mpy('X0', 'Y0', 'A')             # dry*x + wet*acc
h.xr('X0', G_ACC); h.xr('Y0', 4, R=5); h.mac('X0', 'Y0', 'A'); h.mv('A', 'X1')
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal6.py runs past P:%04X: %X' % (END, end)
VOCAL6_INIT, FX_GRAIN = a.labels['vocal6_init'], a.labels['fx_grain']
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  init=%04X grain=%04X' % (len(words), end, VOCAL6_INIT, FX_GRAIN))
    a.hexfile(os.path.join(HERE, 'vocal6.hex'))
