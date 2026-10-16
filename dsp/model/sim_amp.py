"""Run dsp/amp.py's fx_amp in the simulator against model/amp_ref.py (the same algorithm in float).
A minimal kernel-style driver calls fx_amp once per frame (right slot), like os.py does, so AMP can be tested before
its table entry exists.  py -3.10 sim_amp.py [seconds] [out.wav]
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
import amp_ref as R  # noqa: E402

Q = 1 << 23
DRV = 0x0F00


def hexwords(name):
    tk = open(os.path.join(HERE, '..', name)).read().split()
    return int(tk[0], 16), [int(v, 16) for v in tk[1:]]


def driver():
    w = [0x05F439, 0x800300, 0x0500BB]                # movec #$800300,sr ; movec #0,sp
    for m in range(8):
        w += [0x05F420 | m, 0xFFFFFF]                 # M0-M7 linear
    loop = DRV + len(w)
    w += [0x01B388, loop, 0x0445C9]                   # jclr #8,x:SAISR,loop ; movep x:RX1,x1
    fix = len(w)
    w += [0x01B3A6, 0]                                # jset #6,x:SAISR,left
    w += [0x0BF080, 0x0C00]                           # jsr fx_amp
    w += [0x453100, 0x04C5C1, 0x0AF080, loop]         # x:$31 = out ; movep x1,x:TX1 ; jmp loop
    w[fix + 1] = DRV + len(w)
    w += [0x45B100, 0x04C5C1, 0x0AF080, loop]         # left slot: output the last result
    return w, loop


if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.15
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(HERE, '..', 'amp.py'), run_name='__main__')
    ab, aw = hexwords('amp.hex')
    tb, tw = hexwords('amp_tab.hex')
    dw, loop = driver()
    s = Sim(dw, DRV)
    s.P.update({ab + i: v for i, v in enumerate(aw)})
    s.X.update({tb + i: v for i, v in enumerate(tw)})       # SRAM: P/X/Y alias on the hardware
    s.pc = DRV
    while s.pc != loop:
        s.step()
    s.run_audio([0, 0], [0, 0])                             # first call runs init (table copy): not timed
    x = am.di_riff()[:int(secs * R.FS)] * 2.0               # hot DI (-6 dBFS peaks)
    xi = np.round(x * (Q - 1)).astype(int)
    t = time.time()
    n0 = len(s.out)                                         # run_audio returns every output so far: skip the warm-up
    out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=500000)
    y = np.array(out[n0 + 1::2], float) / Q
    ref = R.Amp().run(np.concatenate([[0.0, 0.0], xi / Q]))[2:]   # same two warm-up zeros
    n = min(len(y), len(ref))
    y, ref = y[:n], ref[:n]
    err = y - ref
    snr = 10 * np.log10(np.sum(ref ** 2) / max(np.sum(err ** 2), 1e-30))
    print('%.2f s audio, %.0f s sim | worst %d instr/frame (budget ~2070 with a bare loop)' % (secs, time.time() - t, worst))
    print('DSP vs reference: max |err| %.2e, SNR %.1f dB | out peak %.3f rms %.3f' % (
        np.abs(err).max(), snr, np.abs(y).max(), np.sqrt((y ** 2).mean())))
    bad = np.flatnonzero(np.abs(err) * Q > 0.5)
    print('bit-exact: %d of %d samples%s' % (n - len(bad), n, ' (first miss at %d)' % bad[0] if len(bad) else ''))
    if len(sys.argv) > 2:
        from scipy.io import wavfile
        wavfile.write(sys.argv[2], R.FS, (np.clip(y, -1, 1) * 32767).astype(np.int16))
        print('wrote', sys.argv[2])
