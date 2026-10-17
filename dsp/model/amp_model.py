"""Amp sim option A: a modeled amp chain, float reference + DSP56362 cost tally + demo renders.

Chain (44.1 kHz in/out, preamp at 4x):
  input HPF -> 4x up (polyphase FIR) -> 3 asymmetric triode stages (interstage HPF/LPF, dynamic bias)
  -> 4x down -> TMB tone stack (Yeh & Smith '59 Bassman topology, ESP-computed coefficients)
  -> power amp (resonance/presence EQ, push-pull soft clip, supply sag) -> 512-tap cab IR -> level

Every block also counts DSP56362 cycles per base-rate frame (1 cycle per internal MAC/ALU op, measured core budget
2112 cycles/frame at 93.1 MHz; table lookup with linear interpolation ~8 cycles). Run:
  py -3.10 amp_model.py            -> cost table, aliasing test, 24-bit check, WAVs in tc_mone/research/amp_demo/
"""
import os
import numpy as np
import scipy.signal as ss
from scipy.io import wavfile

FS, OS = 44100, 4
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', '..', 'research', 'amp_demo')
BUDGET = 2112
cost = {}                                    # block -> cycles per base-rate frame


# ---------------------------------------------------------------- test DI (Karplus-Strong guitar)
def pluck(f0, n, damp=0.996, bright=0.5, seed=0):
    rng = np.random.default_rng(seed)
    p = int(round(FS / f0))
    buf = rng.uniform(-1, 1, p)
    buf = ss.lfilter([1 - bright], [1, -bright], buf)          # softer pick
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = damp * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out


def di_riff():
    """Power chords + a palm-muted chug + an open E chord, ~7 s, DI level (-12 dBFS peaks)."""
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    seg = []
    for root in (40, 43, 45, 40):            # E5 G5 A5 E5, 1 s each
        n = FS
        s = sum(pluck(midi(root + iv), n, 0.997, seed=root + iv) for iv in (0, 7, 12))
        seg.append(s)
    chug = np.zeros(FS)
    for k in range(8):                        # palm mutes: short, dark
        n = FS // 8
        chug[k * n:(k + 1) * n] = sum(pluck(midi(40 + iv), n, 0.97, 0.8, seed=k + iv) for iv in (0, 7))
    seg.append(chug)
    n = 2 * FS
    seg.append(sum(pluck(midi(m), n, 0.998, seed=m) for m in (40, 47, 52, 56, 59, 64)))   # open E major
    x = np.concatenate(seg)
    return x / np.max(np.abs(x)) * 10 ** (-12 / 20)


# ---------------------------------------------------------------- blocks
def onepole_hp(fc, fs):
    a = np.exp(-2 * np.pi * fc / fs)
    return [(1 + a) / 2, -(1 + a) / 2], [1, -a]


def onepole_lp(fc, fs):
    a = np.exp(-2 * np.pi * fc / fs)
    return [1 - a], [1, -a]


H_OS = ss.firwin(48, 0.9 / OS, window=('kaiser', 7.0)) * OS   # 4x interpolation / decimation low-pass, 12 taps/phase


def up(x):
    return ss.upfirdn(H_OS, x, up=OS)[24:24 + len(x) * OS]


def down(y):
    return ss.upfirdn(H_OS / OS, y, down=OS)[6:6 + len(y) // OS]


def triode(u):
    """Asymmetric transfer: grid conduction (+) rounds off early, cutoff (-) has more room then a harder knee."""
    return np.where(u >= 0, np.tanh(u), np.tanh(0.6 * u) / 0.6)


def pre_stage(x, gain_db, bias, hp, lp, fs, k_bias=0.0):
    b, a = onepole_hp(hp, fs)
    x = ss.lfilter(b, a, x) * 10 ** (gain_db / 20)
    if k_bias:                                # dynamic bias: the grid charges up on big signals (blocking feel)
        env = ss.lfilter(*onepole_lp(8, fs), np.maximum(x, 0))
        bias = bias - k_bias * env
    y = triode(x + bias) - triode(np.asarray(bias))
    b, a = onepole_lp(lp, fs)
    return ss.lfilter(b, a, y)


def tmb(l, m, t, comp='bassman'):
    """Fender/Marshall tone stack, Yeh & Smith (DAFx-06), bilinear. l/m/t = bass/mid/treble 0..1."""
    b1, b2, b3, a1, a2, a3 = tmb_analog(l, m, t, comp)
    return ss.bilinear([b3, b2, b1, 0], [a3, a2, a1, 1], FS)


def tmb_analog(l, m, t, comp='bassman'):
    """The analog H(s) = (b1 s + b2 s^2 + b3 s^3) / (1 + a1 s + a2 s^2 + a3 s^3). comp = a name or the parts
    (C1, C2, C3, R1, R2, R3, R4) themselves (amp_voicings.py)."""
    C1, C2, C3, R1, R2, R3, R4 = comp if isinstance(comp, tuple) else {
        'bassman': (250e-12, 20e-9, 20e-9, 250e3, 1e6, 25e3, 56e3),
        'marshall': (470e-12, 22e-9, 22e-9, 220e3, 1e6, 22e3, 33e3)}[comp]
    b1 = t*C1*R1 + m*C3*R3 + l*(C1*R2 + C2*R2) + (C1*R3 + C2*R3)
    b2 = (t*(C1*C2*R1*R4 + C1*C3*R1*R4) - m*m*(C1*C3*R3*R3 + C2*C3*R3*R3)
          + m*(C1*C3*R1*R3 + C1*C3*R3*R3 + C2*C3*R3*R3) + l*(C1*C2*R1*R2 + C1*C2*R2*R4 + C1*C3*R2*R4)
          + l*m*(C1*C3*R2*R3 + C2*C3*R2*R3) + (C1*C2*R1*R3 + C1*C2*R3*R4 + C1*C3*R3*R4))
    b3 = (l*m*(C1*C2*C3*R1*R2*R3 + C1*C2*C3*R2*R3*R4) - m*m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4)
          + m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4) + t*C1*C2*C3*R1*R3*R4 - t*m*C1*C2*C3*R1*R3*R4
          + t*l*C1*C2*C3*R1*R2*R4)
    a1 = (C1*R1 + C1*R3 + C2*R3 + C2*R4 + C3*R4) + m*C3*R3 + l*(C1*R2 + C2*R2)
    a2 = (m*(C1*C3*R1*R3 - C2*C3*R3*R4 + C1*C3*R3*R3 + C2*C3*R3*R3) + l*m*(C1*C3*R2*R3 + C2*C3*R2*R3)
          - m*m*(C1*C3*R3*R3 + C2*C3*R3*R3) + l*(C1*C2*R2*R4 + C1*C2*R1*R2 + C1*C3*R2*R4 + C2*C3*R2*R4)
          + (C1*C2*R1*R4 + C1*C3*R1*R4 + C1*C2*R3*R4 + C1*C2*R1*R3 + C1*C3*R3*R4 + C2*C3*R3*R4))
    a3 = (l*m*(C1*C2*C3*R1*R2*R3 + C1*C2*C3*R2*R3*R4) - m*m*(C1*C2*C3*R1*R3*R3 + C1*C2*C3*R3*R3*R4)
          + m*(C1*C2*C3*R3*R3*R4 + C1*C2*C3*R1*R3*R3 - C1*C2*C3*R1*R3*R4) + l*C1*C2*C3*R1*R2*R4
          + C1*C2*C3*R1*R3*R4)
    return b1, b2, b3, a1, a2, a3


def peq(fc, gain_db, q, kind='peak'):
    A, w = 10 ** (gain_db / 40), 2 * np.pi * fc / FS
    al, c = np.sin(w) / (2 * q), np.cos(w)
    if kind == 'peak':
        b = [1 + al * A, -2 * c, 1 - al * A]; a = [1 + al / A, -2 * c, 1 - al / A]
    else:                                     # high shelf
        s = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - s)]
        a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - s]
    return np.array(b) / a[0], np.array(a) / a[0]


def power_amp(x, drive_db, sag, presence_db=3, resonance_db=3):
    x = ss.lfilter(*peq(100, resonance_db, 1.2), x)
    x = ss.lfilter(*peq(3000, presence_db, 0.7, 'shelf'), x)
    x = x * 10 ** (drive_db / 20)
    env = np.zeros_like(x); e = 0.0
    att, rel = np.exp(-1 / (0.010 * FS)), np.exp(-1 / (0.150 * FS))
    ax = np.abs(x)
    for i in range(len(x)):                   # supply sag: the rail droops with the current draw
        k = att if ax[i] > e else rel
        e = k * e + (1 - k) * ax[i]
        env[i] = e
    g = 1 / (1 + sag * env)
    return np.tanh(x * g) * 0.9


def cab_ir(n=512):
    """Synthetic 4x12-ish IR: 70 Hz HPF, 110 Hz bump, 400 Hz dip, 2.5 kHz presence, steep roll-off from 5 kHz.
    Minimum phase (cepstrum), n taps. Stand-in for the user's own IRs (loaded over WiFi on the real thing)."""
    N = 8192
    f = np.fft.rfftfreq(N, 1 / FS)
    db = (-12 * np.log2(np.maximum(70 / np.maximum(f, 1), 1)) + 4 * np.exp(-((np.log2(np.maximum(f, 1) / 110)) / 0.35) ** 2)
          - 3 * np.exp(-((np.log2(np.maximum(f, 1) / 400)) / 0.5) ** 2) + 5 * np.exp(-((np.log2(np.maximum(f, 1) / 2500)) / 0.4) ** 2)
          - 30 * np.log2(np.maximum(f / 5000, 1)))
    mag = 10 ** (db / 20)
    cep = np.fft.irfft(np.log(np.maximum(mag, 1e-6)), N)
    w = np.zeros(N); w[0] = 1; w[1:N // 2] = 2; w[N // 2] = 1
    h = np.fft.irfft(np.exp(np.fft.rfft(cep * w)), N)[:n]
    h *= np.concatenate([np.ones(n * 3 // 4), np.hanning(n // 2)[n // 4:]])
    return h / np.max(np.abs(np.fft.rfft(h, 4096)))


PRESETS = {                                   # gain_db per stage, tone stack, power drive, sag
    'clean': dict(g=(6, 0, -6), tmb=(0.5, 0.6, 0.6), drive=-6, sag=0.5, comp='bassman'),
    'crunch': dict(g=(20, 12, 0), tmb=(0.5, 0.5, 0.6), drive=0, sag=1.0, comp='marshall'),
    'lead': dict(g=(30, 24, 12), tmb=(0.6, 0.3, 0.7), drive=3, sag=1.5, comp='marshall'),
}


def amp(x, p, oversample=True, ir=None):
    x = ss.lfilter(*onepole_hp(20, FS), x)
    fs = FS * OS if oversample else FS
    y = up(x) if oversample else x
    y = pre_stage(y, p['g'][0], 0.25, 30, 12000, fs)
    y = pre_stage(y, p['g'][1], 0.15, 120, 9000, fs, k_bias=0.6)
    y = pre_stage(y, p['g'][2], 0.10, 80, 7000, fs, k_bias=0.6)
    y = down(y) if oversample else y
    y = ss.lfilter(*tmb(*p['tmb'], comp=p['comp']), y)
    y = power_amp(y, p['drive'], p['sag'])
    if ir is not None:
        y = ss.lfilter(ir, [1], y)
    return y


def tally(taps=512):
    cost.clear()
    cost['input HPF'] = 4
    cost['4x up, 48-tap polyphase'] = 48 + 8
    cost['3 triode stages @4x (gain, table shaper, 2 one-poles, bias env)'] = 3 * OS * 19
    cost['4x down, 48-tap FIR'] = 48 + 8
    cost['TMB tone stack (3rd order)'] = 10
    cost['power amp (2 EQs, sag env, shaper)'] = 30
    cost['cab IR %d taps (internal X/Y, 1 MAC/cycle)' % taps] = taps + 10
    cost['level + glue'] = 10
    return sum(cost.values())


def alias_db(oversample, f0=3000, p=PRESETS['lead']):
    """Energy at non-harmonic bins (aliases folded back) relative to the output, for a sine at f0."""
    n = FS
    t = np.arange(n) / FS
    y = amp(0.25 * np.sin(2 * np.pi * f0 * t), p, oversample)[FS // 4:]
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / FS)
    harm = np.zeros_like(Y, bool)
    for k in range(1, int(FS / 2 / f0) + 1):
        harm |= np.abs(f - k * f0) < 30
    harm |= f < 30
    return 10 * np.log10(Y[~harm].sum() / Y.sum())


def q24(x):
    return np.round(np.clip(x, -1, 1 - 2 ** -23) * 2 ** 23) / 2 ** 23


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    total = tally(512)
    print('Option A cost per frame (budget %d cycles):' % BUDGET)
    for k, v in cost.items():
        print('  %5d  %s' % (v, k))
    print('  %5d  TOTAL = %.0f%% of the budget' % (total, 100 * total / BUDGET))
    print('  with a 1024-tap IR: %d cycles = %.0f%%' % (tally(1024), 100 * tally(1024) / BUDGET))
    for f0 in (1000, 3000, 5000):
        print('aliasing, lead preset, %d Hz sine: 1x %.1f dB, 4x %.1f dB' % (f0, alias_db(False, f0), alias_db(True, f0)))
    di = di_riff()
    ir = cab_ir()
    wavfile.write(os.path.join(OUT, '0_di.wav'), FS, (di * 32767).astype(np.int16))
    for name, p in PRESETS.items():
        y = amp(di, p, True, ir)
        y = y / np.max(np.abs(y)) * 10 ** (-1 / 20)
        yq = amp(q24(di), p, True, q24(ir))                  # 24-bit coefficients/input check
        yq = yq / np.max(np.abs(yq)) * 10 ** (-1 / 20)
        snr = 10 * np.log10(np.sum(y ** 2) / np.sum((y - yq) ** 2))
        wavfile.write(os.path.join(OUT, '%s.wav' % name), FS, (y * 32767).astype(np.int16))
        print('%-6s rendered, 24-bit input/IR vs float: %.0f dB SNR' % (name, snr))
    print('WAVs in', os.path.abspath(OUT))
