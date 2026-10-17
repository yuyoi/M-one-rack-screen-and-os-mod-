"""Run dsp/spring.py's fx_spring in the simulator against model/spring_ref.py (expect bit-exact).
  py -3.10 sim_spring.py [seconds]        (a burst of the test riff, then silence: the tail)
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
import spring_ref as R  # noqa: E402

Q = 1 << 23

if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.12
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'spring.py'), run_name='__main__')
    import importlib
    SP = importlib.import_module('spring')
    sb, sw = SD.hexwords('spring.hex')
    dw, loop = SD.driver(SP.FX_SPRING)
    s = Sim(dw, SD.DRV)
    s.P.update({sb + i: v for i, v in enumerate(sw)})
    s.pc = SD.DRV
    while s.pc != loop:
        s.step()
    s.run_audio([0, 0], [0, 0])                             # init (clears state + rings), MIX = 0 -> 0
    s.X.update({R.PS + i: v for i, v in enumerate(R.ints(R.build()))})
    x = am.di_riff()[:int(secs * R.FS)] * 2.0
    x[len(x) // 3:] = 0
    xi = np.round(x * (Q - 1)).astype(int)
    n0 = len(s.out)
    t = time.time()
    out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
    y = np.array(out[n0 + 1::2], float) / Q
    ref = R.Spring()
    ref.wp = 1                                              # the init frame advanced the write pointer
    r = ref.run(xi / Q)
    n = min(len(y), len(r))
    bad = np.flatnonzero(np.abs(y[:n] - r[:n]) * Q > 0.5)
    print('SPRING worst %d instr/frame | %s | peak %.3f, tail rms %.4f (%.0f s)' % (
        worst, 'BIT-EXACT %d/%d' % (n, n) if not len(bad) else 'MISS %d (first %d)' % (len(bad), bad[0]),
        np.abs(y).max(), np.sqrt(np.mean(y[2 * n // 3:] ** 2)), time.time() - t))
