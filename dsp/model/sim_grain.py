"""GRAIN (16) in the whole-OS simulator vs grain_model (short grains so a short run covers several restarts)."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import grain_model as gm
import autotune_model as am
Q = 1 << 23
x = am.voice(220, 0.4, vib=0.3)
xi = np.round(x / 2 * (Q - 1)).astype(int)
prm = gm.params(ms=20, range_s=0.05)
t = time.time()
s = boot_os(16)
for k, v in enumerate(prm):
    s.X[0x02C0 + k] = v & 0xFFFFFF
model = gm.Grain(prm)
y, ref, worst = [], [], 0
for k in range(len(xi)):
    out, w = s.run_audio([2 * xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(model.step(int(2 * xi[k])))
y, ref = np.array(y[1:]), np.array(ref[:-1])          # TX1 carries the previous frame's output
err = np.abs(y - ref)
bad = np.flatnonzero(err > 2)
print('GRAIN: worst %d instr/frame | max err %d LSB (first > 2 at %s) | out rms %.3f | %.0f s' % (
    worst, err.max(), bad[0] if len(bad) else '-', (y / Q).std(), time.time() - t))
