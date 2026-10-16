"""STRIP (input stage, X:$0207 = on) and SWELL (id 15): DSP-faithful (integer) models. Mirror dsp/vocal5.py.

STRIP, in order: low cut (100 Hz biquad, fixed) -> gate (peak env vs GATE, gain glides to 0/1) -> de-esser (one-pole
  split at ~5 kHz, the high band's gain backs off while its envelope is over DEESS) -> leveler (VOX style, threshold
  COMP) + makeup -> EQ (one biquad, coefficients in the params: presence / air / low boost) -> drive (cubic soft clip,
  DRIVE = 0 is off).
  Params X:$0270: +0 GATE, +1 DEESS, +2 COMP, +3 MK (makeup/4), +4 DRIVE (x16), +5..+9 EQ b0/2 b1/2 b2/2 -a1/2 -a2/2.
SWELL: env of the input; while it is under THR the gain resets to 0, otherwise it rises by RATE per sample to 1.
  out = x * g^2 (a volume-pedal curve). Params X:$02B0: +0 THR, +1 RATE.
"""
import numpy as np
from reverb_model import q, s24, ld, mpy, st, M24
import vox_model as vm

Q = 1 << 23
FS = 44100
LC = [c & M24 for c in (lambda b: [q(b[0] / 2), q(b[1] / 2), q(b[2] / 2), q(-b[3] / 2), q(-b[4] / 2)])(vm.biquad('hp', 100, 0.707, 0))]
ENV_DEC = q(float(np.exp(-1 / (0.08 * FS))))       # gate / de-ess envelope release 80 ms
GK_OPEN, GK_CLOSE = q(1 - np.exp(-1 / (0.001 * FS))), q(1 - np.exp(-1 / (0.06 * FS)))
KDS = q(1 - np.exp(-2 * np.pi * 5000 / FS))          # de-ess split (one-pole low-pass at 5 kHz)
DS_ATT, DS_REL = q(0.995), q(1 / (0.05 * FS))
SW_DEC = q(float(np.exp(-1 / (0.15 * FS))))


def eq_coefs(kind='flat', f=4000, gdb=0.0, qv=0.7):
    if kind == 'flat' or gdb == 0:
        return [q(0.5), 0, 0, 0, 0]
    b0, b1, b2, a1, a2 = vm.biquad('pk', f, qv, gdb) if kind == 'peak' else shelf(f, gdb, kind)
    return [c & M24 for c in (q(b0 / 2), q(b1 / 2), q(b2 / 2), q(-a1 / 2), q(-a2 / 2))]


def shelf(f, gdb, kind):
    A = 10 ** (gdb / 40); w = 2 * np.pi * f / FS; c, s = np.cos(w), np.sin(w); al = s / 2 * np.sqrt(2)
    if kind == 'high':
        b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
             A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
        a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    else:
        b = [A * ((A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al), 2 * A * ((A - 1) - (A + 1) * c),
             A * ((A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al)]
        a = [(A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al]
    return [v / a[0] for v in b] + [a[1] / a[0], a[2] / a[0]]


def strip_params(gate_db=-50, deess=0.12, comp=0.25, mk=1.5, drive=0.0, eq=None):
    return [q(10 ** (gate_db / 20)), q(deess), q(comp), q(mk / 4), q(drive / 16)] + (eq or eq_coefs())


def swell_params(thr_db=-42, ms=450):
    return [q(10 ** (thr_db / 20)), q(1 / (ms / 1000 * FS))]


def bq(c, s, x):
    acc = mpy(c[0], x) + mpy(c[1], s[0]) + mpy(c[2], s[1]) + mpy(c[3], s[2]) + mpy(c[4], s[3])
    y = st(2 * acc)
    return y, [x, s[0], y, s[2]]


class Strip:
    def __init__(self, prm=None):
        self.p = list(prm or strip_params())
        self.lc = [0] * 4; self.eq = [0] * 4
        self.genv = self.gg = self.dlp = self.denv = 0
        self.dg = self.g = Q - 1
        self.cenv = 0

    def step(self, x):
        gate, deess, comp, mk, drive = self.p[:5]
        eqc = [s24(v) for v in self.p[5:10]]
        x, self.lc = bq([s24(v) for v in LC], self.lc, x)
        self.genv = st(max(ld(abs(x)), mpy(ENV_DEC, self.genv)))                      # gate
        tgt, k = (Q - 1, GK_OPEN) if self.genv > gate else (0, GK_CLOSE)
        self.gg = st(ld(self.gg) + mpy(k, st(ld(tgt) - ld(self.gg))))
        x = st(mpy(x, self.gg))
        self.dlp = st(ld(self.dlp) + mpy(KDS, st(ld(x) - ld(self.dlp))))              # de-esser
        hi = st(ld(x) - ld(self.dlp))
        hs = st(mpy(hi, self.dg))
        self.denv = st(max(ld(abs(hs)), mpy(ENV_DEC, self.denv)))
        self.dg = st(mpy(self.dg, DS_ATT)) if self.denv > deess else st(mpy(self.dg, q(1) - DS_REL) + ld(DS_REL))
        x = st(ld(self.dlp) + ld(hs))
        y = st(mpy(x, self.g))                                                          # leveler
        self.cenv = st(max(ld(abs(y)), mpy(q(vm.DEC), self.cenv)))
        self.g = st(mpy(self.g, q(vm.ATT))) if self.cenv > comp else st(mpy(self.g, q(1 - vm.R)) + ld(q(vm.R)))
        x = st(4 * mpy(y, mk))
        x, self.eq = bq(eqc, self.eq, x)                                                # EQ
        if drive:
            u = st(16 * mpy(x, drive))
            v3 = st(mpy(u, st(mpy(u, u))))
            x = st(2 * (mpy(q(0.75), u) - mpy(q(0.25), v3)))
        return x


class Swell:
    def __init__(self, prm=None):
        self.p = list(prm or swell_params())
        self.env = self.g = 0

    def step(self, x):
        thr, rate = self.p
        self.env = st(max(ld(abs(x)), mpy(SW_DEC, self.env)))
        if self.env > thr:
            self.g = min(Q - 1, self.g + rate)
        else:
            self.g = 0
        g2 = st(mpy(self.g, self.g))
        return st(mpy(x, g2))


if __name__ == '__main__':
    import autotune_model as am
    x = np.concatenate([np.zeros(4410), am.voice(200, 0.5), np.zeros(8820), am.voice(250, 0.3) * 0.05])
    xq = np.round(x * 0.5 * Q).astype(int)
    for name, prm in (('PODCAST', strip_params(eq=eq_coefs('high', 6000, 3))), ('DRIVE', strip_params(drive=3.0))):
        y = np.array([Strip(prm).step(int(v)) for v in xq[:1]])
        s = Strip(prm); y = np.array([s.step(int(v)) for v in xq]) / Q
        print('STRIP %-8s in pk %.2f out pk %.2f  quiet-part pk %.3f  gate gain at the end %.2f' % (
            name, np.abs(x).max() * 0.5, np.abs(y).max(), np.abs(y[-5000:]).max(), s.gg / Q))
    sw = Swell(); y = np.array([sw.step(int(v)) for v in xq]) / Q
    on = 4410
    print('SWELL level 50 ms / 250 ms / 450 ms after the onset: %.3f %.3f %.3f' % tuple(
        np.abs(y[on + n - 200:on + n]).max() for n in (2205, 11025, 19845)))
