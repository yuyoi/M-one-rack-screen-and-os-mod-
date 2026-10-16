"""Output test: 441 Hz square wave at -6 dBFS on both outputs, input ignored. Writes tone.hex (P:$0950).
Uses the kernel's own ESAI idiom (jclr RDF / movep RX1 / movep TX1). Leave it with 'go A00' (kernel) or a power-cycle.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, C5, EA_IMM, encode  # noqa: E402
from dis56k import listing  # noqa: E402

a = Asm(0x950)
def mv(s, d): a.par(move=('Mover', dict(e=R5[s], d=R5[d])))
def li(reg, v): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **EA_IMM)), ext=v)

a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)
a.op('Movec_xx', i=0, D=C5['SP'])
li('B', 0x400000)                  # +0.5
li('Y0', 100)                      # slots per half period (2 slots per frame -> 50 frames -> 441 Hz)
li('X0', 0)                        # slot counter
a.label('wait')
a.word(0x01B388); a.dc('wait')     # jclr #8,x:SAISR,wait   (kernel encoding)
a.word(0x0445C9)                   # movep x:RX1,x1          (kernel encoding, clears RDF)
mv('B', 'X1')
a.word(0x04C5C1)                   # movep x1,x:TX1          (kernel encoding)
mv('X0', 'A'); a.op('Add_xx', i=1, d=0); mv('A', 'X0')          # count++
a.par(alu=('Cmp_S1S2', dict(J=5, d=0)))                          # cmp y0,a
a.jshort('NE', 'wait')
li('X0', 0)
a.par(alu=('Neg', dict(d=1)))                                    # b = -b
a.jshort('T', 'wait')

words = a.link()
if __name__ == '__main__':
    print(listing(words, base=0x950))
    a.hexfile(os.path.join(HERE, 'tone.hex'))
