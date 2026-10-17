"""PHASER (effect 19: Phase 90) and WAH (effect 20: Cry Baby, Reso Wah). Writes filt.hex. References:
model/filt_ref.py (same steps); voicings: model/filt_model.py; test: model/sim_filt.py (bit-exact).

fx_phaser / fx_wah: sample in X1 -> out in X1. No init needed: the ESP's pedal pick writes the params and clears the
state (zeros; the wah's PS = POS). With nothing written, both output 0 (DRY = WET = 0 / IG = 0).
Uses R0, R4, R5 (left linear).
Memory (agreed with the FX lab 2026-10-17, VOCAL_ARCH.md): P $0960-$09FF, X $0DC0-$0DFF.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, ea  # noqa: E402
from asmh import H, MAC, MPY  # noqa: E402
from dis56k import listing  # noqa: E402
import filt_ref as FR  # noqa: E402

BASE, END = 0x0960, 0x09FF
PP, PS, PW, WS = FR.PP, FR.PS, FR.PW, FR.WS

a = Asm(BASE)
h = H(a)


def macr(s1, s2, d, k=0):
    return ('Macr_S1S2', MAC(s1, s2, d, k)[1])


def horner(n, off, x='X1', out='X0'):
    """out = sat(...sat(c[n] x + c[n-1]) x ... + c0), coefficients at X:(R5 + off + k), x in a register"""
    h.xr('Y0', off + n, R=5); h.mpy(x, 'Y0', 'A'); h.xr('Y0', off + n - 1, R=5); h.add('Y0', 'A')
    for k in range(n - 2, -1, -1):
        h.mv('A', 'Y0'); h.mpy(x, 'Y0', 'A'); h.xr('Y0', off + k, R=5); h.add('Y0', 'A')
    h.mv('A', out)


# ======================================================================== fx_phaser (R5 = params, R4 = state)
a.label('fx_phaser')
h.li('R5', PP); h.li('R4', PS)
h.xr('A', 0, R=4); h.xr('X0', 0, R=5); h.add('X0', 'A'); h.xw('A1', 0, R=4)   # PH += INC (wraps)
h.mv('A1', 'X0'); h.mv('X0', 'A'); h.abs_('A'); h.asl1('A')
h.li('B', 0x7FFFFF); h.sub('A', 'B')
h.mv('B', 'Y1')                                                   # l = 1 - 2|ph|
h.mv('X1', 'B')                                                   # keep x in B
horner(3, 1, x='Y1', out='X0')                                    # X0 = a
h.xw('B', 15, R=4)                                                # x (scratch)
h.xr('X1', 1, R=4); h.xr('Y0', 5, R=5); h.mac('X1', 'Y0', 'B')    # u = x + FB y4
h.li('R0', PS + 2)
a.do(4, 'ap_end')
h.ldxi('(R0)+', 'Y1')                                             # x1s
h.ldxi('(R0)-', 'Y0')                                             # y1s
h.mv('B', 'X1'); h.mv('X1', 'B')                                  # u = sat (and b = sat u)
h.sub('Y0', 'B')                                                  # u - y1s
h.mv('B', 'Y0')
h.mv('Y1', 'A'); a.par(alu=macr('X0', 'Y0', 'A'))                 # y = rnd(x1s + a sat(u - y1s))
h.stxi('X1', '(R0)+')                                             # x1 = u
h.stxi('A', '(R0)+')                                              # y1 = sat(y)
h.mv('A', 'B')
a.label('ap_end')
h.mv('B', 'X0')
h.xw('X0', 1, R=4)                                                # y4
h.xr('Y0', 7, R=5); h.mpy('X0', 'Y0', 'A')
h.xr('X0', 15, R=4); h.xr('Y0', 6, R=5); h.mac('X0', 'Y0', 'A')
h.mv('A', 'X1')
h.rts()

# ======================================================================== fx_wah (R5 = params, R4 = state)
a.label('fx_wah')
h.li('R5', PW); h.li('R4', WS)
h.xr('B', 0, R=5); h.xr('X0', 0, R=4); h.sub('X0', 'B'); h.mv('B', 'Y0')
h.mv('X0', 'A'); h.xr('X0', 1, R=5); a.par(alu=macr('X0', 'Y0', 'A'))   # ps += SM sat(POS - ps), rounded
h.xw('A', 0, R=4)
h.mv('X1', 'B')                                                   # keep x
h.xr('X1', 0, R=4)
horner(3, 2, x='X1', out='X0')                                    # f
h.xw('X0', 7, R=4)
horner(2, 6, x='X1', out='X0')                                    # 1/Q
h.xw('X0', 6, R=4)
h.mv('B', 'X0'); h.xr('Y0', 9, R=5); h.mpy('X0', 'Y0', 'B')       # xi = x IG (B, then sat)
h.xr('A', 1, R=4); h.xr('X0', 2, R=4); h.xr('Y0', 7, R=4); a.par(alu=macr('X0', 'Y0', 'A'))
h.xw('A', 1, R=4)                                                 # lp = rnd(lp + f bp)
h.mv('B', 'X1'); h.mv('X1', 'B')                                  # b = sat(xi)
h.xr('X1', 1, R=4); h.sub('X1', 'B')                              # - lp
h.xr('Y0', 6, R=4); h.mac('X0', 'Y0', 'B', k=1)                   # - q bp
h.mv('B', 'Y0')                                                   # hp = sat
h.xr('A', 2, R=4); h.xr('X0', 7, R=4); a.par(alu=macr('X0', 'Y0', 'A'))
h.xw('A', 2, R=4)                                                 # bp = rnd(bp + f hp)
h.xr('X0', 2, R=4); h.xr('Y0', 10, R=5); h.mpy('X0', 'Y0', 'A')
h.xr('X0', 1, R=4); h.xr('Y0', 11, R=5); h.mac('X0', 'Y0', 'A')
h.asl(4, 'A')
h.mv('A', 'X1')
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'FILTER runs past its P space: %X' % end
FX_PHASER, FX_WAH = a.labels['fx_phaser'], a.labels['fx_wah']

if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d  end=P:%04X  labels=%s' % (len(words), end, {k: '%04X' % v for k, v in a.labels.items()}))
    a.hexfile(os.path.join(HERE, 'filt.hex'))
