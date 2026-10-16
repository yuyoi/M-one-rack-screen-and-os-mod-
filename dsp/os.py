"""M-One OS kernel: routing modes + effect modules, one program. Writes os.hex.

Params (X short, written live by the ESP over J8):
  X:$20 mode   0 = SINGLE (FX1)   1 = DOUBLE (FX1 || FX2, mixed)   2 = DOUBLE-SINGLE (FX1 -> FX2)
  X:$21 FX1    X:$22 FX2   effect ids: 0 clean, 1 heavy, 2 reverse, 3 comp, 4 tune (autotune.py at P:$400),
                           5 vox (vocal.py at P:$700: load vocal.hex too)
  tune: X:$0B retune speed (Q23 per sample), X:$23-$2E snap map (signed semitones per pitch class, 0 = chromatic)
  output stage (the pots, after every mode): X:$2F dry gain, X:$3D wet gain (mix: the ESP sends 1-m and m),
    X:$3E tone k (one-pole low-pass, $7FFFFF = off), X:$3C volume; X:$3F = tone filter state
  level: peak envelope of the output (X:$19, ~150 ms release) -> OGDB (X:$FFFFFC) every frame. OnCE registers can be
    read over JTAG while the core runs, so the ESP's singing face reads it without halting the DSP.
Effects are subroutines: input sample in X1, output in X1. Each keeps its own state:
  heavy $32-$33 | reverse $34-$37 + X:$020000-$02FFFF | comp $38-$39 | kernel $30-$31, $3A-$3B, $2F, $3C-$3F
  tune $00-$18, $23-$2E + X/Y:$0400-$0885 + X:$030000-$030FFF (load autotune.hex too: it lives at P:$400)
  vox $1A-$1F + X:$0100-$0113, Y:$0100-$0118 + X:$032000-$033FFF
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm'):
    sys.path.insert(0, os.path.join(HERE, d))
from dis56k import listing  # noqa: E402
sys.path.insert(0, HERE)
import autotune  # noqa: E402  (assembles it: we only need its entry points)
TUNE_INIT, FX_TUNE = autotune.a.labels['tune_init'], autotune.a.labels['fx_tune']
import vocal  # noqa: E402  (vocal.py at P:$0700: VOX)

BASE = 0xA00
METER = 'meter' in sys.argv[1:]        # py os.py meter: histogram of idle spins per frame at X:$1100-$11FF
# heavy
K_HP, K_LP, H_TRIM = 0x07AE14, 0x399999, 0x080000
# reverse
N = 28760                       # 1 beat @ 92 BPM
STEP = (2 << 23) // N
FB, WET = 0x466666, 0x7FFFFF
# comp
T, DECAY, ATT, ONEMR, R = 0x0CCCCD, 0x7FF972, 0x7FDF3B, 0x7FFE5C, 0x0001A3
# level envelope release: ~150 ms at 44.1 kHz frames
import math  # noqa: E402
ENV_DECAY = round(math.exp(-1 / (0.15 * 44100)) * 8388608)

p = []; labels = {}; fix = []
def w(*x): p.extend(x)
def L(n): labels[n] = BASE + len(p)
def ext(op, n): p.append(op); fix.append((len(p), n, 0)); p.append(0)     # 2nd word = absolute address
def jcc(op, n): fix.append((len(p), n, op)); p.append(0)                    # 12-bit short jump/branch
def data(n): fix.append((len(p), n, 0)); p.append(0)                        # table word = label address

def call_fx(param):                     # jsr table[x:param]
    ext(0x66F400, 'table')              # move #table,r6
    w({0x21: 0x76A100, 0x22: 0x76A200}[param])  # move x:$21/$22,n6
    w(0x000000, 0x07EE96, 0x000000)     # nop ; movem p:(r6+n6),r6 ; nop
    w(0x0BE680)                         # jsr (r6)

# ---------------- init
w(0x05F439, 0x800300)                   # movec #$800300,sr
w(0x0500BB)                             # movec #0,sp   (fresh hardware stack: we JSR)
for m in range(8):                      # m0..m7 linear (TC leaves m0 as a modulo register)
    w(0x05F420 | m, 0xFFFFFF)
w(0x0BF080, TUNE_INIT)                  # jsr tune_init (clears its buffers, default speed, chromatic)
w(0x0BF080, vocal.VOX_INIT)             # jsr vox_init (vocal.py: state, slap buffer, coefficients)
w(0x64F400, 0x020000, 0x200013)         # r4 = $020000 ; clr a
w(0x57F400, 0x010000)                   # b = 65536
L('clr')
w(0x565C00, 0x01418C); jcc(0x0E2000, 'clr')   # clear the reverse buffer
for a in (0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x38, 0x3A, 0x3B, 0x20, 0x22, 0x19):
    w(0x560000 | (a << 8))              # move a,x:$aa  (0)
w(0x57F400, STEP, 0x553700)             # reverse step d = +STEP
w(0x56F400, 0x7FFFFF, 0x563900)         # comp g = 1.0
w(0x56F400, 0x000000, 0x542100)         # FX1 = clean (A1 -> x:$21); the ESP pushes its panel state after boot
w(0x56F400, 0x000002, 0x542200)         # FX2 = reverse
w(0x56F400, 0x7FFFFF, 0x563D00)         # output stage until the ESP sends the pots: wet gain 1.0
w(0x563E00, 0x563C00)                   # tone off (k = 1.0) ; volume 1.0
w(0x200013, 0x562F00, 0x563F00)         # clr a ; dry gain 0 ; tone filter state 0
if METER:
    w(0x67F400, 0x1100, 0x200013, 0x57F400, 256)   # r7 = $1100 ; clr a ; b = 256
    L('m_clr')
    w(0x565F00, 0x01418C); jcc(0x0E2000, 'm_clr')  # clear the histogram
    w(0x67F400, 0x1100, 0x77F400, 256)  # r7 = $1100 (+ spins) ; n7 = warm-up frames (the first ones are partial)
# ---------------- sample loop
L('loop')
if METER:                               # idle spin = 9.1 cycles (cycprobe.py): headroom = 9.1 * min spins
    ext(0x01B3A8, 'got')                # jset #8,x:SAISR,got
    w(0x205F00)                         # move (r7)+
    jcc(0x0C0000, 'loop')
    L('got')
else:
    ext(0x01B388, 'loop')               # jclr #8,x:SAISR,loop
w(0x0445C9)                             # movep x:RX1,x1
ext(0x01B3A6, 'left')                   # jset #6,x:SAISR,left
if METER:
    w(0x23EF00, 0x20000B)               # b = n7 ; tst b
    jcc(0x0EA000, 'm_on')               # jeq: warm-up done
    w(0x01418C, 0x21FF00)               # n7 = b - 1
    jcc(0x0C0000, 'm_keep')
    L('m_on')
    w(0x57E700, 0x014188, 0x576700)     # x:(r7) += 1  (r7 = $1100 + spins this frame)
    L('m_keep')
    w(0x67F400, 0x1100)                 # r7 = $1100
w(0x56B000, 0x200060, 0x21C500, 0x453A00)  # x1 = sat(L+R) ; x:$3A = dry
w(0x56A000, 0x200003)                   # a = mode ; tst a
jcc(0x0EA000, 'single')                 # jeq single
w(0x014185)                             # cmp #1,a
jcc(0x0EA000, 'parallel')               # jeq parallel
# series: FX1 -> FX2
call_fx(0x21); call_fx(0x22)
jcc(0x0C0000, 'out')
L('single')
call_fx(0x21)
jcc(0x0C0000, 'out')
L('parallel')
call_fx(0x21)
w(0x453B00, 0x45BA00)                   # x:$3B = fx1 out ; x1 = dry
call_fx(0x22)
w(0x56BB00, 0x200060, 0x200022, 0x21C500)  # x1 = (fx1 + fx2)/2
L('out')                                # output stage: mix, tone, volume (x1 = wet, x:$3A = dry)
w(0x44BA00, 0x46AF00, 0x2000D0)         # x0 = dry ; y0 = dry gain ; a = dry * dg
w(0x20A400, 0x46BD00, 0x2000D3)         # x0 = wet ; y0 = wet gain ; a += wet * wg (rounded)
w(0x57BF00, 0x200014, 0x21C400)         # b = lp ; a -= lp ; x0 = a
w(0x46BE00, 0x2000DB, 0x573F00)         # y0 = k ; b += k * x0 (one-pole low-pass) ; lp = b
w(0x21E400, 0x46BC00, 0x2000D1, 0x21C500)  # x0 = b ; y0 = volume ; a = x0 * volume ; x1 = a
w(0x20AE00, 0x200026)                   # level: a = |out|
w(0x479900, 0x0141F8, ENV_DECAY)        # y1 = env ; b = env * decay
w(0x20000D); jcc(0x0E1000, 'lvl_keep')  # cmp a,b ; jge (decayed env still above |out|)
w(0x21CF00)                             # b = a  (new peak)
L('lvl_keep')
w(0x571900, 0x08CF3C)                   # env = b ; movep b,x:OGDB
w(0x453100, 0x04C5C1)                   # x:$31 = out ; movep x1,x:TX1
ext(0x0AF080, 'loop')
L('left')
w(0x453000, 0x45B100, 0x04C5C1)         # store L in ; output last result
ext(0x0AF080, 'loop')

# ---------------- effect table
L('table')
data('fx_clean'); data('fx_heavy'); data('fx_rev'); data('fx_comp'); data('fx_tune'); data('fx_vox')
labels['fx_tune'] = FX_TUNE
labels['fx_vox'] = vocal.FX_VOX

# ---------------- clean
L('fx_clean')
w(0x00000C)                             # rts

# ---------------- heavy (x1 -> x1)
L('fx_heavy')
w(0x20AE00, 0x57B200, 0x200014, 0x21C400)          # a = x ; hp = x - lp ; x0 = hp
w(0x0141CA, K_HP, 0x573200)                        # lp += k*hp
w(0x208E00, 0x0C1D08, 0x21C400)                    # +24 dB, clip
w(0x208E00, 0x0C1D08, 0x21C400)                    # +24 dB, clip
w(0x208E00, 0x0C1D04, 0x21C400)                    # +12 dB, clip
w(0x200080, 0x21C600, 0x2000D0, 0x21C700)          # x^2, x^3
w(0x0141C8, 0x600000, 0x0141FE, 0x200000, 0x20003A, 0x21E500)  # cubic soft clip -> x1
w(0x20AE00, 0x57B300, 0x200014, 0x21C400)          # post LPF
w(0x0141CA, K_LP, 0x573300, 0x21E500)
w(0x0141E0, H_TRIM, 0x21C500)                      # trim
w(0x00000C)                                        # rts

# ---------------- reverse (x1 -> x1)
L('fx_rev')
w(0x20A400)                                        # x0 = dry
w(0x57B500, 0x20003A, 0x56B400, 0x200014, 0x014184)  # a = w - 2c - 1
w(0x0140C6, 0x00FFFF, 0x0140C2, 0x020000, 0x219500, 0x000000)
w(0x46E500)                                        # y0 = buf[read]
w(0x47B600, 0x2000B0, 0x21C600)                    # y0 = wet * window
w(0x208E00, 0x0141D2, FB, 0x21C500)                # x1 = dry + FB*wet  (to write)
w(0x57B400, 0x0140CE, 0x00FFFF, 0x0140CA, 0x020000, 0x21B400, 0x000000)
w(0x456400)                                        # buf[w] = x1
w(0x208E00, 0x200022, 0x0141D2, WET, 0x0C1D04, 0x21C500)  # x1 = (dry/2 + wet) * 4
w(0x56B400, 0x014180, 0x0140C6, 0x00FFFF, 0x543400)  # w++
w(0x57B600, 0x47B700, 0x200078, 0x553600)          # g += d
w(0x56B500, 0x014180, 0x543500)                    # c++
w(0x0140C5, N // 2); jcc(0x0E2000, 'rev_half')
w(0x57B700, 0x20003E, 0x553700)                    # d = -d
L('rev_half')
w(0x0140C5, N); jcc(0x0E2000, 'rev_done')
w(0x20001B, 0x553500, 0x553600, 0x57F400, STEP, 0x553700)  # c = g = 0 ; d = +STEP
L('rev_done')
w(0x00000C)                                        # rts

# ---------------- comp (x1 -> x1)
L('fx_comp')
w(0x20A400)                                        # x0 = x
w(0x46B900, 0x2000D0, 0x21C500)                    # x1 = y = x*g
w(0x20AF00, 0x20002E)                              # b = |y|
w(0x47B800, 0x0141F0, DECAY)                       # a = env*decay
w(0x20000D)                                        # cmp a,b
jcc(0x0EF000, 'comp_np')                           # jle
w(0x21EE00)                                        # a = b
L('comp_np')
w(0x563800, 0x47B900)                              # env = a ; y1 = g
w(0x0140C5, T); jcc(0x0E7000, 'comp_over')         # cmp #T,a ; jgt over
w(0x0141F8, ONEMR, 0x0140C8, R)                    # release toward 1
jcc(0x0C0000, 'comp_st')
L('comp_over')
w(0x0141F8, ATT)                                   # attack
L('comp_st')
w(0x573900, 0x20AE00, 0x0C1D04, 0x21C500)          # g = b ; x1 = sat(y * 4)
w(0x00000C)                                        # rts

for i, n, op in fix:
    p[i] = (op | labels[n]) if op else labels[n]
end = BASE + len(p) - 1
# P RAM is $0000-$13FF: TC's boot sets OMR MS (measured: OMR = $000B81). $0C00-$13FF is kept for the amp sim.
assert end <= 0xBFF, 'kernel runs into P:$0C00 (kept for the amp sim): %X' % end
print(listing(p, base=BASE))
print('words=%d  end=P:%04X  labels=%s' % (len(p), end, {k: '%04X' % v for k, v in labels.items() if k.startswith(('fx', 'table'))}))
open(os.path.join(HERE, 'os_meter.hex' if METER else 'os.hex'), 'w').write('%X\n%s\n' % (BASE, ' '.join('%06X' % x for x in p)))
