"""Run the whole OS in the simulator with FX1 = FORMANT (8) or OCTAVE (9); compare with psola_dsp_model.

  py -3.10 sim_psola.py FX P F [WET]       e.g. 8 1.0 0.78 (GIANT), 9 0.5 1.0 0.5 (octave down, 50 %)
The model gets the DSP's own detector readout (X:$0D) frame by frame, so the comparison is exact.
Input: a 150 Hz voice with formants at 700 / 1200 / 2600 Hz (0.8 s).
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from scipy.signal import lfilter
from sim_radio import boot_os
import psola_dsp_model as pm
import autotune_model as am
from psola_model import env_centroid
Q = 1 << 23
FS = 44100

fx, p, f = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
wet = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
f0 = 150.0
n = int(FS * 0.8)
pulses = np.zeros(n); pulses[(np.arange(0, n, FS / f0)).astype(int)] = 1.0
v = pulses
for fc, bw in ((700, 90), (1200, 110), (2600, 160)):
    r = np.exp(-np.pi * bw / FS); th = 2 * np.pi * fc / FS
    v = lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], v)
v = 0.3 * v / np.abs(v).max()
xi = np.round(v / 2 * (Q - 1)).astype(int)
xq = 2 * xi

t = time.time()
s = boot_os(fx)
prm = pm.params(p, f, wet)
pb = 0x0220 if fx == 8 else 0x0230
for k, val in enumerate(prm):
    s.X[pb + k] = val
model = pm.PsolaDSP(*prm)
y, ref, worst = [], [], 0
for k in range(n):
    out, w = s.run_audio([2 * xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(model.step(int(xq[k]), s.X.get(0x0D, 0)))
y, ref = np.array(y[1:]), np.array(ref[:-1])          # TX1 carries the previous frame's output
err = np.abs(y - ref)
bad = np.flatnonzero(err > 0)
seg = slice(20000, n)
yf = y / Q
print('fx %d p %.2f f %.2f | worst %d instr/frame | max err %d LSB (first at %s) | f0 %.1f -> %.1f  centroid %.0f -> %.0f'
      ' | %.0f s' % (fx, p, f, worst, err.max(), bad[0] if len(bad) else '-', am.pitch_of(v[seg]), am.pitch_of(yf[seg]),
                     env_centroid(v[seg], f0), env_centroid(yf[seg], f0), time.time() - t))
