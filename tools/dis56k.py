"""DSP56300 disassembler (table-driven).

Opcode bit patterns: opcodes56300.json, built by fetch_opcodes.py from the GPL-3.0 dsp56300 emulator
(github.com/dsp56300/dsp56300, opcodeinfo.h). Field meanings: DSP56300 Family Manual
Table 12-13/12-16 (docs/DSP56300FM.pdf).

    from dis56k import disasm
    text, nwords = disasm(words, i, pc)   # words = list of 24-bit ints, decode words[i] at address pc
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
OPS = json.load(open(os.path.join(_HERE, 'opcodes56300.json')))

# ---- register / field tables -------------------------------------------------------------
REG6 = {}
for i, n in enumerate(['X0', 'X1', 'Y0', 'Y1']): REG6[0b000100 + i] = n
for i, n in enumerate(['A0', 'B0', 'A2', 'B2', 'A1', 'B1', 'A', 'B']): REG6[0b001000 + i] = n
for i in range(8):
    REG6[0b010000 + i] = 'R%d' % i
    REG6[0b011000 + i] = 'N%d' % i
    REG6[0b100000 + i] = 'M%d' % i
REG6.update({0b101010: 'EP', 0b110000: 'VBA', 0b110001: 'SC', 0b111000: 'SZ', 0b111001: 'SR',
             0b111010: 'OMR', 0b111011: 'SP', 0b111100: 'SSH', 0b111101: 'SSL', 0b111110: 'LA', 0b111111: 'LC'})
REG5 = {k & 0x1F: v for k, v in REG6.items() if k < 0b100000}   # data/address regs, 5-bit form
CTRL5 = {k & 0x1F: v for k, v in REG6.items() if k >= 0b100000}  # MOVEC: program-control regs
CC = ['CC', 'GE', 'NE', 'PL', 'NN', 'EC', 'LC', 'GT', 'CS', 'LT', 'EQ', 'MI', 'NR', 'ES', 'LS', 'LE']
JJJ = {1: None, 2: 'X', 3: 'Y', 4: 'X0', 5: 'Y0', 6: 'X1', 7: 'Y1'}  # 1 = the other accumulator
JJ = ['X0', 'Y0', 'X1', 'Y1']
QQQ = ['X0,X0', 'Y0,Y0', 'X1,X0', 'Y1,Y0', 'X0,Y1', 'Y0,X0', 'X1,Y0', 'Y1,X1']
QQ_MPYS = ['Y1', 'X0', 'Y0', 'X1']
qq_MPYI = ['X0', 'Y0', 'X1', 'Y1']
LLL = ['A10', 'B10', 'X', 'Y', 'A', 'B', 'AB', 'BA']
PERIPH = {0xFFFFFF: 'IPRC', 0xFFFFFE: 'IPRP', 0xFFFFFD: 'PCTL', 0xFFFFFC: 'OGDB', 0xFFFFFB: 'BCR', 0xFFFFFA: 'DCR',
          0xFFFFF9: 'AAR0', 0xFFFFF8: 'AAR1', 0xFFFFF7: 'AAR2', 0xFFFFF6: 'AAR3', 0xFFFFF5: 'IDR',
          0xFFFFC9: 'HDR', 0xFFFFC8: 'HDDR', 0xFFFFC4: 'HPCR', 0xFFFFBF: 'PCRC', 0xFFFFBE: 'PRRC', 0xFFFFBD: 'PDRC',
          0xFFFFBC: 'RSMB', 0xFFFFBB: 'RSMA', 0xFFFFBA: 'TSMB', 0xFFFFB9: 'TSMA', 0xFFFFB8: 'RCCR', 0xFFFFB7: 'RCR',
          0xFFFFB6: 'TCCR', 0xFFFFB5: 'TCR', 0xFFFFB4: 'SAICR', 0xFFFFB3: 'SAISR',
          0xFFFFAB: 'RX3', 0xFFFFAA: 'RX2', 0xFFFFA9: 'RX1', 0xFFFFA8: 'RX0', 0xFFFFA7: 'TSR',
          0xFFFFA5: 'TX5', 0xFFFFA4: 'TX4', 0xFFFFA3: 'TX3', 0xFFFFA2: 'TX2', 0xFFFFA1: 'TX1', 0xFFFFA0: 'TX0',
          0xFFFF94: 'HRX', 0xFFFF93: 'HTX', 0xFFFF92: 'HSAR', 0xFFFF91: 'HCSR', 0xFFFF90: 'HCKR',
          0xFFFF8F: 'TCSR0', 0xFFFF8E: 'TLR0', 0xFFFF8D: 'TCPR0', 0xFFFF8C: 'TCR0',
          0xFFFF8B: 'TCSR1', 0xFFFF8A: 'TLR1', 0xFFFF89: 'TCPR1', 0xFFFF88: 'TCR1',
          0xFFFF87: 'TCSR2', 0xFFFF86: 'TLR2', 0xFFFF85: 'TCPR2', 0xFFFF84: 'TCR2', 0xFFFF83: 'TPLR', 0xFFFF82: 'TPCR'}


def per(a):
    return PERIPH.get(a, '$%06X' % a)


def sx(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


# ---- pattern compilation ------------------------------------------------------------------
class Op:
    def __init__(self, name, pat, asm, ext):
        self.name, self.pat, self.asm, self.ext = name, pat, asm, ext
        self.m1 = self.m0 = 0
        for i, c in enumerate(pat):
            bit = 1 << (23 - i)
            if c == '1': self.m1 |= bit
            elif c == '0': self.m0 |= bit
        self.fixed = bin(self.m1 | self.m0).count('1')
        self.alu = pat.startswith('?' * 16)          # parallel ALU part (low byte)
        self.pmove = pat.endswith('?' * 8) and not self.alu  # parallel move part (high 16 bits)

    def match(self, w):
        return (w & self.m1) == self.m1 and (w & self.m0) == 0

    def f(self, w, ch):
        """Concatenate all bits marked with letter ch (MSB first)."""
        v = 0
        for i, c in enumerate(self.pat):
            if c == ch:
                v = (v << 1) | ((w >> (23 - i)) & 1)
        return v


ALL = [Op(*r) for r in OPS]
ALU = sorted([o for o in ALL if o.alu], key=lambda o: -o.fixed)
PMOVE = sorted([o for o in ALL if o.pmove], key=lambda o: -o.fixed)
SINGLE = sorted([o for o in ALL if not o.alu and not o.pmove], key=lambda o: -o.fixed)


def is_parallel(w):
    return w >= 0x100000 or (w & 0xFE4000) == 0x080000


# ---- effective addresses --------------------------------------------------------------------
def ea6(mmmrrr, ext):
    """Returns (text, uses_ext)."""
    m, r = mmmrrr >> 3, mmmrrr & 7
    if m == 0: return '(R%d)-N%d' % (r, r), False
    if m == 1: return '(R%d)+N%d' % (r, r), False
    if m == 2: return '(R%d)-' % r, False
    if m == 3: return '(R%d)+' % r, False
    if m == 4: return '(R%d)' % r, False
    if m == 5: return '(R%d+N%d)' % (r, r), False
    if m == 7: return '-(R%d)' % r, False
    if r == 0: return '$%06X' % ext if ext is not None else '$??????', True
    if r == 4: return '#$%06X' % ext if ext is not None else '#$??????', True
    return '?ea%02o' % mmmrrr, False


def ea5(mmrrr):
    m, r = mmrrr >> 3, mmrrr & 7
    return ['(R%d)-N%d' % (r, r), '(R%d)+N%d' % (r, r), '(R%d)-' % r, '(R%d)+' % r][m]


def xyea(mm, rn):
    return ['(R%d)' % rn, '(R%d)+N%d' % (rn, rn), '(R%d)-' % rn, '(R%d)+' % rn][mm]


def mem(space, eatxt, uses_ext, imm_ok=True):
    if eatxt.startswith('#'):
        return eatxt
    return '%s:%s' % (space, eatxt)


# ---- parallel moves ---------------------------------------------------------------------
def pmove_text(o, w, ext):
    """Returns (text, uses_ext) for the high-16-bit move field."""
    n = o.name
    if n == 'Move_Nop': return '', False
    if n in ('Ifcc', 'Ifcc_U'): return 'IF%s%s' % (CC[o.f(w, 'C')], '.U' if n == 'Ifcc_U' else ''), False
    if n == 'Move_xx':
        return '#$%02X,%s' % (o.f(w, 'i'), REG5.get(o.f(w, 'd'), '?')), False
    if n == 'Mover':
        return '%s,%s' % (REG5.get(o.f(w, 'e'), '?'), REG5.get(o.f(w, 'd'), '?')), False
    if n == 'Move_ea': return ea5(o.f(w, 'M') << 3 | o.f(w, 'R')), False
    if n in ('Movex_ea', 'Movey_ea', 'Movex_aa', 'Movey_aa'):
        sp = 'X' if n.startswith('Movex') else 'Y'
        reg = REG5.get(o.f(w, 'd'), '?')
        W = o.f(w, 'W')
        if n.endswith('_aa'):
            e, ue = '$%02X' % o.f(w, 'a'), False
            m = '%s:%s' % (sp, e)
        else:
            e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
            m = mem(sp, e, ue)
        return (('%s,%s' % (m, reg)) if W else ('%s,%s' % (reg, m))), ue
    if n in ('Movel_ea', 'Movel_aa'):
        reg = LLL[o.f(w, 'L')]
        if n.endswith('_aa'):
            e, ue = '$%02X' % o.f(w, 'a'), False
        else:
            e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
        m = 'L:' + e
        return (('%s,%s' % (m, reg)) if o.f(w, 'W') else ('%s,%s' % (reg, m))), ue
    if n == 'Movexr_ea':
        d1 = ['X0', 'X1', 'A', 'B'][o.f(w, 'f')]
        s2 = 'AB'[o.f(w, 'd')]
        d2 = ['Y0', 'Y1'][o.f(w, 'F')]
        e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
        m = mem('X', e, ue)
        first = ('%s,%s' % (m, d1)) if o.f(w, 'W') else ('%s,%s' % (d1, m))
        return '%s %s,%s' % (first, s2, d2), ue
    if n == 'Moveyr_ea':
        s1 = 'AB'[o.f(w, 'd')]
        d1 = ['X0', 'X1'][o.f(w, 'e')]
        d2 = ['Y0', 'Y1', 'A', 'B'][o.f(w, 'f')]
        e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
        m = mem('Y', e, ue)
        second = ('%s,%s' % (m, d2)) if o.f(w, 'W') else ('%s,%s' % (d2, m))
        return '%s,%s %s' % (s1, d1, second), ue
    if n == 'Movexr_A':
        a = 'AB'[o.f(w, 'd')]
        e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
        return '%s,X:%s X0,%s' % (a, e, a), ue
    if n == 'Moveyr_A':
        a = 'AB'[o.f(w, 'd')]
        e, ue = ea6(o.f(w, 'M') << 3 | o.f(w, 'R'), ext)
        return 'Y0,%s %s,Y:%s' % (a, a, e), ue
    if n == 'Movexy':
        rx = o.f(w, 'R')
        ry = (o.f(w, 'r') + (0 if rx >= 4 else 4))
        ex = xyea(o.f(w, 'M'), rx)
        ey = xyea(o.f(w, 'm'), ry)
        xr = ['X0', 'X1', 'A', 'B'][o.f(w, 'e')]
        yr = ['Y0', 'Y1', 'A', 'B'][o.f(w, 'f')]
        xs = ('X:%s,%s' % (ex, xr)) if o.f(w, 'W') else ('%s,X:%s' % (xr, ex))
        ys = ('Y:%s,%s' % (ey, yr)) if o.f(w, 'w') else ('%s,Y:%s' % (yr, ey))
        return '%s %s' % (xs, ys), False
    return '<%s>' % n, False


def alu_text(o, w):
    n, d = o.name, 'AB'[(w >> 3) & 1]
    other = 'BA'[(w >> 3) & 1]
    base = n.split('_')[0].upper()
    if n in ('Add_SD', 'Sub_SD', 'Cmp_S1S2', 'Cmpm_S1S2', 'Tfr'):
        j = o.f(w, 'J')
        s = JJJ.get(j) or other
        return '%s %s,%s' % (base, s, d)
    if n in ('And_SD', 'Or_SD', 'Eor_SD'):
        return '%s %s,%s' % (base, JJ[o.f(w, 'J')], d)
    if n in ('ADC', 'Sbc'):
        return '%s %s,%s' % (base, 'XY'[o.f(w, 'J')], d)
    if n in ('Addl', 'Addr', 'Subl', 'Subr'):
        return '%s %s,%s' % (n.upper(), other, d)
    if n.startswith(('Mpy_S1S2D', 'Mpyr_S1S2D', 'Mac_S1S2', 'Macr_S1S2')):
        k = '-' if o.f(w, 'k') else ''
        return '%s %s%s,%s' % (n.split('_')[0].upper(), k, QQQ[o.f(w, 'Q')], d)
    if n in ('Max', 'Maxm'):
        return '%s A,B' % n.upper()
    if n in ('Lsl_D', 'Lsr_D'):
        return '%s %s' % (base, 'AB'[o.f(w, 'D')])
    return '%s %s' % (base, d)


# ---- main entry ---------------------------------------------------------------------------
def disasm(words, i, pc):
    w = words[i]
    ext = words[i + 1] if i + 1 < len(words) else None
    if is_parallel(w):
        mv = next((o for o in PMOVE if o.match(w & 0xFFFF00 | 0)), None) if False else None
        # parallel: high 16 bits = move, low byte = ALU
        mv = next((o for o in PMOVE if (w & o.m1 & 0xFFFF00) == (o.m1 & 0xFFFF00) and (w & o.m0 & 0xFFFF00) == 0), None)
        alu = None
        if (w & 0xFF) != 0 or mv is None or mv.name in ('Ifcc', 'Ifcc_U'):
            alu = next((o for o in ALU if (w & o.m1) == o.m1 and (w & o.m0) == 0), None)
        mtxt, ue = pmove_text(mv, w, ext) if mv else ('<move?>', False)
        if mv and mv.name in ('Ifcc', 'Ifcc_U'):
            return '%s %s' % (alu_text(alu, w) if alu else '<alu?>', mtxt), 1
        atxt = alu_text(alu, w) if alu else ('MOVE' if (w & 0xFF) == 0 else '<alu %02X?>' % (w & 0xFF))
        return ('%s %s' % (atxt, mtxt)).strip(), (2 if ue else 1)
    o = next((o for o in SINGLE if o.match(w)), None)
    if o is None:
        return 'DC $%06X' % w, 1
    return single_text(o, w, ext, pc)


def single_text(o, w, ext, pc):
    n = o.name
    f = lambda ch: o.f(w, ch)
    sp = 'XY'[f('S')] if o.pat.count('S') == 1 else 'X'
    mnem = n.split('_')[0].upper()
    two = 1

    def eatxt():
        nonlocal two
        e, ue = ea6(f('M') << 3 | f('R'), ext)
        if ue: two = 2
        return e

    if n == 'Nop': return 'NOP', 1
    if n in ('Rts', 'Rti', 'Illegal', 'Trap', 'Pflush', 'Pflushun', 'Pfree', 'Debug'): return mnem, 1
    if n in ('Reset', 'Stop', 'Wait', 'Enddo'): return mnem, 1
    if n in ('Jmp_xxx', 'Jsr_xxx'): return '%s $%04X' % (mnem, f('a')), 1
    if n in ('Jcc_xxx', 'Jscc_xxx'):
        return '%s%s $%04X' % (mnem[:-2], CC[f('C')], f('a')), 1
    if n in ('Jmp_ea', 'Jsr_ea'): return '%s %s' % (mnem, eatxt()), two
    if n in ('Jcc_ea', 'Jscc_ea'): return '%s%s %s' % (mnem[:-2], CC[f('C')], eatxt()), two
    if n in ('Bra_xxx', 'Bsr_xxx'): return '%s $%06X' % (mnem, (pc + sx(f('a'), 9)) & 0xFFFFFF), 1
    if n in ('Bcc_xxx', 'BScc_xxx'): return '%s%s $%06X' % (mnem[:-2], CC[f('C')], (pc + sx(f('a'), 9)) & 0xFFFFFF), 1
    if n in ('Bra_xxxx', 'Bsr_xxxx'): return '%s $%06X' % (mnem, (pc + ext) & 0xFFFFFF), 2
    if n in ('Bcc_xxxx', 'BScc_xxxx'): return '%s%s $%06X' % (mnem[:-2], CC[f('C')], (pc + ext) & 0xFFFFFF), 2
    if n in ('Bra_Rn', 'Bsr_Rn'): return '%s R%d' % (mnem, f('R')), 1
    if n in ('Bcc_Rn', 'BScc_Rn'): return '%s%s R%d' % (mnem[:-2], CC[f('C')], f('R')), 1
    bitops = ('Bchg', 'Bclr', 'Bset', 'Btst', 'Jclr', 'Jset', 'Jsclr', 'Jsset', 'Brclr', 'Brset', 'Bsclr', 'Bsset')
    if mnem.capitalize() in [b.upper().capitalize() for b in bitops] or n.split('_')[0] in bitops:
        base = n.split('_')[0]
        kind = n.split('_')[1]
        b = '#%d' % f('b')
        if kind == 'ea': opnd = '%s:%s' % (sp, eatxt())
        elif kind == 'aa': opnd = '%s:$%02X' % (sp, f('a'))
        elif kind == 'pp': opnd = '%s:%s' % (sp, per(0xFFFFC0 + f('p')))
        elif kind == 'qq': opnd = '%s:%s' % (sp, per(0xFFFF80 + f('q')))
        else: opnd = REG6.get(f('D'), '?')
        out = '%s %s,%s' % (base.upper(), b, opnd)
        if base[0] == 'J':
            out += ',$%06X' % (ext if ext is not None else 0)
            return out, two + 1
        if base in ('Brclr', 'Brset', 'Bsclr', 'Bsset'):
            out += ',$%06X' % ((pc + (ext or 0)) & 0xFFFFFF)
            return out, two + 1
        return out, two
    if n.startswith('Movep'):
        W = f('W')
        if n == 'Movep_ppea':
            p = '%s:%s' % ('XY'[f('s')], per(0xFFFFC0 + f('p')))
            e = eatxt(); m = e if e.startswith('#') else '%s:%s' % (sp, e)
        elif n == 'Movep_Xqqea':
            p = 'X:' + per(0xFFFF80 + f('q'))
            e = eatxt(); m = e if e.startswith('#') else '%s:%s' % (sp, e)
        elif n == 'Movep_Yqqea':
            p = 'Y:' + per(0xFFFF80 + f('q'))
            e = eatxt(); m = e if e.startswith('#') else '%s:%s' % (sp, e)
        elif n == 'Movep_eapp':
            p = '%s:%s' % ('XY'[f('s')], per(0xFFFFC0 + f('p')))
            m = 'P:' + eatxt()
        elif n == 'Movep_eaqq':
            p = '%s:%s' % (sp, per(0xFFFF80 + f('q')))
            m = 'P:' + eatxt()
        elif n == 'Movep_Spp':
            p = '%s:%s' % ('XY'[f('s')], per(0xFFFFC0 + f('p'))); m = REG6.get(f('d'), '?')
        elif n == 'Movep_SXqq':
            p = 'X:' + per(0xFFFF80 + f('q')); m = REG6.get(f('d'), '?')
        else:
            p = 'Y:' + per(0xFFFF80 + f('q')); m = REG6.get(f('d'), '?')
        return ('MOVEP %s,%s' % (m, p)) if W else ('MOVEP %s,%s' % (p, m)), two
    if n.startswith('Movem'):
        m = 'P:' + (eatxt() if n == 'Movem_ea' else '$%02X' % f('a'))
        r = REG6.get(f('d'), '?')
        return ('MOVEM %s,%s' % (m, r)) if f('W') else ('MOVEM %s,%s' % (r, m)), two
    if n.startswith('Movec'):
        cr = CTRL5.get(f('D'), '?')
        if n == 'Movec_xx': return 'MOVEC #$%02X,%s' % (f('i'), cr), 1
        if n == 'Movec_S1D2':
            r = REG6.get(f('e'), '?')
            return ('MOVEC %s,%s' % (r, cr)) if f('W') else ('MOVEC %s,%s' % (cr, r)), 1
        e = eatxt() if n == 'Movec_ea' else '$%02X' % f('a')
        m = e if e.startswith('#') else '%s:%s' % (sp, e)
        return ('MOVEC %s,%s' % (m, cr)) if f('W') else ('MOVEC %s,%s' % (cr, m)), two
    if n in ('Movex_Rnxxxx', 'Movey_Rnxxxx'):
        spc = 'X' if n[4] == 'x' else 'Y'
        m = '%s:(R%d+$%06X)' % (spc, f('R'), ext or 0); r = REG6.get(f('D'), '?')
        return ('MOVE %s,%s' % (m, r)) if f('W') else ('MOVE %s,%s' % (r, m)), 2
    if n in ('Movex_Rnxxx', 'Movey_Rnxxx'):
        spc = 'X' if n[4] == 'x' else 'Y'
        m = '%s:(R%d%+d)' % (spc, f('R'), sx(f('a'), 7)); r = REG5.get(f('D') | 0x10 if f('D') >= 8 else f('D') | 4, '?')
        return ('MOVE %s,%s' % (m, r)) if f('W') else ('MOVE %s,%s' % (r, m)), 1
    if n.startswith(('Do_', 'Dor_', 'Rep_')) or n in ('DoForever', 'DorForever'):
        base = n.split('_')[0].upper().replace('DOFOREVER', 'DO FOREVER').replace('DORFOREVER', 'DOR FOREVER')
        kind = n.split('_')[1] if '_' in n else ''
        if kind == 'xxx': src = '#%d' % ((f('h') << 8) | f('i'))
        elif kind == 'ea': src = '%s:%s' % (sp, eatxt())
        elif kind == 'aa': src = '%s:$%02X' % (sp, f('a'))
        elif kind == 'S': src = REG6.get(f('D') if 'D' in o.pat else f('d'), '?')
        else: src = ''
        if base == 'REP': return 'REP %s' % src, 1
        tgt = ext if base.startswith('DO') and not base.startswith('DOR') else (pc + (ext or 0)) & 0xFFFFFF
        return ('%s %s,$%06X' % (base, src, (tgt or 0) + (1 if base.startswith('DO') and not base.startswith('DOR') else 0))).replace(' ,', ' '), 2
    if n in ('Andi', 'Ori'):
        return '%sI #$%02X,%s' % (n[:-1].upper(), f('i'), ['MR', 'CCR', 'COM', 'EOM'][f('E')]), 1
    if n in ('Add_xx', 'Sub_xx', 'Cmp_xxS2', 'And_xx', 'Or_xx', 'Eor_xx'):
        return '%s #$%02X,%s' % (mnem, f('i'), 'AB'[f('d')]), 1
    if n in ('Add_xxxx', 'Sub_xxxx', 'Cmp_xxxxS2', 'And_xxxx', 'Or_xxxx', 'Eor_xxxx'):
        return '%s #$%06X,%s' % (mnem, ext or 0, 'AB'[f('d')]), 2
    if n in ('Mpy_SD', 'Mpyr_SD', 'Mac_S', 'Macr_S'):
        return '%s %s%s,#%d,%s' % (mnem, '-' if f('k') else '', QQ_MPYS[f('Q')], f('s'), 'AB'[f('d')]), 1
    if n in ('Mpyi', 'Mpyri', 'Maci_xxxx', 'Macri_xxxx'):
        return '%s %s#$%06X,%s,%s' % (mnem, '-' if f('k') else '', ext or 0, qq_MPYI[f('q')], 'AB'[f('d')]), 2
    if n in ('Asl_ii', 'Asr_ii'):
        return '%s #%d,%s,%s' % (mnem, f('i'), 'AB'[f('S')], 'AB'[f('D')]), 1
    if n in ('Lsl_ii', 'Lsr_ii'):
        return '%s #%d,%s' % (mnem, f('i'), 'AB'[f('D')]), 1
    if n in ('Lua_ea',):
        return 'LUA %s,%s' % (ea5(f('M') << 3 | f('R')), REG5.get(f('d'), '?')), 1
    if n == 'Lua_Rn':
        d = f('d'); r = ('N%d' if d & 8 else 'R%d') % (d & 7)
        return 'LUA (R%d%+d),%s' % (f('R'), sx(f('a'), 7), r), 1
    if n in ('Tcc_S1D1', 'Tcc_S1D1S2D2', 'Tcc_S2D2'):
        s = 'T%s' % CC[f('C')]
        if n != 'Tcc_S2D2':
            j = f('J'); s += ' %s,%s' % (JJJ.get(j) or 'BA'[f('d')], 'AB'[f('d')])
        if n != 'Tcc_S1D1':
            s += ' R%d,R%d' % (f('t'), f('T'))
        return s, 1
    if n in ('Dec', 'Inc'): return '%s %s' % (mnem, 'AB'[f('d')]), 1
    if n == 'Norm': return 'NORM R%d,%s' % (f('R'), 'AB'[f('d')]), 1
    if n == 'Div': return 'DIV %s,%s' % (JJ[f('J')], 'AB'[f('d')]), 1
    if n in ('Trapcc', 'Debugcc', 'BRKcc'): return '%s%s' % (n[:-2].upper(), CC[f('C')]), 1
    if n == 'Plockr' or n == 'Punlockr': return '%s $%06X' % (mnem, (pc + (ext or 0)) & 0xFFFFFF), 2
    # fallback: name + raw fields
    fields = sorted(set(c for c in o.pat if c.isalpha() and c not in 'o'))
    two = 2 if o.ext in ('ImmediateData', 'AbsoluteAddressExt', 'PCRelativeAddressExt') else two
    return '%s %s' % (o.asm.split(' ')[0], ' '.join('%s=%X' % (c, f(c)) for c in fields)), two


def listing(words, base=0, start=0, count=None, out=None):
    i, end = start, len(words) if count is None else min(len(words), start + count)
    lines = []
    while i < end:
        txt, n = disasm(words, i, base + i)
        raw = ' '.join('%06X' % words[k] for k in range(i, min(i + n, len(words))))
        lines.append('P:%06X  %-14s %s' % (base + i, raw, txt))
        i += n
    s = '\n'.join(lines)
    if out: open(out, 'w').write(s + '\n')
    return s


if __name__ == '__main__':
    tests = [0x08F4BD, 0xFF0040, 0x62F400, 0x800001, 0x01918F, 0x03929E, 0x04D293, 0x07DA84,
             0x04C493, 0x0C010E, 0x07F413, 0xC0FFEE, 0x0AF080, 0x02FF6E, 0x000000, 0x0870B8, 0xFFFFFC,
             0x08D87C, 0x077011, 0xFFFFFC, 0x08FA3C]
    print(listing(tests))
