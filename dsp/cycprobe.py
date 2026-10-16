"""Cycle-ceiling probe for the M-One DSP. Writes cycprobe.hex (P:$0950). Outputs SILENCE (zeros) the whole time.

Frame loop like the kernel's (wait RDF, read RX1, RFS = left slot). After each right slot it burns N single-cycle
NOPs (REP x0 ; NOP) and counts how many idle spins are left before the next slot. N steps from 1 by STEP for NPH
phases of FRAMES frames each. Per phase it stores at X:$1000 + 3k: N, the minimum spins per frame, and how many
slots arrived with the ESAI receiver overrun flag (ROE) set. The N where min spins reaches 0 / ROE starts = ceiling.
Afterwards X:$10FF = $C0FFEE and it keeps the ESAI fed with zeros (run `boot` again to get the OS back).

  py -3.10 cycprobe.py [ext]     ext: the work is REP x0 ; MOVE X:(R4),Y0 with R4 in the external SRAM instead
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, EA_IMM, ea  # noqa: E402
from dis56k import listing  # noqa: E402

BASE, STEP, NPH, FRAMES, RES = 0x950, 64, 48, 256, 0x1000
EXT = 'ext' in sys.argv[1:]
SAISR, RX1, TX1 = 0x33, 0x29, 0x21
MIN, ROE, NN = 0x1A, 0x1C, 0x1D

a = Asm(BASE)
def ldx(aa, reg): a.par(move=('Movex_aa', dict(W=1, a=aa, d=R5[reg])))
def stx(reg, aa): a.par(move=('Movex_aa', dict(W=0, a=aa, d=R5[reg])))
def li(reg, v): a.par(move=('Movex_ea', dict(W=1, d=R5[reg], **EA_IMM)), ext=v)
def stxi(reg, e): a.par(move=('Movex_ea', dict(W=0, d=R5[reg], **ea(e))))

a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)
a.op('Movec_xx', i=0, D=C5['SP'])
for m in range(8):
    a.op('Movec_ea', ext=0xFFFFFF, W=1, S=0, D=C5['M%d' % m], **EA_IMM)
li('R1', RES); li('R4', 0x038000); li('Y1', 0)
li('B', 1); stx('B', NN)
a.do(NPH, 'ph_end')
ldx(NN, 'X0')
li('B', 0x7FFFFF); stx('B', MIN)
a.par(alu=('Clr', dict(d=1))); stx('B', ROE)
a.par(alu=('Clr', dict(d=0)))                      # a1 = spin counter
a.do(FRAMES, 'fr_end')
a.label('spin')
a.op('Jset_qq', label='got', q=SAISR, S=0, b=8)    # RDF: a slot is waiting
a.op('Add_xx', i=1, d=0)                           # spins++
a.jshort('T', 'spin')
a.label('got')
a.op('Jclr_qq', label='no_roe', q=SAISR, S=0, b=7) # ROE: we were late
ldx(ROE, 'B'); a.op('Add_xx', i=1, d=1); stx('B', ROE)
a.label('no_roe')
a.op('Movep_SXqq', W=0, d=R6['X1'], q=RX1)
a.op('Movep_SXqq', W=1, d=R6['Y1'], q=TX1)          # silence out
a.op('Jset_qq', label='spin', q=SAISR, S=0, b=6)   # left slot: keep counting
ldx(MIN, 'B'); a.par(alu=('Cmp_S1S2', dict(J=0, d=1)))   # b - a
a.jshort('LE', 'keep')
stx('A', MIN)
a.label('keep')
a.par(alu=('Clr', dict(d=0)))
a.op('Rep_S', d=R6['X0'])                          # the work: N cycles
if EXT:
    a.par(move=('Movex_ea', dict(W=1, d=R5['Y0'], **ea('(R4)'))))
else:
    a.word(0)                                      # nop
a.word(0); a.word(0)
a.label('fr_end')
stxi('X0', '(R1)+'); ldx(MIN, 'B'); stxi('B', '(R1)+'); ldx(ROE, 'B'); stxi('B', '(R1)+')
ldx(NN, 'B'); a.op('Add_xxxx', ext=STEP, d=1); stx('B', NN)
a.word(0)
a.label('ph_end')
li('B', 0xC0FFEE); a.par(move=('Movex_ea', dict(W=0, d=R5['B'], M=6, R=0)), ext=RES + 0xFF)
a.label('idle')
a.op('Jclr_qq', label='idle', q=SAISR, S=0, b=8)
a.op('Movep_SXqq', W=0, d=R6['X1'], q=RX1)
a.op('Movep_SXqq', W=1, d=R6['Y1'], q=TX1)
a.jshort('T', 'idle')

words = a.link()
assert BASE + len(words) <= 0xA00, 'runs into the kernel'
if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d end=P:%04X ext=%s' % (len(words), BASE + len(words) - 1, EXT))
    a.hexfile(os.path.join(HERE, 'cycprobe_ext.hex' if EXT else 'cycprobe.hex'))
