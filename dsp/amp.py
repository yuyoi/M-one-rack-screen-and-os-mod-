"""AMP: modeled tube amp, effect id 6 (PEDAL). Writes amp.hex (P:$0C00-$0DFF) and amp_tab.hex (P:$031C00, in the
external SRAM, which P/X/Y all see). Reference model: model/amp_ref.py (same steps, same scaling); test: model/sim_amp.py.

fx_amp: sample in X1 -> out in X1, like every effect. On its first call it copies its tables from the SRAM into
internal RAM (IR + FIR coefficients -> Y:$0800-$0A5F, default params -> X:$12C0) and clears its state.
Uses R0-R6 / M0-M2, M4, M6 and puts the M registers back to linear before it returns.

Memory (agreed with the FX lab, VOCAL_ARCH.md): P $0C00-$0DFF, X $1000-$12FF, Y $0800-$0CFF; SRAM $031C00-$031FFF
(proposed: the vocal tables sit at $031000-$031858).
  X:$1000-$11FF IR history (modulo 512)    X:$1200 upsampler history (mod 16)   X:$1240 decimator history (mod 64)
  X:$1280-$12BF state                       X:$12C0-$12EF params (the ESP writes these, long X addresses)
  Y:$0800-$09FF IR coefficients (mod 512)  Y:$0A00 48 upsampler (phase blocks) + 48 decimator coefficients
Params X:$12C0+: 0-2 stage gain/32, 3-5 bias, 6-8 coupling-HPF pole, 9-11 Miller-LPF step, 12 dynamic-bias depth,
  13 bias-envelope step, 14 input DC-blocker pole, 16-20 tone-stack biquad (b0 b1 b2 -a1 -a2, all /2),
  21-23 tone-stack first order (c0 c1 -d1), 24-28 resonance biquad /2, 29-33 presence biquad /2, 34 drive/8,
  35 sag depth, 36 sag attack step, 37 sag release step, 38 master.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
for d in ('../tools', '../disasm', 'model', '.'):
    sys.path.insert(0, os.path.join(HERE, d))
from asm56 import Asm, R5  # noqa: E402
from asmh import H, MAC, MPY  # noqa: E402
from dis56k import listing  # noqa: E402

BASE, TAB = 0x0C00, 0x031C00
IRX, IRY, UPX, DNX, FIRY = 0x1000, 0x0800, 0x1200, 0x1240, 0x0A00
ST, PAR = 0x1280, 0x12C0
RIR, RUP, RDN, DCX, DCY = ST + 0, ST + 1, ST + 2, ST + 3, ST + 4
SG = ST + 8                                   # stage s: +4s HPX, HPY, LPY, ENV
TB = ST + 0x14                                # tone stack: x1 x2 y1 y2 (biquad), x1 y1 (first order)
PQ = ST + 0x1A                                # power EQ: 2 x (x1 x2 y1 y2)
SAGE, OSB, INITF = ST + 0x22, ST + 0x23, ST + 0x3F
MAGIC = 0x24F00D                               # positive: a 24-bit immediate compare sign-extends
P_G, P_B, P_HP, P_LP, P_KB, P_EC, P_DC = PAR + 0, PAR + 3, PAR + 6, PAR + 9, PAR + 12, PAR + 13, PAR + 14
P_TB, P_T1, P_PQ = PAR + 16, PAR + 21, PAR + 24
P_DRV, P_SAG, P_SA, P_SR, P_MST = PAR + 34, PAR + 35, PAR + 36, PAR + 37, PAR + 38

a = Asm(BASE)
h = H(a)


def xy_mac(acc, xr='X0', yr='Y0', xmode=2, xreg=0, ymode=3, yreg=0, alu='mac', last=False):
    """mac/macr/clr with a dual move: X:(Rx)<mode>,X0  Y:(Ry)<mode>,Y0. mode 2 = (Rn)-, 3 = (Rn)+"""
    if alu == 'clr':
        al = ('Clr', dict(d='AB'.index(acc)))
    else:
        n, f = MAC('X0', 'Y0', acc)
        al = ('Macr_S1S2' if last else n, f)
    a.par(alu=al, move=('Movexy', dict(W=1, w=1, e=0, f=0, M=xmode, R=xreg, m=ymode, r=yreg)))


def fir(n, acc='A', xreg=2, yreg=0):          # n-tap dot product: X:(Rx)- newest first, Y:(Ry)+ coefficients
    xy_mac(acc, alu='clr', xreg=xreg, yreg=yreg)
    h.rep(n - 1)
    xy_mac(acc, xreg=xreg, yreg=yreg)
    n_, f = MAC('X0', 'Y0', acc)
    a.par(alu=('Macr_S1S2', f))


def biquad(coef, state, acc):
    """DF1, coefficients /2: acc = 2*(b0 x + b1 x1 + b2 x2 - a1 y1 - a2 y2); x in X0, result (limited) in acc."""
    h.ldl(coef + 0, 'Y0'); h.mpy('X0', 'Y0', acc)
    h.ldl(state + 0, 'X1'); h.ldl(coef + 1, 'Y0'); h.mac('X1', 'Y0', acc)
    h.ldl(state + 1, 'X1'); h.ldl(coef + 2, 'Y0'); h.mac('X1', 'Y0', acc)
    h.ldl(state + 2, 'Y1'); h.ldl(coef + 3, 'Y0'); h.mac('Y1', 'Y0', acc)
    h.ldl(state + 3, 'X1'); h.ldl(coef + 4, 'Y0'); h.mac('X1', 'Y0', acc)
    h.asl1(acc)
    h.ldl(state + 0, 'X1'); h.stl('X1', state + 1)       # x2 = x1
    h.stl('X0', state + 0)                               # x1 = x
    h.stl('Y1', state + 3)                               # y2 = y1
    h.stl(acc, state + 2)                                # y1 = y (limited)
    h.mv(acc, 'X0')                                      # x0 = y (limited) for whatever comes next


def shaper(u='X0', out='B'):
    """out = u + (u - u^3)/2 (cubic soft clip; u limited to +/-1)"""
    h.mpy(u, u, 'A')
    h.mv('A', 'Y0')
    h.mpy(u, 'Y0', 'A')                       # a = u^3
    h.mv(u, out)
    h.sub('A', out)                           # out = u - u^3
    h.asr(1, out)
    h.add(u, out)


# ======================================================================== fx_amp
a.label('fx_amp')
h.ldl(INITF, 'A'); h.cmpi(MAGIC, 'A'); h.j('EQ', 'go')
a.jsr('init')
a.label('go')
# ---- input DC blocker: y = x - xprev + R*yprev  (x in X1)
h.mv('X1', 'A')
h.ldl(DCX, 'X0'); h.sub('X0', 'A')
h.stl('X1', DCX)
h.ldl(DCY, 'X0'); h.ldl(P_DC, 'Y0'); h.mac('X0', 'Y0', 'A')
h.stl('A', DCY)
# ---- 4x upsample: newest at (R1); 4 phases x 12 taps into OSB[0..3]
h.movec('M1', 15); h.movec('M2', 15)
h.ldl(RUP, 'R1')
h.li('R4', FIRY)
h.stxi('A', '(R1)')
for p in range(4):
    h.mv('R1', 'R2')
    h.nop()
    fir(12, 'A', xreg=2, yreg=0)
    h.stl('A', OSB + p)
h.ldxi('(R1)+', 'X0')                          # next write slot (dummy read: post-modify wraps with M1; LUA in sim56 ignores Mn)
h.stl('R1', RUP)
# ---- three triode stages at 4x; each output goes into the decimator history (R6, modulo 64)
h.movec('M6', 63)
h.ldl(RDN, 'R6')
h.li('R3', OSB)
a.do(4, 'os_end')
h.ldxi('(R3)+', 'A')
for s in range(3):
    hpx, hpy, lpy, env = SG + 4 * s, SG + 4 * s + 1, SG + 4 * s + 2, SG + 4 * s + 3
    h.tfr('A', 'B')                           # b = stage input
    h.ldl(hpx, 'X0'); h.sub('X0', 'A')        # a = x - xprev
    h.stl('B', hpx)
    h.ldl(hpy, 'X0'); h.ldl(P_HP + s, 'Y0'); h.mac('X0', 'Y0', 'A')
    h.stl('A', hpy)
    h.mv('A', 'X0')                           # v (limited)
    h.ldl(P_G + s, 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(5, 'A')   # a = v * gain
    h.ldl(P_B + s, 'X0'); h.add('X0', 'A')                         # + bias
    h.ldl(env, 'X0'); h.ldl(P_KB, 'Y0'); h.mac('X0', 'Y0', 'A', k=1)   # - depth * env
    h.mv('A', 'X0')                           # u = clamp
    h.mv('X0', 'B'); h.abs_('B')              # env += step * (|u| - env)
    h.ldl(env, 'Y1'); h.sub('Y1', 'B')
    h.mv('B', 'Y0'); h.ldl(P_EC, 'X1'); h.mpy('X1', 'Y0', 'B'); h.add('Y1', 'B')
    h.stl('B', env)
    shaper('X0', 'B')                         # b = soft clip
    h.ldl(lpy, 'Y1'); h.sub('Y1', 'B')        # b = s - lpy
    h.mv('B', 'X0'); h.ldl(P_LP + s, 'Y0'); h.mpy('X0', 'Y0', 'A'); h.add('Y1', 'A')
    h.stl('A', lpy)
h.stxi('A', '(R6)+')
a.label('os_end')
h.stl('R6', RDN)
# ---- decimate: 48 taps over the newest OS samples
h.movec('M2', 63)
h.mv('R6', 'R2')
h.nop()
h.ldxi('(R2)-', 'X0')                          # newest = slot before the write pointer (dummy read, wraps with M2)
h.li('R4', FIRY + 48)
h.nop()
fir(48, 'A', xreg=2, yreg=0)
# ---- tone stack: biquad + first order
h.mv('A', 'X0')
biquad(P_TB, TB, 'B')                         # X0 = biquad out
h.ldl(P_T1 + 0, 'Y0'); h.mpy('X0', 'Y0', 'A')
h.ldl(TB + 4, 'X1'); h.ldl(P_T1 + 1, 'Y0'); h.mac('X1', 'Y0', 'A')
h.ldl(TB + 5, 'X1'); h.ldl(P_T1 + 2, 'Y0'); h.mac('X1', 'Y0', 'A')
h.stl('X0', TB + 4)
h.stl('A', TB + 5)
h.mv('A', 'X0')
# ---- power amp: resonance, presence, sag, drive, soft clip
biquad(P_PQ, PQ, 'B')
biquad(P_PQ + 5, PQ + 4, 'B')                 # X0 = EQ'd signal
h.ldl(SAGE, 'X1'); h.ldl(P_SAG, 'Y0')
h.li('B', 0x7FFFFF); h.mac('X1', 'Y0', 'B', k=1)   # g = 1 - sag * env
h.mv('B', 'Y0'); h.mpy('X0', 'Y0', 'A')       # a = x * g
h.mv('A', 'X0')
h.ldl(P_DRV, 'Y0'); h.mpy('X0', 'Y0', 'A'); h.asl(3, 'A')   # * drive
h.mv('A', 'X0')                               # u = clamp
h.mv('X0', 'B'); h.abs_('B')                  # sag envelope: attack / release
h.ldl(SAGE, 'Y1'); h.sub('Y1', 'B')
h.ldl(P_SR, 'X1')
h.tst('B'); h.j('LE', 'sag_rel')
h.ldl(P_SA, 'X1')
a.label('sag_rel')
h.mv('B', 'Y0'); h.mpy('X1', 'Y0', 'B'); h.add('Y1', 'B')
h.stl('B', SAGE)
shaper('X0', 'B')
h.mv('B', 'X0'); h.mpyi(0x733333, 'X0', 'B')  # * 0.9
# ---- cab IR: newest at (R0), 512 taps
h.movec('M0', 511); h.movec('M4', 511)
h.ldl(RIR, 'R0')
h.li('R4', IRY)
h.stxi('B', '(R0)')
h.nop()
fir(512, 'A', xreg=0, yreg=0)
h.ldxi('(R0)+', 'X0')                          # next write slot (dummy read, wraps with M0)
h.stl('R0', RIR)
# ---- master -> X1, M registers back to linear
h.mv('A', 'X0'); h.ldl(P_MST, 'Y0'); a.par(alu=('Mpyr_S1S2D', MPY('X0', 'Y0', 'A')[1])); h.mv('A', 'X1')
for m in ('M0', 'M1', 'M2', 'M4', 'M6'):
    h.movec(m, 0xFFFFFF)
h.rts()

# ======================================================================== init (first call)
a.label('init')
h.movec('M1', 0xFFFFFF); h.movec('M4', 0xFFFFFF); h.movec('M5', 0xFFFFFF)
h.li('R1', TAB)
h.li('R4', IRY)
a.do(512 + 96, 'cp_end')                      # IR + FIRs: SRAM -> Y:$0800-$0A5F
h.ldxi('(R1)+', 'A')
h.styi('A', '(R4)+')
a.label('cp_end')
h.li('R5', PAR)
a.do(48, 'cp2_end')                           # default params -> X:$12C0
h.ldxi('(R1)+', 'A')
h.stxi('A', '(R5)+')
a.label('cp2_end')
h.li('R1', IRX); h.clr('A')
h.rep(0x2C0)                                  # clear IR ring, FIR histories, state (X:$1000-$12BF)
h.stxi('A', '(R1)+')
h.li('A', IRX); h.stl('A', RIR)
h.li('A', UPX); h.stl('A', RUP)
h.li('A', DNX); h.stl('A', RDN)
h.li('A', MAGIC); h.stl('A', INITF)
h.rts()

words = a.link()
end = BASE + len(words) - 1
assert end <= 0x0DFF, 'AMP runs past its P space: %X' % end


def table():
    import numpy as np
    import amp_ref as R
    up, down = R.fir()
    data = np.concatenate([R.cab_ir(), up, down, R.params()])
    return [int(round(v * R.Q)) & 0xFFFFFF for v in data]


if __name__ == '__main__':
    print(listing(words, base=BASE))
    print('words=%d  end=P:%04X  labels=%s' % (len(words), end, {k: '%04X' % v for k, v in a.labels.items()}))
    a.hexfile(os.path.join(HERE, 'amp.hex'))
    t = table()
    open(os.path.join(HERE, 'amp_tab.hex'), 'w').write('%X\n%s\n' % (TAB, ' '.join('%06X' % v for v in t)))
    print('table: %d words at P:%06X' % (len(t), TAB))
