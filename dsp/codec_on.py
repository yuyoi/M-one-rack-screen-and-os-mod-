"""Codec power-up for the M-One without its front panel. Writes codec_on.hex (P:$0900).

TC's firmware powers the AK4524 up fully muted (input gain 04/05 and DAC level 06/07 = $00) and only raises the levels
from its front-panel settings, so with the front board gone the DSP sees exact zeros in and sends silence out.
This routine bit-bangs the same 16-bit control words TC uses (app P:$02D90B), in TC's order (table P:$02D92A, with
TC's own un-mute values from its table P:$02D941), drives MUTE* low (outputs on), then starts the OS kernel at its entry.

Codec control (schematic P16001-4 page 3): CCLK = PB15 (HDR bit 15), CS_CODEC* = PB10 (HDR bit 10),
CDTI = A_DATA = SDO0 used as GPIO (PDRC bit 11). MUTE* = PB12 (HDR bit 12): despite the name, 0 = playing, 1 or open = muted (page 9 "open=mute"; TC runs with 0).
Word layout (AK4524): C1 C0 R/W A4..A0 D7..D0 = bits 23..8 of A1, MSB first, data valid on the CCLK rising edge.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, EA_IMM, encode  # noqa: E402
from dis56k import listing  # noqa: E402

BASE, KERNEL_LOOP = 0x900, 0xA00            # os.py entry: its init, then its sample loop
# test overrides: py codec_on.py [dac=HH] [ret=HHHH]  (DAC level 06/07, where to jump when done)
ARGS = dict(a.split('=') for a in sys.argv[1:] if '=' in a)
DAC = int(ARGS.get('dac', '7F'), 16)
KERNEL_LOOP = int(ARGS.get('ret', '%X' % KERNEL_LOOP), 16)
HDR, PDRC = 0x09, 0x3D                      # pp offset of X:$FFFFC9, qq offset of X:$FFFFBD
WORDS = [0xA00700,                          # 00 = $07: DAC, ADC, Vref powered (explicit)
         0xA26400, 0xA31900,                # 02 clock/format, 03  (TC init table)
         0xA49800, 0xA59800,                # 04/05 ADC input gain L/R = $98 (TC's un-mute table)
         0xA60000 | DAC << 8, 0xA70000 | DAC << 8,   # 06/07 DAC level L/R (TC's un-mute table uses $7F)
         0xA31900, 0xA10300]                # 03 again, 01 = $03: ADC + DAC out of reset (TC init table end)

a = Asm(BASE)
a.labels['loop'] = KERNEL_LOOP
def bset_hdr(b): a.op('Bset_pp', p=HDR, S=0, b=b)
def bclr_hdr(b): a.op('Bclr_pp', p=HDR, S=0, b=b)
def delay():                                # >= 32 cycles: AK4524 CCLK needs >= 200 ns per phase
    a.op('Rep_xxx', i=32, h=0); a.op('Nop')

a.op('Movec_ea', ext=0x800300, W=1, S=0, D=C5['SR'], **EA_IMM)   # interrupts masked, no loop flag
a.op('Movec_xx', i=0, D=C5['SP'])                                 # fresh stack (we came in via OnCE GO)
bclr_hdr(12)                                                      # MUTE* = 0: analog outputs ON (the board mutes on high or open)
for w in WORDS:
    a.par(move=('Movex_ea', dict(W=1, d=R5['A1'], **EA_IMM)), ext=w)
    a.jsr('cw')
a.jshort('T', 'loop')

a.label('cw')                               # send A1 bits 23..8 to the codec
bclr_hdr(15); delay()
bclr_hdr(10); delay()                       # CS low
a.do(16, 'cw_end')
bclr_hdr(15); delay()                       # CCLK low
a.op('Jset_S', D=R6['A1'], b=23, label='one')
a.op('Bclr_qq', q=PDRC, S=0, b=11)
a.jshort('T', 'next')
a.label('one')
a.op('Bset_qq', q=PDRC, S=0, b=11)
a.label('next')
delay()
bset_hdr(15); delay()                       # CCLK high: codec latches the bit
a.par(alu=('Lsl_D', dict(D=0)))             # next bit into A1 bit 23
a.label('cw_end')
bset_hdr(10)                                # CS high: word done
a.word(encode('Rts'))

words = a.link()
assert BASE + len(words) <= 0xA00, 'runs into the kernel'
if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d end=P:%04X' % (len(words), BASE + len(words) - 1))
    a.hexfile(os.path.join(HERE, 'codec_on.hex'))
