"""Run the whole OS in the simulator with FX1 = RADIO in one mode; compare with radio_model (exact).

  py -3.10 sim_radio.py MODE [out.npz]      MODE 0-5 (TELEPHONE MEGAPHONE AM WALKIE CASSETTE VINYL)
Input: a voice (vibrato) for 0.45 s, then 0.3 s of silence (squelch burst, tails).
"""
import os, sys, time, runpy, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ('disasm', 'tools'): sys.path.insert(0, os.path.join(HERE, '..', '..', _d))
sys.path.insert(0, HERE)
import numpy as np
from sim56 import Sim
import autotune_model as am
import radio_model as rm
Q = 1 << 23
FS = 44100


def hexwords(name):
    tk = open(os.path.join(HERE, '..', name)).read().split()
    return int(tk[0], 16), [int(v, 16) for v in tk[1:]]


def boot_os(fx1):
    """the OS as `boot` loads it: P programs + the external-SRAM tables (P/X/Y alias there, so they go into X)"""
    with contextlib.redirect_stdout(io.StringIO()):          # MONE_NOBUILD=1: use the .hex as is (parallel runs)
        if not os.environ.get('MONE_NOBUILD'):
            runpy.run_path(os.path.join(HERE, '..', 'vocal.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'vocal2.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'vocal3.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'vocal4.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'vocal5.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'vocal6.py'), run_name='__main__')
            runpy.run_path(os.path.join(HERE, '..', 'amp.py'), run_name='__main__')
            for name in ('dirt.py', 'mod.py', 'filt.py'):
                runpy.run_path(os.path.join(HERE, '..', name), run_name='__main__')
        labels = runpy.run_path(os.path.join(HERE, '..', 'os.py'), run_name='labels')['labels']
    ob, ow = hexwords('os.hex')
    s = Sim(ow, ob)
    for name in ('autotune.hex', 'vocal.hex', 'vocal2.hex', 'vocal3.hex', 'vocal4.hex', 'vocal5.hex', 'vocal6.hex', 'amp.hex',
                 'vocal3b.hex', 'dirt.hex', 'mod.hex', 'filt.hex'):
        b, w = hexwords(name)
        s.P.update({b + i: v for i, v in enumerate(w)})
    for name in ('vocal_tab.hex', 'vocal2_tab.hex', 'vocal3_tab.hex', 'vocal4_tab.hex', 'vocal5_tab.hex', 'amp_tab.hex'):
        b, w = hexwords(name)
        s.X.update({b + i: v for i, v in enumerate(w)})
    s.pc = ob
    while s.pc != labels['loop']:
        s.step()
    s.X[0x20], s.X[0x21] = 0, fx1
    return s


if __name__ == '__main__':
    mode = int(sys.argv[1])
    x = np.concatenate([am.voice(200, 0.45, vib=0.3), np.zeros(int(0.3 * FS))])
    xi = np.round(x / 2 * (Q - 1)).astype(int)
    xs = 2 * xi / Q
    t = time.time()
    s = boot_os(7)
    s.X[0x0210] = mode
    out, worst = s.run_audio(list(2 * xi), list(xi), max_instr_per_frame=100000)
    y = np.array(out[3::2], float) / Q
    ref = rm.Radio(exact=True, mode=mode).run(xs)
    n = min(len(y), len(ref))
    err = np.abs(y[:n] - ref[:n])
    bad = np.flatnonzero(err > 1e-5)
    print('%-10s worst %d instr/frame | max err %.2e (first > 1e-5 at %s) | out pk %.2f | %.0f s' % (
        rm.MODES[mode], worst, err.max(), bad[0] if len(bad) else '-', np.abs(y).max(), time.time() - t))
    if len(sys.argv) > 2:
        np.savez(sys.argv[2], y=y, ref=ref, xs=xs)
