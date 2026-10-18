"""STRIP (input stage) + SWELL in the whole-OS simulator vs strip_model.

  py -3.10 sim_strip.py strip     X:$0207 = 1, FX1 = CLEAN (podcast EQ + some drive)
  py -3.10 sim_strip.py swell     FX1 = SWELL
  py -3.10 sim_strip.py gate      guitar gate only: low cut off (flat LC words), de-ess/comp/EQ/drive neutral
  py -3.10 sim_strip.py strip10   'strip' but only the first 10 words written (the LC words come from the init)
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import strip_model as sm
import autotune_model as am
Q = 1 << 23
which = sys.argv[1] if len(sys.argv) > 1 else 'strip'
x = np.concatenate([np.zeros(2000), am.voice(200, 0.3), np.zeros(4000), am.voice(250, 0.15) * 0.05])
xi = np.round(x / 2 * (Q - 1) * 0.6).astype(int)
t = time.time()
if which in ('strip', 'strip10', 'gate'):
    prm = (sm.strip_params(-45, 1.0, 1.0, 1.0, 0.0, [sm.q(0.5), 0, 0, 0, 0], lc=False) if which == 'gate'
           else sm.strip_params(eq=sm.eq_coefs('high', 6000, 3), drive=1.5))
    s = boot_os(0); s.X[0x0207] = 1; base = 0x0270; model = sm.Strip(prm)
    if which == 'strip10':
        prm = prm[:10]
else:
    prm = sm.swell_params()
    s = boot_os(15); base = 0x02B0; model = sm.Swell(prm)
for k, v in enumerate(prm):
    s.X[base + k] = v & 0xFFFFFF
y, ref, worst = [], [], 0
for k in range(len(xi)):
    out, w = s.run_audio([2 * xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    ref.append(model.step(int(2 * xi[k])))
y, ref = np.array(y[1:]), np.array(ref[:-1])          # TX1 carries the previous frame's output
err = np.abs(y - ref)
bad = np.flatnonzero(err > 2)
print('%s: worst %d instr/frame | max err %d LSB (first > 2 at %s) | out pk %.2f | %.0f s' % (
    which, worst, err.max(), bad[0] if len(bad) else '-', np.abs(y).max() / Q, time.time() - t))
