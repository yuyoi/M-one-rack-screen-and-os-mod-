"""Vocal effects, part 4 (P:$1220-$13FF): HARMONY (id 10), DOUBLER (id 11) and the shared two-head shifter.
Writes vocal4.hex + vocal4_tab.hex. Mirrors dsp/model/harmony_model.py step by step.

HARMONY: ring X:$036000 (4096), state X:$03A0 (R3), voices at X:$03A4 / X:$03A6, params X:$0240 (R5).
  Voice semitones come from TUNE's note (X:$0E, the detector runs at most once a frame) through 12-word maps.
DOUBLER: ring X:$037000 (2048), state X:$03B0, params X:$0260.
Tables (SRAM $031900): pitch class by MIDI note (128), shifter INC by semitone (-12..+24).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm  # noqa: E402
from dis56k import listing  # noqa: E402
from asmh import H  # noqa: E402
import io, contextlib  # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    import autotune  # noqa: E402
import harmony_model as hm  # noqa: E402

BASE, END = 0x1220, 0x13FF
TUNE_DETECT, NOTE_ADDR = autotune.a.labels['tune_detect'], 0x0E
HRING, DRING, TAB4 = 0x036000, 0x037000, 0x031900
PCT, INCT = TAB4, TAB4 + 128
HS, HP, DS, DP = 0x03A0, 0x0240, 0x03B0, 0x0260
(H_W, H_DRY, H_ACC, H_TMP) = range(4)            # harmony state (R3)
V1, V2 = 4, 6                                    # voice states: +0 PH
(D_W, D_S, D_C, D_X, D_ACC) = range(5)           # doubler state
q = hm.q
TAB = hm.PCTAB + [v & 0xFFFFFF for v in hm.INCTAB]

a = Asm(BASE)
h = H(a)
j = h.j

# ============================================================ sh: one shifter voice
# in: R2 -> voice state (+0 PH), Y0 = INC, N6 = newest ring index, ring base HRING.  out: X1 (Q23)
a.label('sh')
h.xr('A', 0, R=2); h.sub('Y0', 'A'); h.andi(0x7FFFFF, 'A'); h.xw('A1', 0, R=2)        # PH -= INC (mod 1)
h.clr('B'); h.xw('B', H_ACC); h.mv('A1', 'X1')
a.jsr('sh_head')
h.mv('X1', 'A'); h.addi(0x400000, 'A'); h.andi(0x7FFFFF, 'A'); h.mv('A1', 'X1')       # second head: +1/2
a.jsr('sh_head')
h.xr('A', H_ACC); h.mv('A', 'X1')
h.rts()
# sh_head: X1 = head phase p; acc (X:H_ACC, 24-bit) += tri(p) * interp(ring, w - p*WN); X1 kept
a.label('sh_head')
h.mv('X1', 'X0'); h.mpyi(hm.WN, 'X0', 'A')                                         # delay = p*WN (A1:A0)
h.mv('A0', 'Y1'); h.mv('A1', 'Y0'); h.mv('N6', 'B'); h.sub('Y0', 'B')                                 # B1 = w - di
h.clr('A'); h.mv('Y1', 'A1'); h.lsr(1, 'A'); h.mv('A1', 'Y1')                      # frac
h.andi(hm.NR - 1, 'B'); h.ori(HRING, 'B'); h.mv('B1', 'R1')
h.subi(1, 'B'); h.andi(hm.NR - 1, 'B'); h.ori(HRING, 'B'); h.mv('B1', 'R4')
h.li('A', 0x7FFFFF); h.sub('X0', 'A'); h.sub('X0', 'A'); h.abs_('A')               # |1 - 2p|
h.li('B', 0x7FFFFF); h.sub('A', 'B'); h.mv('B', 'Y0')                              # g = 1 - |1 - 2p|
h.ldxi('(R1)', 'X0'); h.ldxi('(R4)', 'A'); h.sub('X0', 'A'); h.mv('A', 'X0')       # b1 - b0
h.mpy('X0', 'Y1', 'A'); h.ldxi('(R1)', 'X0'); h.add('X0', 'A'); h.mv('A', 'X0')    # v
h.xr('B', H_ACC); h.mac('X0', 'Y0', 'B'); h.xw('B', H_ACC)
h.rts()

# ============================================================ vocal4_init
a.label('vocal4_init')
h.clr('A'); h.li('R0', HS); h.rep(8); h.stxi('A', '(R0)+')
h.li('R0', DS); h.rep(5); h.stxi('A', '(R0)+')
h.li('R0', HRING); h.rep(4095); h.stxi('A', '(R0)+')
h.stxi('A', '(R0)+')
h.li('R0', DRING); h.rep(2048); h.stxi('A', '(R0)+')
h.li('A', 0x7FFFFF); h.stl('A', DS + D_C)
for k, v in enumerate(hm.harmony_params()):
    h.li('A', v); h.stl('A', HP + k)
for k, v in enumerate(hm.doubler_params()):
    h.li('A', v); h.stl('A', DP + k)
for k, v in enumerate(hm.shimmer_params()):
    h.li('A', v); h.stl('A', 0x02A0 + k)
h.rts()

# ============================================================ fx_harmony (X1 in -> X1 out)
a.label('fx_harmony')
h.stl('X1', HS + H_TMP)
a.jsr('tune_detect'); a.labels['tune_detect'] = TUNE_DETECT
h.li('R3', HS); h.li('R5', HP)
h.ldl(HS + H_TMP, 'X1')
h.xr('A', H_W); h.ori(HRING, 'A'); h.mv('A1', 'R1'); h.xr('A', H_W); h.mv('A1', 'N6')   # ring write
h.xr('Y0', 2, R=5); h.mpy('X1', 'Y0', 'A'); h.xw('A', H_DRY)                         # dry part (stored)
h.stxi('X1', '(R1)')
h.clr('A'); h.ldx(NOTE_ADDR, 'A1'); h.andi(127, 'A'); h.addi(PCT, 'A'); h.mv('A1', 'R1'); h.nop(); h.nop()
h.ldxi('(R1)', 'N4')                                                                    # pitch class
for k, (vs, mix) in enumerate(((V1, 0), (V2, 1))):
    h.li('R4', HP + 4 + 12 * k); h.nop(); h.nop(); h.ldxi('(R4+N4)', 'A')             # semitones (signed)
    h.cmpi(hm.SEMI_HI, 'A'); j('LE', 'h_hi%d' % k); h.li('A', hm.SEMI_HI)
    a.label('h_hi%d' % k)
    h.a.op('Cmp_xxxxS2', ext=hm.SEMI_LO & 0xFFFFFF, d=0); j('GE', 'h_lo%d' % k); h.li('A', hm.SEMI_LO & 0xFFFFFF)
    a.label('h_lo%d' % k)
    h.addi(INCT - hm.SEMI_LO, 'A'); h.mv('A1', 'R1'); h.li('R2', HS + vs); h.nop()
    h.ldxi('(R1)', 'Y0')
    a.jsr('sh')
    h.li('R5', HP); h.nop(); h.nop(); h.xr('Y0', mix, R=5); h.xr('A', H_DRY)          # += mix * voice
    h.mac('X1', 'Y0', 'A'); h.xw('A', H_DRY)
h.xr('A', H_DRY); h.mv('A', 'X1')
h.xr('A', H_W); h.addi(1, 'A'); h.andi(hm.NR - 1, 'A'); h.xw('A1', H_W)
h.rts()

# ============================================================ fx_doubler (X1 in -> X1 out)
a.label('fx_doubler')
h.li('R3', DS); h.li('R5', DP)
h.xw('X1', D_X)
h.xr('A', D_W); h.ori(DRING, 'A'); h.mv('A1', 'R1'); h.xr('A', D_W); h.mv('A1', 'N6'); h.nop()
h.stxi('X1', '(R1)')
h.xr('Y0', 3, R=5); h.xr('X0', D_C); h.xr('A', D_S); h.mac('X0', 'Y0', 'A'); h.xw('A', D_S)   # LFO
h.mv('A', 'X0'); h.xr('A', D_C); h.mac('X0', 'Y0', 'A', k=1); h.xw('A', D_C)
for d, m in ((0, D_S), (1, D_C)):
    h.xr('X0', m); h.xr('Y0', 2, R=5); h.mpy('X0', 'Y0', 'A'); h.xr('X0', d, R=5); h.add('X0', 'A')   # pos
    h.mv('A0', 'Y1'); h.mv('A1', 'Y0'); h.mv('N6', 'B'); h.sub('Y0', 'B')
    h.clr('A'); h.mv('Y1', 'A1'); h.lsr(1, 'A'); h.mv('A1', 'Y1')
    h.andi(hm.DR - 1, 'B'); h.ori(DRING, 'B'); h.mv('B1', 'R1')
    h.subi(1, 'B'); h.andi(hm.DR - 1, 'B'); h.ori(DRING, 'B'); h.mv('B1', 'R4'); h.nop()
    h.ldxi('(R1)', 'X0'); h.ldxi('(R4)', 'A'); h.sub('X0', 'A'); h.mv('A', 'X1')
    h.mpy('X1', 'Y1', 'A'); h.add('X0', 'A'); h.mv('A', 'X0')                          # st(interp)
    if d == 0:
        h.xw('X0', D_ACC)
h.xr('A', D_ACC); h.add('X0', 'A'); h.alu('Asr_D', d=0); h.mv('A', 'Y0')            # v = (v1 + v2)/2
h.xr('X1', D_X); h.mv('X1', 'A'); h.xr('Y1', 4, R=5); h.mac('Y0', 'Y1', 'A'); h.mv('A', 'X1')
h.xr('A', D_W); h.addi(1, 'A'); h.andi(hm.DR - 1, 'A'); h.xw('A1', D_W)
h.rts()

# ============================================================ fx_shimmer (X1 in -> X1 out), id 14
SP, REV_OK = 0x02A0, 0x0304                   # params; REVERB's last output (vocal3 state OK)
a.label('fx_shimmer')
h.li('R3', HS); h.li('R5', SP)
h.xw('X1', H_TMP)
h.xr('A', H_W); h.ori(HRING, 'A'); h.mv('A1', 'R1'); h.xr('A', H_W); h.mv('A1', 'N6')
h.ldl(REV_OK, 'X0'); h.li('R2', HS + V1); h.xr('Y0', 1, R=5); h.stxi('X0', '(R1)')
a.jsr('sh')
h.xr('A', H_TMP); h.xr('Y0', 0, R=5); h.mac('X1', 'Y0', 'A'); h.mv('A', 'X1')
h.xr('A', H_W); h.addi(1, 'A'); h.andi(hm.NR - 1, 'A'); h.xw('A1', H_W)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal4.py runs past P:%04X: %X' % (END, end)
assert TAB4 + len(TAB) <= 0x031C00, 'vocal4_tab runs into the AMP table'
VOCAL4_INIT, FX_HARMONY, FX_DOUBLER, FX_SHIMMER = (a.labels[n] for n in ('vocal4_init', 'fx_harmony', 'fx_doubler',
                                                                           'fx_shimmer'))
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  init=%04X harmony=%04X doubler=%04X  table %d words at %06X' % (
        len(words), end, VOCAL4_INIT, FX_HARMONY, FX_DOUBLER, len(TAB), TAB4))
    a.hexfile(os.path.join(HERE, 'vocal4.hex'))
    open(os.path.join(HERE, 'vocal4_tab.hex'), 'w').write('%X\n%s\n' % (TAB4, ' '.join('%06X' % (w & 0xFFFFFF) for w in TAB)))
