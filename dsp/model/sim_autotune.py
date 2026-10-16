"""Run dsp/autotune.hex in the simulator on test voices; report output pitch vs the nearest note."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ('disasm', 'tools'): sys.path.insert(0, os.path.join(HERE, '..', '..', _d))
sys.path.insert(0, HERE)
import numpy as np
from sim56 import Sim
import autotune_model as m
Q = 1 << 23
tk = open(os.path.join(HERE, '..', 'autotune.hex')).read().split()
base, words = int(tk[0], 16), [int(v, 16) for v in tk[1:]]
for f0 in [float(v) for v in (sys.argv[1:] or ['215'])]:
    x = m.voice(f0, 0.6)
    xi = np.round(x / 2 * (Q - 1)).astype(int)            # L = R = x/2 -> mono = x
    s = Sim(words, base)
    t = time.time()
    out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=3_000_000)
    y = np.array(out[1::2], float) / Q
    f = m.pitch_of(y[16000:26000])
    n = 69 + 12 * np.log2(f / 440); tgt = 440 * 2 ** ((round(n) - 69) / 12)
    n0 = 69 + 12 * np.log2(f0 / 440)
    print('in %6.1f Hz (%+5.1f c) -> out %7.2f Hz (%+5.1f c from note %d) | DSP note=%d  worst %d instr/frame (after init)  %.0fs' % (
        f0, 100 * (n0 - round(n0)), f, m.cents(f, tgt), round(n), s.X.get(0x0E, -1), worst, time.time() - t))
