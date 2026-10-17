"""Run dsp/mod.py's fx_mod in the simulator against model/mod_ref.py, pedal by pedal (expect bit-exact).
The params + voice start states go into X like the ESP writes them (DIRT's code is loaded too: MOD calls its biquad).
  py -3.10 sim_mod.py [seconds] [pedal ...]        (default: 0.05 s of the test riff through every MOD pedal)
"""
import contextlib
import io
import os
import runpy
import sys
import time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import sim_dirt as SD  # noqa: E402
from sim56 import Sim  # noqa: E402
import amp_model as am  # noqa: E402
import mod_model as mm  # noqa: E402
import mod_ref as R  # noqa: E402

Q = 1 << 23


def build_sim():
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'dirt.py'), run_name='__main__')
        runpy.run_path(os.path.join(HERE, '..', 'mod.py'), run_name='__main__')
    db, dw_ = SD.hexwords('dirt.hex')
    mb, mw = SD.hexwords('mod.hex')
    dw, loop = SD.driver(mb)
    s = Sim(dw, SD.DRV)
    s.P.update({db + i: v for i, v in enumerate(dw_)})
    s.P.update({mb + i: v for i, v in enumerate(mw)})
    s.pc = SD.DRV
    while s.pc != loop:
        s.step()
    s.run_audio([0, 0], [0, 0])                             # first call: init (clears state + rings)
    return s


def pick_writes(name, kn=None):
    """{X address: word} a pedal pick writes: params + the voices' INCH / INCL / PH"""
    w, st = R.build(name, kn)
    out = {R.PM + i: v for i, v in enumerate(R.param_ints(w))}
    si = R.state_ints(st)
    for v in range(2):
        for k in range(3):
            o = R.S_V + 4 * v + k
            out[R.SM + o] = si[o]
    out[R.SM + 31] = 0                                       # INITF: clear-on-pick
    return out


def run_one(name, secs, kn=None, kn2=None):
    """kn2: knobs moved half way through (only the param words that change are written, like a knob move)"""
    s = build_sim()
    s.X.update(pick_writes(name, kn))
    x = am.di_riff()[:int(secs * mm.FS)] * 2.0
    xi = np.round(x * (Q - 1)).astype(int)
    n0 = len(s.out)
    t = time.time()
    m = R.Mod(name, kn)
    # the pick wrote INITF = 0: the first stream frame re-inits (rings cleared, pointers back at the ring bases)
    half = len(xi) // 2 if kn2 else len(xi)
    _, worst = s.run_audio(list(xi[:half]), list(xi[:half]), max_instr_per_frame=500000)
    ref = list(m.run(xi[:half] / Q))
    if kn2:
        w1, w2 = R.param_ints(R.build(name, kn)[0]), R.param_ints(R.build(name, {**(kn or {}), **kn2})[0])
        s.X.update({R.PM + i: v for i, v in enumerate(w2) if v != w1[i]})
        m.w = R.q(R.build(name, {**(kn or {}), **kn2})[0])
        out, w_ = s.run_audio(list(xi[half:]), list(xi[half:]), max_instr_per_frame=500000)
        worst = max(worst, w_)
        ref += list(m.run(xi[half:] / Q))
    out = s.out
    y = np.array(out[n0 + 1::2], float) / Q
    ref = np.array(ref)
    n = min(len(y), len(ref))
    err = y[:n] - ref[:n]
    bad = np.flatnonzero(np.abs(err) * Q > 0.5)
    print('%-12s worst %4d instr/frame | %s | peak %.3f rms %.3f (%.0f s)' % (
        name, worst, 'BIT-EXACT %d/%d' % (n, n) if not len(bad) else 'MISS %d of %d (first at %d, %+d LSB)' % (
            len(bad), n, bad[0], int(round(err[bad[0]] * Q))), np.abs(y).max(), np.sqrt(np.mean(y ** 2)),
        time.time() - t))
    return not len(bad), worst


if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    names = sys.argv[2:] or list(mm.PEDALS)
    ok = [run_one(nm, secs) for nm in names]
    print('pick FLANGER over a playing CE-2 (tail must be gone):', end=' ')
    s = build_sim()
    s.X.update(pick_writes('CE-2'))
    x = am.di_riff()[:int(secs * mm.FS)] * 2.0
    xi = np.round(x * (Q - 1)).astype(int)
    s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
    s.X.update(pick_writes('FLANGER'))
    n0 = len(s.out)
    _, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
    y = np.array(s.out[n0 + 1::2], float) / Q
    r = R.Mod('FLANGER').run(xi / Q)
    bad = np.flatnonzero(np.abs(y - r[:len(y)]) * Q > 0.5)
    print('worst %d instr/frame (the re-init frame) | %s' % (worst, 'BIT-EXACT' if not len(bad) else 'MISS %d' % len(bad)))
    ok.append((not len(bad), worst))
    if 'LESLIE' in names:
        print('LESLIE slow -> fast half way:', end=' ')
        ok.append(run_one('LESLIE', secs, {'SPEED': 0.0}, {'SPEED': 1.0}))
    print('all bit-exact' if all(o for o, _ in ok) else 'MISMATCH')
