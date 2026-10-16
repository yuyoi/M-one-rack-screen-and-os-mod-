"""Simple distortion: +48 dB in two saturating stages, cubic soft clip, -24 dB out. Writes distortion.hex.
The 56k saturates when a too-big accumulator is moved to a register: that is the hard clip, for free."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dis56k import listing  # noqa: E402

BASE = 0xA00
p = [0x05F439, 0x800300,                      # movec #$800300,sr
     0x01B388, 0x000A02,                      # loop: jclr #8,x:SAISR,loop
     0x0445C9,                                # movep x:RX1,x1
     0x20AE00, 0x0C1D08, 0x21C400,            # a = x1 ; +24 dB ; x0 = a (clip)
     0x208E00, 0x0C1D08, 0x21C400,            # a = x0 ; +24 dB ; x0 = a (clip)
     0x200080, 0x21C600, 0x2000D0, 0x21C700,  # y0 = x^2 ; y1 = x^3
     0x0141C8, 0x600000, 0x0141FE, 0x200000,  # b = 0.75x - 0.25x^3
     0x20003A, 0x21E500,                      # asl b ; x1 = b (1.5x - 0.5x^3)
     0x0141E0, 0x080000, 0x21C500,            # x1 *= 1/16 (-24 dB)
     0x04C5C1,                                # movep x1,x:TX1
     0x0AF080, 0x000A02]                      # jmp loop
print(listing(p, base=BASE))
open('distortion.hex', 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
