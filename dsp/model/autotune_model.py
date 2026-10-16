"""Bit-faithful-ish model of the M-One autotune before it becomes DSP56300 code.

Stages (same structure the DSP will run):
  1. pitch shifter: delay line, two read heads W/2 apart, triangle crossfade, linear interpolation
  2. pitch detector: 4x decimation, AMDF over lags 11..140 (79-1000 Hz), YIN-style normalisation, parabolic refine
  3. snap: detected period -> nearest note (chromatic or scale mask) -> ratio r -> retune smoothing

All state uses the DSP's formats: 24-bit fractions (Q23 ints), integer ring indices.
Run: py -3.10 autotune_model.py   (prints cents error per test case)
"""
import numpy as np

FS = 44100
Q = 1 << 23

# ---------------------------------------------------------------- shifter
L_BUF = 4096          # ring (power of 2)
W = 2048              # crossfade window = max delay of a head (46 ms)


def tri(dfrac):       # triangle gain, dfrac in [0, Q)
    return Q - abs(2 * dfrac - Q)


class Shifter:
    def __init__(self):
        self.buf = np.zeros(L_BUF, np.int64)
        self.w = 0
        self.d = 0        # head 1 delay as Q23 fraction of W

    def step(self, x, inc):
        """x: Q23 sample, inc: delay increment per sample in Q23-of-W units = (1-r)*Q/W"""
        self.buf[self.w & (L_BUF - 1)] = x
        out = 0
        for d in (self.d, (self.d + Q // 2) % Q):
            D = d * W                                  # delay in samples, Q23 fixed
            di, df = D >> 23, D & (Q - 1)
            i0 = (self.w - di) & (L_BUF - 1)
            i1 = (i0 - 1) & (L_BUF - 1)
            s = self.buf[i0] + ((self.buf[i1] - self.buf[i0]) * df >> 23)   # linear interp
            out += s * tri(d) >> 23
        self.d = (self.d + inc) % Q
        self.w += 1
        return out


# ---------------------------------------------------------------- detector
DEC = 4
FSD = FS // DEC        # 11025
TMIN, TMAX = 8, 140    # lags at FSD: 1378 Hz .. 79 Hz
NWIN = 256
HOP = 128              # decimated samples between detections (11.6 ms)


def detect(seg):
    """seg: decimated samples (ints), len >= NWIN + TMAX. Returns period in decimated samples (float) or None."""
    x = seg[-(NWIN + TMAX):].astype(np.int64)
    D = np.array([np.abs(x[:NWIN] - x[t:t + NWIN]).sum() for t in range(TMIN, TMAX + 1)], np.int64)
    cum = np.cumsum(D)
    taus = np.arange(TMIN, TMAX + 1)
    nd = D * (taus - TMIN + 1) / np.maximum(cum, 1)    # CMNDF over the searched lags
    th = 0.25
    k = None
    for i in range(len(nd) - 1):
        if nd[i] < th:
            while i + 1 < len(nd) and nd[i + 1] < nd[i]:
                i += 1
            k = i
            break
    if k is None:
        k = int(np.argmin(nd))
        if nd[k] > 0.5:
            return None                                 # unvoiced
    if 0 < k < len(D) - 1:                              # parabolic refine on D
        a, b, c = D[k - 1], D[k], D[k + 1]
        den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den else 0.0
    else:
        off = 0.0
    return TMIN + k + off


# ---------------------------------------------------------------- snap
def note_period(n):    # MIDI note -> period at FSD
    return FSD / (440.0 * 2 ** ((n - 69) / 12))


def snap(P, mask=0xFFF):
    """nearest allowed note (mask bit k = pitch class k, C=0) -> target period"""
    n = 69 + 12 * np.log2(FSD / P / 440.0)
    best = None
    for cand in range(int(np.floor(n)) - 6, int(np.ceil(n)) + 7):
        if mask >> (cand % 12) & 1:
            if best is None or abs(cand - n) < abs(best - n):
                best = cand
    return note_period(best), best


# ---------------------------------------------------------------- whole chain
def autotune(x, speed=0.02, mask=0xFFF):
    """x: float signal -1..1. speed: retune smoothing per detection (1 = instant). Returns float output."""
    sh = Shifter()
    xi = np.round(x * (Q - 1)).astype(np.int64)
    dec = []
    acc = 0
    r = 1.0
    r_target = 1.0
    out = np.zeros(len(x))
    for n, s in enumerate(xi):
        acc += s
        if n % DEC == DEC - 1:
            dec.append(acc // DEC)
            acc = 0
            if len(dec) >= NWIN + TMAX and len(dec) % HOP == 0:
                P = detect(np.array(dec[-(NWIN + TMAX):]))
                if P:
                    Pt, _ = snap(P, mask)
                    r_target = P / Pt                   # >1 = shift up
        r += (r_target - r) * speed / HOP / DEC * 4     # per-sample smoothing
        inc = int(round((1 - r) * Q / W))
        out[n] = sh.step(s, inc) / Q
    return out


def pitch_of(y, fs=FS):
    """robust pitch estimate of a steady segment (autocorrelation + parabolic)"""
    y = y - y.mean()
    c = np.correlate(y, y, 'full')[len(y) - 1:]
    lo, hi = int(fs / 1100), int(fs / 70)
    k = lo + int(np.argmax(c[lo:hi]))
    a, b, d = c[k - 1], c[k], c[k + 1]
    k = k + 0.5 * (a - d) / (a - 2 * b + d)
    return fs / k


def voice(f0, secs=1.5, vib=0.0):
    t = np.arange(int(FS * secs)) / FS
    f = f0 * 2 ** (vib * np.sin(2 * np.pi * 5.5 * t) / 12)
    ph = 2 * np.pi * np.cumsum(f) / FS
    s = sum(np.sin(k * ph) / k ** 1.2 for k in range(1, 15))
    return 0.25 * s / np.abs(s).max()


def cents(f, ref):
    return 1200 * np.log2(f / ref)


if __name__ == '__main__':
    print('shifter alone (fixed ratios, 220 Hz in):')
    for semis in (-12, -5, 7, 12):
        r = 2 ** (semis / 12)
        sh = Shifter()
        x = np.round(voice(220, 1.0) * (Q - 1)).astype(np.int64)
        inc = int(round((1 - r) * Q / W))
        y = np.array([sh.step(s, inc) for s in x]) / Q
        f = pitch_of(y[20000:40000])
        print('  %+3d st  expect %7.2f Hz  got %7.2f Hz  err %+5.1f c' % (semis, 220 * r, f, cents(f, 220 * r)))
    print('detector (decimated AMDF/YIN):')
    for f0 in (82.4, 110, 196, 261.6, 440, 659.3, 880):
        x = voice(f0, 0.3)
        xi = np.round(x * (Q - 1)).astype(np.int64)
        d = xi[:len(xi) // 4 * 4].reshape(-1, 4).mean(1)
        P = detect(d)
        fd = FSD / P if P else 0
        print('  %6.1f Hz -> %7.2f Hz  err %+5.1f c' % (f0, fd, cents(fd, f0) if fd else float('nan')))
    print('full autotune (chromatic, fast retune):')
    for f0 in (215.0, 233.0, 300.0, 151.0):
        x = voice(f0, 2.0)
        y = autotune(x, speed=1.0)
        f = pitch_of(y[60000:84000])
        n = 69 + 12 * np.log2(f / 440)
        tgt = 440 * 2 ** ((round(n) - 69) / 12)
        print('  in %6.1f Hz (%+5.1f c off grid) -> out %7.2f Hz, %+5.1f c from note %d' % (
            f0, cents(f0, 440 * 2 ** ((round(69 + 12 * np.log2(f0 / 440)) - 69) / 12)), f, cents(f, tgt), round(n)))
