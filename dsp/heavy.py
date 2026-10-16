"""Heavy distortion for the M-One DSP (hand-encoded, verified with dis56k). Writes heavy.hex.
State in internal X RAM (short absolute): $30 left input, $31 last output, $32 pre-HPF lowpass state, $33 post-LPF state."""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dis56k import listing
BASE = 0xA00
K_HP = 0x07AE14   # 0.06  -> ~360 Hz one-pole (tighten)
K_LP = 0x399999   # 0.45  -> ~4.2 kHz one-pole (fizz cut)
TRIM = 0x080000   # -24 dB output
p = []; labels = {}; fix = []
def w(*x): p.extend(x)
def L(n): labels[n] = BASE + len(p)
def j(op, n): p.append(op); fix.append((len(p), n)); p.append(0)
w(0x05F439, 0x800300)          # movec #$800300,sr
w(0x200013)                    # clr a
w(0x563100, 0x563200, 0x563300)  # a -> x:$31,$32,$33
L('loop')
j(0x01B388, 'loop')            # jclr #8,x:SAISR,loop   (RDF)
w(0x0445C9)                    # movep x:RX1,x1
j(0x01B3A6, 'left')            # jset #6,x:SAISR,left   (RFS = first slot)
# ---- right slot: process mono (L+R)/2
w(0x56B000)                    # move x:$30,a
w(0x200060)                    # add x1,a
w(0x200022)                    # asr a                  (/2)
w(0x57B200)                    # move x:$32,b           (lp state)
w(0x200014)                    # sub b,a                (hp = m - lp)
w(0x21C400)                    # move a,x0
w(0x0141CA, K_HP)              # maci #k,x0,b           (lp += k*hp)
w(0x573200)                    # move b,x:$32
w(0x208E00, 0x0C1D08, 0x21C400)  # stage 1: +24 dB, clip
w(0x208E00, 0x0C1D08, 0x21C400)  # stage 2: +24 dB, clip
w(0x208E00, 0x0C1D04, 0x21C400)  # stage 3: +12 dB, clip
w(0x200080, 0x21C600, 0x2000D0, 0x21C700)        # x^2 -> y0, x^3 -> y1
w(0x0141C8, 0x600000, 0x0141FE, 0x200000)        # b = 0.75x - 0.25x^3
w(0x20003A, 0x21E500)          # asl b, move b,x1       (soft clip out)
w(0x20AE00)                    # move x1,a
w(0x57B300)                    # move x:$33,b           (post lp state)
w(0x200014)                    # sub b,a
w(0x21C400)                    # move a,x0
w(0x0141CA, K_LP)              # maci #k2,x0,b
w(0x573300)                    # move b,x:$33
w(0x21E500)                    # move b,x1
w(0x0141E0, TRIM, 0x21C500)    # mpyi #trim,x1,a ; move a,x1
w(0x453100)                    # move x1,x:$31
w(0x04C5C1)                    # movep x1,x:TX1
j(0x0AF080, 'loop')            # jmp loop
# ---- left slot: remember input, output last result
L('left')
w(0x453000)                    # move x1,x:$30
w(0x45B100)                    # move x:$31,x1
w(0x04C5C1)                    # movep x1,x:TX1
j(0x0AF080, 'loop')
for i, n in fix: p[i] = labels[n]
print(listing(p, base=BASE))
open('heavy.hex', 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
