"""MOD (effect 18): Q23 words + a reference that follows dsp/mod.py step by step. sim_mod.py compares the two.

Params X:$0D10 (48 words): +0 DRV/8 (0 = no drive)  +1 OUT/4  +2..+6 split biquad /2  +7 KA  +8 KL  +9 FB  +10 DRY
  +11..+15 post biquad /2   +16 + 12v voice v: TGT (LFO step, a cycle = 2.0), ACC (rate ramp step), BASE, DEPTH
  (delay in samples / 1024), WET, AMC, AMH (gain = AMC + AMH * lfo), SHP (0 triangle, else sine), AOFF (AM tap
  phase), WG/8 (AM LFO gain, clipped: triangle -> square), WPP (X address of the ring's write pointer), MV (its M).
State X:$0D40 (32): +0 WPA +1 WPB +2 split bq (4) +6 post bq (4) +10 XD (input after drive) +11 LPS (split out)
  +12 WS (wet sum) +16 + 4v voice v: INCH INCL PH READ.  Rings: A X:$0E00 (512, mod 512), B X:$0D80 (64).
A pedal pick writes the params and the voice states (PH = start phase, INCH = TGT).
"""
import numpy as np
import mod_model as mm
import amp_ref as AR
import dirt_model as dm

FS, Q = mm.FS, 1 << 23
q, sat = AR.q, AR.sat
ONE = (Q - 1) / Q
PM, SM, RINGA, RINGB = 0x0D10, 0x0D40, 0x0E00, 0x0D80
NPM, NSM = 48, 32
WPA, WPB, S_SPL, S_POST, XD, LPS, WS, S_V = 0, 1, 2, 6, 10, 11, 12, 16
P_DRV, P_OUT, P_SPL, P_KA, P_KL, P_FB, P_DRY, P_POST, P_V = 0, 1, 2, 7, 8, 9, 10, 11, 16
V_TGT, V_ACC, V_BASE, V_DEPTH, V_WET, V_AMC, V_AMH, V_SHP, V_AOFF, V_WG, V_WPP, V_MV = range(12)
K225 = 0x1CCCCD                  # 0.225: the parabolic sine's refinement


def racc(v):
    return np.floor(v * Q + 0.5) / Q


def bq_words(sec):
    if sec is None:
        b, a = np.array([1.0, 0, 0]), np.array([1.0, 0, 0])
    else:
        b, a = dm.rbj(sec[0], sec[1], 0, sec[2])
    w = np.array([b[0], b[1], b[2], -a[1], -a[2]]) / 2
    assert np.all(np.abs(w) < 1)
    return list(w)


def build(name, kn=None):
    """-> (48 param words, 32 state words: the pick's start state) as Q23 values (ints for WPP / MV / WPA / WPB)"""
    v = mm.PEDALS[name]['voice']({**mm.knobs_default(name), **(kn or {})})
    w = np.zeros(NPM)
    w[P_DRV] = v.drive / 8
    w[P_OUT] = v.out / 4
    w[P_SPL:P_SPL + 5] = bq_words(v.split)
    w[P_KA], w[P_KL], w[P_FB], w[P_DRY] = v.ka, v.kl, v.fb, v.dry
    w[P_POST:P_POST + 5] = bq_words(v.post)
    s = np.zeros(NSM)
    assert 1 <= len(v.voices) <= 2
    for i, vc in enumerate(v.voices):
        o = P_V + 12 * i
        w[o + V_TGT] = 2 * vc.hz / FS
        w[o + V_ACC] = ONE if vc.ramp_s <= 0 else 1 - np.exp(-1 / (vc.ramp_s * FS))
        w[o + V_BASE] = vc.base_ms * FS / 1000 / 1024
        w[o + V_DEPTH] = vc.depth_ms * FS / 1000 / 1024
        ring = mm.RA if vc.ring == 'A' else mm.RB
        assert (vc.base_ms + vc.depth_ms) * FS / 1000 < ring - 2 and vc.depth_ms <= vc.base_ms + 1e-9
        w[o + V_WET] = vc.wet
        w[o + V_AMC], w[o + V_AMH] = 1 - vc.am / 2, vc.am / 2
        w[o + V_SHP] = ONE if vc.sine else 0.0
        w[o + V_AOFF] = vc.aoff
        w[o + V_WG] = vc.wave / 8
        w[o + V_WPP] = (SM + (WPA if vc.ring == 'A' else WPB)) / Q
        w[o + V_MV] = (ring - 1) / Q
        s[S_V + 4 * i + 0] = w[o + V_TGT]
        s[S_V + 4 * i + 2] = vc.phase if vc.phase < 1 else vc.phase - 2
    s[WPA], s[WPB] = RINGA / Q, RINGB / Q
    return w, s


INT_P = [P_V + 12 * i + V_WPP for i in range(2)] + [P_V + 12 * i + V_MV for i in range(2)]


def ints(w, ints_at):
    out = [int(round(x * Q)) & 0xFFFFFF for x in q(w)]
    for i in ints_at:
        out[i] = int(round(w[i] * Q))
    return out


def param_ints(w):
    return ints(w, INT_P)


def state_ints(s):
    return ints(s, [WPA, WPB])


def lfo(ph, shp):
    if shp == 0:
        return sat(ONE - 2 * abs(ph))
    P = sat(4 * (ph - ph * sat(abs(ph))))
    return sat(P + (K225 / Q) * sat(P * sat(abs(P)) - P))


def wrap(v):
    i = int(round(v * Q)) & 0xFFFFFF
    return (i - (1 << 24) if i >> 23 else i) / Q


class Mod:
    def __init__(self, name, kn=None):
        w, s = build(name, kn)
        self.w, self.s = q(w), list(q(s))
        self.wp = [RINGA, RINGB]
        self.ring = {RINGA: np.zeros(mm.RA), RINGB: np.zeros(mm.RB)}
        self.inc = [self.s[S_V], self.s[S_V + 4]]                  # INCH + INCL as one exact value
        self.ph = [self.s[S_V + 2], self.s[S_V + 6]]
        self.read = [0.0, 0.0]
        self.spl, self.post = np.zeros(4), np.zeros(4)

    @staticmethod
    def biquad(c, s, x):
        a = 2 * racc(c[0] * x + c[1] * s[0] + c[2] * s[1] + c[3] * s[2] + c[4] * s[3])
        s[1], s[0], s[3], s[2] = s[0], x, s[2], sat(a)
        return sat(a)

    def rd(self, base, n):
        size = mm.RA if base == RINGA else mm.RB
        k = self.wp[0 if base == RINGA else 1] - base
        return self.ring[base][(k + n) % size]

    def voice(self, i):
        w = self.w
        o = P_V + 12 * i
        tot = self.inc[i] + w[o + V_ACC] * sat(w[o + V_TGT] - np.floor(self.inc[i] * Q) / Q)
        self.inc[i] = np.floor(tot * 2 ** 47) / 2 ** 47
        inch = np.floor(self.inc[i] * Q) / Q
        self.ph[i] = wrap(self.ph[i] + inch)
        shp = w[o + V_SHP]
        x0 = lfo(self.ph[i], shp)
        d = sat(w[o + V_DEPTH] * x0 + w[o + V_BASE])
        di = int(round(d * Q))
        n = -(di >> 13)
        frac = ((di & 0x1FFF) << 10) / Q
        base = RINGA if int(round(w[o + V_WPP] * Q)) == SM + WPA else RINGB
        t0, t1 = self.rd(base, n), self.rd(base, n - 1)
        r = t0 + frac * sat(t1 - t0)
        self.read[i] = sat(r)
        if w[o + V_AMH] != 0:
            x0 = lfo(wrap(self.ph[i] + w[o + V_AOFF]), shp)
            x0 = sat(x0 * w[o + V_WG] * 8)
            g = sat(w[o + V_AMC] + w[o + V_AMH] * x0)
        else:
            g = w[o + V_AMC]
        return sat(self.read[i] * g) * w[o + V_WET]

    def sample(self, x):
        w = self.w
        if w[P_DRV] != 0:
            u = sat(x * w[P_DRV] * 8)
            u3 = u * sat(u * u)
            half = np.floor((u - u3) * 2 ** 47 / 2) / 2 ** 47
            x = sat(u + half)
        xd = x
        lp = self.biquad(w[P_SPL:P_SPL + 5], self.spl, xd)
        a = sat(w[P_KA] * xd + w[P_KL] * lp + w[P_FB] * self.read[0])
        self.ring[RINGA][self.wp[0] - RINGA] = a
        self.ring[RINGB][self.wp[1] - RINGB] = lp
        ws = sat(self.voice(0))
        if w[P_V + 12 + V_WET] != 0:
            ws = sat(ws + self.voice(1))
        y = self.biquad(w[P_POST:P_POST + 5], self.post, ws)
        y = sat(w[P_DRY] * xd + y)
        self.wp = [RINGA + (self.wp[0] - RINGA + 1) % mm.RA, RINGB + (self.wp[1] - RINGB + 1) % mm.RB]
        return sat(y * w[P_OUT] * 4)

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])
