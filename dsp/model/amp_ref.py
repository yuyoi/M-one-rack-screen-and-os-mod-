"""AMP (effect 6): coefficients + a reference model that follows dsp/amp.py step by step (same order, same scaling,
same saturation points, coefficients quantised to Q23 like the table the DSP loads). sim_amp.py compares the two.

Chain per 44.1 kHz sample: input DC blocker -> 4x polyphase upsample -> 3 triode stages at 4x (coupling HPF, gain,
bias minus dynamic bias, clamp, cubic soft clip u + (u - u^3)/2, Miller LPF) -> 48-tap decimator -> TMB tone stack
(biquad + first order) -> power amp (resonance + presence biquads, supply sag, drive, soft clip, x0.9) -> 512-tap
cab IR -> master.
"""
import numpy as np
import scipy.signal as ss
import amp_model as am

FS, OS, Q = 44100, 4, 1 << 23
FS4 = FS * OS


def q(v):                                     # Q23 like the DSP table (24-bit two's complement, saturating)
    return np.clip(np.round(np.asarray(v, float) * Q), -Q, Q - 1) / Q


def sat(v):                                   # move a,x0 / move a,x:ea: the limiter, then the top 24 bits (floor)
    return min(max(np.floor(v * Q), -Q), Q - 1) / Q


def rnd(v):                                   # macr / mpyr: round (half up, like sim56), then the limiter
    return min(max(np.floor(v * Q + 0.5), -Q), Q - 1) / Q


# ---------------------------------------------------------------- coefficients
def fir():
    h = am.H_OS                               # 48 taps, x4 gain (interpolation)
    up = np.concatenate([h[p::OS] for p in range(OS)])     # phase blocks: h[p], h[p+4], ... h[p+44]
    down = h / OS                             # decimator, DC gain 1
    return q(up), q(down)


def tmb_sos(l=0.5, m=0.5, t=0.6, comp='marshall'):
    """Tone stack as a biquad (coefficients /2, -a1/2, -a2/2) + first order (c0, c1, -d1)."""
    b, a = am.tmb(l, m, t, comp)
    sos = ss.tf2sos(b, a)
    first = [s for s in sos if abs(s[2]) < 1e-12 and abs(s[5]) < 1e-12]
    second = [s for s in sos if not (abs(s[2]) < 1e-12 and abs(s[5]) < 1e-12)]
    if not first:                             # tf2sos padded the order: split the real pole out ourselves
        z, p, k = ss.tf2zpk(b, a)
        pr = p[np.argmin(np.abs(p.imag))].real
        zr = z[np.argmin(np.abs(z.imag))].real
        rest_p = np.delete(p, np.argmin(np.abs(p.imag)))
        rest_z = np.delete(z, np.argmin(np.abs(z.imag)))
        bq, aq = ss.zpk2tf(rest_z, rest_p, k)
        second = [np.concatenate([bq, aq])]
        first = [np.array([1, -zr, 0, 1, -pr, 0])]
    s2, s1 = second[0], first[0]
    bq = np.array([s2[0], s2[1], s2[2], -s2[4], -s2[5]]) / 2
    f1 = np.array([s1[0], s1[1], -s1[4]])
    # keep the biquad's numerator inside Q23 (/2 domain): move gain into the first-order section
    g = max(1.0, np.max(np.abs(bq[:3])) / 0.95)
    bq[:3] /= g
    f1[:2] *= g
    return q(bq), q(f1)


def peq_coefs():
    out = []
    for b, a in (am.peq(100, 3, 1.2), am.peq(3000, 3, 0.7, 'shelf')):
        out.append(q(np.array([b[0], b[1], b[2], -a[1], -a[2]]) / 2))
    return out


def cab_ir():
    h = am.cab_ir(512)
    return q(h / max(1.0, np.max(np.abs(h)) / 0.99))


PRESET = dict(g=(20, 12, 0), bias=(0.25, 0.15, 0.10), hp=(30, 120, 80), lp=(12000, 9000, 7000), kb=0.6,
              drive=0, sag=0.5, master=0.7, tmb=(0.5, 0.5, 0.6), comp='marshall')


def params(p=PRESET):
    """The 48-word param block X:$12C0 (see dsp/amp.py for the layout)."""
    w = np.zeros(48)
    for s in range(3):
        w[0 + s] = 10 ** (p['g'][s] / 20) / 32          # stage gain /32 (the DSP shifts left 5)
        w[3 + s] = p['bias'][s]
        w[6 + s] = np.exp(-2 * np.pi * p['hp'][s] / FS4)        # coupling HPF pole
        w[9 + s] = 1 - np.exp(-2 * np.pi * p['lp'][s] / FS4)    # Miller LPF step
    w[12] = p['kb']
    w[13] = 1 - np.exp(-2 * np.pi * 8 / FS4)            # dynamic bias envelope, 8 Hz
    w[14] = np.exp(-2 * np.pi * 20 / FS)                # input DC blocker pole
    bq, f1 = tmb_sos(*p['tmb'], comp=p['comp'])
    w[16:21], w[21:24] = bq, f1
    pe = peq_coefs()
    w[24:29], w[29:34] = pe[0], pe[1]
    w[34] = 10 ** (p['drive'] / 20) / 8                 # drive /8 (the DSP shifts left 3)
    w[35] = p['sag']                                    # sag depth: g = 1 - sag * env
    w[36] = 1 - np.exp(-1 / (0.010 * FS))               # sag attack 10 ms
    w[37] = 1 - np.exp(-1 / (0.150 * FS))               # sag release 150 ms
    w[38] = p['master']
    return q(w)


# ---------------------------------------------------------------- reference (mirrors the DSP code)
class Amp:
    def __init__(self, p=PRESET):
        self.w = params(p)
        self.up, self.down = fir()
        self.ir = cab_ir()
        self.uph = np.zeros(12)               # newest first
        self.dnh = np.zeros(48)
        self.irh = np.zeros(512)
        self.dcx = self.dcy = 0.0
        self.st = np.zeros((3, 4))            # HPX, HPY, LPY, ENV
        self.tb = np.zeros(6)                 # biquad x1 x2 y1 y2, first order x1 y1
        self.pq = np.zeros((2, 4))
        self.env = 0.0

    def biquad(self, c, s, x):
        y = 2 * (c[0] * x + c[1] * s[0] + c[2] * s[1] + c[3] * s[2] + c[4] * s[3])
        s[1], s[0], s[3], s[2] = s[0], x, s[2], sat(y)
        return sat(y)

    def sample(self, x):
        w = self.w
        y = (x - self.dcx) + w[14] * self.dcy            # DC blocker
        self.dcx, self.dcy = x, sat(y)
        y = sat(y)
        self.uph = np.concatenate([[y], self.uph[:-1]])
        for p in range(OS):
            a = rnd(float(np.dot(self.up[p * 12:(p + 1) * 12], self.uph)))
            for s in range(3):                          # the three triode stages (a: the full accumulator)
                hpx, hpy, lpy, env = self.st[s]
                v = (a - hpx) + w[6 + s] * hpy
                self.st[s][0] = sat(a)
                self.st[s][1] = sat(v)
                acc = sat(v) * w[0 + s] * 32 + w[3 + s] - w[12] * env
                u = sat(acc)
                self.st[s][3] = sat(env + w[13] * sat(abs(u) - env))
                sh = u + (u - u * sat(u * u)) / 2
                a = lpy + w[9 + s] * sat(sh - lpy)
                self.st[s][2] = sat(a)
            self.dnh = np.concatenate([[sat(a)], self.dnh[:-1]])
        y = rnd(float(np.dot(self.down, self.dnh)))
        b = self.biquad(w[16:21], self.tb[:4], y)      # TMB
        z = sat(w[21] * b + w[22] * self.tb[4] + w[23] * self.tb[5])
        self.tb[4], self.tb[5] = b, z
        z = self.biquad(w[24:29], self.pq[0], z)       # resonance
        z = self.biquad(w[29:34], self.pq[1], z)       # presence
        g = sat((Q - 1) / Q - w[35] * self.env)       # supply sag
        u = sat(sat(z * g) * w[34] * 8)
        d = abs(u) - self.env
        self.env = sat(self.env + (w[36] if d > 0 else w[37]) * sat(d))
        sh = sat(u + (u - u * sat(u * u)) / 2)
        self.irh = np.concatenate([[sat(sh * (0x733333 / Q))], self.irh[:-1]])   # x 0.9
        o = rnd(float(np.dot(self.ir, self.irh)))
        return rnd(o * w[38])

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])
