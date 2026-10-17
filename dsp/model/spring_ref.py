"""SPRING (effect 21): a two-spring reverb tank (6G15 / Accutronics style), Q23 words + a reference that follows
dsp/spring.py step by step. sim_spring.py compares the two.

Model (after Valimaki, Parker & Abel, "Parametric spring reverberation effect", JAES 2010, cut down to fit):
  dwell: the 12AT7 driver into the tank's transducer, a cubic soft clip after the DWELL gain;
  per spring s (2, slightly different lengths): z = ring out (the spring's travel time, ~33 / 41 ms),
    lp = LP(z) (the tank's band edge), v = u + FB * lp, v -> 8 stretched all-passes A(z) = (a + z^-2) / (1 + a z^-2)
    (the dispersion: every trip down the spring smears the highs later: the "boing" chirp) -> ring in;
  out = DRY * x + MIX * TONE-LP(z1 + z2).
Params X:$0888: +0 DWELL/8 +1 FB +2 KD (band-edge LP step) +3 KT (tone LP step) +4 MIX +5 DRY,
  +8 + 4s spring s: L (int samples), A (all-pass coefficient), RB (ring base address).
State X:$0898: +0 WP (int 0..2047) +1 TONE +2 + s: LP of spring s, +8 + 32s: spring s's 8 all-passes (x1 x2 y1 y2).
Rings: X:$038000 / $038800 (2048 each, modulo): REVERB's buffer, so SPRING and REVERB never share a chain.
"""
import numpy as np
import amp_ref as AR

FS, Q = 44100, 1 << 23
q, sat = AR.q, AR.sat
ONE = (Q - 1) / Q
NAP = 8
PS, SS = 0x0888, 0x0898
RINGS, RLEN = (0x038000, 0x038800), 2048


def racc(v):
    return np.floor(v * Q + 0.5) / Q


def lin(x, lo, hi):
    return lo + (hi - lo) * min(max(x, 0.0), 1.0)


PEDALS = {'SPRING': dict(knobs=[('DWELL', 'B', 0.5), ('TONE', 'B', 0.5), ('MIX', 'B', 0.4)], colour=0xA7B8A0)}


def knobs_default(name):
    return {l: d for l, _, d in PEDALS[name]['knobs']}


def build(name='SPRING', kn=None):
    k = {**knobs_default(name), **(kn or {})}
    w = np.zeros(16)
    w[0] = lin(k['DWELL'], 0.5, 4.0) / 8                  # dwell: drive into the tank
    w[1] = lin(k['DWELL'], 0.62, 0.8)                     # ~2-3.5 s: driven harder, the tail hangs on longer
    w[2] = 1 - np.exp(-2 * np.pi * 4300 / FS)             # tank band edge ~4.3 kHz
    w[3] = 1 - np.exp(-2 * np.pi * lin(k['TONE'], 1500, 7000) / FS)
    w[4], w[5] = lin(k['MIX'], 0, 0.9), 0.85
    w[8], w[9], w[10] = round(0.0331 * FS), -0.62, RINGS[0] / Q     # spring 1
    w[12], w[13], w[14] = round(0.0412 * FS), -0.58, RINGS[1] / Q   # spring 2
    return w


def ints(w):
    out = [int(round(x * Q)) & 0xFFFFFF for x in q(w)]
    out[8], out[12] = int(w[8]), int(w[12])
    out[10], out[14] = RINGS
    return out


class Spring:
    def __init__(self, name='SPRING', kn=None):
        b = build(name, kn)
        self.w = q(b)
        self.L = [int(b[8]), int(b[12])]
        self.ring = [np.zeros(RLEN), np.zeros(RLEN)]
        self.wp = 0
        self.lp = [0.0, 0.0]
        self.tone = 0.0
        self.ap = np.zeros((2, NAP, 4))

    def sample(self, x):
        w = self.w
        u = sat(x * w[0] * 8)
        u = sat(u + np.floor((u - u * sat(u * u)) * 2 ** 47 / 2) / 2 ** 47)
        acc = 0.0
        for s in range(2):
            z = self.ring[s][(self.wp - self.L[s]) % RLEN]
            self.lp[s] = sat(racc(self.lp[s] + w[2] * sat(z - self.lp[s])))
            v = sat(u + w[1] * self.lp[s])
            a = w[9 + 4 * s]
            for i in range(NAP):
                x1, x2, y1, y2 = self.ap[s][i]
                y = sat(racc(x2 + a * sat(v - y2)))
                self.ap[s][i] = (v, x1, y, y1)
                v = y
            self.ring[s][self.wp] = v
            acc = acc + z
        self.tone = sat(racc(self.tone + w[3] * sat(sat(acc) - self.tone)))
        self.wp = (self.wp + 1) % RLEN
        return sat(w[5] * x + w[4] * self.tone)

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])
