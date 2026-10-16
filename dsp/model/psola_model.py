"""PSOLA: pitch-synchronous grains for FORMANT (formants move, pitch stays) and OCTAVE (pitch moves, formants stay).

Float prototype to settle the algorithm before the DSP version.
  marks   : one pitch mark per period = the biggest |x| in each block of P input samples (P = detected period)
  grains  : every Pout = P/p output samples a grain starts, centred on the mark nearest (now - D), 2P long
            (triangle window, +-P around the mark), read at rate f (formant ratio) with linear interpolation
  p = pitch ratio (0.5 = octave down), f = formant ratio (0.8 = giant, 1.3 = chipmunk). Up to 4 grains overlap.
"""
import numpy as np

FS = 44100


class Psola:
    def __init__(self, p=1.0, f=1.0, D=1200, nbuf=4096):
        self.p, self.f, self.D = p, f, D
        self.buf = np.zeros(nbuf)
        self.n = nbuf
        self.w = 0
        self.marks = []            # absolute sample positions
        self.bmax, self.bpos, self.bcnt = 0.0, 0, 0
        self.timer = 0.0
        self.grains = []           # [src_centre, t (output samples since start), P]

    def step(self, x, P):
        P = max(40, min(int(P), 600))
        self.buf[self.w % self.n] = x
        # marks: max |x| per block of P samples
        if abs(x) > self.bmax:
            self.bmax, self.bpos = abs(x), self.w
        self.bcnt += 1
        if self.bcnt >= P:
            self.marks.append(self.bpos)
            self.marks = self.marks[-16:]
            self.bmax, self.bcnt = 0.0, 0
        # schedule
        self.timer -= 1
        if self.timer <= 0:
            self.timer += P / self.p
            want = self.w - self.D
            m = min(self.marks, key=lambda v: abs(v - want)) if self.marks else want
            self.grains.append([m, -P, P])
            self.grains = self.grains[-4:]
        y = 0.0
        keep = []
        for g in self.grains:
            m, t, Pg = g
            if t < Pg:
                wv = 1 - abs(t) / Pg
                pos = m + t * self.f
                i = int(np.floor(pos)); fr = pos - i
                b0 = self.buf[i % self.n]; b1 = self.buf[(i + 1) % self.n]
                y += wv * (b0 + fr * (b1 - b0))
                g[1] += 1
                keep.append(g)
        self.grains = keep
        self.w += 1
        return y

    def run(self, xs, P):
        return np.array([self.step(v, P) for v in xs])


def env_centroid(y, f0):
    """spectral centroid of the harmonic amplitudes up to 4 kHz (formant position proxy)"""
    s = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    fr = np.fft.rfftfreq(len(y), 1 / FS)
    m = fr < 4000
    return (s[m] * fr[m]).sum() / s[m].sum()


if __name__ == '__main__':
    import autotune_model as am
    f0 = 150.0
    # a voice with real formants: pulse train through 3 resonances (700, 1200, 2600 Hz)
    from scipy.signal import lfilter
    t = np.arange(int(FS * 1.0))
    pulses = np.zeros(len(t)); pulses[(np.arange(0, len(t), FS / f0)).astype(int)] = 1.0
    v = pulses
    for fc, bw in ((700, 90), (1200, 110), (2600, 160)):
        r = np.exp(-np.pi * bw / FS); th = 2 * np.pi * fc / FS
        v = lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], v)
    v = 0.3 * v / np.abs(v).max()
    P = FS / f0
    seg = slice(20000, 40000)
    print('input : f0 %.1f Hz  centroid %.0f Hz' % (am.pitch_of(v[seg]), env_centroid(v[seg], f0)))
    for name, p, f in (('OCTAVE DOWN', 0.5, 1.0), ('GIANT', 1.0, 0.78), ('CHIPMUNK', 1.0, 1.35), ('M->F', 1.33, 1.18)):
        y = Psola(p, f).run(v, P)
        print('%-11s: f0 %.1f Hz  centroid %.0f Hz  rms %.3f (in %.3f)' % (
            name, am.pitch_of(y[seg]), env_centroid(y[seg], f0), y[seg].std(), v[seg].std()))
