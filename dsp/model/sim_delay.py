"""Run the whole OS in the simulator with FX1 = DELAY (13); compare with delay_model (exact).

  py -3.10 sim_reverb.py [SLAP|TEMPO|DOTTED|DUCKING|TAPE|MULTI]
Input: a voice for 0.15 s, then 0.35 s of silence (the tail).
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import delay_model as dm
import autotune_model as am
Q = 1 << 23
FS = 44100
name = sys.argv[1] if len(sys.argv) > 1 else 'SLAP'
prm = list(dm.PRESETS[name])
freeze = 'freeze' in sys.argv[2:]
x = np.concatenate([am.voice(200, 0.15, vib=0.3), np.zeros(int(0.9 * FS))])
xi = np.round(x / 2 * (Q - 1)).astype(int)
t = time.time()
s = boot_os(13)
for k, v in enumerate(prm):
    s.X[0x0290 + k] = v & 0xFFFFFF
model = dm.Delay(list(prm))
y, ref, worst = [], [], 0
for k in range(len(xi)):
    if freeze and k == int(0.15 * FS):
        pass
    out, w = s.run_audio([2 * xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(model.step(int(2 * xi[k])))
y, ref = np.array(y[1:]), np.array(ref[:-1])          # TX1 carries the previous frame's output
err = np.abs(y - ref)
bad = np.flatnonzero(err > 2)
tail = y[int(0.3 * FS):] / Q
print('%s%s: worst %d instr/frame | max err %d LSB (first > 2 at %s) | tail rms %.4f | %.0f s' % (
    name, ' FREEZE' if freeze else '', worst, err.max(), bad[0] if len(bad) else '-', tail.std(), time.time() - t))
