"""HARMONY (10) / DOUBLER (11) in the whole-OS simulator vs harmony_model (the model gets the DSP's note readout).

  py -3.10 sim_harmony.py harmony [MAP1 MAP2]     e.g. harmony 12 7  (fixed semitones for every pitch class)
  py -3.10 sim_harmony.py doubler
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import harmony_model as hm
import autotune_model as am
Q = 1 << 23
which = sys.argv[1] if len(sys.argv) > 1 else 'harmony'
x = am.voice(220, 0.6, vib=0.2)
xi = np.round(x / 2 * (Q - 1)).astype(int)
t = time.time()
if which == 'harmony':
    m1 = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    m2 = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    prm = hm.harmony_params(0.5, 0.5, 0.5, [m1] * 12, [m2] * 12)
    s = boot_os(10); base = 0x0240; model = hm.Harmony(prm)
else:
    prm = hm.doubler_params()
    s = boot_os(11); base = 0x0260; model = hm.Doubler(prm)
for k, v in enumerate(prm):
    s.X[base + k] = v & 0xFFFFFF
y, ref, worst = [], [], 0
for k in range(len(xi)):
    out, w = s.run_audio([xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(model.step(int(2 * xi[k]), s.X.get(0x0E, 0)) if which == 'harmony' else model.step(int(2 * xi[k])))
y, ref = np.array(y), np.array(ref)
err = np.abs(y - ref)
bad = np.flatnonzero(err > 2)
print('%s: worst %d instr/frame | max err %d LSB (first > 2 at %s) | note %d | %.0f s' % (
    which, worst, err.max(), bad[0] if len(bad) else '-', s.X.get(0x0E, 0), time.time() - t))
