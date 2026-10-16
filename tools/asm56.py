"""Tiny DSP56300 assembler: encodes from the same opcode table as dis56k.py, with labels.

    from asm56 import Asm, R5, R6
    a = Asm(0xA00)
    a.op('Movex_ea', W=1, d=R5['X0'], **ea('(R4)+'))      # MOVE X:(R4)+,X0
    a.par(alu=('Add_SD', dict(J=4, d=0)), move=None)       # ADD X0,A
    a.label('loop'); a.jmp('loop')
    words = a.link()                                       # resolves labels, round-trip checks every word

Field values are given per pattern letter (all bits of that letter, MSB first), exactly like dis56k's Op.f().
"""
from dis56k import ALL, REG5, REG6, CTRL5, disasm

OPS = {o.name: o for o in ALL}
R5 = {v: k for k, v in REG5.items()}
R6 = {v: k for k, v in REG6.items()}
C5 = {v: k for k, v in CTRL5.items()}
CC = {n: i for i, n in enumerate(['CC', 'GE', 'NE', 'PL', 'NN', 'EC', 'LC', 'GT', 'CS', 'LT', 'EQ', 'MI', 'NR', 'ES', 'LS', 'LE'])}
CC['HS'], CC['LO'] = 0, 8


def ea(spec):
    """'(R4)+' etc -> dict(M=..., R=...) for MMMRRR fields. Absolute/immediate: use ea_abs / ea_imm."""
    s = spec.replace(' ', '').upper()
    r = int(s[s.index('R') + 1])
    if s.startswith('-('): m = 7
    elif s.endswith(')+N%d' % r): m = 1
    elif s.endswith(')-N%d' % r): m = 0
    elif s.endswith(')-'): m = 2
    elif s.endswith(')+'): m = 3
    elif '+N' in s: m = 5
    else: m = 4
    return dict(M=m, R=r)


EA_ABS = dict(M=6, R=0)
EA_IMM = dict(M=6, R=4)


def encode(name, **f):
    o = OPS[name]
    word = 0
    pos = {}
    for i, c in enumerate(o.pat):
        bit = 23 - i
        if c == '1':
            word |= 1 << bit
        elif c in '0?o':
            pass
        else:
            pos.setdefault(c, []).append(bit)
    for c, bits in pos.items():
        if c not in f:
            raise ValueError('%s: field %r missing (pattern %s)' % (name, c, o.pat))
        v = f[c]
        n = len(bits)
        if v < 0:
            v &= (1 << n) - 1
        if v >> n:
            raise ValueError('%s: field %r=%X does not fit %d bits' % (name, c, f[c], n))
        for k, bit in enumerate(bits):
            if (v >> (n - 1 - k)) & 1:
                word |= 1 << bit
    extra = set(f) - set(pos)
    if extra:
        raise ValueError('%s: unknown fields %s' % (name, extra))
    return word


class Asm:
    def __init__(self, base):
        self.base = base
        self.w = []
        self.labels = {}
        self.fix = []          # (index, label, kind)
        self.notes = {}

    @property
    def pc(self):
        return self.base + len(self.w)

    def label(self, n):
        assert n not in self.labels, n
        self.labels[n] = self.pc

    def word(self, w, note=None):
        if note: self.notes[len(self.w)] = note
        self.w.append(w & 0xFFFFFF)

    def op(self, name, ext=None, label=None, **f):
        """single instruction; ext = 2nd word value; label = 2nd word is a label address (absolute)"""
        self.word(encode(name, **f))
        if label is not None:
            self.fix.append((len(self.w), label, 'abs'))
            self.w.append(0)
        elif ext is not None:
            self.w.append(ext & 0xFFFFFF)

    def par(self, alu=None, move=None, ext=None):
        """parallel instruction: alu=(name, fields) for the low byte, move=(name, fields) for the high 16 bits"""
        lo = encode(alu[0], **alu[1]) & 0xFF if alu else 0
        hi = encode(move[0], **move[1]) & 0xFFFF00 if move else 0x200000   # Move_Nop
        self.word(hi | lo)
        if ext is not None:
            self.w.append(ext & 0xFFFFFF)

    def jshort(self, cond, label):          # Jcc xxx (12-bit), cond 'T' = JMP
        if cond == 'T':
            self.fix.append((len(self.w), label, ('jmp12', 0x0C0000)))
        else:
            self.fix.append((len(self.w), label, ('jmp12', encode('Jcc_xxx', C=CC[cond], a=0))))
        self.w.append(0)

    def jmp(self, label):                   # JMP absolute (2 words)
        self.op('Jmp_ea', label=label, **EA_ABS)

    def jsr(self, label):
        self.op('Jsr_ea', label=label, **EA_ABS)

    def do(self, count_imm, end_label):     # DO #n,end  (end_label = first address AFTER the loop)
        self.word(encode('Do_xxx', i=count_imm & 0xFF, h=count_imm >> 8))
        self.fix.append((len(self.w), end_label, 'do'))
        self.w.append(0)

    def dc(self, label):                    # data word = label address
        self.fix.append((len(self.w), label, 'abs'))
        self.w.append(0)

    def link(self, check=True):
        for i, n, kind in self.fix:
            a = self.labels[n]
            if kind == 'abs':
                self.w[i] = a
            elif kind == 'do':
                self.w[i] = a - 1
            else:
                assert a <= 0xFFF, 'short jump target %X out of range' % a
                self.w[i] = kind[1] | a
        if check:
            self.roundtrip()
        return self.w

    def roundtrip(self):
        """every word must decode to a known instruction (catches pattern/field slips)"""
        i = 0
        while i < len(self.w):
            t, n = disasm(self.w, i, self.base + i)
            if t.startswith(('DC ', '<')) and i not in self.notes:
                raise ValueError('P:%04X %06X does not decode: %s' % (self.base + i, self.w[i], t))
            i += n

    def hexfile(self, path):                # atomic (temp + rename): parallel simulator runs read these
        import os
        tmp = '%s.%d' % (path, os.getpid())
        open(tmp, 'w').write('%X\n%s\n' % (self.base, ' '.join('%06X' % x for x in self.w)))
        if os.path.exists(path) and open(path).read() == open(tmp).read():
            os.remove(tmp)          # unchanged: don't touch it (Windows can't replace a file another run has open)
        else:
            os.replace(tmp, path)
