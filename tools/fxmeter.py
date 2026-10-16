"""Hardware check of effects with the outputs MUTED: boot the OS meter build with FX1 = id, read back state + load.

  py -3.10 fxmeter.py socket://192.168.1.77:23 4 7 8 9      (effect ids)
  py -3.10 fxmeter.py socket://192.168.1.77:23 chain:7,12   (CHAIN mode: RADIO -> REVERB)
For each id: builds os_meter.hex with FX1 = id at init, loads every module + its tables + codec_on with the DAC level
at 0 (silent), runs 6 s, then reads the idle-spin histogram (X:$1400, 1 spin = 9.14 cycles) and a few state words.
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
    port = sys.argv[1]
    ids = [v if v.startswith('chain:') else int(v) for v in sys.argv[2:]]
    tmpd = tempfile.mkdtemp()
    for name in ('autotune.py', 'vocal.py', 'vocal2.py', 'vocal3.py', 'vocal4.py', 'vocal5.py', 'amp.py'):
        subprocess.run([PY, os.path.join(DSP, name)], check=True, capture_output=True)
    subprocess.run([PY, os.path.join(DSP, 'os.py'), 'meter'], check=True, capture_output=True)
    subprocess.run([PY, os.path.join(DSP, 'codec_on.py'), 'dac=00'], check=True, capture_output=True, cwd=DSP)
    mute = os.path.join(tmpd, 'codec_mute.hex')
    os.replace(os.path.join(DSP, 'codec_on.hex'), mute)
    subprocess.run([PY, os.path.join(DSP, 'codec_on.py')], check=True, capture_output=True, cwd=DSP)   # restore
    base, words = open(os.path.join(DSP, 'os_meter.hex')).read().split('\n')[:2]
    w = words.split()
    k = next(i for i in range(len(w) - 2) if w[i] == '56F400' and w[i + 1] == '000000' and w[i + 2] == '542100')
    import runpy, io, contextlib
    sys.argv = ['os.py', 'meter']
    with contextlib.redirect_stdout(io.StringIO()):
        loop = runpy.run_path(os.path.join(DSP, 'os.py'))['labels']['loop']
    for fx in ids:
        strip = isinstance(fx, str) and fx.endswith('+s')                 # chain:...+s = STRIP on too
        chain = [int(v) for v in fx.split(':')[1].rstrip('+s').split(',')] if isinstance(fx, str) else None
        w[k + 1] = '%06X' % (0 if chain else fx)
        osk = os.path.join(tmpd, 'os_m%s.hex' % str(fx).replace(':', '_').replace(',', '_'))
        open(osk, 'w').write(base + '\n' + ' '.join(w) + '\n')
        for f in ('autotune.hex', 'vocal.hex', 'vocal_tab.hex', 'vocal2.hex', 'vocal2_tab.hex', 'vocal3.hex',
                  'vocal3_tab.hex', 'vocal4.hex', 'vocal4_tab.hex', 'vocal5.hex', 'vocal5_tab.hex', 'amp.hex',
                  'amp_tab.hex'):
            out = run(port, 'load', os.path.join(DSP, f))
            if 'verify OK' not in out:
                raise SystemExit('%s: %s' % (f, out))
        for f in (osk, mute):
            out = run(port, 'load', f)
            if 'verify OK' not in out:
                raise SystemExit('%s: %s' % (f, out))
        run(port, 'go', '900')
        if chain:                                    # poke CHAIN mode in, then back into the kernel loop
            time.sleep(1)
            from asm56 import Asm, R5
            pa = Asm(0x950)
            for addr, val in ([(0x20, 3), (0x0200, len(chain)), (0x0207, int(strip))]
                              + [(0x0201 + i, c) for i, c in enumerate(chain)]):
                pa.par(move=('Movex_ea', dict(W=1, d=R5['A'], M=6, R=4)), ext=val)
                pa.par(move=('Movex_ea', dict(W=0, d=R5['A'], M=6, R=0)), ext=addr)
            pa.labels['loop'] = loop
            pa.jmp('loop')
            pa.link()
            pk = os.path.join(tmpd, 'poke.hex')
            pa.hexfile(pk)
            out = run(port, 'load', pk)
            if 'verify OK' not in out:
                raise SystemExit('poke: ' + out)
            run(port, 'go', '950')
        time.sleep(6)
        hist = read(port, 'x', 0x1400, 0x100, os.path.join(tmpd, 'h.bin'))
        fx1 = read(port, 'x', 0x21, 1, os.path.join(tmpd, 'f.bin'))[0]
        nz = [(s, c) for s, c in enumerate(hist) if c]
        tot = sum(hist)
        lo = nz[0][0] if nz else -1
        print('FX1=%s (read back %d)  frames %d  min spins %d -> worst %d cycles used of %d  (typical %d)' % (
            fx, fx1, tot, lo, FRAME - lo * SPIN, FRAME, FRAME - max(nz, key=lambda t: t[1])[0] * SPIN))
        print('   lowest bins:', nz[:5], ' top bins:', sorted(nz, key=lambda t: -t[1])[:4])
        if chain:
            cb = read(port, 'x', 0x0200, 4, os.path.join(tmpd, 'c.bin'))
            print('   CHAIN mode %d  block %s' % (read(port, 'x', 0x20, 1, os.path.join(tmpd, 'm.bin'))[0], cb))
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
