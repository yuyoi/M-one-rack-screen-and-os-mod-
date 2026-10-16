"""GRAIN (id 16): a granular cloud from the last ~1.5 s. DSP-faithful (integer) model of fx_grain in dsp/vocal6.py.

Ring: REVERSE's buffer X:$020000-$02FFFF (64K; never chain GRAIN with REVERSE). Two grain voices, half a grain apart.
Each voice: phase PH += DPH (= 1/L) every sample; window = 1 - |1 - 2 ph| (the two voices sum to 1). When PH wraps,
the voice restarts at a random point 2L + (rand & RANGE) samples back, read at rate 1, or with SCATTER on rate 2
(+12, sparkle) on a coin flip. Integer positions (no interpolation needed at rates 1 and 2).
out = DRY*x + WET*(v1 + v2).   Params X:$02C0: +0 DPH, +1 L (int), +2 RANGE (int mask), +3 SCATTER (int), +4 WET, +5 DRY.
"""
import numpy as np
from reverb_model import q, s24, ld, mpy, st, M24

Q = 1 << 23
FS = 44100
NB = 65536


def params(ms=110, range_s=1.0, scatter=1, wet=0.8, dry=0.4):
    L = int(ms * FS / 1000)
    rng = (1 << int(np.log2(range_s * FS))) - 1
    return [q(1 / L), L, rng, int(scatter), q(wet), q(dry)]


class Grain:
    def __init__(self, prm=None):
        self.p = list(prm or params())
        self.buf = [0] * NB
        self.w = 0
        self.lf = 0x3C3C3C
        self.ph = [0, Q >> 1]
        self.pos = [0, 0]
        self.rate = [1, 1]
        self.acc = 0

    def rnd(self):
        c = self.lf >> 23
        self.lf = (self.lf << 1) & M24
        if c:
            self.lf ^= 0xC20001
        return self.lf

    def step(self, x):
        dph, L, rng, scat, wet, dry = self.p
        self.buf[self.w] = x & M24
        self.acc = 0
        for k in range(2):
            ph = self.ph[k] + dph
            if ph & 0x800000:                   # wrap: new grain
                ph &= 0x7FFFFF
                r = self.rnd()
                self.pos[k] = (self.w - 2 * L - (r & rng)) & 0xFFFF
                self.rate[k] = 1 + (((r >> 20) & 1) if scat else 0)
            self.ph[k] = ph
            g = (Q - 1) - abs((Q - 1) - 2 * ph)
            v = s24(self.buf[self.pos[k] & 0xFFFF])
            self.acc = st(ld(self.acc) + mpy(g, v))
            self.pos[k] = (self.pos[k] + self.rate[k]) & M24
        self.w = (self.w + 1) & 0xFFFF
        return st(mpy(dry, x) + mpy(wet, self.acc))

    def run(self, xs):
        return np.array([self.step(int(v)) for v in xs])


if __name__ == '__main__':
    import autotune_model as am
    x = am.voice(220, 2.0, vib=0.3)
    y = Grain().run(np.round(x * 0.5 * Q).astype(int)) / Q
    print('GRAIN rms in %.3f out %.3f' % (x.std() * 0.5, y.std()))
