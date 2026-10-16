"""Small DSP56300 simulator for the instructions our M-One programs use.

    from sim56 import Sim
    s = Sim(words, base=0xA00)
    out = s.run_audio(left_samples, right_samples)   # feeds ESAI RX1 (L, R per frame), returns TX1 per frame

Model: A/B 56-bit ints (value = int / 2^47), X0..Y1 24-bit, fractional MPY (product << 1), saturation when an
accumulator is moved to a 24-bit register, CCR N/Z/V/C/E for Jcc, hardware DO/REP, linear addressing only
(M = $FFFFFF; anything else raises). ESAI: SAISR RDF (bit 8) set while a slot is waiting, RFS (bit 6) on the
left slot; reading RX1 consumes it; writes to TX1 are recorded. Unknown instructions raise, so nothing is silently wrong.
"""
from dis56k import ALL, ALU, PMOVE, SINGLE, REG5, REG6, CTRL5, is_parallel

M24, M56 = (1 << 24) - 1, (1 << 56) - 1
CCN = ['CC', 'GE', 'NE', 'PL', 'NN', 'EC', 'LC', 'GT', 'CS', 'LT', 'EQ', 'MI', 'NR', 'ES', 'LS', 'LE']


def s24(v): v &= M24; return v - (1 << 24) if v >> 23 else v
def s56(v): v &= M56; return v - (1 << 56) if v >> 55 else v


class SimError(Exception):
    pass


class Sim:
    def __init__(self, words, base):
        self.P = {base + i: w for i, w in enumerate(words)}
        self.X, self.Y = {}, {}
        self.r = {k: 0 for k in ('X0', 'X1', 'Y0', 'Y1')}
        self.R = [0] * 8; self.N = [0] * 8; self.M = [M24] * 8
        self.acc = {'A': 0, 'B': 0}
        self.ccr = dict(N=0, Z=0, V=0, C=0, E=0)
        self.pc = base
        self.stack = []           # (pc) for JSR
        self.loops = []           # [start, la, lc]
        self.rep = 0
        self.icount = 0
        self.inp = []             # pending ESAI slots: (sample, is_left)
        self.last_rfs = False
        self.out = []
        self.sr_val = 0
        self._dec = {}

    # ---------------- registers
    def acc_to24(self, name, limit=True):
        v = self.acc[name]
        if limit and not (-(1 << 47) <= v < (1 << 47)):
            return 0x7FFFFF if v > 0 else 0x800000
        return (v >> 24) & M24

    def get(self, name, limit=True):
        if name in self.r: return self.r[name]
        if name in ('A', 'B'): return self.acc_to24(name, limit)
        if name in ('A1', 'B1'): return (self.acc[name[0]] >> 24) & M24
        if name in ('A0', 'B0'): return self.acc[name[0]] & M24
        if name in ('A2', 'B2'): return (self.acc[name[0]] >> 48) & 0xFF
        if name[0] == 'R': return self.R[int(name[1])]
        if name[0] == 'N': return self.N[int(name[1])]
        if name[0] == 'M': return self.M[int(name[1])]
        if name == 'SR': return self.sr_val
        if name == 'SP': return len(self.stack)
        raise SimError('read reg %s' % name)

    def put(self, name, v):
        v &= M24
        if name in self.r: self.r[name] = v
        elif name in ('A', 'B'): self.acc[name] = s24(v) << 24
        elif name in ('A1', 'B1'):
            a = self.acc[name[0]]; self.acc[name[0]] = s56((a & ~(M24 << 24)) | (v << 24))
        elif name in ('A0', 'B0'):
            a = self.acc[name[0]]; self.acc[name[0]] = s56((a & ~M24) | v)
        elif name[0] == 'R': self.R[int(name[1])] = v
        elif name[0] == 'N': self.N[int(name[1])] = v
        elif name[0] == 'M':
            if v != M24 and v >= 0x8000: raise SimError('M%s=%06X not modelled' % (name[1], v))
            self.M[int(name[1])] = v
        elif name == 'SR': self.sr_val = v
        elif name == 'SP':
            if v: raise SimError('SP write %X' % v)
            self.stack = []
        else: raise SimError('write reg %s' % name)

    # ---------------- memory / peripherals
    def rd(self, sp, a):
        a &= M24
        if a >= 0xFFFF80:
            if sp == 'X' and a == 0xFFFFB3:   # SAISR: RDF = a word is waiting, RFS = the word in RX is the first slot
                v = (1 << 8) if self.inp else 0
                if self.last_rfs: v |= 1 << 6
                return v
            if sp == 'X' and a == 0xFFFFA9:   # RX1
                if not self.inp: raise SimError('RX1 read with no slot pending')
                val, self.last_rfs = self.inp.pop(0)
                return val & M24
            raise SimError('peripheral read %s:%06X' % (sp, a))
        if sp == 'P': return self.P.get(a, 0)
        return (self.X if sp == 'X' else self.Y).get(a, 0)

    def wr(self, sp, a, v):
        a &= M24; v &= M24
        if a >= 0xFFFF80:
            if sp == 'X' and a == 0xFFFFA1:   # TX1
                self.out.append(s24(v)); return
            raise SimError('peripheral write %s:%06X' % (sp, a))
        if sp == 'P': self.P[a] = v
        else: (self.X if sp == 'X' else self.Y)[a] = v

    def addmod(self, r, R, delta):
        """R + delta with the Mr addressing mode: linear ($FFFFFF) or modulo (Mr = size-1 < $8000)"""
        m = self.M[r]
        if m == M24:
            return (R + delta) & M24
        if m >= 0x8000:
            raise SimError('M%d=%06X: only linear and modulo (<$8000) modelled' % (r, m))
        size = m + 1
        k = 1
        while k < size: k <<= 1
        base = R & ~(k - 1)
        return base + ((R - base + delta) % size)

    def ea(self, mmmrrr, ext):
        """returns (address, extra_words_used) and applies post/pre modification"""
        m, r = mmmrrr >> 3, mmmrrr & 7
        R = self.R[r]
        if m == 0: self.R[r] = self.addmod(r, R, -s24(self.N[r])); return R, 0
        if m == 1: self.R[r] = self.addmod(r, R, s24(self.N[r])); return R, 0
        if m == 2: self.R[r] = self.addmod(r, R, -1); return R, 0
        if m == 3: self.R[r] = self.addmod(r, R, 1); return R, 0
        if m == 4: return R, 0
        if m == 5: return self.addmod(r, R, s24(self.N[r])), 0
        if m == 7: self.R[r] = self.addmod(r, R, -1); return self.R[r], 0
        if r == 0: return ext, 1
        raise SimError('ea mode %o' % mmmrrr)

    # ---------------- flags
    def flags(self, v, carry=None, ovf=False):
        v = s56(v)
        self.ccr['N'] = int(v < 0)
        self.ccr['Z'] = int(v == 0)
        self.ccr['V'] = int(ovf)
        self.ccr['E'] = int(not (-(1 << 47) <= v < (1 << 47)))
        if carry is not None: self.ccr['C'] = carry

    def cond(self, c):
        n, z, v, cc = self.ccr['N'], self.ccr['Z'], self.ccr['V'], self.ccr['C']
        return {
            'CC': not cc, 'CS': cc, 'NE': not z, 'EQ': z, 'PL': not n, 'MI': n,
            'GE': not (n ^ v), 'LT': n ^ v, 'GT': not (z or (n ^ v)), 'LE': z or (n ^ v),
            'EC': not self.ccr['E'], 'ES': self.ccr['E'],
        }[CCN[c]]

    def setacc(self, d, v, carry=None):
        raw = v
        v = s56(v)
        self.acc[d] = v
        self.flags(v, carry, ovf=(raw != v))

    # ---------------- decode
    def decode(self, pc):
        if pc in self._dec: return self._dec[pc]
        w = self.P.get(pc, 0)
        if is_parallel(w):
            mv = next((o for o in PMOVE if (w & o.m1 & 0xFFFF00) == (o.m1 & 0xFFFF00) and (w & o.m0 & 0xFFFF00) == 0), None)
            alu = None
            if (w & 0xFF) != 0 or (mv and mv.name in ('Ifcc', 'Ifcc_U')):
                alu = next((o for o in ALU if (w & o.m1) == o.m1 and (w & o.m0) == 0), None)
                if alu is None: raise SimError('P:%06X %06X: unknown ALU op' % (pc, w))
            d = ('par', mv, alu, w)
        else:
            o = next((o for o in SINGLE if o.match(w)), None)
            if o is None: raise SimError('P:%06X %06X: unknown instruction' % (pc, w))
            d = ('one', o, None, w)
        self._dec[pc] = d
        return d

    # ---------------- ALU
    def src24(self, j, d):        # JJJ (ADD/SUB table 12-13), returns 56-bit aligned value
        other = 'BA'[d]
        if j == 1: return self.acc[other]
        name = {2: 'X', 3: 'Y', 4: 'X0', 5: 'Y0', 6: 'X1', 7: 'Y1'}[j]
        if name in ('X', 'Y'):
            hi, lo = self.r[name + '1'], self.r[name + '0']
            return s56((s24(hi) << 24) | lo)
        return s24(self.r[name]) << 24

    def alu(self, o, w):
        n = o.name
        d = (w >> 3) & 1
        D = 'AB'[d]
        a = self.acc[D]
        if n in ('Add_SD', 'Sub_SD', 'Cmp_S1S2', 'Tfr'):
            j = o.f(w, 'J')
            if n in ('Cmp_S1S2', 'Tfr'):          # table 12-16: 000 = other acc
                s = self.acc['BA'[d]] if j == 0 else s24(self.r[{4: 'X0', 5: 'Y0', 6: 'X1', 7: 'Y1'}[j]]) << 24
            else:
                s = self.src24(j, d)
            if n == 'Add_SD': self.setacc(D, a + s)
            elif n == 'Sub_SD': self.setacc(D, a - s)
            elif n == 'Cmp_S1S2': self.flags(a - s, ovf=(s56(a - s) != a - s))
            else: self.acc[D] = s
            return
        if n in ('Or_SD', 'And_SD', 'Eor_SD'):
            s = self.r[['X0', 'Y0', 'X1', 'Y1'][o.f(w, 'J')]]
            a1 = (a >> 24) & M24
            r = {'Or_SD': a1 | s, 'And_SD': a1 & s, 'Eor_SD': a1 ^ s}[n]
            self.put(D + '1', r); self.ccr['N'] = r >> 23; self.ccr['Z'] = int(r == 0); self.ccr['V'] = 0
            return
        if n == 'Clr': self.acc[D] = 0; self.flags(0); return
        if n == 'Tst': self.flags(a); return
        if n == 'Abs': self.setacc(D, abs(a)); return
        if n == 'Neg': self.setacc(D, -a); return
        if n == 'Asl_D': self.setacc(D, a << 1, carry=(a >> 55) & 1); return
        if n == 'Asr_D': self.setacc(D, a >> 1, carry=a & 1); return
        if n in ('Mpy_S1S2D', 'Mac_S1S2', 'Mpyr_S1S2D', 'Macr_S1S2'):
            q = ['X0,X0', 'Y0,Y0', 'X1,X0', 'Y1,Y0', 'X0,Y1', 'Y0,X0', 'X1,Y0', 'Y1,X1'][o.f(w, 'Q')].split(',')
            prod = (s24(self.r[q[0]]) * s24(self.r[q[1]])) << 1
            if o.f(w, 'k'): prod = -prod
            r = prod if n.startswith('Mpy') else a + prod
            if n in ('Mpyr_S1S2D', 'Macr_S1S2'): r = (r + (1 << 23)) >> 24 << 24   # round into A1 (two's complement)
            self.setacc(D, r)
            return
        if n == 'Max':   # MAX A,B: if |A| > |B| ... (not used)
            raise SimError('MAX not modelled')
        raise SimError('ALU %s not modelled' % n)

    # ---------------- parallel moves
    def pmove(self, mv, w, ext):
        """returns (list of (kind, target, value) writes to apply after the ALU, words used)"""
        n = mv.name
        f = lambda c: mv.f(w, c)
        if n == 'Move_Nop': return [], 0
        if n == 'Move_xx':
            reg = REG5[f('d')]
            i = f('i')
            v = (s24(i << 16) if reg in ('X0', 'X1', 'Y0', 'Y1', 'A', 'B', 'A1', 'B1') else i)
            return [('reg', reg, v & M24)], 0
        if n == 'Mover': return [('reg', REG5[f('d')], self.get(REG5[f('e')]))], 0
        if n == 'Move_ea':
            mm = f('M') << 3 | f('R')
            r = mm & 7
            self.ea({0: 0, 1: 1, 2: 2, 3: 3}[mm >> 3] << 3 | r, None)
            return [], 0
        if n in ('Movex_ea', 'Movey_ea', 'Movex_aa', 'Movey_aa'):
            sp = 'X' if n[4] == 'x' else 'Y'
            reg = REG5[f('d')]
            if n.endswith('_aa'): addr, used = f('a'), 0
            else:
                mm = f('M') << 3 | f('R')
                if mm == 0o64:   # immediate
                    return [('reg', reg, ext)], 1
                addr, used = self.ea(mm, ext)
            if f('W'): return [('reg', reg, self.rd(sp, addr))], used
            return [('mem', (sp, addr), self.get(reg))], used
        if n == 'Movexy':
            rx = f('R'); ry = f('r') + (0 if rx >= 4 else 4)
            def xy(mm, rn):
                Rv = self.R[rn]
                if mm == 1: self.R[rn] = self.addmod(rn, Rv, s24(self.N[rn]))
                elif mm == 2: self.R[rn] = self.addmod(rn, Rv, -1)
                elif mm == 3: self.R[rn] = self.addmod(rn, Rv, 1)
                return Rv
            ax, ay = xy(f('M'), rx), xy(f('m'), ry)
            xr = ['X0', 'X1', 'A', 'B'][f('e')]; yr = ['Y0', 'Y1', 'A', 'B'][f('f')]
            wr = []
            wr.append(('reg', xr, self.rd('X', ax)) if f('W') else ('mem', ('X', ax), self.get(xr)))
            wr.append(('reg', yr, self.rd('Y', ay)) if f('w') else ('mem', ('Y', ay), self.get(yr)))
            return wr, 0
        raise SimError('parallel move %s not modelled' % n)

    def apply(self, writes):
        for kind, t, v in writes:
            if kind == 'reg': self.put(t, v)
            else: self.wr(t[0], t[1], v)

    # ---------------- single-word (non-parallel) instructions
    def one(self, o, w, ext, pc):
        n = o.name
        f = lambda c: o.f(w, c)
        nxt = pc + 1
        if n == 'Nop': return nxt
        if n == 'Rts': return self.stack.pop()
        if n == 'Jmp_xxx': return f('a')
        if n == 'Jcc_xxx': return f('a') if self.cond(f('C')) else nxt
        if n == 'Jsr_xxx': self.stack.append(nxt); return f('a')
        if n in ('Jmp_ea', 'Jsr_ea', 'Jcc_ea'):
            addr, used = self.ea(f('M') << 3 | f('R'), ext)
            ret = pc + 1 + used
            if n == 'Jcc_ea' and not self.cond(f('C')): return ret
            if n == 'Jsr_ea': self.stack.append(ret)
            return addr
        if n in ('Jclr_qq', 'Jset_qq', 'Jclr_pp', 'Jset_pp', 'Jsclr_qq', 'Jsset_qq'):
            base = 0xFFFF80 if n.endswith('qq') else 0xFFFFC0
            ch = 'q' if n.endswith('qq') else 'p'
            v = self.rd('XY'[f('S')], base + f(ch))
            bit = (v >> f('b')) & 1
            take = bit if 'set' in n else not bit
            self.ccr['C'] = bit
            return ext if take else pc + 2
        if n in ('Jclr_S', 'Jset_S'):
            v = self.get(REG6[f('D')], limit=False)
            bit = (v >> f('b')) & 1
            return ext if (bit if n == 'Jset_S' else not bit) else pc + 2
        if n in ('Movep_SXqq', 'Movep_Spp'):
            base = 0xFFFF80 if 'qq' in n else 0xFFFFC0
            a = base + (f('q') if 'qq' in n else f('p'))
            reg = REG6[f('d')]
            if f('W'): self.wr('X', a, self.get(reg))
            else: self.put(reg, self.rd('X', a))
            return nxt
        if n in ('Movep_Xqqea', 'Movep_ppea'):
            base = 0xFFFF80 if 'qq' in n else 0xFFFFC0
            a = base + (f('q') if 'qq' in n else f('p'))
            mm = f('M') << 3 | f('R')
            if mm == 0o64:
                self.wr('X', a, ext); return pc + 2
            addr, used = self.ea(mm, ext)
            sp = 'XY'[f('S')]
            if f('W'): self.wr('X', a, self.rd(sp, addr))
            else: self.wr(sp, addr, self.rd('X', a))
            return pc + 1 + used
        if n == 'Movec_ea':
            mm = f('M') << 3 | f('R')
            reg = CTRL5[f('D')]
            if mm == 0o64: self.put(reg, ext); return pc + 2
            addr, used = self.ea(mm, ext)
            sp = 'XY'[f('S')]
            if f('W'): self.put(reg, self.rd(sp, addr))
            else: self.wr(sp, addr, self.get(reg))
            return pc + 1 + used
        if n == 'Movec_xx': self.put(CTRL5[f('D')], f('i')); return nxt
        if n == 'Movec_S1D2':
            r, c = REG6[f('e')], CTRL5[f('D')]
            if f('W'): self.put(c, self.get(r))
            else: self.put(r, self.get(c))
            return nxt
        if n == 'Movem_ea':
            addr, used = self.ea(f('M') << 3 | f('R'), ext)
            reg = REG6[f('d')]
            if f('W'): self.put(reg, self.rd('P', addr))
            else: self.wr('P', addr, self.get(reg))
            return pc + 1 + used
        if n in ('Add_xx', 'Sub_xx', 'Cmp_xxS2', 'Add_xxxx', 'Sub_xxxx', 'Cmp_xxxxS2', 'And_xxxx', 'Or_xxxx', 'And_xx', 'Or_xx'):
            D = 'AB'[f('d')]
            used = 1 if 'xxxx' in n else 0
            imm = ext if used else f('i')
            if n.startswith(('And', 'Or')):
                a1 = (self.acc[D] >> 24) & M24
                r = (a1 & imm) if n.startswith('And') else (a1 | imm)
                self.put(D + '1', r); self.ccr['N'] = r >> 23; self.ccr['Z'] = int(r == 0); self.ccr['V'] = 0
                return pc + 1 + used
            s = s24(imm) << 24 if used else imm << 24
            a = self.acc[D]
            if n.startswith('Add'): self.setacc(D, a + s)
            elif n.startswith('Sub'): self.setacc(D, a - s)
            else: self.flags(a - s, ovf=(s56(a - s) != a - s))
            return pc + 1 + used
        if n in ('Mpyi', 'Maci_xxxx'):
            D = 'AB'[f('d')]
            sreg = ['X0', 'Y0', 'X1', 'Y1'][f('q')]
            prod = (s24(ext) * s24(self.r[sreg])) << 1
            if f('k'): prod = -prod
            self.setacc(D, prod if n == 'Mpyi' else self.acc[D] + prod)
            return pc + 2
        if n in ('Asl_ii', 'Asr_ii'):
            S, D, i = 'AB'[f('S')], 'AB'[f('D')], f('i')
            v = self.acc[S] << i if n == 'Asl_ii' else self.acc[S] >> i
            self.setacc(D, v)
            return nxt
        if n in ('Lsl_ii', 'Lsr_ii'):
            D, i = 'AB'[f('D')], f('i')
            a1 = (self.acc[D] >> 24) & M24
            r = ((a1 << i) if n == 'Lsl_ii' else (a1 >> i)) & M24
            self.put(D + '1', r); self.ccr['N'] = r >> 23; self.ccr['Z'] = int(r == 0); self.ccr['V'] = 0
            return nxt
        if n in ('Lua_ea',):
            mm = f('M') << 3 | f('R')
            r = mm & 7
            m = mm >> 3
            R = self.R[r]
            v = {0: R - self.N[r], 1: R + self.N[r], 2: R - 1, 3: R + 1}[m]
            self.put(REG5[f('d')], v & M24)
            return nxt
        if n == 'Do_xxx':
            cnt = (f('h') << 8) | f('i')
            if cnt == 0: raise SimError('DO #0')
            self.loops.append([nxt + 1, ext, cnt])
            return nxt + 1
        if n == 'Do_S':
            cnt = self.get(REG6[f('D')], limit=False)
            if cnt == 0: raise SimError('DO with LC=0')
            self.loops.append([nxt + 1, ext, cnt])
            return nxt + 1
        if n == 'Rep_xxx':
            self.rep = (f('h') << 8) | f('i')
            return nxt
        if n in ('Andi', 'Ori'):
            return nxt   # MR/CCR mask bits: interrupts are not modelled
        if n == 'Enddo': self.loops.pop(); return nxt
        raise SimError('P:%06X %06X: %s not modelled' % (pc, w, n))

    # ---------------- step / run
    def step(self):
        pc = self.pc
        kind, o, alu, w = self.decode(pc)
        ext = self.P.get(pc + 1, 0)
        reps = 1
        if self.rep:
            reps, self.rep = self.rep, 0
        for _ in range(reps):
            self.icount += 1
            if kind == 'par':
                writes, used = self.pmove(o, w, ext) if o else ([], 0)
                if alu: self.alu(alu, w)
                self.apply(writes)
                npc = pc + 1 + used
            else:
                npc = self.one(o, w, ext, pc)
        # hardware loop end
        while self.loops and npc == self.loops[-1][1] + 1 and pc == self.loops[-1][1]:
            lp = self.loops[-1]
            if lp[2] > 1:
                lp[2] -= 1
                npc = lp[0]
            else:
                self.loops.pop()
            break
        self.pc = npc

    def run_audio(self, left, right, max_instr_per_frame=100000):
        """feed frames (L, R as Q23 ints); returns list of TX1 words (2 per frame) and max instructions per frame"""
        worst = 0
        for l, r in zip(left, right):
            self.inp += [(int(l), True), (int(r), False)]
            start = self.icount
            n_out = len(self.out)
            while len(self.out) < n_out + 2:
                self.step()
                if self.icount - start > max_instr_per_frame:
                    raise SimError('frame took > %d instructions (pc %06X)' % (max_instr_per_frame, self.pc))
            worst = max(worst, self.icount - start)
        return self.out, worst
