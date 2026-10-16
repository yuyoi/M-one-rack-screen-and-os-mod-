"""PSOLA engine, DSP-faithful model (one instance = FORMANT or OCTAVE). Mirrors fx_psola in dsp/vocal2.py.

Per sample:
  period  : P = PF >> 13 (TUNE detector readout X:$0D, Q23 of P/256 at 11025 Hz), clamped 40..600, 200 if PF = 0.
            invP = 1/P (Q23) from a table in SRAM (X:INVTAB + P, vocal2_tab.hex).
  ring    : x -> X:RING + (W & 4095) (external SRAM), W counts samples forever (24-bit).
  marks   : the biggest |x| in each block of P samples -> MARKS[8] (absolute positions).
  timer   : 48-bit (A1 = samples, A0 = fraction). -1 per sample; at <= 0: += Pout = P/p and start a grain.
  grain   : slot (round robin of 4) gets ACT = 2P, TC = P, WV = 0, DW = +invP, POS = mark - P*f (48-bit), where
            mark = the MARKS entry nearest W - D, D = P + P*f + 64.
  slots   : y += WV * interp(POS); POS += f; WV += DW; TC-- (0 -> DW = -DW); ACT-- (0 -> idle).
  out     : y * (1/p), then wet/dry.
Params (X long): +0 INVP2 = 1/(2p), +1 F2 = f/2, +2 WET, +3 GAIN2 = gain/2 (Q23; level vs pitch ratio).
"""
import numpy as np

Q = 1 << 23
M24 = (1 << 24) - 1
NRING, NM, NS = 4096, 4, 3              # 3 grain slots: enough for p <= 1.5 (more pitch-up cuts grains short)
INVTAB = 0x031600                        # SRAM: floor((2^23 - 1) / P) for P = 0..600


def s24(v):
    v &= M24
    return v - (1 << 24) if v >> 23 else v


def st(v):
    """saturate + truncate to Q23 (what a move from an accumulator does)"""
    v = min(max(v, -1.0), (Q - 1) / Q)
    return np.floor(v * Q) / Q


def inv_table():
    return [0] + [((1 << 23) - 1) // P for P in range(1, 601)]


def recip(P):
    """1/P as Q23, as the table holds it"""
    return ((1 << 23) - 1) // P


class PsolaDSP:
    def __init__(self, invp2=0x400000, f2=0x400000, wet=0x7FFFFF, gain2=0x400000):
        self.p = [invp2, f2, wet, gain2]
        self.ring = [0] * NRING            # 24-bit words
        self.W = 0
        self.bmax = 0; self.bpos = 0; self.bcnt = 0
        self.marks = [0] * NM; self.mi = 0
        self.tim = 0                       # 48-bit fixed: samples * 2^24
        self.pc = -1; self.invp = 0
        self.slot = [dict(act=0, tc=0, wv=0, dw=0, pos=0) for _ in range(NS)]   # pos 48-bit (samples * 2^24)
        self.rr = 0

    def step(self, xq, PF):
        """xq: input as Q23 int; PF: detector readout (int). Returns output Q23 int."""
        invp2, f2, wet, gain2 = self.p
        P = (PF & M24) >> 13 if PF else 200
        P = min(max(P, 40), 600)
        if P != self.pc:
            self.pc, self.invp = P, recip(P)
        f48 = f2 << 2                                  # f in samples * 2^24 (f2 = f/2 in Q23)
        Pf = (P * f48) >> 24                           # integer part of P*f (samples)
        Pf48 = P * f48                                 # P*f, 48-bit
        # ring write + marks
        self.ring[self.W & (NRING - 1)] = xq & M24
        ax = abs(s24(xq))
        if ax > self.bmax:
            self.bmax, self.bpos = ax, self.W
        self.bcnt += 1
        if self.bcnt >= P:
            self.marks[self.mi] = self.bpos & M24
            self.mi = (self.mi + 1) & (NM - 1)
            self.bmax = 0; self.bcnt = 0
        # scheduler
        self.tim -= 1 << 24
        if self.tim <= 0:
            pout48 = (P * invp2 * 2) << 1              # P/p in samples * 2^24  (P * (1/(2p)) * 2, Q23 -> *2^24)
            self.tim += pout48
            want = (self.W - (P + Pf + 64)) & M24
            best, bd = 0, None
            for m in self.marks:
                d = abs(s24(m - want))
                if bd is None or d < bd:
                    best, bd = m, d
            s = self.slot[self.rr]
            self.rr = 0 if self.rr + 1 == NS else self.rr + 1
            s.update(act=2 * P, tc=P, wv=0, dw=self.invp, pos=(best << 24) - Pf48)
        # grains
        acc = 0                                        # 56-bit accumulator in units of 2^-46 (Q23 * Q23)
        for s in self.slot:
            if s['act'] <= 0:
                continue
            i = (s['pos'] >> 24) & (NRING - 1)
            fr = (s['pos'] & M24) >> 1                 # Q23 fraction
            b0 = s24(self.ring[i]); b1 = s24(self.ring[(i + 1) & (NRING - 1)])
            d = b1 - b0
            dq = max(-Q, min(Q - 1, d))                # sat(b1 - b0)
            v = b0 + ((fr * dq * 2) >> 24)             # b0 + fr*(b1-b0), truncated to Q23
            v = max(-Q, min(Q - 1, v))
            acc += 2 * s['wv'] * v                     # mac
            s['pos'] += f48
            s['wv'] = s['wv'] + s['dw']
            s['wv'] = max(-Q, min(Q - 1, s['wv']))
            s['tc'] -= 1
            if s['tc'] == 0:
                s['dw'] = -s['dw']
            s['act'] -= 1
        self.W = (self.W + 1) & M24
        y = acc >> 24                                  # A1 (truncate)
        y = max(-Q, min(Q - 1, y))
        g = (2 * y * gain2 * 2) >> 24                  # y * gain : mpy y,gain2 ; asl
        g = max(-Q, min(Q - 1, g))
        dx = max(-Q, min(Q - 1, g - s24(xq)))          # wet/dry
        o = s24(xq) + ((2 * dx * wet) >> 24)
        return max(-Q, min(Q - 1, o))


def params(p, f, wet=1.0, gain=None):
    """gain None: level-matched to the input for a voiced signal (1/sqrt(p) is close)"""
    g = gain if gain is not None else min(1.9, p ** -0.5 if p < 1 else 1.0 + 0.6 * (p - 1))
    c = lambda v: int(round(min(v, 1 - 1 / Q) * Q))
    return [c(0.5 / p), c(f / 2), c(wet), c(g / 2)]


if __name__ == '__main__':
    import autotune_model as am
    from psola_model import env_centroid
    from scipy.signal import lfilter
    FS = 44100
    f0 = 150.0
    t = np.arange(int(FS * 1.0))
    pulses = np.zeros(len(t)); pulses[(np.arange(0, len(t), FS / f0)).astype(int)] = 1.0
    v = pulses
    for fc, bw in ((700, 90), (1200, 110), (2600, 160)):
        r = np.exp(-np.pi * bw / FS); th = 2 * np.pi * fc / FS
        v = lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], v)
    v = 0.3 * v / np.abs(v).max()
    xq = np.round(v * Q).astype(int)
    PF = int(round(FS / f0 / 1024 * Q))
    seg = slice(20000, 40000)
    print('input : f0 %.1f  centroid %.0f' % (am.pitch_of(v[seg]), env_centroid(v[seg], f0)))
    for name, p, f in (('OCTAVE DOWN', 0.5, 1.0), ('GIANT', 1.0, 0.78), ('CHIPMUNK', 1.0, 1.35), ('M->F', 1.33, 1.18),
                       ('THRU', 1.0, 1.0)):
        e = PsolaDSP(*params(p, f))
        y = np.array([e.step(int(x), PF) for x in xq]) / Q
        print('%-11s: f0 %.1f  centroid %.0f  rms %.3f (in %.3f)' % (
            name, am.pitch_of(y[seg]), env_centroid(y[seg], f0), y[seg].std(), v[seg].std()))
