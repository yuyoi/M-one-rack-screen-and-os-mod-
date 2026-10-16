"""Vocal effects, part 2 (P:$0700-$08FF): the PSOLA engine with two instances. Writes vocal2.hex.
Mirrors dsp/model/psola_dsp_model.py step by step.

  fx_formant (id 8): formants move, pitch stays (GIANT / CHIPMUNK / M<->F). Params X:$0220.
  fx_octave  (id 9): pitch moves, formants stay (octave down). Params X:$0230.
  Params: +0 INVP2 = 1/(2p) (p = pitch ratio), +1 F2 = f/2 (f = formant ratio), +2 WET, +3 GAIN2 = gain/2.
The period comes from TUNE's detector (tune_detect in autotune.py, readout X:$0D), which runs at most once a frame.
Instance state: X (R3 + displacement) 50 words at $0180 / $01C0; rings X:$034000 / X:$035000 (4096 each, SRAM).
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
import psola_dsp_model as pm  # noqa: E402

BASE, END = 0x700, 0x8FF
TUNE_DETECT, PF_ADDR = autotune.a.labels['tune_detect'], 0x0D
INST = {'formant': (0x0180, 0x0220, 0x034000, pm.params(1.0, 0.78)),        # default GIANT
        'octave': (0x01C0, 0x0230, 0x035000, pm.params(0.5, 1.0, wet=0.5))}  # default octave down, 50 % blend
TMP = 0x01FF                                     # X: input sample while tune_detect runs
# state offsets (X:(R3+n))
(W, BMAX, BPOS, BCNT, MI) = range(5)
MARKS = 5
(TIM1, TIM0, PC, INVP, RR, RB, DRY, P_, PF1, PF0, F1, F0, F2C) = range(13, 26)   # PC = cached PF
SLOTS = 27
(ACT, TC, WV, DW, POS1, POS0) = range(6)
NST = SLOTS + 6 * pm.NS
assert NST <= 0x40

a = Asm(BASE)
h = H(a)
j = h.j

# ============================================================ vocal2_init
a.label('vocal2_init')
for name, (xs, pb, ring, prm) in INST.items():
    h.clr('A'); h.li('R0', xs)
    h.rep(NST); h.stxi('A', '(R0)+')
    h.li('R1', ring)
    for _ in range(pm.NRING // 2048):                     # REP counts to 4095
        h.rep(2048); h.stxi('A', '(R1)+')
    h.li('R3', xs); h.li('A', ring); h.nop()
    h.xw('A', RB)
    h.li('A', 0xFFFFFF); h.xw('A1', PC)
    for k, v in enumerate(prm):
        h.li('A', v); h.stl('A', pb + k)
h.rts()

# ============================================================ fx_formant / fx_octave (X1 in -> X1 out)
for name, (xs, pb, ring, prm) in INST.items():
    a.label('fx_' + name)
    h.stl('X1', TMP)
    a.jsr('tune_detect'); a.labels['tune_detect'] = TUNE_DETECT
    h.ldl(TMP, 'X1'); h.li('R3', xs); h.li('R5', pb)
    a.jmp('psola')

# ============================================================ psola: R3 = state, R5 = params, X1 = input
a.label('psola')
h.xw('X1', DRY)
h.ldx(PF_ADDR, 'A'); h.xr('B', PC); h.cmp('A', 'B'); j('NE', 'p_set')         # period or F2 changed: recompute
h.xr('A', 1, R=5); h.xr('B', F2C); h.cmp('A', 'B'); j('EQ', 'p_ready')
h.ldx(PF_ADDR, 'A')
a.label('p_set')
h.xw('A', PC); h.xr('A', 1, R=5); h.xw('A', F2C); h.ldx(PF_ADDR, 'A')
h.tst('A'); j('NE', 'p_have')                                       # period P from the detector
h.li('A', 200); j('T', 'p_clamp')
a.label('p_have')
h.lsr(13, 'A')
a.label('p_clamp')
h.cmpi(40, 'A'); j('GE', 'p_lo'); h.li('A', 40)
a.label('p_lo')
h.cmpi(600, 'A'); j('LE', 'p_hi'); h.li('A', 600)
a.label('p_hi')
h.xw('A1', P_)
h.addi(pm.INVTAB, 'A'); h.mv('A1', 'R1'); h.nop()                  # 1/P from the SRAM table (vocal2_tab.hex)
h.ldxi('(R1)', 'X0'); h.xw('X0', INVP)
h.xr('A', 1, R=5); h.tfr('A', 'B'); h.lsr(22, 'A'); h.xw('A1', F1)  # f as 24.24: F1 = F2 >> 22, F0 = F2 << 2
h.lsl(2, 'B'); h.xw('B1', F0)
h.xr('X0', P_); h.xr('Y0', 1, R=5); h.mpy('X0', 'Y0', 'A'); h.asl1('A')     # P*f (24.24)
h.xw('A1', PF1); h.xw('A0', PF0)
a.label('p_ready')
h.xr('A', W); h.xr('Y0', RB); h.andi(pm.NRING - 1, 'A'); h.orr('Y0', 'A'); h.mv('A1', 'R1')
h.mv('X1', 'A'); h.abs_('A'); h.xr('B', BMAX)
h.stxi('X1', '(R1)')                                                 # ring write
h.cmp('B', 'A'); j('LE', 'p_mk1')                                    # marks
h.xw('A', BMAX); h.xr('B', W); h.xw('B1', BPOS)
a.label('p_mk1')
h.xr('B', BCNT); h.addi(1, 'B'); h.xr('Y0', P_); h.cmp('Y0', 'B'); j('LT', 'p_mk2')
h.xr('A', MI); h.addi(MARKS, 'A'); h.mv('A1', 'N3'); h.xr('B', BPOS); h.xr('A', MI); h.nop(); h.lua(3, 'R2')
h.addi(1, 'A'); h.andi(pm.NM - 1, 'A'); h.xw('A1', MI); h.stxi('B', '(R2)')
h.clr('A'); h.xw('A', BMAX); h.clr('B')
a.label('p_mk2')
h.xw('B1', BCNT)
h.xr('A', TIM1); h.xr('A0', TIM0)                                    # timer (48-bit)
h.subi(1, 'A'); h.tst('A'); j('GT', 'p_keep')
h.xr('X0', P_); h.xr('Y0', 0, R=5); h.mpy('X0', 'Y0', 'B'); h.asl1('B'); h.add('B', 'A')   # += P/p
h.xw('A1', TIM1); h.xw('A0', TIM0)
h.xr('A', W); h.xr('X0', P_); h.sub('X0', 'A'); h.xr('X0', PF1); h.sub('X0', 'A'); h.subi(64, 'A')
h.mv('A1', 'Y0')                                                     # want = W - (P + P*f + 64)
h.li('B', 0x7FFFFF)
for m in range(pm.NM):                                               # nearest mark (unrolled)
    h.xr('X1', MARKS + m); h.mv('X1', 'A'); h.sub('Y0', 'A'); h.mv('A1', 'X0'); h.mv('X0', 'A'); h.abs_('A')
    h.cmp('B', 'A'); j('GE', 'p_nb%d' % m)
    h.tfr('A', 'B'); h.mv('X1', 'Y1')
    a.label('p_nb%d' % m)
h.xr('A', RR); h.tfr('A', 'B'); h.asl(2, 'A'); h.asl1('B'); h.add('B', 'A'); h.addi(SLOTS, 'A')   # slot RR
h.mv('A1', 'N3'); h.xr('A', RR); h.addi(1, 'A'); h.cmpi(pm.NS, 'A'); j('LT', 'p_rr'); h.clr('A')
a.label('p_rr')
h.xw('A1', RR); h.lua(3, 'R2')
h.xr('A', P_); h.asl1('A'); h.xr('B', P_); h.xr('X1', PF1); h.xr('X0', PF0); h.nop()
h.xw('A1', ACT, R=2); h.xw('B1', TC, R=2)
h.clr('A'); h.xw('A', WV, R=2)
h.xr('A', INVP); h.xw('A1', DW, R=2)
h.clr('A'); h.mv('Y1', 'A1'); h.sub('X', 'A')                       # POS = mark - P*f
h.xw('A1', POS1, R=2); h.xw('A0', POS0, R=2)
j('T', 'p_slots')
a.label('p_keep')
h.xw('A1', TIM1); h.xw('A0', TIM0)
a.label('p_slots')                                                   # grains (unrolled: no R2 interlocks)
h.clr('B'); h.xr('Y0', RB)
for k in range(pm.NS):
    o = SLOTS + 6 * k
    h.xr('A', o + ACT); h.tst('A'); j('LE', 'p_skip%d' % k)
    h.xr('A', o + POS1); h.andi(pm.NRING - 1, 'A'); h.orr('Y0', 'A'); h.mv('A1', 'R1')
    h.addi(1, 'A'); h.andi(pm.NRING - 1, 'A'); h.orr('Y0', 'A'); h.mv('A1', 'R4')
    h.clr('A'); h.xr('A1', o + POS0); h.lsr(1, 'A'); h.mv('A1', 'Y1')                    # fraction (Q23)
    h.ldxi('(R1)', 'X0'); h.ldxi('(R4)', 'A'); h.sub('X0', 'A'); h.xr('Y0', o + WV); h.mv('A', 'X1')
    h.mpy('X1', 'Y1', 'A'); h.add('X0', 'A'); h.xr('X0', F0); h.mv('A', 'X1')            # v
    h.mac('X1', 'Y0', 'B')
    h.xr('A', o + POS1); h.xr('A0', o + POS0); h.xr('X1', F1); h.add('X', 'A')
    h.xr('Y0', o + DW); h.xw('A1', o + POS1); h.xw('A0', o + POS0)
    h.xr('A', o + WV); h.add('Y0', 'A'); h.xr('X0', o + TC); h.xw('A', o + WV)
    h.mv('X0', 'A'); h.subi(1, 'A'); h.xw('A1', o + TC); j('NE', 'p_tc%d' % k)
    h.xr('A', o + DW); h.neg('A'); h.xw('A', o + DW)
    a.label('p_tc%d' % k)
    h.xr('A', o + ACT); h.subi(1, 'A'); h.xw('A1', o + ACT)
    a.label('p_skip%d' % k)
    h.xr('Y0', RB)
h.mv('B', 'X0'); h.xr('Y0', 3, R=5); h.mpy('X0', 'Y0', 'A'); h.asl1('A'); h.mv('A', 'X0')   # gain
h.xr('X1', DRY); h.mv('X0', 'A'); h.sub('X1', 'A'); h.mv('A', 'Y0')                       # wet / dry
h.xr('Y1', 2, R=5); h.mv('X1', 'B'); h.mac('Y0', 'Y1', 'B'); h.mv('B', 'X1')
h.xr('A', W); h.addi(1, 'A'); h.xw('A1', W)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal2.py runs past P:%04X: %X' % (END, end)
VOCAL2_INIT, FX_FORMANT, FX_OCTAVE = a.labels['vocal2_init'], a.labels['fx_formant'], a.labels['fx_octave']
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  init=%04X formant=%04X octave=%04X' % (len(words), end, VOCAL2_INIT, FX_FORMANT,
                                                                       FX_OCTAVE))
    a.hexfile(os.path.join(HERE, 'vocal2.hex'))
    open(os.path.join(HERE, 'vocal2_tab.hex'), 'w').write('%X\n%s\n' % (pm.INVTAB, ' '.join('%06X' % v for v in pm.inv_table())))
