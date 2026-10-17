"""DIRT (effect 17): circuit models of the dirt pedals. One engine, every pedal is a set of coefficients.

Structure per 44.1 kHz sample (volts in, 1.0 = 1 V at the pedal input):
  input coupling HPF -> pre-EQ (biquad, the gain network ahead of the clipper) -> 4x up ->
  1-3 stages at 176.4 kHz:  coupling HPF -> gain + pre-clip LPF (feedback cap / op-amp GBW) -> + bias - dynamic bias
                            -> transfer curve (solved from the circuit: diodes in feedback, diodes to ground,
                               transistor stage, op-amp rails, class-B crossover)
  -> 4x down -> post * clipped + blend * dry (the TS / Klon clean sum) -> 1-3 tone sections -> level.
Each stage is a static nonlinearity between linear filters (Wiener-Hammerstein). The curves here are the exact
solutions of the circuit equations (dense parametric tables); dirt_ref.py turns them into the DSP's 257-point
tables and Q23 words and mirrors the DSP step by step.

Component values are from the published schematics where known (TS808 clip stage, RAT gain network + filter, Big Muff
tone stack, Fuzz Face bias); the rest are fitted to the published responses and are marked ~ in the voicing.

  py -3.10 dirt_model.py [pedal] [out.wav]      renders the test riff through one pedal (float model)
"""
import numpy as np
import scipy.signal as ss

FS, OS = 44100, 4
FS4 = FS * OS
VT = 0.025852                    # thermal voltage at 300 K
OUT_V = 2.0                      # digital output 1.0 = 2 V at the pedal output
DRY_D = 11                       # clean-path delay (samples) = the 4x FIRs' group delay, so TS / Klon sums line up
H_OS = ss.firwin(48, 0.9 / OS, window=('kaiser', 7.0)) * OS   # same 4x FIR as AMP (amp_model.H_OS)


# ---------------------------------------------------------------- pot tapers (x = knob 0..1)
def taper(x, kind='B'):
    x = min(max(float(x), 0.0), 1.0)
    if kind == 'A':              # audio / log: 10 % at the middle
        return (10 ** (2 * x) - 1) / 99
    if kind == 'C':              # reverse log
        return 1 - (10 ** (2 * (1 - x)) - 1) / 99
    return x


# ---------------------------------------------------------------- transfer curves (volts -> volts, monotonic)
def _interp(xs, ys):
    return lambda v: np.interp(v, xs, ys)


def diode_r(R, Is=2.52e-9, n=1.752, mp=1, mn=1, N=60001):
    """Solves v = e + R * Id(e): a diode pair in an op-amp's feedback (R = the feedback resistor, v = the open
    drive R * i) and diodes to ground behind a series R (v = source voltage) are the same equation.
    mp / mn = diodes in series per direction (SD-1: 2 / 1). Default diode 1N914 / 1N4148."""
    def emax(m):
        return m * n * VT * np.log(1e4 / (R * Is) + 1)
    e = np.concatenate([np.linspace(-emax(mn), 0, N // 2, endpoint=False), np.linspace(0, emax(mp), N // 2 + 1)])
    v = e + R * Is * (np.expm1(e / (mp * n * VT)) - np.expm1(-e / (mn * n * VT)))
    return _interp(v, e)


GE = dict(Is=2e-7, n=1.3)        # 1N34A germanium
SI = dict(Is=2.52e-9, n=1.752)   # 1N914 / 1N4148
LED = dict(Is=1e-16, n=2.0)


def rail(vr, p=6):
    """op-amp output stage: linear until close to the rail, then a hard-ish knee"""
    return lambda v: v / (1 + np.abs(v / vr) ** p) ** (1 / p)


def bjt_ce(rc, re, ic0, vcc=9.0, vsat=0.1, vt=VT, p=4, N=60001):
    """Common-emitter stage, base driven by v (AC volts on top of the bias). Ebers-Moll Ic, unbypassed Re,
    saturation (Vce -> vsat) as a soft limit, cutoff (Ic -> 0). Output = AC collector voltage (inverting)."""
    icsat = (vcc - vsat) / (rc + re)
    ic = np.geomspace(ic0 * 1e-6, icsat * 4, N)
    ice = ic / (1 + (ic / icsat) ** p) ** (1 / p)
    v = vt * np.log(ic / ic0) + (ic - ic0) * re
    out = -(ice - ic0 * (1 / (1 + (ic0 / icsat) ** p) ** (1 / p))) * rc
    return _interp(v, out)


def triode_12ax7(rp=100e3, bplus=300.0, rg=1e6, N=4001):
    """12AX7 on a 100k plate load (Koren): grid voltage -> AC plate voltage (inverting). Grid conduction above 0 V
    through the grid stopper rounds the top off."""
    mu, ex, kg1, kp, kvb = 100.0, 1.4, 1060.0, 600.0, 300.0
    def ip(vp, vg):
        e1 = vp / kp * np.log1p(np.exp(kp * (1 / mu + vg / np.sqrt(kvb + vp * vp))))
        return np.where(e1 > 0, e1 ** ex, 0) / kg1 * 2   # amps
    vg = np.linspace(-8, 6, N)
    vge = np.where(vg > 0, vg / (1 + vg * rg / 3e5), vg)  # grid current: the stopper eats most of the positive swing
    vp = np.full(N, bplus / 2)
    for _ in range(80):                                  # Newton on vp = B+ - Ip(vp, vg) * Rp
        f = vp - bplus + ip(vp, vge) * rp
        d = 1 + (ip(vp + 1e-3, vge) - ip(vp, vge)) / 1e-3 * rp
        vp = np.clip(vp - f / d, 0.5, bplus)
    vb = -1.5                                            # cathode bias
    out = vp - np.interp(vb, vg, vp)
    return _interp(vg - vb, out)


def xover(vd=0.15, vr=1.2):
    """class-B push-pull without enough bias: dead band around 0 (crossover), then the small supply's rails"""
    r = rail(vr, 4)
    return lambda v: r(v - vd * np.tanh(v / vd))


def compose(*fs):
    def f(v):
        for g in fs:
            v = g(v)
        return v
    return f


# ---------------------------------------------------------------- filters
def onepole_hp_pole(fc, fs=FS4):
    return 0.0 if fc is None else float(np.exp(-2 * np.pi * fc / fs))


def bilinear(b, a, fs=FS, fp=None):
    """analog (descending powers of s) -> digital biquad (b0 b1 b2), (1 a1 a2); prewarped at fp if given"""
    fse = fs if fp is None else 2 * np.pi * fp / (2 * np.tan(np.pi * fp / fs))
    bz, az = ss.bilinear(b, a, fse)
    bz, az = np.concatenate([bz, np.zeros(3 - len(bz))]), np.concatenate([az, np.zeros(3 - len(az))])
    return bz / az[0], az / az[0]


def lp1(fc, fs=FS):
    return bilinear([2 * np.pi * fc], [1, 2 * np.pi * fc], fs, fp=min(fc, 0.45 * fs))


def hp1(fc, fs=FS):
    return bilinear([1, 0], [1, 2 * np.pi * fc], fs, fp=min(fc, 0.45 * fs))


def rbj(kind, f0, gain_db=0.0, q=0.707, fs=FS):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / fs
    c, s = np.cos(w), np.sin(w)
    al = s / (2 * q)
    if kind == 'peak':
        b = [1 + al * A, -2 * c, 1 - al * A]; a = [1 + al / A, -2 * c, 1 - al / A]
    elif kind in ('low', 'high'):
        sq = 2 * np.sqrt(A) * al
        sg = 1 if kind == 'low' else -1
        b = [A * ((A + 1) - sg * (A - 1) * c + sq), sg * 2 * A * ((A - 1) - sg * (A + 1) * c),
             A * ((A + 1) - sg * (A - 1) * c - sq)]
        a = [(A + 1) + sg * (A - 1) * c + sq, -sg * 2 * ((A - 1) + sg * (A + 1) * c), (A + 1) + sg * (A - 1) * c - sq]
    elif kind == 'lp':
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == 'hp':
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]; a = [1 + al, -2 * c, 1 - al]
    elif kind == 'bp':
        b = [al, 0, -al]; a = [1 + al, -2 * c, 1 - al]
    b, a = np.array(b, float), np.array(a, float)
    return b / a[0], a / a[0]


def band(fl, fh, fs=FS):
    """analog band-pass s/w1 / ((1 + s/w1)(1 + s/w2)): a coupling HPF and a roll-off LPF in one biquad (gain 1)"""
    w1, w2 = 2 * np.pi * fl, 2 * np.pi * fh
    return bilinear([1 / w1, 0], np.polymul([1 / w1, 1], [1 / w2, 1]), fs, fp=np.sqrt(fl * fh))


def cascade(*sec):
    b, a = np.array([1.0]), np.array([1.0])
    for bb, aa in sec:
        b, a = np.polymul(b, bb), np.polymul(a, aa)
    return b, a


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def blend_stack(r1, c1, c2, r2, rp, t, rl):
    """Big Muff / DS-1 tone: Vin -R1- A -C1- gnd (low-pass leg), Vin -C2- B -R2- gnd (high-pass leg), pot Rp from A
    to B, wiper at t (0 = A = bass side) into a load RL. Nodal analysis with polynomials in s -> H(s) = W / Vin."""
    P = np.poly1d
    t = min(max(t, 1e-3), 1 - 1e-3)
    ga, gb, g1, g2, gl = 1 / (t * rp), 1 / ((1 - t) * rp), 1 / r1, 1 / r2, 1 / rl
    sC1, sC2 = P([c1, 0]), P([c2, 0])
    M = [[P([g1 + ga]) + sC1, P([0]), P([-ga])],
         [P([0]), sC2 + P([g2 + gb]), P([-gb])],
         [P([-ga]), P([-gb]), P([ga + gb + gl])]]
    rhs = [P([g1]), sC2, P([0])]                     # Vin = 1 injected through R1 and C2
    Mw = [row[:2] + [rhs[i]] for i, row in enumerate(M)]
    num, den = det3(Mw), det3(M)
    return num.coeffs, den.coeffs


def ts_tone(t):
    """~ TS808 tone (Electrosmash): 1k / 0.22u low-pass at 723 Hz, and the active tone stage moves a zero from far
    above (TONE 0: plain 723 Hz low-pass) down to ~450 Hz (TONE 10: the low-pass cancelled, a little treble lift),
    with the op-amp stage's own pole near 8 kHz."""
    w1, wp = 2 * np.pi * 723, 2 * np.pi * 8000
    wz = 2 * np.pi * 723 / (0.02 + 1.6 * t)
    return np.polymul([1 / wz, 1], [1]), np.polymul([1 / w1, 1], [1 / wp, 1])


# ---------------------------------------------------------------- voicing data
class Stage:
    """hp: coupling HPF (Hz, None = DC coupled), gain: linear V/V into the curve, lp: pre-clip LPF (Hz, None = open),
    curve: exact circuit curve (volts), tcurve: the knob-independent curve the DSP table holds (default = curve),
    umax: table domain (volts; the clamp, so op-amp rails can sit here), bias: volts added before the curve,
    kb: dynamic bias depth (fraction of umax per unit envelope), env_hz: envelope rate."""
    def __init__(self, gain, curve, umax, hp=None, lp=None, tcurve=None, bias=0.0, kb=0.0, env_hz=8.0, fit=False):
        self.gain, self.curve, self.umax, self.hp, self.lp = gain, curve, umax, hp, lp
        self.tcurve = tcurve or curve
        self.bias, self.kb, self.env_hz, self.fit = bias, kb, env_hz, fit


class Voicing:
    def __init__(self, stages, pre=None, dc=10.0, blend=0.0, tone=(), level=1.0, post=1.0, predry=0.0):
        self.stages, self.pre, self.dc, self.blend, self.predry = stages, pre, dc, blend, predry
        self.tone, self.level, self.post = list(tone), level, post


def fit_scale(st, lo=0.01):
    """The DSP holds one table per stage; a knob that changes the curve itself (TS DRIVE moves the feedback R, and
    with it the knee) is matched by scaling: curve(w) ~ post * tcurve(alpha * w), least squares over 0.01..umax V
    (log spaced). Returns (alpha, post)."""
    w = np.geomspace(lo, st.umax, 400)
    w = np.concatenate([-w[::-1], w])
    y = st.curve(w)
    best = (1e30, 1.0, 1.0)
    for alpha in np.geomspace(0.5, 2.0, 121):
        t = st.tcurve(np.clip(alpha * w, -st.umax, st.umax))
        post = float(np.dot(t, y) / np.dot(t, t))
        err = float(np.sum((post * t - y) ** 2))
        if err < best[0]:
            best = (err, alpha, post)
    return best[1], best[2]


# ---------------------------------------------------------------- the pedals
# knobs: (label, taper, default 0..1). voice(k) gets {label: 0..1} and returns a Voicing.
PEDALS = {}


# output trim per pedal: every pedal at its default knobs comes out at ~0.12 rms (-18 dBFS) with the hot test DI
# (0.063 rms), a little above unity like a real pedal at noon. Measured with run(); re-measure after a voicing change.
TRIM = {'TUBE SCREAMER': 1.41, 'SD-1': 0.85, 'KLON': 2.75, 'RAT': 2.37, 'DS-1': 3.40, 'BIG MUFF': 3.60,
        'METAL MUFF': 1.58, 'METAL ZONE': 1.45, 'FUZZ FACE': 0.32, 'FUNERAL': 1.57, 'IRON MAN': 0.50, 'RADIO': 2.44}


def pedal(name, knobs, colour):
    def reg(f):
        def voice(k):
            v = f(k)
            v.level *= TRIM.get(name, 1.0)
            return v
        PEDALS[name] = dict(knobs=knobs, voice=voice, colour=colour, src=f)
        return f
    return reg


TS_RF0 = 168e3                                   # TS table: feedback R in the middle of the DRIVE range


@pedal('TUBE SCREAMER', [('DRIVE', 'A', 0.5), ('TONE', 'B', 0.5), ('LEVEL', 'A', 0.6)], 0x2FB34A)
def ts808(k):
    rf = 51e3 + 500e3 * taper(k['DRIVE'], 'A')
    st = Stage(gain=rf / 4.7e3, hp=720.0, lp=1 / (2 * np.pi * rf * 51e-12), umax=12.0,
               curve=diode_r(rf, **SI), tcurve=diode_r(TS_RF0, **SI), fit=True)
    return Voicing([st], dc=7.0, blend=1.0, tone=[bilinear(*ts_tone(k['TONE']), fp=1000)],
                   level=4.0 * taper(k['LEVEL'], 'A'))


@pedal('SD-1', [('LEVEL', 'A', 0.6), ('TONE', 'B', 0.5), ('DRIVE', 'A', 0.5)], 0xF2D21B)
def sd1(k):
    rf = 33e3 + 1e6 * taper(k['DRIVE'], 'A')                       # ~ SD-1: 1M drive, asymmetric 2 + 1 diodes
    st = Stage(gain=rf / 4.7e3, hp=720.0, lp=1 / (2 * np.pi * rf * 51e-12), umax=12.0,
               curve=diode_r(rf, mp=2, mn=1, **SI), tcurve=diode_r(180e3, mp=2, mn=1, **SI), fit=True)
    t = k['TONE']                                                  # ~ a little brighter than the TS
    tone = bilinear([1 / (2 * np.pi * 1000 / (0.02 + 2.0 * t)), 1], np.polymul([1 / (2 * np.pi * 1000), 1],
                    [1 / (2 * np.pi * 10e3), 1]), fp=1000)
    return Voicing([st], dc=7.0, blend=1.0, tone=[tone], level=4.0 * taper(k['LEVEL'], 'A'))


@pedal('KLON', [('GAIN', 'A', 0.4), ('TREBLE', 'B', 0.5), ('OUTPUT', 'A', 0.5)], 0xD9A441)
def klon(k):
    g = taper(k['GAIN'], 'A')                    # ~ dual gang: gang 1 = clip-amp gain, gang 2 = less clean blend
    st = Stage(gain=1 + 100e3 * g / 1.8e3, hp=400.0, lp=12e3 / (1 + 4 * g), umax=8.0,
               curve=compose(rail(8.0), diode_r(1e3, **GE)))
    tr = 12 * (k['TREBLE'] - 0.55)
    return Voicing([st], dc=10.0, blend=0.9 * (1 - 0.85 * g),
                   tone=[rbj('peak', 1000, 3 + 3 * g, 0.7), rbj('high', 1500, tr, 0.6)],
                   level=3.0 * taper(k['OUTPUT'], 'A'), post=1.6)


def rat_gain(d):
    """RAT: LM308 non-inverting, Rd = 100k log in the feedback, ground legs 47R + 2.2u and 560R + 4.7u:
    G(s) = 1 + Rd * Yg(s) (DC gain 1, shelves up at 60 Hz and 1.5 kHz, up to ~67 dB). The DSP runs it as that sum
    (biquad Rd * Yg plus the dry 1: a single biquad of G would need its zeros right next to its poles, which Q23
    coefficients can't hold). The 100 pF across Rd and the op-amp's gain-bandwidth (~700 kHz with its 30 pF) then
    roll the top off: one real pole, their time constants added. Returns ((b, a) of Rd * Yg, pole Hz)."""
    rd = 100e3 * taper(d, 'A') + 10
    P = np.poly1d
    y1 = (P([2.2e-6, 0]), P([47 * 2.2e-6, 1]))                     # admittance of 47R + 2.2u: sC / (1 + sRC)
    y2 = (P([4.7e-6, 0]), P([560 * 4.7e-6, 1]))
    yg_num, yg_den = y1[0] * y2[1] + y2[0] * y1[1], y1[1] * y2[1]
    num, den = rd * yg_num, yg_den
    g_hf = 1 + rd * (1 / 47 + 1 / 560)
    tau = rd * 100e-12 + g_hf / (2 * np.pi * 700e3)
    return (num.coeffs, den.coeffs), 1 / (2 * np.pi * tau)


@pedal('RAT', [('DISTORTION', 'A', 0.5), ('FILTER', 'B', 0.4), ('VOLUME', 'A', 0.5)], 0x3A3A3A)
def rat(k):
    (bn, bd), fpole = rat_gain(k['DISTORTION'])
    pre = bilinear(bn, bd, fp=1500)                                # gain network Rd * Yg (+ the dry 1: predry)
    st = Stage(gain=1.0, lp=fpole, umax=4.0, curve=compose(rail(3.6), diode_r(1e3, **SI)))
    rf = 100e3 * k['FILTER']                                       # FILTER: 1k5 + 100k into 3n3 (+ the 1k ahead)
    fc = 1 / (2 * np.pi * (2.5e3 + rf) * 3.3e-9)
    return Voicing([st], pre=pre, predry=1.0, dc=7.0, tone=[lp1(min(fc, 20e3))], level=3.0 * taper(k['VOLUME'], 'A'))


@pedal('DS-1', [('TONE', 'B', 0.5), ('LEVEL', 'A', 0.5), ('DIST', 'A', 0.5)], 0xF07818)
def ds1(k):
    # ~ transistor booster (+28 dB, 3.3 kHz-ish pre-emphasis) then the op-amp (DIST 100k / 4k7) into 1N4148s to
    # ground behind 2k2, then the passive LPF / HPF blend (6k8 / 100n, 22n / 2k2, 20k pot)
    pre = rbj('high', 2000, 6, 0.6)
    st = Stage(gain=25 * (1 + 100e3 * taper(k['DIST'], 'A') / 4.7e3), hp=100.0, lp=8e3, umax=4.0,
               curve=compose(rail(3.6), diode_r(2.2e3, **SI)))
    tone = bilinear(*blend_stack(6.8e3, 0.1e-6, 22e-9, 2.2e3, 20e3, k['TONE'], 100e3), fp=1000)
    return Voicing([st], pre=pre, dc=10.0, tone=[tone], level=6.0 * taper(k['LEVEL'], 'A'))


def muff_stage(gain, hp):
    """Big Muff clipping stage: transistor, 470k + 470p + a 1N914 pair from collector to base (diodes in feedback)"""
    return Stage(gain=gain, hp=hp, lp=1 / (2 * np.pi * 470e3 * 470e-12) * 2.5, umax=12.0, curve=diode_r(470e3, **SI))


@pedal('BIG MUFF', [('VOLUME', 'A', 0.5), ('TONE', 'B', 0.5), ('SUSTAIN', 'A', 0.6)], 0xC8102E)
def bigmuff(k):
    s = taper(k['SUSTAIN'], 'A')
    pre = band(60, 9000)                                           # input booster (~ +20 dB, folded into the gains)
    st = [muff_stage(10 * 40 * (0.02 + s), 100.0), muff_stage(45.0, 160.0)]
    tone = bilinear(*blend_stack(39e3, 10e-9, 4e-9, 22e3, 100e3, k['TONE'], 100e3), fp=1000)
    return Voicing(st, pre=pre, dc=10.0, tone=[tone], level=8.0 * taper(k['VOLUME'], 'A'))


@pedal('METAL MUFF', [('VOLUME', 'A', 0.5), ('BOTTOM', 'B', 0.6), ('MIDDLE', 'B', 0.4), ('TOP', 'B', 0.6),
                      ('DISTORTION', 'A', 0.6), ('BOOST', 'S', 0.0)], 0x9A9A9A)
def metalmuff(k):
    # ~ two op-amp gain stages into Si diodes to ground (tight + buzzy), active 3-band, TOP BOOST = a treble boost
    pre = rbj('peak', 1200, 4, 0.8)
    st = [Stage(gain=2 + 150 * taper(k['DISTORTION'], 'A'), hp=180.0, lp=9e3, umax=4.0,
                curve=compose(rail(3.6), diode_r(2.2e3, **SI))),
          Stage(gain=8.0, hp=200.0, lp=7e3, umax=4.0, curve=compose(rail(3.6), diode_r(1e3, **SI)))]
    tone = [rbj('low', 120, 15 * (2 * k['BOTTOM'] - 1), 0.7), rbj('peak', 900, 15 * (2 * k['MIDDLE'] - 1), 0.8),
            rbj('high', 3000, 15 * (2 * k['TOP'] - 1) + (8 if k['BOOST'] >= 0.5 else 0), 0.7)]
    return Voicing(st, pre=pre, dc=10.0, tone=tone, level=3.0 * taper(k['VOLUME'], 'A'))


@pedal('METAL ZONE', [('LEVEL', 'A', 0.5), ('LOW', 'B', 0.5), ('HIGH', 'B', 0.5), ('MIDDLE', 'B', 0.5),
                      ('MIDFREQ', 'B', 0.5), ('DIST', 'A', 0.6)], 0x2B2B2B)
def mt2(k):
    # ~ MT-2 (Electrosmash): fixed pre-EQ (low cut + presence), gain stage 1 into diodes in feedback, stage 2 into
    # diodes to ground (the double clipping), then LOW / HIGH shelves (+-15 dB) and the swept mid (200 Hz-5 kHz)
    pre = rbj('peak', 2500, 6, 0.7)
    st = [Stage(gain=4 + 200 * taper(k['DIST'], 'A'), hp=200.0, lp=10e3, umax=12.0, curve=diode_r(220e3, **SI)),
          Stage(gain=12.0, hp=150.0, lp=8e3, umax=4.0, curve=compose(rail(3.6), diode_r(1e3, **SI)))]
    fm = 200 * 25 ** k['MIDFREQ']
    tone = [rbj('low', 100, 15 * (2 * k['LOW'] - 1), 0.7), rbj('peak', fm, 15 * (2 * k['MIDDLE'] - 1), 1.2),
            rbj('high', 5000, 15 * (2 * k['HIGH'] - 1), 0.7)]
    return Voicing(st, pre=pre, dc=10.0, tone=tone, level=3.0 * taper(k['LEVEL'], 'A'))


GE_Q = dict(vcc=9.0, vsat=0.15, vt=VT * 1.3)              # germanium: softer knee (n ~ 1.3)


@pedal('FUZZ FACE', [('VOLUME', 'A', 0.6), ('FUZZ', 'B', 0.8)], 0x1C6BD9)
def fuzzface(k):
    # ~ AC128 pair: Q1 33k collector (high gain, no Re), Q2 8k2 + 470R with the 1k FUZZ pot bypassing its emitter
    f = k['FUZZ']                                                  # FUZZ = how much of the 1k Re is bypassed: AC gain
    st = [Stage(gain=1.0, hp=15.0, umax=0.25, curve=bjt_ce(33e3, 20.0, 0.25e-3, **GE_Q), kb=0.25, env_hz=6.0),
          Stage(gain=0.9 * (0.15 + 0.85 * f), hp=60.0, lp=12e3, umax=1.0,
                curve=bjt_ce(8.67e3, 25.0, 0.6e-3, **GE_Q))]
    return Voicing(st, dc=7.0, tone=[lp1(7000)], level=1.2 * taper(k['VOLUME'], 'A'))


@pedal('FUNERAL', [('VOLUME', 'A', 0.6), ('FUZZ', 'A', 0.8), ('WAH', 'B', 0.35), ('LOW', 'B', 0.7)], 0x5A1E6E)
def funeral(k):
    # doom fuzz (Funeralopolis): a Big Muff core with more gain, the tone stack parked dark, a cocked wah, low boost
    s = taper(k['FUZZ'], 'A')
    pre = band(40, 7000)
    st = [muff_stage(10 * 80 * (0.02 + s), 60.0), muff_stage(60.0, 90.0)]
    tone = [bilinear(*blend_stack(39e3, 10e-9, 4e-9, 22e3, 100e3, 0.25, 100e3), fp=600),
            rbj('peak', 350 * 6 ** k['WAH'], 10, 3.0), rbj('low', 110, 12 * k['LOW'], 0.7)]
    return Voicing(st, pre=pre, dc=7.0, tone=tone, level=6.0 * taper(k['VOLUME'], 'A'))


@pedal('IRON MAN', [('BOOST', 'A', 0.7), ('TREBLE', 'B', 0.6), ('VOLUME', 'A', 0.5)], 0x6E6E50)
def ironman(k):
    # Rangemaster (OC44, 5n input cap = the treble boost) into a cranked Laney preamp stage (12AX7)
    pre = rbj('high', 1500, 14, 0.5)
    st = [Stage(gain=1.0, hp=60.0, umax=0.3, curve=bjt_ce(10e3, 20.0, 0.5e-3, **GE_Q)),
          Stage(gain=0.5 + 6 * taper(k['BOOST'], 'A'), hp=80.0, lp=9e3, umax=8.0, curve=triode_12ax7(), kb=0.15)]
    tone = [rbj('high', 2500, 12 * (k['TREBLE'] - 0.4), 0.6), rbj('peak', 700, -3, 0.8)]
    return Voicing(st, pre=pre, dc=10.0, tone=tone, level=0.05 * taper(k['VOLUME'], 'A'))


@pedal('RADIO', [('TUNE', 'B', 0.5), ('VOLUME', 'A', 0.6)], 0xB08D57)
def radio(k):
    # germanium transistor radio amp (amp voicing): small driver, class-B output with crossover, 4 V of battery,
    # a 2.5" speaker (300 Hz - 3.5 kHz) and its honky cone break-up peak, swept by TUNE (800 Hz - 2 kHz)
    pre = rbj('hp', 250, 0, 0.7)
    st = [Stage(gain=6.0, hp=200.0, lp=6e3, umax=2.0, curve=xover(0.12, 1.1))]
    tone = [rbj('peak', 800 * 2.5 ** k['TUNE'], 9, 2.5), rbj('lp', 3500, 0, 0.9), rbj('hp', 300, 0, 0.7)]
    return Voicing(st, pre=pre, dc=20.0, tone=tone, level=2.0 * taper(k['VOLUME'], 'A'))


def knobs_default(name):
    return {l: d for l, _, d in PEDALS[name]['knobs']}


# ---------------------------------------------------------------- float model (same structure, exact curves)
def run(x, name, kn=None, exact=False):
    """float model of the DSP structure (table domain clamp at +-umax, knob-fitted curves) or, exact=True, the
    circuit itself: every stage with its own knob-dependent curve and no clamp."""
    v = PEDALS[name]['voice']({**knobs_default(name), **(kn or {})})
    pdc = float(np.exp(-2 * np.pi * v.dc / FS))
    y = ss.lfilter([1, -1], [1, -pdc], x)
    dry = y
    if v.pre is not None:
        y = ss.lfilter(*v.pre, y) + v.predry * y
    u4 = ss.upfirdn(H_OS, y, up=OS)[:len(y) * OS]
    post_all = v.post
    for st in v.stages:
        php = onepole_hp_pole(st.hp)
        c2 = 1.0 if st.lp is None else 1 - np.exp(-2 * np.pi * st.lp / FS4)
        alpha, post = fit_scale(st) if (st.fit and not exact) else (1.0, 1.0)
        post_all *= post
        ec = 1 - np.exp(-2 * np.pi * st.env_hz / FS4)
        hpx = hpy = lpy = env = 0.0
        out = np.empty_like(u4)
        g = st.gain * alpha
        for i, a in enumerate(u4):
            hv = a - (1 - 2.0 ** -23) * hpx + php * hpy if st.hp is not None else a
            hpx, hpy = a, hv
            lpy = lpy + c2 * (g * hv - lpy)
            if not exact:                                    # the DSP holds the LPF state in the table domain
                lpy = min(max(lpy, -st.umax), st.umax)
            w = lpy + st.bias - st.kb * st.umax * env
            env += ec * (min(abs(w) / st.umax, 1.0) - env)
            out[i] = w
        if exact:
            u4 = st.curve(out)
        else:
            u4 = (st.tcurve if st.fit else st.curve)(np.clip(out, -st.umax, st.umax))
    d = ss.upfirdn(H_OS / OS, u4[OS - 1:], down=OS)[:len(y)]      # the DSP decimates at the last of the 4
    d = np.concatenate([d, np.zeros(len(y) - len(d))])
    dry = np.concatenate([np.zeros(DRY_D), dry[:len(dry) - DRY_D]])   # the clean path waits for the FIRs
    y = post_all * d + v.blend * dry
    for b, a in v.tone:
        y = ss.lfilter(b, a, y)
    return y * v.level / OUT_V


if __name__ == '__main__':
    import sys
    import amp_model as am
    name = sys.argv[1] if len(sys.argv) > 1 else 'TUBE SCREAMER'
    x = am.di_riff()[:3 * FS] * 2.0
    y = run(x, name)
    print('%s: out peak %.3f rms %.3f' % (name, np.abs(y).max(), np.sqrt(np.mean(y ** 2))))
    if len(sys.argv) > 2:
        from scipy.io import wavfile
        wavfile.write(sys.argv[2], FS, (np.clip(y, -1, 1) * 32767).astype(np.int16))
