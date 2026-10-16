"""Hardware check of effects with the outputs MUTED: boot the OS meter build with FX1 = id, read back state + load.

  py -3.10 fxmeter.py socket://192.168.1.77:23 4 7 8 9      (effect ids)
For each id: builds os_meter.hex with FX1 = id at init, loads every module + its tables + codec_on with the DAC level
at 0 (silent), runs 6 s, then reads the idle-spin histogram (X:$1100, 1 spin = 9.14 cycles) and a few state words.
Leaves the DSP running the muted meter build: run `mone.py ... boot` afterwards for the normal OS with sound.
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DSP = os.path.join(HERE, '..', 'dsp')
PY = sys.executable
SPIN, FRAME = 9.14, 2112


def run(*args, check=True):
    r = subprocess.run([PY, os.path.join(HERE, 'mone.py')] + list(args), capture_output=True, text=True, timeout=120)
    if check and r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    return r.stdout


def read(port, space, start, count, tmp):
    run(port, space + 'mem', tmp, '%X' % start, '%X' % count)
    d = open(tmp, 'rb').read()
    return [int.from_bytes(d[i:i + 3], 'little') for i in range(0, len(d), 3)]


def main():
    port, ids = sys.argv[1], [int(v) for v in sys.argv[2:]]
    tmpd = tempfile.mkdtemp()
    for name in ('autotune.py', 'vocal.py', 'vocal2.py'):
        subprocess.run([PY, os.path.join(DSP, name)], check=True, capture_output=True)
    subprocess.run([PY, os.path.join(DSP, 'os.py'), 'meter'], check=True, capture_output=True)
    subprocess.run([PY, os.path.join(DSP, 'codec_on.py'), 'dac=00'], check=True, capture_output=True, cwd=DSP)
    mute = os.path.join(tmpd, 'codec_mute.hex')
    os.replace(os.path.join(DSP, 'codec_on.hex'), mute)
    subprocess.run([PY, os.path.join(DSP, 'codec_on.py')], check=True, capture_output=True, cwd=DSP)   # restore
    base, words = open(os.path.join(DSP, 'os_meter.hex')).read().split('\n')[:2]
    w = words.split()
    k = next(i for i in range(len(w) - 2) if w[i] == '56F400' and w[i + 1] == '000000' and w[i + 2] == '542100')
    for fx in ids:
        w[k + 1] = '%06X' % fx
        osk = os.path.join(tmpd, 'os_m%d.hex' % fx)
        open(osk, 'w').write(base + '\n' + ' '.join(w) + '\n')
        for f in ('autotune.hex', 'vocal.hex', 'vocal_tab.hex', 'vocal2.hex'):
            out = run(port, 'load', os.path.join(DSP, f))
            if 'verify OK' not in out:
                raise SystemExit('%s: %s' % (f, out))
        for f in (osk, mute):
            out = run(port, 'load', f)
            if 'verify OK' not in out:
                raise SystemExit('%s: %s' % (f, out))
        run(port, 'go', '900')
        time.sleep(6)
        hist = read(port, 'x', 0x1100, 0x100, os.path.join(tmpd, 'h.bin'))
        fx1 = read(port, 'x', 0x21, 1, os.path.join(tmpd, 'f.bin'))[0]
        nz = [(s, c) for s, c in enumerate(hist) if c]
        tot = sum(hist)
        lo = nz[0][0] if nz else -1
        print('FX1=%d (read back %d)  frames %d  min spins %d -> worst %d cycles used of %d  (typical %d)' % (
            fx, fx1, tot, lo, FRAME - lo * SPIN, FRAME, FRAME - max(nz, key=lambda t: t[1])[0] * SPIN))
        print('   lowest bins:', nz[:5])
        if fx == 7:
            st = read(port, 'x', 0x0140 + 20, 22, os.path.join(tmpd, 's.bin'))
            print('   RADIO cur mode %d  W %d  LFSR %06X  g %06X  env %06X' % (st[16], st[6], st[11], st[1], st[2]))
        if fx in (8, 9):
            b = 0x0180 if fx == 8 else 0x01C0
            st = read(port, 'x', b, 26, os.path.join(tmpd, 's.bin'))
            print('   PSOLA W %d  P %d  invP %06X  marks %s  PF(X:$0D) %06X' % (
                st[0], st[20], st[16], st[5:13], read(port, 'x', 0x0D, 1, os.path.join(tmpd, 'p.bin'))[0]))
        if fx == 4:
            st = read(port, 'x', 0x00, 0x19, os.path.join(tmpd, 's.bin'))
            print('   TUNE period X:$0D %06X  note X:$0E %d  state %d' % (st[0x0D], st[0x0E], st[5]))


main()
