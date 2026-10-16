"""CHAIN SHIMMER (14) -> REVERB (12, HALL) in the simulator vs the chained models."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import harmony_model as hm
import reverb_model as rv
import autotune_model as am
Q = 1 << 23
x = np.concatenate([am.voice(220, 0.15), np.zeros(int(0.35 * 44100))])
xi = np.round(x / 2 * (Q - 1)).astype(int)
t = time.time()
s = boot_os(0)
s.X[0x20] = 3; s.X[0x0200] = 2; s.X[0x0201] = 14; s.X[0x0202] = 12
prm = list(rv.PRESETS['HALL'])
for k, v in enumerate(prm):
    s.X[0x0280 + k] = v & 0xFFFFFF
sh, r = hm.Shimmer(), rv.Reverb(prm)
y, ref, worst = [], [], 0
for k in range(len(xi)):
    out, w = s.run_audio([xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(r.step(sh.step(int(2 * xi[k]), r.ok)))
y, ref = np.array(y), np.array(ref)
err = np.abs(y - ref)
bad = np.flatnonzero(err > 2)
print('SHIMMER -> HALL: worst %d instr/frame | max err %d LSB (first > 2 at %s) | tail rms %.4f | %.0f s' % (
    worst, err.max(), bad[0] if len(bad) else '-', (y[int(0.3 * 44100):] / Q).std(), time.time() - t))
