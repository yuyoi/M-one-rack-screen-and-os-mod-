"""PHASER (effect 19) and WAH (effect 20): Q23 words + references that follow dsp/filt.py step by step.

PHASER params X:$0DC0: +0 INC (LFO step, a cycle = 2.0)  +1..+4 C0..C3 (all-pass coefficient = cubic of the
  triangle LFO)  +5 FB  +6 DRY  +7 WET.  State X:$0DD0: +0 PH  +1 Y4 (chain out)  +2 + 2s: stage s X1, Y1.
WAH params X:$0DE0: +0 POS (treadle 0..1, the ESP writes it)  +1 SM (smoothing step)  +2..+5 F0..F3 (Chamberlin f =
  cubic of the smoothed position)  +6..+8 Q0..Q2 (1/Q = quadratic)  +9 IG (input gain)  +10 GB/16 (band-pass out)
  +11 GL/16 (low-pass leak).  State X:$0DF0: +0 PS (smoothed position)  +1 LP  +2 BP.
"""
import numpy as np
import filt_model as fm
import amp_ref as AR

FS, Q = fm.FS, 1 << 23
q, sat = AR.q, AR.sat
ONE = (Q - 1) / Q
PP, PS, PW, WS = 0x0DC0, 0x0DD0, 0x0DE0, 0x0DF0


def racc(v):
    return np.floor(v * Q + 0.5) / Q


def build(name, kn=None):
    p = fm.PEDALS[name]
    v = p['voice']({**fm.knobs_default(name), **(kn or {})})
    if p['fx'] == 'phaser':
        w = np.zeros(16)
        w[0] = 2 * v['hz'] / FS
        w[1:5] = v['coef']
        w[5], w[6], w[7] = v['fb'], v['dry'], v['wet']
    else:
        w = np.zeros(16)
        qmax = 1 / min(np.polyval(v['qpoly'][::-1], np.linspace(0, 1, 101)))
        qmin = 1 / max(np.polyval(v['qpoly'][::-1], np.linspace(0, 1, 101)))
        ig = 0.45 / qmax                                    # the band-pass peaks at ~Q x input: keep it < 0.5
        w[0], w[1] = min(v['pos'], ONE), v['smooth']
        w[2:6], w[6:9] = v['fpoly'], v['qpoly']
        w[9] = ig
        w[10] = v['gain'] * 2 / (16 * ig * np.sqrt(qmin * qmax))   # resonance ~ +6 dB over the dry level
        w[11] = v['leak'] / (16 * ig)
    assert np.all(np.abs(w) < 1), (name, w)
    return w


class Phaser:
    def __init__(self, name, kn=None):
        self.w = q(build(name, kn))
        self.ph, self.y4 = 0.0, 0.0
        self.st = np.zeros((4, 2))

    def sample(self, x):
        w = self.w
        self.ph = wrap(self.ph + w[0])
        l = sat(ONE - 2 * abs(self.ph))
        t = sat(w[4] * l + w[3])
        t = sat(t * l + w[2])
        a = sat(t * l + w[1])
        u = sat(x + w[5] * self.y4)
        for s in range(4):
            x1, y1 = self.st[s]
            y = sat(racc(x1 + a * sat(u - y1)))
            self.st[s] = (u, y)
            u = y
        self.y4 = u
        return sat(w[6] * x + w[7] * u)

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])


class Wah:
    def __init__(self, name, kn=None):
        self.w = q(build(name, kn))
        self.ps = self.w[0]                                 # a pick writes PS = POS (no sweep in from 0)
        self.lp = self.bp = 0.0

    def sample(self, x):
        w = self.w
        self.ps = sat(racc(self.ps + w[1] * sat(w[0] - self.ps)))
        p = self.ps
        f = sat(w[5] * p + w[4]); f = sat(f * p + w[3]); f = sat(f * p + w[2])
        qq = sat(w[8] * p + w[7]); qq = sat(qq * p + w[6])
        xi = sat(x * w[9])
        self.lp = sat(racc(self.lp + f * self.bp))
        hp = sat(xi - self.lp - qq * self.bp)
        self.bp = sat(racc(self.bp + f * hp))
        return sat((w[10] * self.bp + w[11] * self.lp) * 16)

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])


def wrap(v):
    i = int(round(v * Q)) & 0xFFFFFF
    return (i - (1 << 24) if i >> 23 else i) / Q


def ints(w):
    return [int(round(x * Q)) & 0xFFFFFF for x in q(w)]
