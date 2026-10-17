"""Run dsp/dirt.py's fx_dirt in the simulator against model/dirt_ref.py, pedal by pedal (expect bit-exact).
The params and curves go into X like the ESP writes them; AMP's SRAM table supplies the FIR coefficients (as at boot).
  py -3.10 sim_dirt.py [seconds] [pedal ...]        (default: 0.02 s of the test riff through every dirt pedal)
"""
import contextlib
import io
import os
import runpy
import sys
import time
HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ('disasm', 'tools'):
    sys.path.insert(0, os.path.join(HERE, '..', '..', _d))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from sim56 import Sim  # noqa: E402
import amp_model as am  # noqa: E402
import dirt_model as dm  # noqa: E402
import dirt_ref as R  # noqa: E402

Q = 1 << 23
DRV = 0x0D80


def hexwords(name):
    tk = open(os.path.join(HERE, '..', name)).read().split()
    return int(tk[0], 16), [int(v, 16) for v in tk[1:]]


def driver(fx):
    w = [0x05F439, 0x800300, 0x0500BB]                # movec #$800300,sr ; movec #0,sp
    for m in range(8):
        w += [0x05F420 | m, 0xFFFFFF]                 # M0-M7 linear
    loop = DRV + len(w)
    w += [0x01B388, loop, 0x0445C9]                   # jclr #8,x:SAISR,loop ; movep x:RX1,x1
    fix = len(w)
    w += [0x01B3A6, 0]                                # jset #6,x:SAISR,left
    w += [0x0BF080, fx]                               # jsr fx
    w += [0x453100, 0x04C5C1, 0x0AF080, loop]         # x:$31 = out ; movep x1,x:TX1 ; jmp loop
    w[fix + 1] = DRV + len(w)
    w += [0x45B100, 0x04C5C1, 0x0AF080, loop]         # left slot: output the last result
    return w, loop


def build_sim():
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'amp.py'), run_name='__main__')
        runpy.run_path(os.path.join(HERE, '..', 'dirt.py'), run_name='__main__')
    db, dw_ = hexwords('dirt.hex')
    tb, tw = hexwords('amp_tab.hex')
    dw, loop = driver(db)
    s = Sim(dw, DRV)
    s.P.update({db + i: v for i, v in enumerate(dw_)})
    s.X.update({tb + i: v for i, v in enumerate(tw)})       # SRAM: P/X/Y alias on the hardware
    s.pc = DRV
    while s.pc != loop:
        s.step()
    s.run_audio([0, 0], [0, 0])                             # first call: init (passes through: NST = 0)
    return s


def load_pedal(s, name, kn=None):
    w, tabs, _ = R.build(name, kn)
    s.X.update({R.PAR + i: v for i, v in enumerate(R.ints(w))})
    for addr, t in tabs.items():
        s.X.update({addr + i: v for i, v in enumerate(R.tab_ints(t))})


def run_one(name, secs, kn=None):
    s = build_sim()
    load_pedal(s, name, kn)
    x = am.di_riff()[:int(secs * dm.FS)] * 2.0             # hot DI (-6 dBFS peaks)
    xi = np.round(x * (Q - 1)).astype(int)
    n0 = len(s.out)
    t = time.time()
    out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
    y = np.array(out[n0 + 1::2], float) / Q
    ref = R.Dirt(name, kn).run(xi / Q)
    n = min(len(y), len(ref))
    err = y[:n] - ref[:n]
    bad = np.flatnonzero(np.abs(err) * Q > 0.5)
    print('%-14s %d stage(s): worst %4d instr/frame | %s | peak %.3f  (%.0f s)' % (
        name, len(R.build(name)[2]), worst,
        'BIT-EXACT %d/%d' % (n, n) if not len(bad) else 'MISS %d of %d (first at %d, %+d LSB)' % (
            len(bad), n, bad[0], int(round(err[bad[0]] * Q))), np.abs(y).max(), time.time() - t))
    return not len(bad), worst


if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.02
    names = sys.argv[2:] or list(dm.PEDALS)
    ok = [run_one(nm, secs) for nm in names]
    print('all bit-exact' if all(o for o, _ in ok) else 'MISMATCH')
