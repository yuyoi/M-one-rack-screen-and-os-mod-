"""Run the whole OS (os.hex + autotune.hex) in the simulator with FX1 = TUNE; report output pitch.

  py -3.10 sim_os_tune.py 215            chromatic: 215 Hz -> nearest note (A3 220)
  py -3.10 sim_os_tune.py 233 Cmaj       C major snap map (as the ESP writes it): A#3 233 Hz -> A3 220 (ties snap down)
"""
import os, sys, time, runpy, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ('disasm', 'tools'): sys.path.insert(0, os.path.join(HERE, '..', '..', _d))
sys.path.insert(0, HERE)
import numpy as np
from sim56 import Sim
import autotune_model as m
Q = 1 << 23


def hexwords(name):
    tk = open(os.path.join(HERE, '..', name)).read().split()
    return int(tk[0], 16), [int(v, 16) for v in tk[1:]]


def snap_map(key, scale):            # same rule as the ESP (menu.h): offset to the nearest scale note, ties go down
    steps = {'chromatic': range(12), 'major': (0, 2, 4, 5, 7, 9, 11), 'minor': (0, 2, 3, 5, 7, 8, 10)}[scale]
    allowed = {(key + s) % 12 for s in steps}
    out = []
    for pc in range(12):
        for d in (0, -1, 1, -2, 2):
            if (pc + d) % 12 in allowed:
                out.append(d)
                break
    return out


f0 = float(sys.argv[1]) if len(sys.argv) > 1 else 215.0
scale = sys.argv[2] if len(sys.argv) > 2 else 'chromatic'
smap = snap_map(0, 'major') if scale == 'Cmaj' else [0] * 12

t = time.time()
from sim_radio import boot_os        # the whole OS as `boot` loads it (kernel init calls every module's init)
s = boot_os(4)                       # SINGLE, FX1 = TUNE  (what the ESP writes over J8)
for pc, d in enumerate(smap):
    s.X[0x23 + pc] = d & 0xFFFFFF
x = m.voice(f0, 0.6)
xi = np.round(x / 2 * (Q - 1)).astype(int)
out, worst = s.run_audio(list(2 * xi), list(xi), max_instr_per_frame=3_000_000)
y = np.array([v - (1 << 24) if v >> 23 else v for v in out[3::2]], float) / Q
f = m.pitch_of(y[16000:26000])
n = 69 + 12 * np.log2(f / 440)
tgt = 440 * 2 ** ((round(n) - 69) / 12)
names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
print('%s: in %.1f Hz -> out %.2f Hz = %s%d %+.1f c | DSP note=%d | worst %d instr/frame | %.0f s' % (
    scale, f0, f, names[round(n) % 12], round(n) // 12 - 1, m.cents(f, tgt), s.X.get(0x0E, -1), worst, time.time() - t))
