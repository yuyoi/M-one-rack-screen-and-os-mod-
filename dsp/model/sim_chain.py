"""CHAIN mode in the simulator: X:$20 = 3, chain = RADIO (mode 0) -> FORMANT (GIANT); compare with the models chained.

  py -3.10 sim_chain.py [seconds]
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from sim_radio import boot_os
import radio_model as rm
import psola_dsp_model as pm
import autotune_model as am
Q = 1 << 23
FS = 44100
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
x = am.voice(180, secs, vib=0.3)
xi = np.round(x / 2 * (Q - 1)).astype(int)
t = time.time()
s = boot_os(0)
s.X[0x20] = 3
s.X[0x0200], s.X[0x0201], s.X[0x0202] = 2, 7, 8
radio = rm.Radio(exact=True, mode=0)
form = pm.PsolaDSP(*pm.params(1.0, 0.78))
y, ref, worst = [], [], 0
for k in range(len(xi)):
    out, w = s.run_audio([2 * xi[k]], [xi[k]], max_instr_per_frame=200000)
    worst = max(worst, w)
    y.append(out[-1])
    r = radio.step(2 * xi[k] / Q)
    ref.append(form.step(int(round(r * Q)), s.X.get(0x0D, 0)))
y, ref = np.array(y[1:]), np.array(ref[:-1])          # TX1 carries the previous frame's output
err = np.abs(y - ref)
print('chain RADIO -> FORMANT: worst %d instr/frame | max err %d LSB | out pk %.2f | %.0f s' % (
    worst, err.max(), np.abs(y).max() / Q, time.time() - t))
