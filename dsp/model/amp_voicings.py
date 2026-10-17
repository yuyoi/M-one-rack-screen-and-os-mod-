"""The board's 6 amp voicings for AMP (effect 6, dsp/amp.py, unchanged): CLEAN (Deluxe Reverb), TWIN, JCM800, AC30,
DOOM, DI. A voicing = AMP's own words (stage gains, coupling HPF + Miller LPF per stage, tone-stack parts, presence /
resonance / drive / sag / master defaults) + its own cab IR. The 7th amp, RADIO, is a DIRT voicing (dirt_model.py).

Tone stacks: Yeh's TMB cubic with each amp's parts (blackface AB763 for the Deluxe (fixed 6k8 mid leg) and the Twin,
JCM800 2203, a Laney-style Marshall stack for DOOM; the AC30 top boost isn't a TMB circuit, so it is ~ fitted with
TMB parts: 1M treble and bass, no mid pot, a small treble cap). CUT (AC30) = presence turned negative.
Cab IRs are synthetic (own design, minimum phase, no captures): speaker + box shapes per amp, DI = no cab.
The ESP computes the tone stack (menu.h ampTmb) from the parts in VOICINGS and writes the IR (512 words) into
Y:$0800 and AMP's SRAM table X:$031C00 (so AMP's first-call init copies the same IR); the param words go to X:$12C0
and to the table's param block X:$031E60 likewise (the sim test loads a voicing through the table).

  py -3.10 amp_voicings.py            sim56 run of every voicing against amp_ref (bit-exact), levels
"""
import numpy as np
import amp_model as am
import amp_ref as AR

FS = 44100
# parts: (C1 treble cap, C2 bass cap, C3 mid cap, R1 treble pot, R2 bass pot, R3 mid pot, R4 slope)
BLACKFACE = (250e-12, 100e-9, 47e-9, 250e3, 250e3, 10e3, 100e3)
DELUXE = (250e-12, 100e-9, 47e-9, 250e3, 250e3, 6.87e3, 100e3)          # 6k8 fixed: mid held at 0.99 of 6k87
MARSHALL = (470e-12, 22e-9, 22e-9, 220e3, 1e6, 22e3, 33e3)
LANEY = (250e-12, 47e-9, 22e-9, 250e3, 1e6, 25e3, 47e3)
VOX_TB = (100e-12, 22e-9, 22e-9, 1e6, 1e6, 10e3, 100e3)

# cab shapes: (low cut Hz, bump Hz, bump dB, dip Hz, dip dB, presence Hz, presence dB, roll-off Hz)
CABS = {
    '1x12 open': (90, 120, 2, 500, -2, 2200, 4, 5500),
    '2x12 open': (70, 110, 2, 600, -2, 3000, 3, 6500),
    '4x12 closed': (70, 110, 4, 400, -3, 2500, 5, 5000),
    '2x12 blue': (85, 130, 2, 800, -2, 3200, 5, 5500),
    '4x12 v30': (60, 90, 5, 450, -4, 2800, 3, 4500),
    'none': None,
}

VOICINGS = {
    # stage gains dB, coupling HPF Hz, Miller LPF Hz, parts, defaults (bass mid treble pres res drive sag master), cab
    'CLEAN': dict(g=(8, 2, -6), hp=(20, 80, 60), lp=(14000, 11000, 9000), parts=DELUXE,
                  d=dict(bass=50, mid=99, treble=60, presence=0, resonance=2, drive=-6, sag=40, master=70),
                  cab='1x12 open', colour=0xD0C8B0),
    'TWIN': dict(g=(6, 0, -8), hp=(20, 60, 60), lp=(16000, 13000, 10000), parts=BLACKFACE,
                 d=dict(bass=40, mid=50, treble=65, presence=2, resonance=1, drive=-9, sag=20, master=70),
                 cab='2x12 open', colour=0xC0C0C8),
    'JCM800': dict(g=(24, 18, 6), hp=(30, 140, 90), lp=(12000, 9000, 7000), parts=MARSHALL,
                   d=dict(bass=50, mid=60, treble=65, presence=4, resonance=3, drive=0, sag=50, master=70),
                   cab='4x12 closed', colour=0xC9A227),
    'AC30': dict(g=(14, 8, 0), hp=(40, 120, 100), lp=(15000, 12000, 9000), parts=VOX_TB,
                 d=dict(bass=45, mid=99, treble=60, presence=0, resonance=2, drive=2, sag=60, master=70),
                 cab='2x12 blue', colour=0x8E1B1B),
    'DOOM': dict(g=(28, 22, 10), hp=(20, 60, 50), lp=(10000, 7500, 6000), parts=LANEY,
                 d=dict(bass=70, mid=55, treble=45, presence=0, resonance=6, drive=3, sag=70, master=70),
                 cab='4x12 v30', colour=0xE36A12),
    'DI': dict(g=(0, -6, -12), hp=(10, 10, 10), lp=(20000, 20000, 20000), parts=None,
               d=dict(bass=50, mid=50, treble=50, presence=0, resonance=0, drive=-12, sag=0, master=70),
               cab='none', colour=0x707070),
}
# the board's knobs per voicing: (label, AMP row) -- rows of the AMP EDIT page (menu.h ampP), real amp controls
KNOBS = {
    'CLEAN': [('VOLUME', 'GAIN'), ('TREBLE', 'TREBLE'), ('BASS', 'BASS'), ('MASTER', 'MASTER')],
    'TWIN': [('VOLUME', 'GAIN'), ('TREBLE', 'TREBLE'), ('MIDDLE', 'MID'), ('BASS', 'BASS'), ('MASTER', 'MASTER')],
    'JCM800': [('PRE-AMP', 'GAIN'), ('MASTER', 'MASTER'), ('TREBLE', 'TREBLE'), ('MIDDLE', 'MID'), ('BASS', 'BASS'),
               ('PRESENCE', 'PRESENCE')],
    'AC30': [('VOLUME', 'GAIN'), ('TREBLE', 'TREBLE'), ('BASS', 'BASS'), ('CUT', 'PRESENCE'), ('MASTER', 'MASTER')],
    'DOOM': [('GAIN', 'GAIN'), ('BASS', 'BASS'), ('MID', 'MID'), ('TREBLE', 'TREBLE'), ('VOLUME', 'MASTER')],
    'DI': [('VOLUME', 'MASTER')],
}


def cab_ir(kind, n=512):
    if CABS[kind] is None:
        h = np.zeros(n); h[0] = 0.99
        return AR.q(h)
    lc, bf, bd, df, dd, pf, pd, ro = CABS[kind]
    N = 8192
    f = np.maximum(np.fft.rfftfreq(N, 1 / FS), 1)
    lg = np.log2
    db = (-12 * lg(np.maximum(lc / f, 1)) + bd * np.exp(-(lg(f / bf) / 0.35) ** 2) + dd * np.exp(-(lg(f / df) / 0.5) ** 2)
          + pd * np.exp(-(lg(f / pf) / 0.4) ** 2) - 30 * lg(np.maximum(f / ro, 1)))
    mag = 10 ** (db / 20)
    cep = np.fft.irfft(np.log(np.maximum(mag, 1e-6)), N)
    w = np.zeros(N); w[0] = 1; w[1:N // 2] = 2; w[N // 2] = 1
    h = np.fft.irfft(np.exp(np.fft.rfft(cep * w)), N)[:n]
    h *= np.concatenate([np.ones(n * 3 // 4), np.hanning(n // 2)[n // 4:]])
    h = h / np.max(np.abs(np.fft.rfft(h, 4096)))
    return AR.q(h / max(1.0, np.max(np.abs(h)) / 0.99))


def flat_stack():
    """DI: tone stack bypassed (biquad = 1, first order = a DC blocker at ~2 Hz)"""
    h = (AR.Q - 1) / AR.Q
    return AR.q(np.array([1 / h, 0, 0, 0, 0]) / 2), AR.q([h, -h, float(np.exp(-2 * np.pi * 2 / FS))])


def words(name, kn=None):
    """the 48-word AMP param block for a voicing (knob rows as amp_ref.ui_words: 0..100, dB, %)"""
    v = VOICINGS[name]
    d = {**v['d'], 'gain': 70, **(kn or {})}
    p = dict(AR.PRESET)
    p.update(g=tuple(gg + ((d['gain'] - 70) * 0.25 if s < 2 else 0) for s, gg in enumerate(v['g'])),
             hp=v['hp'], lp=v['lp'], drive=d['drive'], sag=d['sag'] / 100, master=d['master'] / 100)
    p['g'] = tuple(min(gg, 30) for gg in p['g'])
    w = np.array(AR.params(p))                      # stage words, envelope, DC blocker, sag steps
    if v['parts'] is None:
        bq, f1 = flat_stack()
    else:
        bq, f1 = AR.tmb_sos(d['bass'] / 100, d['mid'] / 100, d['treble'] / 100, comp=v['parts'])
    pe = AR.peq_coefs(d['resonance'], d['presence'])
    w[16:21], w[21:24], w[24:29], w[29:34] = bq, f1, pe[0], pe[1]
    return AR.q(w)


def ref(name, kn=None):
    amp = AR.Amp()
    amp.w = words(name, kn)
    amp.ir = cab_ir(VOICINGS[name]['cab'])
    return amp


if __name__ == '__main__':
    import contextlib, io, os, runpy, sys, time  # noqa: E401
    HERE = os.path.dirname(os.path.abspath(__file__))
    import sim_amp as SA
    from sim56 import Sim
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'amp.py'), run_name='__main__')
    ab, aw = SA.hexwords('amp.hex')
    tb, tw = SA.hexwords('amp_tab.hex')
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.02
    x = am.di_riff()[:int(secs * FS)] * 2.0
    xi = np.round(x * (AR.Q - 1)).astype(int)
    for name in VOICINGS:
        dw, loop = SA.driver()
        s = Sim(dw, SA.DRV)
        s.P.update({ab + i: v for i, v in enumerate(aw)})
        tv = list(tw)                                                   # what the ESP writes: AMP's SRAM table
        tv[:512] = [int(round(v * AR.Q)) & 0xFFFFFF for v in cab_ir(VOICINGS[name]['cab'])]   # IR
        tv[608:656] = [int(round(v * AR.Q)) & 0xFFFFFF for v in words(name)]                  # params
        s.X.update({tb + i: v for i, v in enumerate(tv)})
        s.pc = SA.DRV
        while s.pc != loop:
            s.step()
        s.run_audio([0, 0], [0, 0])                                     # AMP's init copies the voicing in
        n0 = len(s.out)
        t = time.time()
        out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
        y = np.array(out[n0 + 1::2], float) / AR.Q
        r = ref(name)
        r.run(np.zeros(2))                                              # the same two warm-up frames
        rr = r.run(xi / AR.Q)
        n = min(len(y), len(rr))
        bad = np.flatnonzero(np.abs(y[:n] - rr[:n]) * AR.Q > 0.5)
        print('%-7s worst %d instr | %s | peak %.3f rms %.3f (%.0f s)' % (
            name, worst, 'BIT-EXACT %d/%d' % (n, n) if not len(bad) else 'MISS %d (first %d)' % (len(bad), bad[0]),
            np.abs(y).max(), np.sqrt(np.mean(y ** 2)), time.time() - t))
