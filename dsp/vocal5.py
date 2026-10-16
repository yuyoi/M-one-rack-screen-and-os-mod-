"""Vocal effects, part 5 (P:$0310-$03FF): STRIP (input stage, on when X:$0207 != 0) and SWELL (id 15).
Writes vocal5.hex. Mirrors dsp/model/strip_model.py step by step. Uses vocal.py's `bq` (DF1 biquad: R0 -> X states,
R4 -> Y coefficients, X0 in/out).
STRIP: state X:$03C0 (R3), params X:$0270 (R5), low-cut coefficients Y:$0180, EQ coefficients Y:$0185 (copied from
the params every sample). SWELL: state X:$03D0, params X:$02B0.
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
    import vocal  # noqa: E402
import strip_model as sm  # noqa: E402
import vox_model as vm  # noqa: E402

BASE, END = 0x0310, 0x03FF
LCTAB = 0x031A80                                      # SRAM: the 5 low-cut coefficients (vocal5_tab.hex)
SS, SP, YLC, YEQ = 0x03C0, 0x0270, 0x0180, 0x0185
(S_GENV, S_GG, S_DLP, S_DENV, S_DG, S_G, S_CENV) = range(8, 15)     # after LC (0-3) and EQ (4-7) biquad states
WS, WP = 0x03D0, 0x02B0
(W_ENV, W_G) = range(2)
q = sm.q

a = Asm(BASE)
h = H(a)
j = h.j
a.labels['bq'] = vocal.a.labels['bq']

# ============================================================ vocal5_init
a.label('vocal5_init')
h.clr('A'); h.li('R0', SS); h.rep(S_CENV + 1); h.stxi('A', '(R0)+')
h.stl('A', WS + W_ENV); h.stl('A', WS + W_G)
h.li('A', 0x7FFFFF); h.stl('A', SS + S_DG); h.stl('A', SS + S_G)
h.li('R4', YLC); h.li('R1', LCTAB)                 # low-cut coefficients: SRAM table -> Y
a.do(5, 'i_lc'); h.ldxi('(R1)+', 'X0'); h.styi('X0', '(R4)+'); a.label('i_lc')
for k, v in enumerate(sm.strip_params()):
    h.li('A', v & 0xFFFFFF); h.stl('A', SP + k)
for k, v in enumerate(sm.swell_params()):
    h.li('A', v); h.stl('A', WP + k)
h.rts()

# ============================================================ fx_strip (X1 in -> X1 out)
a.label('fx_strip')
h.li('R3', SS); h.li('R5', SP); h.li('R4', YEQ); h.li('R1', SP + 5)
a.do(5, 's_eqc'); h.ldxi('(R1)+', 'X0'); h.styi('X0', '(R4)+'); a.label('s_eqc')   # EQ coefficients -> Y
h.mv('X1', 'X0'); h.li('R0', SS); h.li('R4', YLC)
a.jsr('bq')                                                              # low cut (R0/R4 then point at the EQ)
h.mv('X0', 'A'); h.abs_('A'); h.xr('Y1', S_GENV); h.mpyi(sm.ENV_DEC, 'Y1', 'B')   # gate envelope
h.cmp('B', 'A'); j('GE', 's_g1'); h.tfr('B', 'A')
a.label('s_g1')
h.xw('A', S_GENV); h.xr('Y0', 0, R=5); h.cmp('Y0', 'A'); j('GT', 's_open')
h.clr('B'); h.li('Y1', sm.GK_CLOSE); j('T', 's_gk')
a.label('s_open')
h.li('B', 0x7FFFFF); h.li('Y1', sm.GK_OPEN)
a.label('s_gk')
h.xr('Y0', S_GG); h.sub('Y0', 'B'); h.mv('B', 'X1'); h.xr('A', S_GG); h.mac('X1', 'Y1', 'A')
h.xw('A', S_GG); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'X0')          # x *= gate gain
h.xr('Y0', S_DLP); h.mv('X0', 'A'); h.sub('Y0', 'A'); h.mv('A', 'X1')               # de-esser split
h.xr('B', S_DLP); h.maci(sm.KDS, 'X1', 'B'); h.xw('B', S_DLP)
h.mv('X0', 'A'); h.xr('Y0', S_DLP); h.sub('Y0', 'A'); h.mv('A', 'X1')               # hi
h.xr('Y0', S_DG); h.mpy('X1', 'Y0', 'A'); h.mv('A', 'X1')                          # hs = hi * dg
h.mv('X1', 'A'); h.abs_('A'); h.xr('Y1', S_DENV); h.mpyi(sm.ENV_DEC, 'Y1', 'B')
h.cmp('B', 'A'); j('GE', 's_d1'); h.tfr('B', 'A')
a.label('s_d1')
h.xw('A', S_DENV); h.xr('Y0', 1, R=5); h.cmp('Y0', 'A'); j('GT', 's_dsa')
h.xr('Y1', S_DG); h.mpyi(q(1) - sm.DS_REL, 'Y1', 'B'); h.addi(sm.DS_REL, 'B'); j('T', 's_dss')
a.label('s_dsa')
h.xr('Y1', S_DG); h.mpyi(sm.DS_ATT, 'Y1', 'B')
a.label('s_dss')
h.xw('B', S_DG)
h.xr('A', S_DLP); h.add('X1', 'A'); h.mv('A', 'X0')                                # x = low + hs
h.xr('Y0', S_G); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'X1')                           # leveler
h.tfr('A', 'B'); h.abs_('B'); h.xr('Y1', S_CENV); h.mpyi(q(vm.DEC), 'Y1', 'A')
h.cmp('B', 'A'); j('GE', 's_c1'); h.tfr('B', 'A')
a.label('s_c1')
h.xw('A', S_CENV); h.xr('Y1', S_G); h.xr('X0', 2, R=5); h.cmp('X0', 'A'); j('GT', 's_ca')
h.mpyi(q(1 - vm.R), 'Y1', 'B'); h.addi(q(vm.R), 'B'); j('T', 's_cs')
a.label('s_ca')
h.mpyi(q(vm.ATT), 'Y1', 'B')
a.label('s_cs')
h.xw('B', S_G)
h.xr('Y0', 3, R=5); h.mpy('X1', 'Y0', 'A'); h.asl(2, 'A'); h.mv('A', 'X0')         # makeup
a.jsr('bq')                                                              # EQ
h.xr('A', 4, R=5); h.tst('A'); j('EQ', 's_nd')                                       # drive
h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(4, 'A'); h.mv('A', 'X0')
h.mpy('X0', 'X0', 'A'); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'Y1')
h.mpyi(q(0.75), 'X0', 'A'); h.maci(q(0.25), 'Y1', 'A', k=1); h.asl1('A'); h.mv('A', 'X0')
a.label('s_nd')
h.mv('X0', 'X1')
h.rts()

# ============================================================ fx_swell (X1 in -> X1 out), id 15
a.label('fx_swell')
h.li('R3', WS); h.li('R5', WP)
h.mv('X1', 'A'); h.abs_('A'); h.xr('Y1', W_ENV); h.mpyi(sm.SW_DEC, 'Y1', 'B')
h.cmp('B', 'A'); j('GE', 'w_e'); h.tfr('B', 'A')
a.label('w_e')
h.xw('A', W_ENV); h.xr('Y0', 0, R=5); h.cmp('Y0', 'A'); j('GT', 'w_on')
h.clr('B'); j('T', 'w_st')
a.label('w_on')
h.xr('B', W_G); h.xr('Y0', 1, R=5); h.add('Y0', 'B')
a.label('w_st')
h.xw('B', W_G); h.xr('X0', W_G); h.mpy('X0', 'X0', 'A'); h.mv('A', 'Y0'); h.mpy('X1', 'Y0', 'A'); h.mv('A', 'X1')
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal5.py runs past P:%04X: %X' % (END, end)
VOCAL5_INIT, FX_STRIP, FX_SWELL = (a.labels[n] for n in ('vocal5_init', 'fx_strip', 'fx_swell'))
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  init=%04X strip=%04X swell=%04X' % (len(words), end, VOCAL5_INIT, FX_STRIP, FX_SWELL))
    a.hexfile(os.path.join(HERE, 'vocal5.hex'))
    open(os.path.join(HERE, 'vocal5_tab.hex'), 'w').write('%X\n%s\n' % (LCTAB, ' '.join('%06X' % v for v in sm.LC)))
