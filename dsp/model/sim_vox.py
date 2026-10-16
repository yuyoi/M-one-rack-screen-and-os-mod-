"""Run the whole OS (os.hex + autotune.hex + vocal.hex) in the simulator with FX1 = VOX; compare with vox_model.

  py -3.10 sim_vox.py        loud voice (comp + tube working), silence (slap tail), quiet voice, sine EQ points
"""
import os, sys, time, runpy, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ('disasm', 'tools'): sys.path.insert(0, os.path.join(HERE, '..', '..', _d))
sys.path.insert(0, HERE)
import numpy as np
from sim56 import Sim
import autotune_model as am
import vox_model as vm
Q = 1 << 23
FS = 44100


def hexwords(name):
    tk = open(os.path.join(HERE, '..', name)).read().split()
    return int(tk[0], 16), [int(v, 16) for v in tk[1:]]


with contextlib.redirect_stdout(io.StringIO()):
    labels = runpy.run_path(os.path.join(HERE, '..', 'os.py'))['labels']
    runpy.run_path(os.path.join(HERE, '..', 'vocal.py'), run_name='__main__')

x = np.concatenate([am.voice(220, 0.6, vib=0.3) * 2.0, np.zeros(int(0.35 * FS)), am.voice(330, 0.3) * 0.08])
xi = np.round(x / 2 * (Q - 1)).astype(int)                  # L = R = x/2: the kernel sums them
xs = 2 * xi / Q

ob, ow = hexwords('os.hex')
s = Sim(ow, ob)
for name in ('autotune.hex', 'vocal.hex'):
    b, w = hexwords(name)
    s.P.update({b + i: v for i, v in enumerate(w)})
s.pc = ob
t = time.time()
while s.pc != labels['loop']:
    s.step()
s.X[0x20], s.X[0x21] = 0, 5                                 # SINGLE, FX1 = VOX
out, worst = s.run_audio(list(xi), list(xi), max_instr_per_frame=100000)
y = np.array(out[1::2], float) / Q                          # the sim records signed TX1 words
ref = vm.Vox(exact=True).run(xs)
n = min(len(y), len(ref))
y, ref = y[:n], ref[:n]                                     # same frame: the right slot is output right away
err = np.abs(y - ref)
seg = lambda a, b: slice(int(a * FS), int(b * FS))
pk = lambda v: 20 * np.log10(np.abs(v).max() + 1e-12)
print('worst %d instr/frame | %.0f s' % (worst, time.time() - t))
print('max |sim - model| = %.2e (%.0f dB)   rms %.2e' % (err.max(), 20 * np.log10(err.max() + 1e-12), np.sqrt((err ** 2).mean())))
print('in  peaks: loud %.1f dB  quiet %.1f dB' % (pk(xs[seg(0, 0.6)]), pk(xs[seg(0.95, 1.25)])))
print('out peaks: loud %.1f dB  tail %.1f dB  quiet %.1f dB' % (pk(y[seg(0.3, 0.6)]), pk(y[seg(0.62, 0.72)]), pk(y[seg(1.0, 1.25)])))
print('DSP: g = %.3f  env = %.3f  input peak X:$1F = %.3f' % (s.X.get(0x1B, 0) / Q, s.X.get(0x1A, 0) / Q, s.X.get(0x1F, 0) / Q))
if len(sys.argv) > 1:
    np.savez(sys.argv[1], y=np.array(out[1::2], float) / Q, xs=xs)
