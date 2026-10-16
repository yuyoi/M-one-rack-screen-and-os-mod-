"""RADIO: lo-fi voice machine with 6 voiced modes. Reference model for fx_radio in dsp/vocal.py.

Chain per sample (every mode runs the same blocks; the mode table sets them):
  squelch detector on the input -> HP1 HP2 PK (band + resonance) -> leveler (AGC) + makeup -> drive (gain, bias,
  cubic soft clip, DC block) -> crush (sample-and-hold rate, bit mask) -> + hiss (+ squelch burst) -> LP1 LP2 ->
  wobble delay (wow + flutter LFOs, direct/delay mix = horn comb for MEGAPHONE) -> + crackle -> gate -> out gain ->
  wet/dry.
Params (X:$0210 block): +0 mode (int 0-5), +1 wet, +2 drive trim, +3 noise trim (trims: $400000 = as voiced).
Mode tables (48 words each) live in external SRAM X:$031000 (loaded by `boot` as radio_tab.hex) and are copied to
Y when the mode param changes.
"""
import numpy as np
import vox_model as vm

FS = 44100
Q = 1 << 23
q23, sat = vm.q23, vm.sat
MODES = ['TELEPHONE', 'MEGAPHONE', 'AM RADIO', 'WALKIE', 'CASSETTE', 'VINYL']
D0 = 40                     # wobble delay centre, samples (1 ms)
DSQ = float(np.exp(-1 / (0.15 * FS)))      # squelch detector release
KDC = vm.KDC
NTAB = 48
RING = 256


def hz(f): return 2 * np.pi * f / FS


def lp(f, q=0.707): return ('lp', f, q, 0)


def mode_specs():
    """per mode: filters (HP1 HP2 PK LP1 LP2) and the scalar table, in plain units"""
    S = []
    S.append(dict(  # 0 TELEPHONE: 300-3400 Hz 4th order, earpiece honk, 8 kHz sample-and-hold, 10-bit, AGC
        f=[('hp', 300, 0.707, 0), ('hp', 300, 0.707, 0), ('pk', 1700, 1.2, 4), lp(3400), lp(3400)],
        drv=1.5, bias=0.03, sr=8000, bits=10, hiss=0.003, hk=6000, cth=0, camp=0, cdec=0.9,
        wow=(0, 0.5), flut=(0, 6), sq=0, sqt=0.01, blev=0, bn=0, T=0.25, mk=2.0, outg=0.6, dmix=0.0, dly=1.0))
    S.append(dict(  # 1 MEGAPHONE: 500 Hz-4 kHz, big horn peak, hard asymmetric breakup, 0.5 ms horn comb
        f=[('hp', 500, 0.8, 0), ('hp', 500, 0.8, 0), ('pk', 1800, 2.5, 10), lp(4000, 0.9), lp(4000, 0.9)],
        drv=6.0, bias=0.18, sr=0, bits=24, hiss=0.0, hk=5000, cth=0, camp=0, cdec=0.9,
        wow=(0, 0.5), flut=(0, 6), sq=0, sqt=0.01, blev=0, bn=0, T=0.3, mk=1.5, outg=0.55, dmix=1.0, dly=0.55,
        d0=22))
    S.append(dict(  # 2 AM RADIO: 200 Hz-4.5 kHz, boxy cabinet, tube-ish drive, static + light crackle
        f=[('hp', 200, 0.707, 0), ('hp', 200, 0.707, 0), ('pk', 1000, 0.7, 3), lp(4500), lp(4500)],
        drv=2.0, bias=0.08, sr=0, bits=24, hiss=0.008, hk=3000, cth=1 / 9000, camp=0.12, cdec=0.6,
        wow=(0, 0.5), flut=(0, 6), sq=0, sqt=0.01, blev=0, bn=0, T=0.2, mk=2.0, outg=0.55, dmix=0.0, dly=1.0))
    S.append(dict(  # 3 WALKIE / CB: narrow, harsh, 11 kHz hold, 7-bit, crushed AGC, squelch "kshh" when you stop
        f=[('hp', 400, 0.707, 0), ('hp', 400, 0.707, 0), ('pk', 2200, 1.5, 6), lp(3000), lp(3000)],
        drv=4.0, bias=0.1, sr=11025, bits=7, hiss=0.012, hk=4000, cth=0, camp=0, cdec=0.9,
        wow=(0, 0.5), flut=(0, 6), sq=1, sqt=0.015, blev=0.35, bn=0.2, T=0.15, mk=3.0, outg=0.55, dmix=0.0,
        dly=1.0))
    S.append(dict(  # 4 CASSETTE: head bump, soft tape saturation, 9 kHz roll-off, hiss, wow 0.6 Hz + flutter 7 Hz
        f=[('hp', 45, 0.707, 0), ('hp', 45, 0.707, 0), ('pk', 100, 0.7, 3), lp(9000, 0.6), lp(9000, 0.6)],
        drv=1.2, bias=0.02, sr=0, bits=24, hiss=0.005, hk=8000, cth=0, camp=0, cdec=0.9,
        wow=(24, 0.6), flut=(0.6, 7), sq=0, sqt=0.01, blev=0, bn=0, T=1.0, mk=1.0, outg=0.7, dmix=0.0, dly=1.0))
    S.append(dict(  # 5 VINYL 78: gramophone horn, 250 Hz-5 kHz, heavy crackle + surface noise, 78 rpm wow
        f=[('hp', 250, 0.707, 0), ('hp', 250, 0.707, 0), ('pk', 1500, 0.8, 4), lp(5000), lp(5000)],
        drv=1.3, bias=0.0, sr=0, bits=24, hiss=0.004, hk=6000, cth=1 / 1200, camp=0.45, cdec=0.55,
        wow=(8, 1.3), flut=(0, 6), sq=0, sqt=0.01, blev=0, bn=0, T=1.0, mk=1.0, outg=1.0, dmix=0.0, dly=1.0))
    return S


# table layout (Y, 48 words): 25 coefs, then these scalars in this order
SCAL = ['DRV', 'BIAS', 'INC', 'MASK', 'HISS', 'HK', 'CTH', 'CAMP', 'CDEC', 'DW', 'KW', 'DF', 'KF', 'SQ', 'SQT',
        'BLEV', 'BN', 'T', 'MK', 'OUTG', 'DMIX', 'DLY', 'D0']
SI = {n: 25 + i for i, n in enumerate(SCAL)}


def mode_table(m):
    s = mode_specs()[m]
    w = []
    for spec in s['f']:
        b0, b1, b2, a1, a2 = vm.biquad(*spec)
        w += [c & 0xFFFFFF for c in (q23(b0 / 2), q23(b1 / 2), q23(b2 / 2), q23(-a1 / 2), q23(-a2 / 2))]
    v = dict(
        DRV=q23(s['drv'] / 8), BIAS=q23(s['bias']),
        INC=q23(s['sr'] / FS) if s['sr'] else 0,
        MASK=(0xFFFFFF << (24 - s['bits'])) & 0xFFFFFF,
        HISS=q23(s['hiss']), HK=q23(1 - np.exp(-hz(s['hk']))),
        CTH=int(s['cth'] * Q), CAMP=q23(s['camp']), CDEC=q23(s['cdec']),
        DW=q23(s['wow'][0] / RING), KW=q23(hz(s['wow'][1])), DF=q23(s['flut'][0] / RING), KF=q23(hz(s['flut'][1])),
        SQ=s['sq'], SQT=q23(s['sqt']), BLEV=q23(s['blev']), BN=int(s['bn'] * FS),
        T=q23(s['T']), MK=q23(s['mk'] / 4), OUTG=q23(s['outg'] / 2), DMIX=q23(s['dmix']), DLY=q23(s['dly']),
        D0=q23(s.get('d0', D0) / RING))
    w += [v[n] & 0xFFFFFF for n in SCAL]
    w += [0] * (NTAB - len(w))
    assert len(w) == NTAB
    return w


def s24(v):
    v &= 0xFFFFFF
    return v - (1 << 24) if v >> 23 else v


class Radio:
    """exact=True: truncate every 24-bit store like the DSP. Params: mode, wet, drive trim, noise trim (Q23 ints)."""

    def __init__(self, exact=True, mode=0, wet=0x7FFFFF, dtrim=0x400000, ntrim=0x400000):
        self.q = vm.st if exact else sat
        self.p = [mode, wet, dtrim, ntrim]
        self.cur = -1
        self.ring = [0.0] * RING
        self.ein = self.env = self.dcl = self.held = self.hl = self.clk = 0.0
        self.ph = self.w = self.btimer = self.popen = 0
        self.s1 = self.s2 = 0.0
        self.c1 = self.c2 = (Q - 1) / Q
        self.g = (Q - 1) / Q
        self.lfsr = 0x5A5A5A

    def load(self, m):
        t = mode_table(m)
        self.t = [s24(v) / Q for v in t]
        self.ti = t
        self.c = self.t[:25]
        self.st = [[0.0] * 4 for _ in range(5)]
        self.cur = m

    def bq(self, k, x):
        b0, b1, b2, na1, na2 = self.c[5 * k:5 * k + 5]
        s = self.st[k]
        y = self.q(2 * (b0 * x + b1 * s[0] + b2 * s[1] + na1 * s[2] + na2 * s[3]))
        self.st[k] = [x, s[0], y, s[2]]
        return y

    def rnd(self):
        c = self.lfsr >> 23
        self.lfsr = (self.lfsr << 1) & 0xFFFFFF
        if c:
            self.lfsr ^= 0xC20001
        return self.lfsr

    def step(self, x):
        q = self.q
        mode = min(max(self.p[0], 0), len(MODES) - 1)
        if mode != self.cur:
            self.load(mode)
        T = lambda n: self.t[SI[n]]
        dry = x
        self.ein = q(max(abs(x), self.ein * q23(DSQ) / Q))                  # squelch detector
        for k in range(3):
            x = self.bq(k, x)
        y = q(x * self.g)                                                    # leveler
        e = q(max(abs(y), self.env * vm.q23(vm.DEC) / Q))
        self.env = e
        self.g = q(self.g * vm.q23(vm.ATT) / Q if e > T('T') else self.g * vm.q23(1 - vm.R) / Q + vm.q23(vm.R) / Q)
        y = q(4 * y * T('MK'))
        d1 = q(T('DRV') * self.p[2] / Q)                                    # drive
        u = q(16 * y * d1)
        v = q(u + T('BIAS'))
        v3 = q(v * q(v * v))
        f = q(2 * (0.75 * v - 0.25 * v3))
        hp = q(f - self.dcl)
        self.dcl = q(self.dcl + vm.q23(KDC) / Q * hp)
        inc = self.ti[SI['INC']]                                             # crush: sample-and-hold
        if inc == 0:
            self.held = hp
        else:
            a = self.ph + inc
            if a & 0x800000:
                self.ph = a & 0x7FFFFF
                self.held = hp
            else:
                self.ph = a
        z = s24((int(round(self.held * Q)) & self.ti[SI['MASK']])) / Q       # bit mask
        n1 = self.rnd()                                                      # noise
        n2 = self.rnd()
        nz = s24(n2) / Q
        hn = q(2 * T('HISS') * self.p[3] / Q)
        self.hl = q(self.hl + T('HK') * q(nz * hn - self.hl))
        opn = self.ein > T('SQT')                                            # squelch gate
        sq = self.ti[SI['SQ']]
        if sq:
            if self.popen and not opn:
                self.btimer = self.ti[SI['BN']]
            self.popen = int(opn)
        s = q(z + self.hl) if (opn or not sq) else 0.0
        if self.btimer > 0:
            self.btimer -= 1
            bl = q(2 * T('BLEV') * self.p[3] / Q)
            s = q(s + nz * bl)
        s = self.bq(3, s)
        s = self.bq(4, s)
        self.ring[self.w] = s                                                # wobble delay
        self.s1 = q(self.s1 + T('KW') * self.c1); self.c1 = q(self.c1 - T('KW') * self.s1)
        self.s2 = q(self.s2 + T('KF') * self.c2); self.c2 = q(self.c2 - T('KF') * self.s2)
        dd = q(T('D0') + T('DW') * self.s1 + T('DF') * self.s2)
        di_ = int(np.floor(dd * Q)) >> 15
        fr = ((int(np.floor(dd * Q)) & 0x7FFF) << 8) / Q
        b0 = self.ring[(self.w - di_) % RING]
        b1 = self.ring[(self.w - di_ - 1) % RING]
        dv = q(b0 + fr * q(b1 - b0))
        self.w = (self.w + 1) % RING
        y = q(T('DMIX') * s + T('DLY') * dv)
        if (n1 & 0x7FFFFF) < self.ti[SI['CTH']]:                             # crackle
            ca = q(2 * T('CAMP') * self.p[3] / Q)
            self.clk = q(nz * ca)
        else:
            self.clk = q(self.clk * T('CDEC'))
        y = q(y + self.clk)
        o = q(2 * y * T('OUTG'))
        return q(dry + self.p[1] / Q * q(o - dry))

    def run(self, xs):
        return np.array([self.step(float(v)) for v in xs])


if __name__ == '__main__':
    import autotune_model as am
    x = np.concatenate([am.voice(200, 0.5, vib=0.3), np.zeros(int(0.4 * FS))])
    for m, name in enumerate(MODES):
        y = Radio(exact=True, mode=m).run(x)
        print('%-10s in pk %.2f  out pk %.2f  rms %.3f  tail rms %.4f' % (
            name, np.abs(x).max(), np.abs(y[:22050]).max(), np.sqrt((y[5000:22050] ** 2).mean()),
            np.sqrt((y[23000:] ** 2).mean())))
