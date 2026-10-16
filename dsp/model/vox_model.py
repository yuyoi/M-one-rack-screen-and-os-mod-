"""VOX: vocal chain for a crystal/ceramic ham mic (D-104 style: thin, honky, peaky top). Reference model for dsp/vocal.py.

  4 biquads: HPF 80 Hz | body +5 dB @ 180 Hz | honk -4 dB @ 1 kHz | crystal peak -4 dB @ 3.5 kHz
  comp     : feedback leveler like the kernel's COMP (gain g, peak env of the output, threshold T)
  tube     : u = sat(2y), u + C2 u^2 - C3 u^3 (2nd + 3rd harmonic), 20 Hz DC block
  exciter  : HPF 3 kHz -> sat(4h) -> 1.5v - 0.5v^3 soft clip, mixed in at MIXEX
  slap     : 110 ms, low-passed repeats (3.5 kHz), feedback FB, mix MIXS
The DSP code mirrors this step by step (coefficients halved for DF1, saturation on every move to a 24-bit register).
"""
import numpy as np

FS = 44100
Q = 1 << 23

EQ = [('hp', 80, 0.707, 0), ('pk', 180, 0.8, 5.0), ('pk', 1000, 1.0, -4.0), ('pk', 3500, 2.0, -4.0)]
EXHP = ('hp', 3000, 0.707, 0)
T = 0.2                                   # leveler threshold (-14 dBFS)
ATT = 0.997                               # gain x this per sample while over T (6 dB in ~5 ms)
DEC = float(np.exp(-1 / (0.03 * FS)))     # output envelope release 30 ms
R = 1 / (0.2 * FS)                        # gain recovery toward 1, ~200 ms
C2, C3 = 0.10, 0.12                       # tube: even / odd harmonic amounts
KDC = 1 - float(np.exp(-2 * np.pi * 20 / FS))
MX2 = 0.30                                # exciter mix x2 (= 0.15 of 1.5v - 0.5v^3)
DLY, FB, MIXS = 4851, 0.15, 0.32          # slap: 110 ms
KS = 1 - float(np.exp(-2 * np.pi * 3500 / FS))
SLAPN = 8192


def biquad(kind, f, q, gdb):
    """RBJ cookbook, normalized: (b0, b1, b2, a1, a2)"""
    w = 2 * np.pi * f / FS
    al = np.sin(w) / (2 * q)
    c = np.cos(w)
    if kind == 'hp':
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
        a = [1 + al, -2 * c, 1 - al]
    else:
        A = 10 ** (gdb / 40)
        b = [1 + al * A, -2 * c, 1 - al * A]
        a = [1 + al / A, -2 * c, 1 - al / A]
    return [v / a[0] for v in b] + [a[1] / a[0], a[2] / a[0]]


def q23(x):
    return int(max(-Q, min(Q - 1, round(x * Q))))


def coef_words():
    """Y table for the DSP: per biquad b0/2, b1/2, b2/2, -a1/2, -a2/2 (Q23)"""
    out = []
    for spec in EQ + [EXHP]:
        b0, b1, b2, a1, a2 = biquad(*spec)
        out += [q23(b0 / 2), q23(b1 / 2), q23(b2 / 2), q23(-a1 / 2), q23(-a2 / 2)]
    return out


def sat(v):
    return min(max(v, -1.0), (Q - 1) / Q)


def st(v):
    """what the DSP stores when it moves an accumulator to a 24-bit register: saturate, then truncate (floor)"""
    return np.floor(sat(v) * Q) / Q


class Vox:
    """exact=True truncates every 24-bit store like the DSP (sim_vox.py compares bit-close against that)"""
    def __init__(self, exact=False):
        self.q = st if exact else sat
        self.c = [w / Q for w in coef_words()]
        k = dict(DEC=DEC, ATT=ATT, T=T, R=R, C2=C2, C3=C3, KDC=KDC, MX2=MX2, KS=KS, FB=FB, MIXS=MIXS)
        k['1-R'], k['.75'], k['.25'] = 1 - R, 0.75, 0.25
        self.c2 = {n: q23(v) / Q for n, v in k.items()} if exact else k   # the DSP's Q23 constants
        self.st = [[0.0] * 4 for _ in range(5)]
        self.env, self.g, self.lp, self.lpd, self.w = 0.0, (Q - 1) / Q, 0.0, 0.0, 0
        self.buf = [0.0] * SLAPN

    def bq(self, k, x):
        b0, b1, b2, na1, na2 = self.c[5 * k:5 * k + 5]
        s = self.st[k]
        acc = b0 * x + b1 * s[0] + b2 * s[1] + na1 * s[2] + na2 * s[3]
        y = self.q(2 * acc)
        self.st[k] = [x, s[0], y, s[2]]
        return y

    def step(self, x):
        for k in range(4):
            x = self.bq(k, x)
        q, c = self.q, self.c2
        y = q(x * self.g)                                     # leveler
        e = q(max(abs(y), self.env * c['DEC']))
        self.env = e
        self.g = q(self.g * c['ATT'] if e > c['T'] else self.g * c['1-R'] + c['R'])
        u = q(2 * y)                                          # tube
        u2 = q(u * u); u3 = q(u * u2)
        t = u + c['C2'] * u2 - c['C3'] * u3
        hp = q(t - self.lp)
        self.lp = q(self.lp + c['KDC'] * hp)
        h = self.bq(4, hp)                                    # exciter
        v = q(4 * h)
        v2 = q(v * v); v3 = q(v2 * v)
        f2 = q(c['.75'] * v - c['.25'] * v3)
        ex = q(hp + c['MX2'] * f2)
        d = self.buf[(self.w - DLY) % SLAPN]                  # slap
        self.lpd = q(self.lpd + c['KS'] * q(d - self.lpd))
        self.buf[self.w] = q(ex + c['FB'] * self.lpd)
        self.w = (self.w + 1) % SLAPN
        return q(ex + c['MIXS'] * self.lpd)

    def run(self, xs):
        return np.array([self.step(float(v)) for v in xs])


def eq_response(freqs):
    """dB of the 4-biquad EQ (no dynamics), for checking the sim against it"""
    from scipy.signal import freqz
    h = np.ones(len(freqs), complex)
    for spec in EQ:
        b0, b1, b2, a1, a2 = biquad(*spec)
        _, hh = freqz([b0, b1, b2], [1, a1, a2], worN=np.asarray(freqs), fs=FS)
        h *= hh
    return 20 * np.log10(np.abs(h))


if __name__ == '__main__':
    f = [50, 80, 120, 180, 300, 600, 1000, 2000, 3500, 6000, 10000]
    print('EQ dB:', ' '.join('%d:%+.1f' % (a, b) for a, b in zip(f, eq_response(f))))
    print('coefs in range:', all(-Q <= w < Q for w in coef_words()), max(abs(w) for w in coef_words()) / Q)
