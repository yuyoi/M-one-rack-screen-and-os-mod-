"""REVERB: Dattorro plate at half rate (22.05 kHz), one tick spread over two frames. DSP-faithful (integer) model.

One 16K circular buffer (X:$038000, modulo) holds every delay line; the pointer moves down one word per tick, so a
line written at PTR+off is read d ticks later at PTR+off+d.
  frame A: in = (x + x_prev)/2 -> predelay -> bandwidth LP -> 4 input diffusers -> left tank
  frame B: right tank -> 7 output taps (Dattorro's left output) -> PTR--
  output : B frames give the new tick o_k, A frames give (o_k + o_k-1)/2 (linear interpolation, 1 tick late)
  tank   : x + decay*other_end -> mod allpass (-0.7, LFO +-EXC) -> delay -> damping LP -> *decay -> allpass (DD2) ->
           delay -> end
Params X:$0280: +0 SIZE (scales every delay), +1 DECAY, +2 KD = 1 - damping, +3 KB = bandwidth, +4 PREDELAY (int
ticks), +5 WET (reverb level, added to the dry signal), +6 FREEZE (int: input off, decay 1, no damping),
+7 DD2 (decay diffusion 2).
"""
import numpy as np

Q = 1 << 23
M24 = (1 << 24) - 1
FS2 = 22050
NBUF = 16384
DAT = 29761
SMAX = 0.85                       # buffer budget: Dattorro lengths at 22.05 kHz x 0.85
EXC = 10                          # mod allpass excursion (ticks)
KLFO = 2 * np.pi * 0.8 / FS2


def sc(n): return int(round(n * FS2 / DAT * SMAX))


# line -> max length (ticks)
LINES = [('PD', 1400), ('AP1', sc(142)), ('AP2', sc(107)), ('AP3', sc(379)), ('AP4', sc(277)),
         ('MAPL', sc(672) + EXC + 2), ('DL1', sc(4453)), ('APL2', sc(1800)), ('DL2', sc(3720)),
         ('MAPR', sc(908) + EXC + 2), ('DR1', sc(4217)), ('APR2', sc(2656)), ('DR2', sc(3163))]
OFF = {}
_o = 0
for n, L in LINES:
    OFF[n] = _o
    _o += L + 2
assert _o <= NBUF, _o
LEN = dict(LINES)
LEN['MAPL'] -= EXC + 2
LEN['MAPR'] -= EXC + 2
# Dattorro left-output taps (line, length at 29761), sign
TAPS = [('DR1', 266, 1), ('DR1', 2974, 1), ('APR2', 1913, -1), ('DR2', 1996, 1), ('DL1', 1990, -1),
        ('APL2', 187, -1), ('DL2', 1066, -1)]
TAPS = [(n, sc(t), s) for n, t, s in TAPS]
G_IN1, G_IN2, G_DD1 = 0.75, 0.625, -0.70
TAPG = 0.6


def q(v): return int(round(min(max(v, -1.0), 1 - 1 / Q) * Q))


def s24(v):
    v &= M24
    return v - (1 << 24) if v >> 23 else v


def ld(x): return x << 24                              # Q23 -> accumulator (units 2^-47)
def mpy(a, b): return 2 * a * b                         # Q23 x Q23 -> accumulator


def st(acc):                                            # accumulator -> Q23 (saturate, truncate)
    acc = max(-(1 << 47), min((1 << 47) - 1, acc))
    return acc >> 24


def dmul(size, L):                                      # integer delay = floor(size * L) + 1 (mpy of Q23 by int)
    return ((2 * size * L) >> 24) + 1


def params(size=0.8, decay=0.6, damp=0.3, bw=0.9995, pre_ms=10, wet=0.3, freeze=0, dd2=None):
    dd2 = dd2 if dd2 is not None else min(0.5, max(0.25, decay + 0.15))
    return [q(size), q(decay), q(1 - damp), q(bw), int(round(pre_ms * FS2 / 1000)), q(wet), int(freeze), q(dd2)]


class Reverb:
    def __init__(self, prm=None):
        self.p = prm or params()
        self.buf = [0] * NBUF
        self.ptr = 0
        self.ph = 0
        self.xp = 0
        self.bwl = self.dl = self.dr = self.lend = self.rend = 0
        self.ok = self.okp = 0
        self.s, self.c = 0, Q - 1
        self.diff = 0

    def rd(self, line, d): return s24(self.buf[(self.ptr + OFF[line] + d) & (NBUF - 1)])
    def wr(self, line, v): self.buf[(self.ptr + OFF[line]) & (NBUF - 1)] = v & M24

    def ap(self, line, d, g, x):
        z = self.rd(line, d)
        w = st(ld(x) - mpy(g, z))
        self.wr(line, w)
        return st(ld(z) + mpy(g, w))

    def map_(self, line, d, g, x, mod):
        """modulated allpass: read at d + mod (mod = EXC * s, fractional), linear interpolation"""
        pos = (d << 24) + mpy(EXC, mod)                # accumulator: A1 = whole ticks, A0 = fraction
        di, fr = pos >> 24, (pos & M24) >> 1
        z0 = self.rd(line, di); z1 = self.rd(line, di + 1)
        z = st(ld(z0) + mpy(fr, st(ld(z1) - ld(z0))))
        w = st(ld(x) - mpy(g, z))
        self.wr(line, w)
        return st(ld(z) + mpy(g, w))

    def step(self, x):
        size, decay, kd, kb, pre, wet, freeze, dd2 = self.p
        if freeze:
            decay, kd = Q - 1, Q - 1
        if self.ph == 0:                                                       # frame A
            xin = 0 if freeze else st((ld(x) + ld(self.xp)) >> 1)
            self.wr('PD', xin)
            v = self.rd('PD', pre)
            self.bwl = st(ld(self.bwl) + mpy(kb, st(ld(v) - ld(self.bwl))))
            v = self.bwl
            for line, g in (('AP1', G_IN1), ('AP2', G_IN1), ('AP3', G_IN2), ('AP4', G_IN2)):
                v = self.ap(line, dmul(size, LEN[line]), q(g), v)
            self.diff = v
            self.s = st(ld(self.s) + mpy(q(KLFO), self.c)); self.c = st(ld(self.c) - mpy(q(KLFO), self.s))
            t = st(ld(v) + mpy(decay, self.rend))
            t = self.map_('MAPL', dmul(size, LEN['MAPL']), q(G_DD1), t, self.s)
            self.wr('DL1', t)
            t = self.rd('DL1', dmul(size, LEN['DL1']))
            self.dl = st(ld(self.dl) + mpy(kd, st(ld(t) - ld(self.dl))))
            t = st(mpy(decay, self.dl))
            t = self.ap('APL2', dmul(size, LEN['APL2']), dd2, t)
            self.wr('DL2', t)
            self.lend = self.rd('DL2', dmul(size, LEN['DL2']))
            y = st((ld(self.ok) + ld(self.okp)) >> 1)
        else:                                                                  # frame B
            t = st(ld(self.diff) + mpy(decay, self.lend))
            t = self.map_('MAPR', dmul(size, LEN['MAPR']), q(G_DD1), t, self.c)
            self.wr('DR1', t)
            t = self.rd('DR1', dmul(size, LEN['DR1']))
            self.dr = st(ld(self.dr) + mpy(kd, st(ld(t) - ld(self.dr))))
            t = st(mpy(decay, self.dr))
            t = self.ap('APR2', dmul(size, LEN['APR2']), dd2, t)
            self.wr('DR2', t)
            self.rend = self.rd('DR2', dmul(size, LEN['DR2']))
            acc = 0
            for line, tap, sg in TAPS:
                acc += sg * mpy(q(TAPG), self.rd(line, dmul(size, tap)))
            self.okp, self.ok = self.ok, st(acc)
            y = self.ok
            self.ptr = (self.ptr - 1) & (NBUF - 1)
        self.ph ^= 1
        self.xp = x
        return st(ld(x) + mpy(wet, y))                                         # dry + wet * reverb

    def run(self, xs):
        return np.array([self.step(int(v)) for v in xs])


PRESETS = {  # name: params (for presets.py and the tests)
    'ROOM': params(size=0.35, decay=0.45, damp=0.35, pre_ms=5, wet=0.25),
    'PLATE': params(size=0.75, decay=0.65, damp=0.15, pre_ms=12, wet=0.3),
    'HALL': params(size=1.0, decay=0.82, damp=0.45, pre_ms=35, wet=0.35),
}

if __name__ == '__main__':
    FS = 44100
    print('buffer use %d of %d words' % (_o, NBUF))
    x = np.zeros(int(FS * 3)); x[100] = 0.5
    xi = np.round(x * Q).astype(int)
    for name, prm in PRESETS.items():
        y = Reverb(prm).run(xi) / Q
        tail = y[200:]
        e = np.cumsum(tail[::-1] ** 2)[::-1]
        edb = 10 * np.log10(e / e[0] + 1e-20)
        t60 = np.argmax(edb < -60) / FS if (edb < -60).any() else float('nan')
        t30 = np.argmax(edb < -30) / FS
        print('%-6s RT60 ~ %.2f s (2 x T30 %.2f)  peak %.3f' % (name, t60, 2 * t30, np.abs(tail).max()))
    r = Reverb(params(size=0.75, decay=0.65, freeze=1))
    y = r.run(np.round(np.concatenate([np.zeros(10)]) * Q).astype(int))
