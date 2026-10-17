"""Run dsp/filt.py's fx_phaser / fx_wah in the simulator against model/filt_ref.py (expect bit-exact).
  py -3.10 sim_filt.py [seconds]        (Phase 90, Cry Baby with the treadle rocked heel -> toe, Reso Wah)
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
import filt_model as fm  # noqa: E402
import filt_ref as R  # noqa: E402

Q = 1 << 23


def run_one(name, secs, sweep=False):
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'filt.py'), run_name='__main__')
        import filt  # noqa: F401
    fb, fw = SD.hexwords('filt.hex')
    import importlib
    F = importlib.import_module('filt')
    fx = F.FX_PHASER if fm.PEDALS[name]['fx'] == 'phaser' else F.FX_WAH
    dw, loop = SD.driver(fx)
    s = Sim(dw, SD.DRV)
    s.P.update({fb + i: v for i, v in enumerate(fw)})
    s.pc = SD.DRV
    while s.pc != loop:
        s.step()
    wv = R.ints(R.build(name))
    is_ph = fm.PEDALS[name]['fx'] == 'phaser'
    base, st = (R.PP, R.PS) if is_ph else (R.PW, R.WS)
    s.X.update({base + i: v for i, v in enumerate(wv)})
    s.X.update({st + i: 0 for i in range(16)})
    if not is_ph:
        s.X[st] = wv[0]                                        # PS = POS
        ref = R.Wah(name)
    else:
        ref = R.Phaser(name)
    x = am.di_riff()[:int(secs * fm.FS)] * 2.0
    xi = np.round(x * (Q - 1)).astype(int)
    n0 = len(s.out)
    t = time.time()
    ys, rs, worst = [], [], 0
    blocks = 10 if sweep else 1
    for b in range(blocks):
        seg = xi[b * len(xi) // blocks:(b + 1) * len(xi) // blocks]
        if sweep:                                              # the ESP moves the treadle every block (~10 Hz)
            pos = R.q(min(b / (blocks - 1), R.ONE))
            s.X[base] = int(round(pos * Q)) & 0xFFFFFF
            ref.w[0] = pos
        _, wr = s.run_audio(list(seg), list(seg), max_instr_per_frame=500000)
        worst = max(worst, wr)
        rs += list(ref.run(seg / Q))
    y = np.array(s.out[n0 + 1::2], float) / Q
    r = np.array(rs)
    n = min(len(y), len(r))
    err = y[:n] - r[:n]
    bad = np.flatnonzero(np.abs(err) * Q > 0.5)
    print('%-10s%s worst %3d instr/frame | %s | peak %.3f (%.0f s)' % (
        name, ' sweep' if sweep else '', worst, 'BIT-EXACT %d/%d' % (n, n) if not len(bad) else
        'MISS %d of %d (first at %d, %+d LSB)' % (len(bad), n, bad[0], int(round(err[bad[0]] * Q))),
        np.abs(y).max(), time.time() - t))
    return not len(bad)


if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1
    ok = [run_one('PHASE 90', secs), run_one('CRYBABY', secs, sweep=True), run_one('RESO WAH', secs)]
    print('all bit-exact' if all(ok) else 'MISMATCH')
