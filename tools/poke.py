"""Write a batch of X words into the RUNNING kernel (a pedal pick, a preset), any length.

  py -3.10 poke.py socket://192.168.1.77:23 pairs.txt [meter]
  pairs.txt: one 'ADDR VALUE' per line (hex, X space); '#' starts a comment.
  from python: poke.poke(port, [(addr, value), ...], meter=False)
Up to 4095 pairs. The (addr, value) table goes to REVERSE's upper SRAM half X:$028000 (REVERSE plays that garbage
once if it is picked later), in loads of <= 1000 words (the ESP's L command takes 1024). Then a stub at P:$0950
copies the pairs and jumps back into the kernel loop (no re-init). 'meter' = the running build is os.py meter (fxmeter's).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DSP = os.path.join(HERE, '..', 'dsp')
TAB, STUB, CHUNK = 0x028000, 0x0950, 1000


def mone(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'mone.py')] + list(args), capture_output=True, text=True,
                       timeout=120)
    return r.stdout + r.stderr


def loop_label(meter):
    import runpy, io, contextlib
    argv = sys.argv
    sys.argv = ['os.py'] + (['meter'] if meter else [])
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return runpy.run_path(os.path.join(DSP, 'os.py'))['labels']['loop']
    finally:
        sys.argv = argv


def stub(n, loop):
    sys.path.insert(0, HERE)
    from asm56 import Asm, R5, ea
    from asmh import H
    a = Asm(STUB)
    h = H(a)
    h.movec('M0', 0xFFFFFF); h.movec('M1', 0xFFFFFF)
    a.par(move=('Movex_ea', dict(W=1, d=R5['R0'], M=6, R=4)), ext=TAB)          # move #TAB,r0
    a.do(n, 'pk_end')
    a.par(move=('Movex_ea', dict(W=1, d=R5['R1'], **ea('(R0)+'))))
    a.par(move=('Movex_ea', dict(W=1, d=R5['A'], **ea('(R0)+'))))
    a.word(0); a.word(0)
    a.par(move=('Movex_ea', dict(W=0, d=R5['A'], **ea('(R1)'))))
    a.label('pk_end')
    a.labels['loop'] = loop
    a.jmp('loop')
    assert STUB + len(a.link()) <= 0x0960, 'poke stub runs into filt.hex at P:$0960'
    return a


def poke(port, pairs, meter=False, tmpd=None):
    import tempfile
    tmpd = tmpd or tempfile.mkdtemp()
    pairs = [(a & 0xFFFFFF, v & 0xFFFFFF) for a, v in pairs]
    assert 0 < len(pairs) <= 4095, 'pairs: 1..4095 (one DO loop: the stub must fit $0950-$095F)'
    words = [w for p in pairs for w in p]
    for k in range(0, len(words), CHUNK):
        f = os.path.join(tmpd, 'poke_tab%d.hex' % k)
        open(f, 'w').write('%X\n%s\n' % (TAB + k, ' '.join('%06X' % w for w in words[k:k + CHUNK])))
        out = mone(port, 'load', f)
        if 'verify OK' not in out:
            raise SystemExit('poke table at %X: %s' % (TAB + k, out))
    a = stub(len(pairs), loop_label(meter))
    f = os.path.join(tmpd, 'poke_stub.hex')
    a.hexfile(f)
    out = mone(port, 'load', f)
    if 'verify OK' not in out:
        raise SystemExit('poke stub: ' + out)
    return mone(port, 'go', '%X' % STUB)


if __name__ == '__main__':
    pr = []
    for ln in open(sys.argv[2]):
        ln = ln.split('#')[0].split()
        if len(ln) == 2:
            pr.append((int(ln[0], 16), int(ln[1], 16)))
    print(poke(sys.argv[1], pr, meter='meter' in sys.argv[3:]).strip())
    print('%d words written' % len(pr))
