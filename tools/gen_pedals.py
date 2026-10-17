"""The PEDAL board's DSP pedals (DIRT, MOD, PHASER, WAH + the FX lab's delays / reverbs) -> firmware/mone_dev/pedals_dsp.h (the ESP's tables).
  py -3.10 tools/gen_pedals.py [pedal ...]

A pedal is just writes (no math on the ESP):
  pick a pedal  : its init writes (param block at the default knobs + start states), every knob table at the knob's
                  position, its curves (257 words each) and the kernel's FX id, all in one halt;
  move a knob   : that knob's table words (1-8 X writes).
Every param word belongs to one knob table (checked here); the two knob pairs that share one filter (Metal Zone
MIDDLE x MIDFREQ, Metal Muff TOP x BOOST) get one 2-D table, 21 x 21 (or 21 x 2 for a switch).
1-D knobs have 101 steps (position 0..100), 2-D tables 21 steps per knob; switches 2, mode buttons their count.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'dsp', 'model'))
import numpy as np  # noqa: E402
import dirt_model as dm  # noqa: E402
import dirt_ref as R  # noqa: E402
import mod_model as mm  # noqa: E402
import mod_ref as MR  # noqa: E402
import filt_model as fm  # noqa: E402
import filt_ref as FR  # noqa: E402
import fxlab_pedals as XP  # noqa: E402

FW = os.path.join(HERE, '..', 'firmware', 'mone_dev')
STEPS1, STEPS2 = 101, 21
FX_ID = {'dirt': 17, 'mod': 18, 'phaser': 19, 'wah': 20}       # ids agreed with the FX lab (VOCAL_ARCH.md); SPRING 21 has no P


class Engine:
    """adapter: pedal table, words(name, kn) -> {X address: int} (the knob-driven param block),
    extra(name) -> {X address: int} written once at a pick (start states), curves(name) -> {X address: [257]}"""
    def __init__(self, pedals, defaults, words, chain, extra=None, curves=None):
        self.pedals, self.defaults, self.words, self.chain = pedals, defaults, words, chain
        self.extra = extra or (lambda n: {})
        self.curves = curves or (lambda n: {})


def _dirt_words(n, kn):
    return {R.PAR + i: v for i, v in enumerate(R.ints(R.build(n, kn)[0]))}


def _dirt_curves(n):
    return {a: R.tab_ints(t) for a, t in R.build(n)[1].items()}


def _mod_words(n, kn):
    return {MR.PM + i: v for i, v in enumerate(MR.param_ints(MR.build(n, kn)[0]))}


DIRT_INITF, MOD_INITF = R.ST + 63, MR.SM + 31       # a pick writes 0: the engine re-inits (clears its tail)


def _mod_extra(n):
    si = MR.state_ints(MR.build(n)[1])
    out = {MR.SM + MR.S_V + 4 * v + k: si[MR.S_V + 4 * v + k] for v in range(2) for k in range(3)}
    out[MOD_INITF] = 0
    return out


def _filt_words(n, kn):
    base = FR.PP if fm.PEDALS[n]['fx'] == 'phaser' else FR.PW
    return {base + i: v for i, v in enumerate(FR.ints(FR.build(n, kn)))}


def _filt_extra(n):
    if fm.PEDALS[n]['fx'] == 'phaser':
        return {FR.PS + i: 0 for i in range(16)}
    out = {FR.WS + i: 0 for i in range(8)}
    out[FR.WS] = FR.ints(FR.build(n))[0]                       # the smoothed treadle starts where the treadle is
    return out


ENGINES = [
    Engine(dm.PEDALS, dm.knobs_default, _dirt_words, lambda n: [FX_ID['dirt']], lambda n: {DIRT_INITF: 0}, _dirt_curves),
    Engine(mm.PEDALS, mm.knobs_default, _mod_words, lambda n: [FX_ID['mod']], _mod_extra),
    Engine(fm.PEDALS, fm.knobs_default, _filt_words, lambda n: [FX_ID[fm.PEDALS[n]['fx']]], _filt_extra),
    Engine(XP.PEDALS, XP.knobs_default, XP.words, lambda n: XP.PEDALS[n]['chain']),      # the FX lab's engines
]


def engine_of(name):
    for e in ENGINES:
        if name in e.pedals:
            return e
    raise KeyError(name)


def steps_of(taper, two_d=False):
    if taper == 'S':
        return 2
    if taper.startswith('M'):
        return int(taper[1:])
    return STEPS2 if two_d else STEPS1


def words_at(name, kn):
    return engine_of(name).words(name, kn)


def knob_tables(name):
    """-> list of tables: dict(knobs=[i] or [i, j], steps=[..], addr=[X..], val=[[word..] per step (row-major)])"""
    e = engine_of(name)
    p = e.pedals[name]
    labels = [k[0] for k in p['knobs']]
    d = e.defaults(name)
    base = words_at(name, d)
    deps = []
    for lab, tp, _ in p['knobs']:
        ch = set()
        for x in np.linspace(0, 1, min(steps_of(tp), 11)):
            wv = words_at(name, {**d, lab: x})
            ch |= {a for a in base if wv[a] != base[a]}
        deps.append(ch)
    tabs, done = [], set()
    for i, lab in enumerate(labels):
        if i in done or not deps[i]:
            continue
        pair = [j for j in range(len(labels)) if j != i and deps[i] & deps[j]]
        assert len(pair) <= 1, (name, lab, 'shares words with more than one knob')
        if pair:
            j = pair[0]
            idx = sorted(deps[i] | deps[j])
            sw = [steps_of(p['knobs'][k][1], True) for k in (i, j)]
            val = []
            for a_ in range(sw[0]):
                for b_ in range(sw[1]):
                    wv = words_at(name, {**d, lab: a_ / (sw[0] - 1), labels[j]: b_ / (sw[1] - 1)})
                    val.append([wv[k] for k in idx])
            tabs.append(dict(knobs=[i, j], steps=sw, addr=idx, val=val))
            done |= {i, j}
        else:
            idx = sorted(deps[i])
            st = steps_of(p['knobs'][i][1])
            val = [[words_at(name, {**d, lab: s_ / (st - 1)})[k] for k in idx] for s_ in range(st)]
            tabs.append(dict(knobs=[i], steps=[st], addr=idx, val=val))
            done.add(i)
    return tabs


def cid(name):
    return ''.join(c if c.isalnum() else '_' for c in name).strip('_').lower()


HEADER = r'''// Generated by tools/gen_pedals.py from dsp/model/*_model.py + *_ref.py. Do not edit.
// A pedal = writes. Pick: the init writes (param block at the default knobs + start states), every table at its
// knobs' positions, the curves, then the kernel FX id. Knob move: its table(s).
// fx[0..nfx-1]: one id = SINGLE mode (X:$20 = 0, X:$21 = id), more = CHAIN (X:$20 = 3, X:$0200 = n, $0201.. ids).
// 1-D: val[step * nw + w], step = round(pos * (steps - 1) / 100). 2-D: val[(s0 * steps1 + s1) * nw + w].
// pos = 0..100; switches have 2 steps, mode knobs (Dimension D buttons) their count. Long X writes, 24-bit words.
#pragma once
#include <stdint.h>
struct PdTab { uint8_t nk; uint8_t k[2]; uint8_t steps[2]; uint8_t nw; const uint16_t *addr; const uint32_t *val; };
struct PdCurve { uint16_t addr; const uint32_t *val; };            // 257 words
struct PdKnob { const char *label; uint8_t def; uint8_t steps; };  // def = 0..100
struct PdDef { const char *name; uint32_t col; uint8_t nfx; uint8_t fx[3]; uint8_t ninit; const uint16_t *ia; const uint32_t *iv;
               uint8_t ncurve; const PdCurve *curve; uint8_t nk; const PdKnob *k; uint8_t ntab; const PdTab *tab; };
'''


def emit(names):
    out = [HEADER]
    defs = []
    total = 0
    for name in names:
        e = engine_of(name)
        c = cid(name)
        p = e.pedals[name]
        d = e.defaults(name)
        init = {**words_at(name, d), **e.extra(name)}
        ia = sorted(init)
        out.append('// ---- %s' % name)
        out.append('static const uint16_t pd_%s_ia[%d] = {%s};' % (c, len(ia), ', '.join('0x%04X' % a for a in ia)))
        out.append('static const uint32_t pd_%s_iv[%d] = {%s};' % (c, len(ia), ', '.join('0x%06X' % init[a] for a in ia)))
        cl = []
        for k, (addr, tv) in enumerate(sorted(e.curves(name).items())):
            out.append('static const uint32_t pd_%s_c%d[257] = {%s};' % (c, k, ', '.join('0x%06X' % v for v in tv)))
            cl.append('{0x%04X, pd_%s_c%d}' % (addr, c, k))
        out.append('static const PdCurve pd_%s_curve[] = {%s};' % (c, ', '.join(cl) if cl else '{0, 0}'))
        out.append('static const PdKnob pd_%s_k[] = {%s};' % (c, ', '.join(
            '{"%s", %d, %d}' % (lab, round(d[lab] * 100), steps_of(tp)) for lab, tp, _ in p['knobs'])))
        tl = []
        for t, tb in enumerate(knob_tables(name)):
            flat = [v for row in tb['val'] for v in row]
            total += 4 * len(flat)
            out.append('static const uint16_t pd_%s_t%d_a[] = {%s};' % (c, t, ', '.join('0x%04X' % a for a in tb['addr'])))
            out.append('static const uint32_t pd_%s_t%d_v[] = {%s};' % (c, t, ', '.join('0x%06X' % v for v in flat)))
            k2 = tb['knobs'] + [0] * (2 - len(tb['knobs']))
            s2 = tb['steps'] + [1] * (2 - len(tb['steps']))
            tl.append('{%d, {%d, %d}, {%d, %d}, %d, pd_%s_t%d_a, pd_%s_t%d_v}' % (
                len(tb['knobs']), k2[0], k2[1], s2[0], s2[1], len(tb['addr']), c, t, c, t))
        out.append('static const PdTab pd_%s_tab[] = {%s};' % (c, ', '.join(tl)))
        ch = e.chain(name)
        defs.append('  {"%s", 0x%06X, %d, {%s}, %d, pd_%s_ia, pd_%s_iv, %d, pd_%s_curve, %d, pd_%s_k, %d, pd_%s_tab},' % (
            name, p['colour'], len(ch), ', '.join(str(f) for f in ch + [0] * (3 - len(ch))), len(ia), c, c, len(cl), c,
            len(p['knobs']), c, len(tl), c))
        total += 6 * len(ia) + 4 * 257 * len(cl)
        print('%-14s fx %s: %d knobs, %d tables, %d curves, %d init writes' % (
            name, ch, len(p['knobs']), len(tl), len(cl), len(ia)))
    out += ['', 'static const PdDef PD_PEDALS[] = {'] + defs + ['};',
            'static const int PD_N = sizeof PD_PEDALS / sizeof PD_PEDALS[0];', '']
    path = os.path.join(FW, 'pedals_dsp.h')
    tmp = path + '.tmp'
    open(tmp, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
    os.replace(tmp, path)
    print('wrote %s (%d KB of tables)' % (path, total // 1024))


if __name__ == '__main__':
    emit(sys.argv[1:] or [n for e in ENGINES for n in e.pedals])
