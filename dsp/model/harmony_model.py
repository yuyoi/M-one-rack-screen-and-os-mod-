"""DOUBLER and HARMONY (+ the shared two-head shifter), DSP-faithful (integer) models. Mirror dsp/vocal4.py.

SHIFTER (one voice): ring of NR samples, phase PH (Q23, 0..1) of a window of WN samples. Delay of head 1 = PH*WN,
head 2 = (PH + 1/2 mod 1)*WN; gains g = 1 - |1 - 2 ph| (triangles, they sum to 1). PH -= INC every sample, where
INC = (ratio - 1) / WN (Q23, from a table by semitone), wrapping mod 1.
HARMONY (id 10): 2 shifter voices on one ring. Voice semitones = MAP_v[pitch class of TUNE's note X:$0E]; maps are
12 words each (signed ints, like TUNE's snap map). out = DRY*x + MIX1*v1 + MIX2*v2.
  Params X:$0240: +0 MIX1, +1 MIX2, +2 DRY, +4..+15 MAP1, +16..+27 MAP2.
DOUBLER (id 11): 2 delayed copies (centres D1, D2 samples) wobbling +-DEPTH with one LFO (sine / cosine), linear
interpolation. out = x + WET*(v1 + v2)/2.  Params X:$0260: +0 D1 (int), +1 D2 (int), +2 DEPTH (int), +3 KW, +4 WET.
"""
import numpy as np
from reverb_model import q, s24, ld, mpy, st, M24

Q = 1 << 23
FS = 44100
NR = 4096                    # harmony ring (SRAM $036000)
WN = 2048                    # shifter window
DR = 2048                    # doubler ring (SRAM $037000)
SEMI_LO, SEMI_HI = -12, 24
INCTAB = [q((2 ** (s / 12) - 1) / WN) for s in range(SEMI_LO, SEMI_HI + 1)]   # by s - SEMI_LO
PCTAB = [n % 12 for n in range(128)]


def tri(ph):                                      # 1 - |1 - 2 ph| for ph in Q23 [0, 1)
    return (Q - 1) - abs((Q - 1) - 2 * ph) if ph else 0


class Shifter:
    def __init__(self):
        self.ph = 0

    def step(self, ring, w, inc):
        """ring: list (24-bit words), w: write index of the newest sample. Returns Q23 output."""
        self.ph = (self.ph - inc) & (Q - 1)           # wrap mod 1.0
        acc = 0                                       # Q23, stored between the heads (like the DSP)
        for p in (self.ph, (self.ph + (Q >> 1)) & (Q - 1)):
            pos = p * WN * 2                          # mpy(p, WN): delay in samples * 2^24 (A1:A0)
            di, fr = pos >> 24, (pos & M24) >> 1
            b0 = s24(ring[(w - di) % len(ring)]); b1 = s24(ring[(w - di - 1) % len(ring)])
            v = st(ld(b0) + mpy(fr, st(ld(b1) - ld(b0))))
            acc = st(ld(acc) + mpy(tri(p), v))
        return acc


def harmony_params(mix1=0.5, mix2=0.5, dry=0.8, map1=None, map2=None):
    m1 = map1 if map1 is not None else [4] * 12
    m2 = map2 if map2 is not None else [7] * 12
    return [q(mix1), q(mix2), q(dry), 0] + [v & M24 for v in m1] + [v & M24 for v in m2]


def diatonic_map(steps, key=0, scale=(0, 2, 4, 5, 7, 9, 11)):
    """semitone offset per pitch class for a harmony voice `steps` scale degrees away (2 = a 3rd, 4 = a 5th)"""
    out = []
    for pc in range(12):
        rel = (pc - key) % 12
        deg = min(range(7), key=lambda d: (rel - scale[d]) % 12)       # nearest scale degree at or below
        tgt = scale[(deg + steps) % 7] + 12 * ((deg + steps) // 7)
        out.append(tgt - scale[deg])
    return out


class Harmony:
    def __init__(self, prm=None):
        self.p = list(prm or harmony_params())
        self.ring = [0] * NR
        self.w = 0
        self.v = [Shifter(), Shifter()]

    def step(self, x, note):
        mix1, mix2, dry = self.p[0], self.p[1], self.p[2]
        self.ring[self.w] = x & M24
        pc = PCTAB[note & 127]
        acc = st(mpy(dry, x))
        for k, mix in ((0, mix1), (1, mix2)):
            s = s24(self.p[4 + 12 * k + pc])
            s = min(max(s, SEMI_LO), SEMI_HI)
            y = self.v[k].step(self.ring, self.w, INCTAB[s - SEMI_LO])
            acc = st(ld(acc) + mpy(mix, y))
        self.w = (self.w + 1) % NR
        return acc


def doubler_params(d1_ms=18, d2_ms=27, depth=12, rate_hz=0.35, wet=0.6):
    return [int(d1_ms * FS / 1000), int(d2_ms * FS / 1000), int(depth), q(2 * np.pi * rate_hz / FS), q(wet)]


class Doubler:
    def __init__(self, prm=None):
        self.p = list(prm or doubler_params())
        self.ring = [0] * DR
        self.w = 0
        self.s, self.c = 0, Q - 1

    def step(self, x):
        d1, d2, depth, kw, wet = self.p
        self.ring[self.w] = x & M24
        self.s = st(ld(self.s) + mpy(kw, self.c)); self.c = st(ld(self.c) - mpy(kw, self.s))
        vs = []
        for d, m in ((d1, self.s), (d2, self.c)):
            pos = (d << 24) + mpy(depth, m)
            di, fr = pos >> 24, (pos & M24) >> 1
            b0 = s24(self.ring[(self.w - di) % DR]); b1 = s24(self.ring[(self.w - di - 1) % DR])
            vs.append(st(ld(b0) + mpy(fr, st(ld(b1) - ld(b0)))))
        self.w = (self.w + 1) % DR
        v = st((ld(vs[0]) + ld(vs[1])) >> 1)
        return st(ld(x) + mpy(wet, v))


def shimmer_params(gain=0.35, semis=12):
    return [q(gain), INCTAB[semis - SEMI_LO] & M24]


class Shimmer:
    """SHIMMER (id 14): put it right before REVERB in a chain. It pitch-shifts the reverb's last output (X:$0304)
    and adds it to the signal going into the reverb: a shifted feedback loop. Shares HARMONY's ring and voice 1.
    Params X:$02A0: +0 GAIN, +1 INC (shifter increment, default +12)."""
    def __init__(self, prm=None):
        self.p = list(prm or shimmer_params())
        self.ring = [0] * NR
        self.w = 0
        self.v = Shifter()

    def step(self, x, rev):
        self.ring[self.w] = rev & M24
        y = self.v.step(self.ring, self.w, s24(self.p[1]))
        self.w = (self.w + 1) % NR
        return st(ld(x) + mpy(self.p[0], y))


if __name__ == '__main__':
    import autotune_model as am
    x = am.voice(220, 1.0)
    xq = np.round(x * Q).astype(int)
    note = 57                                    # A3
    for name, m in (('+12', [12] * 12), ('+7', [7] * 12), ('-12', [-12] * 12), ('3rd in C', diatonic_map(2))):
        h = Harmony(harmony_params(mix1=1.0, mix2=0.0, dry=0.0, map1=m))
        y = np.array([h.step(int(v), note) for v in xq]) / Q
        print('HARMONY %-9s 220 Hz -> %.1f Hz (map[A] = %+d)' % (name, am.pitch_of(y[10000:30000]), m[9]))
    d = Doubler()
    y = np.array([d.step(int(v)) for v in xq]) / Q
    print('DOUBLER rms in %.3f out %.3f' % (x.std(), y.std()))
    print('3rd map in C:', diatonic_map(2), ' 5th:', diatonic_map(4))
