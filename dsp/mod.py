"""MOD: the modulated-delay pedal engine, effect id 18 (PEDAL board). Writes mod.hex (P:$0EE0). CE-2, Dimension D,
BF-2 flanger, TR-2 tremolo and the Leslie 122 are param sets for it. Reference: model/mod_ref.py (same steps);
voicings: model/mod_model.py; test: model/sim_mod.py (bit-exact). It calls DIRT's biquad routine (dirt.py, 'bq').

fx_mod: sample in X1 -> out in X1. First call: clears its state and both rings. The ESP writes the params and the
voice start states when a pedal is picked (with nothing written, TGT = WET = 0: it outputs DRY * x = silence).
Uses R0-R5, M1, M2 and puts them back to linear.
Memory (PROPOSED to the FX lab): P $0EE0-$0FFF, X $0D10-$0D5F (params, state), $0D80-$0DBF (ring B),
$0E00-$0FFF (ring A).
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5, R6, C5, ea, encode  # noqa: E402
from asmh import H, MAC, MPY  # noqa: E402
from dis56k import listing  # noqa: E402
import mod_ref as MR  # noqa: E402
import contextlib, io  # noqa: E402,E401
with contextlib.redirect_stdout(io.StringIO()):
    import dirt  # noqa: E402  (assembles it: we need its 'bq' entry)
BQ = dirt.a.labels['bq']

BASE, END = 0x0EE0, 0x0FFF
PM, SM = MR.PM, MR.SM
INITF = SM + 31
MAGIC = 0x3D0D18


def P(off): return PM + off
def S(off): return SM + off


a = Asm(BASE)
h = H(a)


def X(e, reg, W=1):
    return ('Movex_ea', dict(W=W, d=R5[reg], **ea(e)))


def macr(s1, s2, d, k=0):
    return ('Macr_S1S2', MAC(s1, s2, d, k)[1])


# ======================================================================== fx_mod
a.label('fx_mod')
h.ldl(INITF, 'A'); h.cmpi(MAGIC, 'A'); h.j('EQ', 'go')
a.jsr('init')
a.label('go')
# ---- drive (Leslie preamp): u = sat(x * DRV * 8), x = u + (u - u^3) / 2
h.ldl(P(MR.P_DRV), 'A'); h.tst('A'); h.j('EQ', 'nodrv')
h.mv('A', 'Y0'); h.mv('X1', 'X0'); h.mpy('X0', 'Y0', 'A'); h.asl(3, 'A')
h.mv('A', 'X0')
h.mpy('X0', 'X0', 'A'); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A')
h.mv('X0', 'B'); h.sub('A', 'B'); h.asr(1, 'B'); h.add('X0', 'B')
h.mv('B', 'X1')
a.label('nodrv')
h.stl('X1', S(MR.XD))
# ---- split biquad (BBD input LP / crossover)
h.mv('X1', 'X0')
h.li('R5', P(MR.P_SPL)); h.li('R0', S(MR.S_SPL))
a.op('Jsr_ea', ext=BQ, M=6, R=0)                    # jsr dirt's bq: X0 = lp
h.stl('X0', S(MR.LPS))
# ---- ring A <- KA x + KL lp + FB read0, ring B <- lp
h.ldl(S(MR.XD), 'X1'); h.ldl(P(MR.P_KA), 'Y0'); h.mpy('X1', 'Y0', 'A')
h.ldl(P(MR.P_KL), 'Y0'); h.mac('X0', 'Y0', 'A')
h.ldl(S(MR.S_V + 3), 'X1'); h.ldl(P(MR.P_FB), 'Y0'); h.mac('X1', 'Y0', 'A')
h.ldl(S(MR.WPA), 'R1')
h.ldl(S(MR.WPB), 'R2')
h.stxi('A', '(R1)')
h.stxi('X0', '(R2)')
# ---- voices
h.li('R5', P(MR.P_V)); h.li('R4', S(MR.S_V))
a.jsr('voice')
h.stl('A', S(MR.WS))                               # ws = sat(w0)
h.ldl(P(MR.P_V + 12 + MR.V_WET), 'B'); h.tst('B'); h.j('EQ', 'v1_off')
h.li('R5', P(MR.P_V + 12)); h.li('R4', S(MR.S_V + 4))
a.jsr('voice')
h.ldl(S(MR.WS), 'X0'); h.add('X0', 'A')
h.stl('A', S(MR.WS))                               # ws = sat(ws + w1)
a.label('v1_off')
# ---- post biquad, DRY x + wet, OUT
h.ldl(S(MR.WS), 'X0')
h.li('R5', P(MR.P_POST)); h.li('R0', S(MR.S_POST))
a.op('Jsr_ea', ext=BQ, M=6, R=0)
h.ldl(S(MR.XD), 'X1'); h.ldl(P(MR.P_DRY), 'Y0'); h.mpy('X1', 'Y0', 'A')
h.add('X0', 'A')
h.mv('A', 'X0'); h.ldl(P(MR.P_OUT), 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(2, 'A')
h.mv('A', 'X1')
# ---- advance the write pointers (modulo 512 / 64)
h.movec('M1', MR.mm.RA - 1)
h.ldl(S(MR.WPA), 'R1')
h.nop()
h.ldxi('(R1)+', 'X0')
h.stl('R1', S(MR.WPA))
h.movec('M1', MR.mm.RB - 1)
h.ldl(S(MR.WPB), 'R1')
h.nop()
h.ldxi('(R1)+', 'X0')
h.stl('R1', S(MR.WPB))
h.movec('M1', 0xFFFFFF)
h.rts()

# ======================================================================== voice
# R5 = voice params, R4 = voice state (INCH INCL PH READ). Out: A = sat(read * g) * WET (full).
a.label('voice')
h.xr('B', MR.V_TGT, R=5); h.xr('X0', 0, R=4); h.sub('X0', 'B')     # TGT - INCH
h.mv('B', 'Y0'); h.xr('X1', MR.V_ACC, R=5)
h.xr('A', 0, R=4); h.xr('A0', 1, R=4)
h.mac('X1', 'Y0', 'A')                                              # inc += ACC sat(TGT - INCH)
h.xw('A1', 0, R=4); h.xw('A0', 1, R=4)
h.xr('X0', 0, R=4); h.xr('A', 2, R=4); h.add('X0', 'A')             # PH += INCH (wraps)
h.xw('A1', 2, R=4)
h.mv('A1', 'X0')
a.jsr('lfo')
h.xr('Y0', MR.V_DEPTH, R=5); h.mpy('X0', 'Y0', 'A')
h.xr('X1', MR.V_BASE, R=5); h.add('X1', 'A')
h.mv('A', 'X0')                                                     # d (samples / 1024)
h.mv('X0', 'B'); h.lsr(13, 'B'); h.neg('B'); h.mv('B1', 'N2')       # n = -int
h.mv('X0', 'A'); h.andi(0x001FFF, 'A'); h.lsl(10, 'A'); h.mv('A1', 'X1')   # frac
h.xr('X0', MR.V_MV, R=5)
a.op('Movec_S1D2', W=1, e=R6['X0'], D=C5['M2'])                     # m2 = ring size - 1
h.xr('X0', MR.V_WPP, R=5); h.mv('X0', 'R3')
h.nop()
h.ldxi('(R3)', 'R2')                                                # r2 = write pointer
h.nop()
h.ldxi('(R2+N2)', 'Y0')                                             # t0
h.ldxi('(R2)-', 'B')                                                # (dummy: step back one, modulo)
h.ldxi('(R2+N2)', 'B')                                              # t1 (one sample older)
h.sub('Y0', 'B'); h.mv('B', 'Y1')
h.mpy('X1', 'Y1', 'A'); h.add('Y0', 'A')                            # r = t0 + frac (t1 - t0)
h.movec('M2', 0xFFFFFF)
h.xw('A', 3, R=4)                                                   # READ = sat(r)
h.xr('B', MR.V_AMH, R=5); h.tst('B'); h.j('EQ', 'v_noam')
h.xr('A', 2, R=4); h.xr('X0', MR.V_AOFF, R=5); h.add('X0', 'A'); h.mv('A1', 'X0')
a.jsr('lfo')
h.xr('Y0', MR.V_WG, R=5); h.mpy('X0', 'Y0', 'A'); h.asl(3, 'A'); h.mv('A', 'X0')
h.xr('A', MR.V_AMC, R=5); h.xr('Y0', MR.V_AMH, R=5); h.mac('X0', 'Y0', 'A')
h.mv('A', 'Y0')                                                     # g = sat(AMC + AMH lfo)
h.j('T', 'v_g')
a.label('v_noam')
h.xr('Y0', MR.V_AMC, R=5)
a.label('v_g')
h.xr('X0', 3, R=4); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'X0')
h.xr('Y0', MR.V_WET, R=5); h.mpy('X0', 'Y0', 'A')
h.rts()

# ======================================================================== lfo: X0 = phase -> X0 = sat(shape(phase))
a.label('lfo')
h.xr('B', MR.V_SHP, R=5); h.tst('B'); h.j('NE', 'sine')
h.mv('X0', 'A'); h.abs_('A'); h.asl1('A')
h.li('B', 0x7FFFFF); h.sub('A', 'B')
h.mv('B', 'X0')                                                     # 1 - 2|ph|
h.rts()
a.label('sine')
h.mv('X0', 'A'); h.abs_('A'); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A')
h.mv('X0', 'B'); h.sub('A', 'B'); h.asl(2, 'B'); h.mv('B', 'X1')    # P = 4 (ph - ph|ph|)
h.mv('X1', 'B'); h.abs_('B'); h.mv('B', 'Y1'); h.mpy('X1', 'Y1', 'A')
h.sub('X1', 'A'); h.mv('A', 'Y1')
h.mpyi(MR.K225, 'Y1', 'A'); h.add('X1', 'A')                        # P + 0.225 (P|P| - P)
h.mv('A', 'X0')
h.rts()

# ======================================================================== init (first call)
a.label('init')
h.clr('A')
h.li('R1', SM)
h.rep(MR.NSM)
h.stxi('A', '(R1)+')
h.li('R1', MR.RINGB)
h.rep(MR.mm.RB)
h.stxi('A', '(R1)+')
h.li('R1', MR.RINGA)
h.rep(MR.mm.RA)
h.stxi('A', '(R1)+')
h.li('A', MR.RINGA); h.stl('A', S(MR.WPA))
h.li('A', MR.RINGB); h.stl('A', S(MR.WPB))
h.li('A', MAGIC); h.stl('A', INITF)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'MOD runs past its P space: %X' % end
FX_MOD = a.labels['fx_mod']

if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d  end=P:%04X  labels=%s' % (len(words), end, {k: '%04X' % v for k, v in a.labels.items()}))
    a.hexfile(os.path.join(HERE, 'mod.hex'))
