"""Compressor for the M-One DSP (servo/feedback style: no division). Writes compressor.hex.
out = in*g. Peak env of out (instant attack, slow decay). env > T: g *= ATT (fast down). env <= T: g eases back to 1.0.
State (X short): $30 left in, $31 last out, $38 env, $39 gain g."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'disasm'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
from dis56k import listing
BASE = 0xA00
T = 0x0CCCCD       # threshold 0.1 (-20 dBFS)
DECAY = 0x7FF972   # env decay 0.9998/sample (~110 ms)
ATT = 0x7FDF3B     # gain *= 0.999 per sample over threshold (~20 ms)
ONEMR = 0x7FFE5C   # release: g = g*0.99995 + 0.00005  (~0.45 s back to 1.0)
R = 0x0001A3
MAKEUP = 0x0C1D04  # asl #2,a,a = +12 dB
p = []; labels = {}; fix = []
def w(*x): p.extend(x)
def L(n): labels[n] = BASE + len(p)
def ext(op, n): p.append(op); fix.append((len(p), n, 0)); p.append(0)
def jcc(op, n): fix.append((len(p), n, op)); p.append(0)
w(0x05F439, 0x800300)                  # movec #$800300,sr
w(0x200013, 0x563100, 0x563800)        # clr a ; out = 0 ; env = 0
w(0x56F400, 0x7FFFFF, 0x563900)        # g = 1.0
L('loop')
ext(0x01B388, 'loop')                  # jclr #8,x:SAISR,loop
w(0x0445C9)                            # movep x:RX1,x1
ext(0x01B3A6, 'left')                  # jset #6,x:SAISR,left
w(0x56B000, 0x200060, 0x21C400)        # a = L+R ; x0 = mono (sat)
w(0x46B900, 0x2000D0, 0x21C500)        # y0 = g ; a = x0*g ; x1 = y (sat)
w(0x20AF00, 0x20002E)                  # b = y ; abs b
w(0x47B800, 0x0141F0, DECAY)           # y1 = env ; a = env*decay
w(0x20000D)                            # cmp a,b   (b - a)  [CMP B/A = JJJ 000, Table 12-16]
jcc(0x0EF000, 'nopeak')                # jle nopeak
w(0x21EE00)                            # a = b     (new peak)
L('nopeak')
w(0x563800)                            # env = a
w(0x47B900)                            # y1 = g
w(0x0140C5, T)                         # cmp #T,a
jcc(0x0E7000, 'over')                  # jgt over
w(0x0141F8, ONEMR, 0x0140C8, R)        # b = g*(1-r) + r   (release toward 1)
jcc(0x0C0000, 'store')                 # jmp store
L('over')
w(0x0141F8, ATT)                       # b = g*ATT          (attack down)
L('store')
w(0x573900)                            # g = b
w(0x20AE00, MAKEUP, 0x21C500)          # a = y ; +12 dB ; x1 (sat)
w(0x453100, 0x04C5C1)                  # x:$31 = out ; movep x1,x:TX1
ext(0x0AF080, 'loop')
L('left')
w(0x453000, 0x45B100, 0x04C5C1)        # store L in ; output last result
ext(0x0AF080, 'loop')
for i, n, op in fix:
    p[i] = (op | labels[n]) if op else labels[n]
print(listing(p, base=BASE))
open('compressor.hex', 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
