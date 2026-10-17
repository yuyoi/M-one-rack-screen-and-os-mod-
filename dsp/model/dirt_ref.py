"""DIRT (effect 17): Q23 words + a reference that follows dsp/dirt.py step by step (same order, same scaling, same
saturation points). sim_dirt.py compares the two; dirt_model.py is the float circuit model behind the words.

Param block X:$0900 (64 words, the ESP writes it when a pedal is picked or a knob moves):
  +0 NST (int 1-3)   +1 NTONE (int 1-3)   +2 input DC-blocker pole   +3 PG (clipped path gain)   +4 BL (dry gain)
  +5 LEVEL/256   +6..+10 pre-EQ biquad (b0 b1 b2 -a1 -a2, all /2)   +11 PREDRY (dry added to the pre-EQ output)
  +16 + 8s, stage s: HPK (1 = coupling HPF, 0 = DC coupled), HPP (its pole), C1/256 (gain into the LPF),
       C2N (1 - LPF step), BIAS, KB (dynamic bias depth), EC (envelope step), TAB (X address of its 257-point curve)
  +40 + 5t, tone section t: biquad /2
Curves: 257 words each, X:$0A00 / $0B01 / $0C02; curve(u) for u = -1 .. +1 in steps of 1/128 (the ESP writes them
with the pedal; pedals that share a curve point two stages at one table).
"""
import os
import numpy as np
import scipy.signal as ss
import dirt_model as dm
import amp_ref as AR

FS, OS, Q = dm.FS, dm.OS, 1 << 23
q, sat, rnd = AR.q, AR.sat, AR.rnd
NTAB = 257
PAR, ST, UPX, DNX = 0x0900, 0x0940, 0x0980, 0x09C0
TABS = (0x0A00, 0x0A00 + NTAB, 0x0A00 + 2 * NTAB)
FIRY = 0x0D00
P_NST, P_NT, P_DC, P_PG, P_BL, P_LV, P_PRE, P_PRED, P_STG, P_TONE, NPAR = 0, 1, 2, 3, 4, 5, 6, 11, 16, 40, 64
LV_SHIFT = 8                     # LEVEL word = level / 256: the tone sections may add up to +48 dB
ONE = (Q - 1) / Q


def racc(v):                      # macr: round the accumulator at the A1 LSB (half up), no limiter
    return np.floor(v * Q + 0.5) / Q


HEAD = 0.5                       # every node peaks at half scale: room for FIR / resonance overshoot


def peak_gain(b, a):
    f = np.concatenate([np.geomspace(5, 21000, 600), [FS / 2 * 0.999]])
    _, h = ss.freqz(b, a, f, fs=FS)
    return float(np.max(np.abs(h)))


def bq_words(b, a):
    w = np.array([b[0], b[1], b[2], -a[1], -a[2]]) / 2
    assert np.all(np.abs(w) < 1), ('biquad does not fit the /2 format', w)
    return list(w)


def table(curve, umax, post, ys):
    u = (np.arange(NTAB) - 128) / 128.0
    return q(curve(u * umax) * post / ys)


def _gains(v):
    """the knob-dependent gains the scaling has to cover: pre peak, PT (post), tone peaks"""
    pre = 1.0
    if v.pre is not None:
        _, h = ss.freqz(*v.pre, np.geomspace(5, 21000, 600), fs=FS)
        pre = float(np.max(np.abs(h + v.predry)))
    st = v.stages[-1]
    pt = v.post * (dm.fit_scale(st)[1] if st.fit else 1.0)
    return pre, pt, v.blend, [peak_gain(b, a) for b, a in v.tone]


def _ys(v):
    out = []
    for st in v.stages:
        tc = st.tcurve if st.fit else st.curve
        out.append(float(np.max(np.abs(tc(np.array([-st.umax, st.umax]))))) / HEAD)
    return out


_NORMS = {}
NORM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dirt_norms.json')


def norms(name):
    """Fixed scaling per pedal, so every param word depends on its own knob only (the ESP looks words up, no math):
    the largest clipped + dry sum / tone peak over every knob alone (11 steps) and every knob pair (6 x 6),
    the rest at their defaults. Cached in dirt_norms.json, keyed by the voicing's source."""
    import inspect, hashlib, json
    if name in _NORMS:
        return _NORMS[name]
    key = hashlib.md5(inspect.getsource(dm.PEDALS[name]['src']).encode() + repr(dm.TRIM.get(name)).encode()).hexdigest()
    cache = json.load(open(NORM_FILE)) if os.path.exists(NORM_FILE) else {}
    if cache.get(name, {}).get('key') == key:
        _NORMS[name] = cache[name]
        return cache[name]
    knobs = dm.PEDALS[name]['knobs']
    d = dm.knobs_default(name)
    pts = [dict(d)]
    for i, (l1, _, _) in enumerate(knobs):
        pts += [{**d, l1: x} for x in np.linspace(0, 1, 11)]
        for l2, _, _ in knobs[i + 1:]:
            pts += [{**d, l1: x, l2: y} for x in np.linspace(0, 1, 6) for y in np.linspace(0, 1, 6)]
    v0 = dm.PEDALS[name]['voice'](d)
    ys_last = _ys(v0)[-1]
    pre, sm, tone = 0.0, 0.0, [0.0] * len(v0.tone)
    for k in pts:
        g = _gains(dm.PEDALS[name]['voice'](k))
        pre = max(pre, g[0])
        sm = max(sm, g[1] * ys_last + g[2])
        tone = [max(a, b) for a, b in zip(tone, g[3])]
    out = dict(key=key, pre=pre, sm=sm, tone=tone)
    cache[name] = out
    tmp = NORM_FILE + '.tmp'
    json.dump(cache, open(tmp, 'w'), indent=1)
    os.replace(tmp, NORM_FILE)
    _NORMS[name] = out
    return out


def build(name, kn=None, verbose=False):
    """-> (64 param words as floats (Q23 values), {X address: 257-word table}, info)"""
    v = dm.PEDALS[name]['voice']({**dm.knobs_default(name), **(kn or {})})
    nm = norms(name)
    w = np.zeros(NPAR)
    n = len(v.stages)
    assert 1 <= n <= 3 and 1 <= len(v.tone) <= 3
    w[P_NST], w[P_NT] = n, len(v.tone)
    w[P_DC] = np.exp(-2 * np.pi * v.dc / FS)
    s = _gains(v)[0] / HEAD                    # the pre's own peak: the knob that moves it also owns stage 0's gain
    if v.pre is None:
        b, a = np.array([HEAD, 0, 0]), np.array([1.0, 0, 0])
    else:
        b, a = v.pre
        b = b / s
        w[P_PRED] = v.predry / s
    w[P_PRE:P_PRE + 5] = bq_words(b, a)
    tabs, info = {}, []
    post_fit = 1.0
    ys_all = _ys(v)
    for k, st in enumerate(v.stages):
        alpha, post = dm.fit_scale(st) if st.fit else (1.0, 1.0)
        assert not st.fit or k == n - 1, 'a fitted curve must be the last stage (its post gain is PG)'
        post_fit = post
        tc = st.tcurve if st.fit else st.curve
        ys = ys_all[k]
        c2 = 1.0 if st.lp is None else 1 - np.exp(-2 * np.pi * st.lp / dm.FS4)
        c1 = c2 * st.gain * alpha * s / st.umax
        assert c1 / 256 < 1, ('stage gain too high for the /256 format', name, k, c1)
        o = P_STG + 8 * k
        w[o + 0] = 0.0 if st.hp is None else ONE
        w[o + 1] = 0.0 if st.hp is None else np.exp(-2 * np.pi * st.hp / dm.FS4)
        w[o + 2] = c1 / 256
        w[o + 3] = 1 - c2
        w[o + 4] = st.bias / st.umax
        w[o + 5] = st.kb
        w[o + 6] = 1 - np.exp(-2 * np.pi * st.env_hz / dm.FS4)
        w[o + 7] = TABS[k] / Q                                       # address (an int word, stored as-is)
        tabs[TABS[k]] = table(tc, st.umax, 1.0, ys)
        info.append(dict(c1=c1, ys=ys, alpha=alpha, post=post))
        s = ys
    pt = v.post * post_fit
    sm = nm['sm']
    w[P_PG], w[P_BL] = pt * s / sm, v.blend / sm
    s = sm
    for t, (b, a) in enumerate(v.tone):
        pk = nm['tone'][t] / HEAD
        b, s = b / pk, s * pk
        w[P_TONE + 5 * t:P_TONE + 5 * t + 5] = bq_words(b, a)
    lv = v.level * s / dm.OUT_V / (1 << LV_SHIFT)
    if lv >= 1:
        if verbose:
            print('%s: level clipped (%.2f)' % (name, lv * (1 << LV_SHIFT)))
        lv = ONE
    w[P_LV] = lv
    if verbose:
        print(name, info, 'out scale', s)
    return w, tabs, info


def ints(w):
    """param words as 24-bit ints (NST / NTONE / TAB are plain integers)"""
    out = [int(round(v * Q)) & 0xFFFFFF for v in q(w)]
    out[P_NST], out[P_NT] = int(w[P_NST]), int(w[P_NT])
    for k in range(3):
        out[P_STG + 8 * k + 7] = int(round(w[P_STG + 8 * k + 7] * Q))
    return out


def tab_ints(t):
    return [int(round(v * Q)) & 0xFFFFFF for v in t]


def fir():
    return AR.fir()


# ---------------------------------------------------------------- reference (mirrors the DSP code)
class Dirt:
    def __init__(self, name, kn=None):
        w, tabs, _ = build(name, kn)
        iw = ints(w)
        self.w = q(w)
        self.nst, self.nt = iw[P_NST], iw[P_NT]
        self.tab = [np.asarray(tabs[iw[P_STG + 8 * k + 7]]) for k in range(self.nst)]
        self.up, self.down = fir()
        self.uph, self.dnh = np.zeros(12), np.zeros(48)
        self.dcx = self.dcy = 0.0
        self.pre = np.zeros(4)
        self.st = np.zeros((3, 4))                                  # HPX HPY LPY ENV
        self.ts = np.zeros((3, 4))
        self.dry = np.zeros(16)                                     # dry ring (newest first)

    @staticmethod
    def biquad(c, s, x, add=0.0):
        a = 2 * racc(c[0] * x + c[1] * s[0] + c[2] * s[1] + c[3] * s[2] + c[4] * s[3])   # macr, asl: no DC creep
        s[1], s[0], s[3], s[2] = s[0], x, s[2], sat(a)
        return sat(a + add)

    def curve(self, k, u):
        ui = int(round(u * Q)) & 0xFFFFFF
        idx = (ui ^ 0x800000) >> 16
        frac = ((ui & 0xFFFF) << 7) / Q
        t0, t1 = self.tab[k][idx], self.tab[k][idx + 1]
        return t0 + frac * sat(t1 - t0)

    def sample(self, x):
        w = self.w
        y = (x - self.dcx) + w[P_DC] * self.dcy
        self.dcx, self.dcy = x, sat(y)
        self.dry = np.concatenate([[self.dcy], self.dry[:-1]])
        x0 = self.biquad(w[P_PRE:P_PRE + 5], self.pre, sat(y), add=w[P_PRED] * sat(y))
        self.uph = np.concatenate([[x0], self.uph[:-1]])
        for p in range(OS):
            a = rnd(float(np.dot(self.up[p * 12:(p + 1) * 12], self.uph)))
            for k in range(self.nst):
                o = P_STG + 8 * k
                hpx, hpy, lpy, env = self.st[k]
                v = racc((a - w[o] * hpx) + w[o + 1] * hpy)
                self.st[k][0], self.st[k][1] = sat(a), sat(v)
                a = racc(w[o + 2] * sat(v) * 256 + w[o + 3] * lpy)
                self.st[k][2] = sat(a)
                u = sat(a + w[o + 4] - w[o + 5] * env)
                self.st[k][3] = sat(env + w[o + 6] * sat(abs(u) - env))
                a = self.curve(k, u)
            self.dnh = np.concatenate([[sat(a)], self.dnh[:-1]])
        d = rnd(float(np.dot(self.down, self.dnh)))
        x0 = sat(w[P_PG] * d + w[P_BL] * self.dry[dm.DRY_D])
        for t in range(self.nt):
            x0 = self.biquad(w[P_TONE + 5 * t:P_TONE + 5 * t + 5], self.ts[t], x0)
        return sat(x0 * w[P_LV] * (1 << LV_SHIFT))

    def run(self, x):
        return np.array([self.sample(float(v)) for v in x])


if __name__ == '__main__':
    import sys
    import amp_model as am
    names = sys.argv[1:] or list(dm.PEDALS)
    x = am.di_riff()[:FS // 4] * 2.0
    xq = np.round(x * (Q - 1)) / Q
    for nm in names:
        r = Dirt(nm).run(xq)
        f = dm.run(xq, nm)
        e = r - f
        print('%-14s ref vs float model: SNR %.1f dB | ref peak %.3f rms %.3f' % (
            nm, 10 * np.log10(np.sum(f ** 2) / np.sum(e ** 2)), np.abs(r).max(), np.sqrt(np.mean(r ** 2))))
