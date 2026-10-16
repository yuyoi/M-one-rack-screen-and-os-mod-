"""Input probe: echoes ESAI RX1 to TX1 and keeps the last 2048 input slots in X:$1000-$17FF (ring). Writes inprobe.hex
(P:$0980). Read the ring with 'xmem out.bin 1000 800' to see whether the ADC sees real signal."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, C5, EA_IMM, ea  # noqa: E402
from dis56k import listing  # noqa: E402

a = Asm(0x980)
a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)
a.op('Movec_xx', i=0, D=C5['SP'])
a.op('Movec_ea', ext=0x7FF, W=1, S=0, D=C5['M0'], **EA_IMM)
a.par(move=('Movex_ea', dict(W=1, d=R5['R0'], **EA_IMM)), ext=0x1000)
a.label('wait')
a.word(0x01B388); a.dc('wait')     # jclr #8,x:SAISR,wait
a.word(0x0445C9)                   # movep x:RX1,x1
a.word(0x04C5C1)                   # movep x1,x:TX1
a.op('Movex_ea', W=0, d=R5['X1'], **ea('(R0)+'))
a.jshort('T', 'wait')
words = a.link()
if __name__ == '__main__':
    print(listing(words, base=0x980))
    a.hexfile(os.path.join(HERE, 'inprobe.hex'))
