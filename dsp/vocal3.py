"""Vocal effects, part 3: REVERB (id 12) and DELAY (id 13). Writes vocal3.hex + vocal3_tab.hex.
Mirrors dsp/model/reverb_model.py and dsp/model/delay_model.py step by step.

REVERB: Dattorro plate at half rate (22.05 kHz), one tick spread over two frames (~half the work each frame).
Buffer X:$038000-$03BFFF (16K, modulo: M0 = $3FFF, R0 = buffer + PTR). State X:$0300 (R3 + n), params X:$0280 (R5).
Every read site's buffer index (OFF + floor(SIZE*L) + 1) is cached at X:$0350 and recomputed only when SIZE
changes; the code then walks the cache with R4. The tank runs once per side: R2 = side state, R6 = write offsets.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../disasm', '../tools', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm  # noqa: E402
from dis56k import listing  # noqa: E402
from asmh import H  # noqa: E402
import reverb_model as rv  # noqa: E402
import delay_model as dm  # noqa: E402

BASE, END = 0x1000, 0x13FF
RBUF, RS, RP, RTAB3 = 0x038000, 0x0300, 0x0280, 0x031400
(PTR, PH, XP, BWL, OK, OKP, DIFF, DRY, DEC, KD, TMP, SIZEC) = range(12)
SIDE_L, SIDE_R = 16, 24                   # side blocks (R2): +0 END, +1 DAMP, +2 LFO (left = sine, right = cosine)
CACHE = 0x0350                            # X: buffer index of every read site
P_SIZE, P_DECAY, P_KD, P_KB, P_PRE, P_WET, P_FREEZE, P_DD2 = range(8)
q = rv.q
DEFAULT = rv.PRESETS['PLATE']
# read sites in the order the code reads them: frame A (diffusers, left tank), frame B (right tank, taps)
SITES = ([(rv.OFF[n], rv.LEN[n]) for n in ('AP1', 'AP2', 'AP3', 'AP4', 'MAPL', 'DL1', 'APL2', 'DL2',
                                          'MAPR', 'DR1', 'APR2', 'DR2')]
         + [(rv.OFF[line], tap) for line, tap, sg in rv.TAPS])
TAB = ([w for o, L in SITES for w in (o, L)]
       + [rv.OFF[n] for n in ('MAPL', 'DL1', 'APL2', 'DL2')] + [rv.OFF[n] for n in ('MAPR', 'DR1', 'APR2', 'DR2')]
       + [q(sg * rv.TAPG) & 0xFFFFFF for line, tap, sg in rv.TAPS])
RDTAB = RTAB3
DESC_L, DESC_R = RTAB3 + 2 * len(SITES), RTAB3 + 2 * len(SITES) + 4
GAINS = DESC_R + 4

a = Asm(BASE)
h = H(a)
j = h.j

# ============================================================ subroutines
# v_ap: allpass, X1 in/out, Y0 = g, N2 = write OFF, R4 -> cached read index.  w = x - g z ; buf = w ; y = z + g w
a.label('v_ap')
h.ldxi('(R4)+', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0')                                # z
h.mv('X1', 'A'); h.mac('X0', 'Y0', 'A', k=1); h.mv('A', 'Y1')
h.mv('N2', 'N0'); h.nop(); h.stxi('Y1', '(R0+N0)')
h.mv('X0', 'B'); h.mac('Y1', 'Y0', 'B'); h.mv('B', 'X1')
h.rts()
# v_tank: A = side input (diffused); R2 = side block, R6 = write OFFs, R4 = cached reads, other END at X:(R3+N3)
a.label('v_tank')
h.xr('Y0', DEC); h.ldxi('(R3+N3)', 'X0'); h.mac('X0', 'Y0', 'A'); h.mv('A', 'X1')   # t = in + decay*other end
h.xw('X1', TMP)                                                                       # mod allpass (G_DD1)
h.xr('X0', 2, R=2); h.mpyi(rv.EXC, 'X0', 'A')                                        # A1:A0 = EXC*lfo
h.ldxi('(R4)+', 'X0'); h.add('X0', 'A')                                              # + OFF + d
h.mv('A0', 'Y1'); h.tfr('A', 'B'); h.clr('A'); h.mv('Y1', 'A1'); h.lsr(1, 'A'); h.mv('A1', 'Y1')   # frac
h.mv('B1', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0')                                   # z0
h.addi(1, 'B'); h.mv('B1', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'A')                    # z1
h.sub('X0', 'A'); h.mv('A', 'X1'); h.mpy('X1', 'Y1', 'A'); h.add('X0', 'A'); h.mv('A', 'X0')   # z
h.xr('A', TMP); h.maci(q(rv.G_DD1), 'X0', 'A', k=1); h.mv('A', 'Y1')
h.ldxi('(R6)+', 'N0'); h.nop(); h.stxi('Y1', '(R0+N0)')
h.mv('X0', 'B'); h.maci(q(rv.G_DD1), 'Y1', 'B'); h.mv('B', 'X1')
h.ldxi('(R6)+', 'N0'); h.nop(); h.stxi('X1', '(R0+N0)')                              # delay 1
h.ldxi('(R4)+', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0')
h.xr('Y0', 1, R=2); h.mv('X0', 'A'); h.sub('Y0', 'A'); h.mv('A', 'X1')               # damping LP
h.xr('Y1', KD); h.xr('B', 1, R=2); h.mac('X1', 'Y1', 'B'); h.xw('B', 1, R=2)
h.mv('B', 'X0'); h.xr('Y0', DEC); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'X1')            # * decay
h.ldxi('(R6)+', 'N2'); h.xr('Y0', P_DD2, R=5); a.jsr('v_ap')                        # DD2 allpass
h.ldxi('(R6)+', 'N0'); h.nop(); h.stxi('X1', '(R0+N0)')                              # delay 2
h.ldxi('(R4)+', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0'); h.xw('X0', 0, R=2)         # END
h.rts()

# ============================================================ vocal3_init
a.label('vocal3_init')
h.clr('A'); h.li('R0', RS); h.rep(SIDE_R + 3); h.stxi('A', '(R0)+')
h.li('R0', RBUF)
for _ in range(rv.NBUF // 4096):
    h.rep(4095); h.stxi('A', '(R0)+')
    h.stxi('A', '(R0)+')
h.li('A', 0x7FFFFF); h.stl('A', RS + SIDE_R + 2)                                   # cosine starts at 1
h.li('A', 0x800000); h.stl('A', RS + SIZEC)                                       # no size cached yet
for k, v in enumerate(DEFAULT):
    h.li('A', v); h.stl('A', RP + k)
a.jmp('delay_init')                                                               # (it returns for us)

# ============================================================ fx_reverb (X1 in -> X1 out)
a.label('fx_reverb')
h.li('R3', RS); h.li('R5', RP)
h.xw('X1', DRY)
h.xr('A', P_SIZE, R=5); h.xr('B', SIZEC); h.cmp('A', 'B'); j('EQ', 'v_cached')     # SIZE changed: new read indexes
h.xw('A', SIZEC); h.mv('A', 'X0'); h.li('R6', RDTAB); h.li('R4', CACHE)
a.do(len(SITES), 'v_cl')
h.ldxi('(R6)+', 'Y0'); h.ldxi('(R6)+', 'Y1'); h.mpy('X0', 'Y1', 'A'); h.add('Y0', 'A'); h.addi(1, 'A')
h.stxi('A1', '(R4)+')
a.label('v_cl')
a.label('v_cached')
h.xr('A', P_DECAY, R=5); h.xw('A', DEC); h.xr('A', P_KD, R=5); h.xw('A', KD)       # freeze: decay 1, no damping
h.xr('A', P_FREEZE, R=5); h.tst('A'); j('EQ', 'v_nf')
h.li('A', 0x7FFFFF); h.xw('A', DEC); h.xw('A', KD)
a.label('v_nf')
h.xr('A', PTR); h.ori(RBUF, 'A'); h.mv('A1', 'R0'); h.movec('M0', rv.NBUF - 1)
h.xr('X1', DRY)
h.xr('A', PH); h.tst('A'); j('NE', 'v_b')
# ---------------- frame A: input, predelay, bandwidth, diffusers, left tank
h.li('R4', CACHE)
h.xr('A', P_FREEZE, R=5); h.tst('A'); j('NE', 'v_mute')
h.xr('X0', XP); h.mv('X1', 'A'); h.add('X0', 'A'); h.alu('Asr_D', d=0); h.mv('A', 'X0'); j('T', 'v_in')
a.label('v_mute')
h.clr('A'); h.mv('A', 'X0')
a.label('v_in')
h.li('N0', rv.OFF['PD']); h.nop(); h.stxi('X0', '(R0+N0)')
h.xr('A', P_PRE, R=5); h.addi(rv.OFF['PD'], 'A'); h.mv('A1', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0')
h.xr('Y0', BWL); h.mv('X0', 'A'); h.sub('Y0', 'A'); h.mv('A', 'X1')
h.xr('Y1', P_KB, R=5); h.xr('B', BWL); h.mac('X1', 'Y1', 'B'); h.xw('B', BWL); h.mv('B', 'X1')
for line, g in (('AP1', rv.G_IN1), ('AP2', rv.G_IN1), ('AP3', rv.G_IN2), ('AP4', rv.G_IN2)):
    h.li('N2', rv.OFF[line]); h.li('Y0', q(g)); a.jsr('v_ap')
h.xw('X1', DIFF)
kl = q(rv.KLFO)
h.xr('X0', SIDE_R + 2); h.xr('A', SIDE_L + 2); h.maci(kl, 'X0', 'A'); h.xw('A', SIDE_L + 2)   # LFO
h.mv('A', 'X0'); h.xr('A', SIDE_R + 2); h.maci(kl, 'X0', 'A', k=1); h.xw('A', SIDE_R + 2)
h.li('R2', RS + SIDE_L); h.li('R6', DESC_L); h.li('N3', SIDE_R); h.xr('A', DIFF)
a.jsr('v_tank')
h.xr('A', OK); h.xr('X0', OKP); h.add('X0', 'A'); h.alu('Asr_D', d=0); h.mv('A', 'Y1')   # y = (ok + okp)/2
j('T', 'v_out')
# ---------------- frame B: right tank, output taps, PTR--
a.label('v_b')
h.li('R4', CACHE + 8)
h.li('R2', RS + SIDE_R); h.li('R6', DESC_R); h.li('N3', SIDE_L); h.xr('A', DIFF)
a.jsr('v_tank')
h.clr('B'); h.li('R6', GAINS)
a.do(len(rv.TAPS), 'v_taps')
h.ldxi('(R4)+', 'N0'); h.nop(); h.ldxi('(R0+N0)', 'X0'); h.ldxi('(R6)+', 'Y0'); h.mac('X0', 'Y0', 'B')
a.label('v_taps')
h.xr('A', OK); h.xw('A', OKP)
h.mv('B', 'Y1'); h.xw('Y1', OK)
h.xr('A', PTR); h.subi(1, 'A'); h.andi(rv.NBUF - 1, 'A'); h.xw('A1', PTR)
a.label('v_out')
h.movec('M0', 0xFFFFFF)
h.xr('A', PH); h.eori(1, 'A'); h.xw('A1', PH)
h.xr('X1', DRY); h.xw('X1', XP)
h.mv('X1', 'A'); h.xr('Y0', P_WET, R=5); h.mac('Y1', 'Y0', 'A'); h.mv('A', 'X1')   # dry + wet * reverb
h.rts()

# ============================================================ DELAY (id 13), mirrors delay_model.py
DBUF, DS, DP = 0x03C000, 0x0330, 0x0290
HEADS_P = 0x0BA0                          # DELAY head loop (vocal3b.hex): kernel spare P, the meter build ends ~$0B85
(D_PTR, D_PH, D_XP, D_LP, D_WO, D_WOP, D_ENV, D_S, D_C, D_DRY, D_TMP, D_Q1, D_Q0, D_PA1, D_PA0, D_M, D_Z) = range(17)
T_TIME, T_FB, T_WET, T_KT, T_DUCK, T_TAPS, T_WOW, T_SAT, T_KW, T_HEADS = range(10)

a.label('delay_init')
h.clr('A'); h.li('R0', DS); h.rep(D_Z + 1); h.stxi('A', '(R0)+')
h.li('R0', DBUF)
for _ in range(dm.NBUF // 4096):
    h.rep(4095); h.stxi('A', '(R0)+')
    h.stxi('A', '(R0)+')
h.li('A', 0x7FFFFF); h.stl('A', DS + D_C)
for k, v in enumerate(dm.PRESETS['SLAP']):
    h.li('A', v & 0xFFFFFF); h.stl('A', DP + k)
h.rts()

a.label('fx_delay')
h.li('R3', DS); h.li('R5', DP)
h.xw('X1', D_DRY)
h.xr('Y1', D_ENV); h.mpyi(dm.DECD, 'Y1', 'B'); h.mv('X1', 'A'); h.abs_('A')          # ducking envelope
h.cmp('B', 'A'); j('GE', 'd_e'); h.tfr('B', 'A')
a.label('d_e')
h.xw('A', D_ENV)
h.xr('A', D_PTR); h.ori(DBUF, 'A'); h.mv('A1', 'R0'); h.movec('M0', dm.NBUF - 1)
h.xr('A', D_PH); h.tst('A'); j('EQ', 'd_a')
h.xr('X0', D_XP); h.mv('X1', 'A'); h.add('X0', 'A'); h.alu('Asr_D', d=0); h.mv('A', 'X0'); h.xw('X0', D_TMP)   # xin
h.xr('Y0', T_KW, R=5); h.xr('X0', D_C); h.xr('A', D_S); h.mac('X0', 'Y0', 'A'); h.xw('A', D_S)           # LFO
h.mv('A', 'X0'); h.xr('A', D_C); h.mac('X0', 'Y0', 'A', k=1); h.xw('A', D_C)
h.xr('X0', D_S); h.xr('Y0', T_WOW, R=5); h.mpy('X0', 'Y0', 'A'); h.xr('X0', T_TIME, R=5); h.add('X0', 'A')   # pos
a.jsr('d_heads')                                                                                       # z (P:$0BA0)
h.xr('Y0', D_LP); h.mv('X0', 'A'); h.sub('Y0', 'A'); h.mv('A', 'X1')                                   # tone
h.xr('Y1', T_KT, R=5); h.xr('B', D_LP); h.mac('X1', 'Y1', 'B'); h.xw('B', D_LP); h.mv('B', 'X0')
h.xr('A', T_SAT, R=5); h.tst('A'); j('EQ', 'd_ns')                                                     # tape
h.mpy('X0', 'X0', 'A'); h.mv('A', 'Y0'); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'Y1')
h.mpyi(q(0.75), 'X0', 'A'); h.maci(q(0.25), 'Y1', 'A', k=1); h.asl1('A'); h.mv('A', 'X0')
a.label('d_ns')
h.xr('A', D_TMP); h.xr('Y0', T_FB, R=5); h.mac('X0', 'Y0', 'A'); h.stxi('A', '(R0)')                  # write
h.xr('A', D_LP)                                                                                         # wet
h.xr('B', T_TAPS, R=5); h.tst('B'); j('EQ', 'd_nt')
for g, k in zip(dm.TAPG, dm.TAPK):
    h.xr('X0', T_TIME, R=5); h.mpyi(k, 'X0', 'B'); h.addi(1, 'B'); h.mv('B1', 'N0'); h.nop()
    h.ldxi('(R0+N0)', 'X0'); h.maci(g, 'X0', 'A')
a.label('d_nt')
h.xr('B', D_WO); h.xw('B', D_WOP); h.mv('A', 'Y1'); h.xw('Y1', D_WO)
h.xr('A', D_PTR); h.subi(1, 'A'); h.andi(dm.NBUF - 1, 'A'); h.xw('A1', D_PTR)
j('T', 'd_out')
a.label('d_a')
h.xr('A', D_WO); h.xr('X0', D_WOP); h.add('X0', 'A'); h.alu('Asr_D', d=0); h.mv('A', 'Y1')
a.label('d_out')
h.movec('M0', 0xFFFFFF)
h.xr('A', D_PH); h.eori(1, 'A'); h.xw('A1', D_PH)
h.xr('X1', D_DRY); h.xw('X1', D_XP)
h.xr('A', D_ENV); h.asl(2, 'A'); h.mv('A', 'X0')                                                       # ducking
h.li('A', 0x7FFFFF); h.xr('Y0', T_DUCK, R=5); h.mac('X0', 'Y0', 'A', k=1); h.mv('A', 'X0')
h.xr('Y0', T_WET, R=5); h.mpy('X0', 'Y0', 'A'); h.mv('A', 'Y0')
h.mv('X1', 'A'); h.mac('Y1', 'Y0', 'A'); h.mv('A', 'X1')
h.rts()

a.labels['d_heads'] = HEADS_P
words = a.link()
end = BASE + len(words) - 1
assert end <= END, 'vocal3.py runs past P:%04X: %X' % (END, end)
assert RTAB3 + len(TAB) <= 0x031600, 'vocal3_tab runs into vocal2_tab'

# ---- the head loop lives in the kernel's spare P (vocal3 is full): vocal3b.hex at P:$0BA0
# d_heads: A = pos (TIME + WOW*lfo, A1 int : A0 frac), R0/R3/R5 as fx_delay -> X0 = z (sum of the heads in the mask)
b = Asm(HEADS_P)
hb = H(b)
jb = hb.j
b.label('d_heads')
hb.xw('A1', D_Q1); hb.xw('A0', D_Q0); hb.clr('B'); hb.xw('B1', D_PA1); hb.xw('B0', D_PA0); hb.xw('B1', D_Z)
hb.xr('B', T_HEADS, R=5); hb.andi(7, 'B'); jb('NE', 'd_m'); hb.addi(1, 'B')                                # 0 = head 1
b.label('d_m')
hb.xw('B1', D_M)
b.label('d_hl')                                                                                        # head k: k*pos
hb.xr('A', D_PA1); hb.xr('A0', D_PA0); hb.xr('B', D_Q1); hb.xr('B0', D_Q0); hb.add('B', 'A')
hb.xw('A1', D_PA1); hb.xw('A0', D_PA0)
hb.xr('B', D_M); hb.alu('Lsr_D', D=1); hb.xw('B1', D_M); jb('CC', 'd_sk')        # LSR B: C = bit 0
hb.mv('A0', 'Y1'); hb.tfr('A', 'B'); hb.clr('A'); hb.mv('Y1', 'A1'); hb.lsr(1, 'A'); hb.mv('A1', 'Y1')        # frac
hb.mv('B1', 'N0'); hb.nop(); hb.ldxi('(R0+N0)', 'X0')
hb.addi(1, 'B'); hb.mv('B1', 'N0'); hb.nop(); hb.ldxi('(R0+N0)', 'A')
hb.sub('X0', 'A'); hb.mv('A', 'X1'); hb.mpy('X1', 'Y1', 'A'); hb.add('X0', 'A'); hb.mv('A', 'X0')            # z_k
hb.xr('A', D_Z); hb.add('X0', 'A'); hb.xw('A', D_Z)                                                       # z += z_k
b.label('d_sk')
hb.xr('B', D_M); hb.tst('B'); jb('NE', 'd_hl')
hb.xr('X0', D_Z)
hb.rts()
wordsb = b.link()
assert HEADS_P + len(wordsb) <= 0x0C00, 'vocal3b runs into AMP: %X' % (HEADS_P + len(wordsb))
VOCAL3_INIT, FX_REVERB, FX_DELAY, DELAY_INIT = (a.labels[n] for n in ('vocal3_init', 'fx_reverb', 'fx_delay',
                                                                       'delay_init'))
if __name__ == '__main__':
    if '-l' in sys.argv:
        print(listing(words, base=BASE))
    print('words=%d end=P:%04X  init=%04X reverb=%04X delay=%04X  table %d words at %06X' % (
        len(words), end, VOCAL3_INIT, FX_REVERB, FX_DELAY, len(TAB), RTAB3))
    a.hexfile(os.path.join(HERE, 'vocal3.hex'))
    b.hexfile(os.path.join(HERE, 'vocal3b.hex'))
    print('vocal3b: %d words at P:%04X-%04X' % (len(wordsb), HEADS_P, HEADS_P + len(wordsb) - 1))
    _t = os.path.join(HERE, 'vocal3_tab.hex')
    open(_t, 'w').write('%X\n%s\n' % (RTAB3, ' '.join('%06X' % (w & 0xFFFFFF) for w in TAB)))
