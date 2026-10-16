"""Memory switch: OMR bit MS = 1 gives 5K of internal program RAM (P:$0000-$13FF, Y RAM shrinks to $0000-$0DFF).
Writes ms_on.hex (P:$0950). Measured 2026-10-16: TC's own boot ALREADY sets MS (OMR = $000B81 before our OS loads,
and P:$1200 loads, verifies and runs), so `boot` doesn't need this. It is the fallback if OMR ever reads MS = 0:
load + go this first, then load the programs, then go $900 as usual.

It clears CE first (the manual: never switch while the cache is on), sets MS, then idles feeding the ESAI zeros
(silence) until the next load halts it. Nothing it runs or reads is in the switched ranges (UM 3.4: the switch
happens 3 cycles after the OMR write).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, EA_IMM  # noqa: E402
from dis56k import listing  # noqa: E402

BASE = 0x950
a = Asm(BASE)
a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)   # CE = 0, interrupts masked
a.op('Ori', i=0x80, E=2)                                          # ori #$80,omr  (COM byte, bit 7 = MS)
for _ in range(4):
    a.word(0)
a.par(move=('Movex_ea', dict(W=1, d=R5['Y1'], **EA_IMM)), ext=0)
a.label('idle')
a.op('Jclr_qq', label='idle', q=0x33, S=0, b=8)
a.op('Movep_SXqq', W=0, d=R6['X1'], q=0x29)
a.op('Movep_SXqq', W=1, d=R6['Y1'], q=0x21)
a.jshort('T', 'idle')

words = a.link()
if __name__ == '__main__':
    print(listing(words, base=BASE))
    a.hexfile(os.path.join(HERE, 'ms_on.hex'))
