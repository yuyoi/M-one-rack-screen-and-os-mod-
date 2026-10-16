"""Reverse delay for the M-One DSP. Writes revdelay.hex.
Buffer: X:$020000-$02FFFF (64K, external SRAM). Chunk N samples, played backwards with a triangle window.
State (X short): $30 left in, $31 last out, $34 write idx w, $35 chunk counter c, $36 window gain g, $37 gain step d."""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dis56k import listing
BASE = 0xA00
N = 28760                    # chunk = 1 beat @ 92 BPM (0.652 s @ 44.1k)
FB = 0x466666               # feedback 0.55 (~5-6 s tail @ 92 BPM)
STEP = (2 << 23) // N        # triangle: 0 -> ~1.0 over N/2, back to 0
WET = 0x7FFFFF               # ~1.0
p = []; labels = {}; fix = []
def w(*x): p.extend(x)
def L(n): labels[n] = BASE + len(p)
def ext(op, n): p.append(op); fix.append((len(p), n, 0)); p.append(0)       # absolute ext word
def jcc(op, n): fix.append((len(p), n, op)); p.append(0)                      # 12-bit short jump
def do(op, n): p.append(op); fix.append((len(p), n, -1)); p.append(0)        # DO: LA = label - 1
w(0x05F439, 0x800300)                        # movec #$800300,sr
w(0x05F424, 0xFFFFFF, 0x05F425, 0xFFFFFF)    # m4,m5 = linear
w(0x64F400, 0x020000)                        # move #$020000,r4
w(0x200013)                                  # clr a
w(0x57F400, 0x010000)                        # move #65536,b
L('clr')
w(0x565C00, 0x01418C)                        # move a,x:(r4)+ ; sub #1,b
jcc(0x0E2000, 'clr')                         # jne clr
w(0x563100, 0x563400, 0x563500, 0x563600)    # out, w, c, g = 0
w(0x57F400, STEP, 0x553700)                  # d = +step
L('loop')
ext(0x01B388, 'loop')                        # jclr #8,x:SAISR,loop
w(0x0445C9)                                  # movep x:RX1,x1
ext(0x01B3A6, 'left')                        # jset #6,x:SAISR,left
# --- right slot: mono in
w(0x56B000, 0x200060, 0x21C400)              # a = L+R ; x0 = dry (sat)
# read buf[w - 2c - 1]
w(0x57B500, 0x20003A)                        # b = c ; asl b (2c)
w(0x56B400, 0x200014, 0x014184)              # a = w - 2c - 1
w(0x0140C6, 0x00FFFF, 0x0140C2, 0x020000, 0x219500, 0x000000)  # r5 = $020000|(..&$FFFF)
w(0x46E500)                                  # move x:(r5),y0  (wet)
w(0x47B600, 0x2000B0, 0x21C600)              # y1 = g ; a = wet*g ; y0 = a
# write buf[w] = dry + FB*wet  (feedback)
w(0x208E00, 0x0141D2, FB, 0x21C500)          # a = x0 + FB*y0 ; x1 = a (sat)
w(0x57B400, 0x0140CE, 0x00FFFF, 0x0140CA, 0x020000, 0x21B400, 0x000000)  # r4 = $020000|(w&$FFFF)
w(0x456400)                                  # move x1,x:(r4)
w(0x208E00, 0x200022, 0x0141D2, WET, 0x0C1D04, 0x21C500)  # a = dry/2 + wet ; +12 dB ; x1 = a (sat)
w(0x453100, 0x04C5C1)                        # x:$31 = out ; movep x1,x:TX1
# advance w, c, g
w(0x56B400, 0x014180, 0x0140C6, 0x00FFFF, 0x543400)   # w = (w+1)&$FFFF
w(0x57B600, 0x47B700, 0x200078, 0x553600)             # g += d
w(0x56B500, 0x014180, 0x543500)                       # c += 1
w(0x0140C5, N // 2); jcc(0x0E2000, 'half')            # cmp #N/2,a ; jne half
w(0x57B700, 0x20003E, 0x553700)                       # d = -d
L('half')
w(0x0140C5, N); jcc(0x0E2000, 'loopj')                # cmp #N,a ; jne loopj
w(0x20001B, 0x553500, 0x553600)                       # c = 0 ; g = 0
w(0x57F400, STEP, 0x553700)                           # d = +step
L('loopj')
ext(0x0AF080, 'loop')
L('left')
w(0x453000, 0x45B100, 0x04C5C1)              # store L in ; output last result
ext(0x0AF080, 'loop')
for i, n, op in fix:
    a = labels[n]
    p[i] = a - 1 if op == -1 else (op | a if op else a)
print(listing(p, base=BASE))
print('N=%d step=%06X  words=%d  end=P:%04X' % (N, STEP, len(p), BASE + len(p) - 1))
open('revdelay.hex', 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
