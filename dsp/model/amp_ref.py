"""AMP (effect 6): coefficients + a reference model that follows dsp/amp.py step by step (same order, same scaling,
same saturation points, coefficients quantised to Q23 like the table the DSP loads). sim_amp.py compares the two.

Chain per 44.1 kHz sample: input DC blocker -> 4x polyphase upsample -> 3 triode stages at 4x (coupling HPF, gain,
bias minus dynamic bias, clamp, cubic soft clip u + (u - u^3)/2, Miller LPF) -> 48-tap decimator -> TMB tone stack
(biquad + first order) -> power amp (resonance + presence biquads, supply sag, drive, soft clip, x0.9) -> 512-tap
cab IR -> master.
"""
import numpy as np
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
    """Tone stack as a biquad (b0 b1 b2 -a1 -a2, all /2) + first order (h, -h, pole). Plain arithmetic, no library
    root finder: the ESP runs the same steps (menu.h ampTmb) and must land on the same words.
    Bilinear of Yeh's cubic, the largest real pole by Newton from z = 1, the DC zero (z = 1) goes with that pole
    into the first-order section, the rest is the biquad. Over the whole knob range: |b| <= 1.79, |a| <= 1.79,
    poles >= 0.987, biquad gain <= 1.0. MID is held <= 0.99: at MID 1 / BASS 0 a pole sits on z = -1."""
    b1, b2, b3, a1, a2, a3 = am.tmb_analog(l, min(m, 0.99), t, comp)
    c = 2.0 * FS
    c2, c3 = c * c, c * c * c
    a0 = a3 * c3 + a2 * c2 + a1 * c + 1
    B0 = (b3 * c3 + b2 * c2 + b1 * c) / a0
    B1 = (-3 * b3 * c3 - b2 * c2 + b1 * c) / a0
    B2 = (3 * b3 * c3 - b2 * c2 - b1 * c) / a0
    A1 = (-3 * a3 * c3 - a2 * c2 + a1 * c + 3) / a0
    A2 = (3 * a3 * c3 - a2 * c2 - a1 * c + 3) / a0
    A3 = (-a3 * c3 + a2 * c2 - a1 * c + 1) / a0
    p = 1.0
    for _ in range(60):
        st = (((p + A1) * p + A2) * p + A3) / ((3 * p + 2 * A1) * p + A2)
        p -= st
        if abs(st) < 1e-15:
            break
    e1 = A1 + p                               # z^3 + A1 z^2 + A2 z + A3 = (z - p)(z^2 + e1 z + e2)
    e2 = A2 + p * e1
    g1 = B1 + B0                              # B(z) = (1 - z^-1)(B0 + g1 z^-1 + g2 z^-2)
    g2 = B2 + g1
    h = (Q - 1) / Q                           # first-order gain as high as Q23 goes: the biquad stays below 1
    bq = np.array([B0 / h, g1 / h, g2 / h, -e1, -e2]) / 2
    return q(bq), q([h, -h, p])


def peq_coefs(resonance=3, presence=3):
    """RESONANCE = peak at 100 Hz Q 1.2, PRESENCE = wide peak at 3 kHz Q 0.5 (a shelf needs b0 > 2 above +3 dB, which
    the /2 format can't hold; after the cab's roll-off the wide peak acts like one). Both fit for -12..+12 dB."""
    out = []
    for b, a in (am.peq(100, resonance, 1.2), am.peq(3000, presence, 0.5)):
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


# ---------------------------------------------------------------- the panel's AMP page (firmware menu.h ampFill)
AMP_TYPES = ('CLEAN', 'CRUNCH', 'LEAD')                 # voicing: stage gains (dB) + tone-stack components
AMP_G = ((6, 0, -6), (20, 12, 0), (30, 24, 12))
AMP_COMP = ('bassman', 'marshall', 'marshall')


def ui_words(typ, gain, bass, mid, treble, presence, resonance, drive, sag, master):
    """The 24 words the panel writes for its AMP rows, {X address: 24-bit word}. gain / bass / mid / treble 0..100,
    presence / resonance / drive in dB, sag / master in %. GAIN 70 = the type's own stage gains; each step of 1 moves
    stages 1 and 2 by 0.25 dB (each held <= 30 dB, the /32 format's limit)."""
    w = {}
    for s in range(3):
        g = min(AMP_G[typ][s] + ((gain - 70) * 0.25 if s < 2 else 0), 30)
        w[s] = 10 ** (g / 20) / 32
    bq, f1 = tmb_sos(bass / 100, mid / 100, treble / 100, AMP_COMP[typ])
    pe = peq_coefs(resonance, presence)
    for i in range(5):
        w[16 + i], w[24 + i], w[29 + i] = bq[i], pe[0][i], pe[1][i]
    for i in range(3):
        w[21 + i] = f1[i]
    w[34] = 10 ** (drive / 20) / 8
    w[35] = sag / 100
    w[38] = master / 100
    return {0x12C0 + k: int(q(v) * Q) & 0xFFFFFF for k, v in w.items()}


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
