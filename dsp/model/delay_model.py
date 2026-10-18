"""DELAY: half-rate (22.05 kHz) delay line, DSP-faithful (integer) model. Mirrors fx_delay in dsp/vocal3.py.

Buffer X:$03C000-$03FFFF (16K ticks = up to ~740 ms), pointer moves down one word per tick (every 2nd frame).
  tick (frame B): xin = (x + x_prev)/2 ; pos = TIME + WOW*lfo ; z = sum over the HEADS mask (bit k-1 = head k) of
                  buf[k*pos] (interpolated, saturating sum; HEADS 0 = head 1 only) ; lp = tone LP(z) ;
                  fb = SAT ? softclip(lp) : lp ; buf[0] = xin + FB*fb ;
                  wet = TAPS ? 0.4 t1 + 0.55 t2 + 0.75 t3 + lp (taps at T/4, T/2, 3T/4) : lp
  output        : B frames give the new wet, A frames (wet_k + wet_k-1)/2 ; ducking: level = WET*(1 - DUCK*min(1, 4 env))
Params X:$0290: +0 TIME (int ticks, 1..16000), +1 FB, +2 WET, +3 KT (tone LP, $7FFFFF = open), +4 DUCK, +5 TAPS (int),
+6 WOW (int ticks of depth), +7 SAT (int 0/1), +8 KW (LFO rate), +9 HEADS (int mask: bit 0 = head at T, bit 1 = 2T,
bit 2 = 3T, tape-echo style: the heads sum feeds both the output and the feedback; 0 = head 1 only; keep 3T < 16380).
"""
import numpy as np
from reverb_model import q, s24, ld, mpy, st, dmul, M24

Q = 1 << 23
FS2 = 22050
NBUF = 16384
DECD = q(float(np.exp(-1 / (0.12 * 44100))))           # ducking envelope release ~120 ms
TAPG = [q(0.4), q(0.55), q(0.75)]
TAPK = [q(0.25), q(0.5), q(0.75)]


def ms(t): return int(round(t * FS2 / 1000))


def params(ms_=110, fb=0.0, wet=0.35, tone=0.6, duck=0.0, taps=0, wow=0, sat=0, wow_hz=0.7, heads=0):
    return [min(NBUF - 40, max(1, ms(ms_))), q(fb), q(wet), q(tone), q(duck), int(taps), int(wow), int(sat),
            q(2 * np.pi * wow_hz / FS2), int(heads)]


PRESETS = {
    'SLAP': params(110, 0.0, 0.35, 0.7),
    'TEMPO': params(500, 0.35, 0.3, 0.5),
    'DOTTED': params(375, 0.4, 0.3, 0.5),
    'DUCKING': params(500, 0.35, 0.4, 0.5, duck=0.8),
    'TAPE': params(500, 0.8, 0.35, 0.35, wow=6, sat=1),
    'MULTI': params(720, 0.3, 0.35, 0.45, taps=1),
    'SPACE': params(150, 0.25, 0.35, 0.4, wow=3, sat=1, heads=7),        # RE-201 style: heads 1+2+3
}


class Delay:
    def __init__(self, prm=None):
        self.p = list(prm or PRESETS['SLAP'])
        self.buf = [0] * NBUF
        self.ptr = 0
        self.ph = 0
        self.xp = self.lp = self.wo = self.wop = self.env = 0
        self.s, self.c = 0, Q - 1

    def rd(self, d): return s24(self.buf[(self.ptr + d) & (NBUF - 1)])

    def step(self, x):
        T, fb, wet, kt, duck, taps, wow, sat, kw, heads = (list(self.p) + [0])[:10]
        self.env = st(max(ld(abs(x)), mpy(DECD, self.env)))                   # ducking envelope
        if self.ph == 1:                                                       # tick
            xin = st((ld(x) + ld(self.xp)) >> 1)
            self.s = st(ld(self.s) + mpy(kw, self.c)); self.c = st(ld(self.c) - mpy(kw, self.s))
            pos = (T << 24) + mpy(wow, self.s)
            z, m = 0, heads or 1
            for k in (1, 2, 3):
                if m & 1:
                    di, fr = (k * pos) >> 24, ((k * pos) & M24) >> 1
                    z0, z1 = self.rd(di), self.rd(di + 1)
                    z = st(ld(z) + ld(st(ld(z0) + mpy(fr, st(ld(z1) - ld(z0))))))
                m >>= 1
            self.lp = st(ld(self.lp) + mpy(kt, st(ld(z) - ld(self.lp))))
            f = self.lp
            if sat:
                v3 = st(mpy(f, st(mpy(f, f))))
                f = st(2 * (mpy(q(0.75), f) - mpy(q(0.25), v3)))
            self.buf[self.ptr] = st(ld(xin) + mpy(fb, f)) & M24
            acc = ld(self.lp)
            if taps:
                for g, k in zip(TAPG, TAPK):
                    acc += mpy(g, self.rd(dmul(k, T)))
            self.wop, self.wo = self.wo, st(acc)
            y = self.wo
            self.ptr = (self.ptr - 1) & (NBUF - 1)
        else:
            y = st((ld(self.wo) + ld(self.wop)) >> 1)
        self.ph ^= 1
        self.xp = x
        e4 = st(ld(self.env) << 2)
        g = st(mpy(wet, st(ld(Q - 1) - mpy(duck, e4))))
        return st(ld(x) + mpy(g, y))

    def run(self, xs):
        return np.array([self.step(int(v)) for v in xs])


if __name__ == '__main__':
    FS = 44100
    x = np.zeros(int(FS * 1.6)); x[100] = 0.5
    xi = np.round(x * Q).astype(int)
    for name, prm in PRESETS.items():
        y = Delay(prm).run(xi) / Q
        pk = np.argsort(-np.abs(y[200:]))[:3] + 200
        print('%-8s first echoes at %s ms  peak %.3f' % (name, sorted((pk - 100) * 1000 // FS), np.abs(y[200:]).max()))
