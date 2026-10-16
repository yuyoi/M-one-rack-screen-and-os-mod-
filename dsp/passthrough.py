"""Passthrough: ADC (ESAI RX1) straight to DAC (TX1). The first program that ran on the M-One DSP. Writes passthrough.hex.
Needs TC's own boot to have set up the codec + ESAI first (power on normally, then load over J8)."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dis56k import listing  # noqa: E402

BASE = 0xA00
p = [0x05F439, 0x800300,   # movec #$800300,sr       (interrupts masked, loop flag clear)
     0x01B388, 0x000A02,   # loop: jclr #8,x:SAISR,loop   (wait RDF)
     0x0445C9,             # movep x:RX1,x1
     0x04C5C1,             # movep x1,x:TX1
     0x0AF080, 0x000A02]   # jmp loop
print(listing(p, base=BASE))
open('passthrough.hex', 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
