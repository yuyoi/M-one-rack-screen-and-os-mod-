"""The 56 vocal presets (Desktop/tc_mone/VOCAL_PRESETS.md) as data: what the ESP writes to the DSP in one halt.

    py -3.10 presets.py            list: number, name, type, chain, estimated cycles
    py -3.10 presets.py json       the whole table as JSON (the ESP's presets.h is generated from it)

Each preset is a chain of effect ids run in CHAIN mode (X:$20 = 3, X:$0200 = n, X:$0201.. = ids), the STRIP input
stage on/off (X:$0207) with its params, and every used effect's param block. Key-dependent parts (TUNE's snap map,
diatonic HARMONY voices) are written for C and also carried as specs ('tune', 'harmony') so the ESP recomputes them
for the key/scale on its TUNE page. Tempo delays assume 120 BPM. "tone dark" in a note = turn the TONE pot down
(the pots stay live in every preset). Cycle estimates come from hardware measurements (tools/fxmeter.py).
"""
import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'model'))
import numpy as np  # noqa: E402
import radio_model as rm  # noqa: E402
import psola_dsp_model as pm  # noqa: E402
import harmony_model as hm  # noqa: E402
import reverb_model as rv  # noqa: E402
import delay_model as dm  # noqa: E402
import strip_model as sm  # noqa: E402
import grain_model as gm  # noqa: E402

M24 = 0xFFFFFF
CLEAN, HEAVY, REVERSE, COMP, TUNE, VOX, AMP, RADIO, FORMANT, OCTAVE, HARMONY, DOUBLER, REVERB, DELAY, SHIMMER, \
    SWELL, GRAIN = range(17)
NAMES = ['CLEAN', 'HEAVY', 'REVERSE', 'COMP', 'TUNE', 'VOX', 'AMP', 'RADIO', 'FORMANT', 'OCTAVE', 'HARMONY',
         'DOUBLER', 'REVERB', 'DELAY', 'SHIMMER', 'SWELL', 'GRAIN']
BASE = {RADIO: 0x0210, FORMANT: 0x0220, OCTAVE: 0x0230, HARMONY: 0x0240, DOUBLER: 0x0260, REVERB: 0x0280,
        DELAY: 0x0290, SHIMMER: 0x02A0, SWELL: 0x02B0, GRAIN: 0x02C0}
STRIP_BASE, STRIP_FLAG, CH_N, MODE = 0x0270, 0x0207, 0x0200, 0x20
TUNE_SPEED, SNAP = 0x0B, 0x23
# hardware cycles per frame (fxmeter, worst case): kernel, chain overhead per effect, effects (detector users add
# DET once: TUNE, FORMANT, OCTAVE, HARMONY share TUNE's pitch detector)
KERNEL, PER_FX, DET, STRIP_CY = 92, 35, 250, 150
CYC = {CLEAN: 0, HEAVY: 60, REVERSE: 80, COMP: 50, TUNE: 210, VOX: 200, AMP: 1680, RADIO: 520, FORMANT: 490,
       OCTAVE: 450, HARMONY: 470, DOUBLER: 155, REVERB: 470, DELAY: 190, SHIMMER: 420, SWELL: 45, GRAIN: 210}
DETECT = {TUNE, FORMANT, OCTAVE, HARMONY}
BUDGET = 1950

# ---------------------------------------------------------------- param builders
def radio(mode, wet=1.0, drive=1.0, noise=1.0):
    q = lambda v: int(round(min(v / 2, 1 - 1 / 2 ** 23) * 2 ** 23))
    return [rm.MODES.index(mode), q(2 * wet), q(drive), q(noise)]


def tune_speed(level):                                  # the ESP's TUNE page: 0..10, log-spaced
    return int(round(0.00005 * 400 ** (level / 10) * 2 ** 23))


def strip(gate=-50, deess=0.12, comp=0.25, mk=1.5, drive=0.0, eq=('flat', 0, 0)):
    kind, f, g = eq
    return sm.strip_params(gate, deess, comp, mk, drive, sm.eq_coefs(kind, f, g) if kind != 'flat' else None)


def reverb(kind, **kw):
    base = dict(ROOM=dict(size=0.35, decay=0.45, damp=0.35, pre_ms=5, wet=0.25),
                PLATE=dict(size=0.75, decay=0.65, damp=0.15, pre_ms=12, wet=0.3),
                HALL=dict(size=1.0, decay=0.82, damp=0.45, pre_ms=35, wet=0.35),
                SPRING=dict(size=0.3, decay=0.6, damp=0.05, pre_ms=2, wet=0.25))[kind]
    base.update(kw)
    return rv.params(**base)


def harmony(v1, v2, mix1=0.5, mix2=0.5, dry=0.8):
    """voices: ('dia', steps) = diatonic in the key (C here), ('st', n) = fixed semitones, None = off"""
    def mp(v):
        if v is None:
            return [0] * 12
        return hm.diatonic_map(v[1]) if v[0] == 'dia' else [v[1]] * 12
    return hm.harmony_params(mix1 if v1 else 0, mix2 if v2 else 0, dry, mp(v1), mp(v2))


# ---------------------------------------------------------------- the presets
P = []


def preset(n, name, typ, chain, strip_p=None, fx=None, tune=None, harm=None, note=''):
    P.append(dict(n=n, name=name, type=typ, chain=chain, strip=strip_p, fx=fx or {}, tune=tune, harmony=harm, note=note))


S_SOFT = strip(comp=0.3, mk=1.3)
S_STD = strip()
S_ROCK = strip(comp=0.2, mk=2.0, eq=('peak', 4000, 4))
S_GENTLE_AIR = strip(comp=0.3, mk=1.4, eq=('high', 10000, 4))
S_WARM = strip(comp=0.25, mk=1.6, drive=1.2, eq=('low', 150, 3))
S_HARD = strip(comp=0.12, mk=2.8)
S_CRUSH = strip(comp=0.1, mk=3.0, drive=2.0)

preset(1, 'LOFI VOCAL', 'LO-FI / RADIO', [RADIO, DOUBLER], S_SOFT,
       {RADIO: radio('CASSETTE', wet=0.8), DOUBLER: hm.doubler_params(12, 19, 6, 0.3, 0.35)}, note='tone dark')
preset(2, 'ROCK VOCAL', 'STUDIO', [DOUBLER, DELAY, REVERB], S_ROCK,
       {DOUBLER: hm.doubler_params(15, 25, 10, 0.35, 0.5), DELAY: dm.params(110, 0.0, 0.3, 0.7),
        REVERB: reverb('PLATE', size=0.55, decay=0.5, wet=0.2)})
preset(3, 'BALLAD VOX', 'STUDIO', [TUNE, DELAY, REVERB], S_GENTLE_AIR,
       {DELAY: dm.params(500, 0.35, 0.4, 0.5, duck=0.8), REVERB: reverb('PLATE', decay=0.75, wet=0.3)},
       tune=dict(speed=2, scale='key'))
preset(4, 'POP POLISH', 'STUDIO', [TUNE, DOUBLER, REVERB], S_STD,
       {DOUBLER: hm.doubler_params(14, 22, 6, 0.3, 0.3), REVERB: reverb('PLATE', size=0.6, decay=0.6)},
       tune=dict(speed=6, scale='key'))
preset(5, 'HARD TUNE', 'TUNE', [TUNE, DELAY, REVERB], S_STD,
       {DELAY: dm.params(110, 0.15, 0.25, 0.7), REVERB: reverb('ROOM')}, tune=dict(speed=10, scale='key'))
preset(6, 'CHOIR STACK', 'HARMONY', [HARMONY, DOUBLER, REVERB], None,
       {DOUBLER: hm.doubler_params(), REVERB: reverb('PLATE', decay=0.78, wet=0.35)},
       harm=dict(v1=('dia', 2), v2=('dia', 4), mix1=0.45, mix2=0.4, dry=0.8))
preset(7, 'GRUNGE DOUBLE', 'HARMONY', [OCTAVE, RADIO], S_CRUSH,
       {OCTAVE: pm.params(0.5, 1.0, wet=0.3), RADIO: radio('MEGAPHONE', wet=0.4, drive=0.6)})
preset(8, 'TELEPHONE INTRO', 'LO-FI / RADIO', [RADIO, DELAY], None,
       {RADIO: radio('TELEPHONE'), DELAY: dm.params(80, 0.0, 0.15, 0.6)})
preset(9, 'RIOT MEGAPHONE', 'LO-FI / RADIO', [RADIO, DELAY], None,
       {RADIO: radio('MEGAPHONE', drive=1.5), DELAY: dm.params(90, 0.1, 0.25, 0.6)})
preset(10, 'WALKIE TALKIE', 'LO-FI / RADIO', [RADIO], None, {RADIO: radio('WALKIE')})
preset(11, 'OLD RADIO', 'LO-FI / RADIO', [RADIO, REVERB], None,
       {RADIO: radio('AM RADIO'), REVERB: reverb('ROOM', wet=0.2)})
preset(12, 'DEMON', 'MONSTER', [FORMANT, OCTAVE, REVERB], None,
       {FORMANT: pm.params(1.0, 0.7), OCTAVE: pm.params(0.5, 1.0, wet=0.6),
        REVERB: reverb('HALL', decay=0.85, damp=0.6, wet=0.4)})
preset(13, 'GIANT', 'MONSTER', [FORMANT, OCTAVE, REVERB], None,
       {FORMANT: pm.params(1.0, 0.78), OCTAVE: pm.params(0.5, 1.0, wet=0.5), REVERB: reverb('HALL', size=1.0)})
preset(14, 'CHIPMUNK', 'MONSTER', [FORMANT], None, {FORMANT: pm.params(1.5, 1.35)})
preset(15, 'GENDER SWAP', 'MONSTER', [FORMANT], None, {FORMANT: pm.params(2 ** (5 / 12), 1.18)},
       note='M->F; for F->M set pitch -5, formant 0.85 on the EDIT page')
preset(16, 'DREAMGAZE', 'AMBIENT', [DOUBLER, REVERSE, REVERB, RADIO], None,
       {DOUBLER: hm.doubler_params(16, 28, 14, 0.25, 0.6), REVERB: reverb('PLATE', decay=0.8, wet=0.45),
        RADIO: radio('CASSETTE', wet=0.5)})
preset(17, 'RAP DOUBLE', 'HARMONY', [DOUBLER, OCTAVE], S_HARD,
       {DOUBLER: hm.doubler_params(10, 16, 4, 0.4, 0.7), OCTAVE: pm.params(0.5, 1.0, wet=0.2)})
preset(18, 'ARENA LEAD', 'STUDIO', [DOUBLER, DELAY, REVERB], S_STD,
       {DOUBLER: hm.doubler_params(16, 26, 10, 0.35, 0.5), DELAY: dm.params(375, 0.35, 0.3, 0.5),
        REVERB: reverb('HALL')})
preset(19, '50s SLAPBACK', 'STUDIO', [DELAY, REVERB], S_WARM,
       {DELAY: dm.params(120, 0.0, 0.4, 0.6), REVERB: reverb('SPRING')})
preset(20, 'MOTOWN ROOM', 'STUDIO', [REVERB], strip(comp=0.25, mk=1.6, drive=2.0, eq=('low', 150, 2)),
       {REVERB: reverb('ROOM', wet=0.3)})
preset(21, 'BEDROOM POP', 'LO-FI / RADIO', [RADIO, DOUBLER, REVERB], S_SOFT,
       {RADIO: radio('CASSETTE', wet=0.5), DOUBLER: hm.doubler_params(), REVERB: reverb('PLATE', size=0.5)})
preset(22, 'PODCAST VOICE', 'STUDIO', [CLEAN], strip(gate=-45, deess=0.1, comp=0.2, mk=2.0, eq=('peak', 4000, 2)))
preset(23, 'RADIO DJ', 'STUDIO', [CLEAN], strip(gate=-45, deess=0.1, comp=0.1, mk=3.0, eq=('low', 150, 5)))
preset(24, 'METAL SCREAM', 'MONSTER', [DOUBLER, OCTAVE, REVERB], strip(comp=0.12, mk=2.5, drive=2.5),
       {DOUBLER: hm.doubler_params(), OCTAVE: pm.params(0.5, 1.0, wet=0.15), REVERB: reverb('ROOM')})
preset(25, 'GROWL BOOST', 'MONSTER', [FORMANT, OCTAVE], strip(comp=0.15, mk=2.0, drive=2.0),
       {FORMANT: pm.params(1.0, 0.9), OCTAVE: pm.params(0.5, 1.0, wet=0.2)})
preset(26, 'ROBOT', 'TUNE', [TUNE, FORMANT, RADIO], None,
       {FORMANT: pm.params(1.0, 1.1), RADIO: radio('TELEPHONE', wet=0.5)}, tune=dict(speed=10, scale='chromatic'))
preset(27, 'ALIEN', 'MONSTER', [FORMANT, REVERB], None,
       {FORMANT: pm.params(2 ** (2 / 12), 1.6), REVERB: reverb('HALL')})
preset(28, 'GHOST WHISPER', 'AMBIENT', [REVERSE, FORMANT, REVERB], None,
       {FORMANT: pm.params(1.0, 1.12), REVERB: reverb('HALL', decay=0.88, wet=0.5)})
preset(29, 'CATHEDRAL', 'HARMONY', [HARMONY, REVERB], None, {REVERB: reverb('HALL', decay=0.9, wet=0.45)},
       harm=dict(v1=('st', 12), v2=None, mix1=0.3, dry=1.0))
preset(30, 'SHIMMER VOX', 'HARMONY', [HARMONY, REVERB], None, {REVERB: reverb('PLATE', decay=0.8, wet=0.4)},
       harm=dict(v1=('st', 12), v2=None, mix1=0.5, dry=0.9))
preset(31, 'GOSPEL STACK', 'HARMONY', [HARMONY, DOUBLER, REVERB], None,
       {DOUBLER: hm.doubler_params(), REVERB: reverb('PLATE')}, harm=dict(v1=('dia', 2), v2=('dia', 5)))
preset(32, 'BARBERSHOP', 'HARMONY', [HARMONY, DOUBLER, REVERB], None,
       {DOUBLER: hm.doubler_params(10, 16, 4, 0.3, 0.4), REVERB: reverb('ROOM')},
       harm=dict(v1=('dia', 2), v2=('dia', 4)))
preset(33, 'OCTAVE FOLK', 'HARMONY', [OCTAVE, REVERB], None,
       {OCTAVE: pm.params(0.5, 1.0, wet=0.4), REVERB: reverb('ROOM')})
preset(34, 'DRIVE-THRU', 'LO-FI / RADIO', [RADIO], None, {RADIO: radio('TELEPHONE', drive=1.8, noise=1.8)})
preset(35, 'VINYL 78', 'LO-FI / RADIO', [RADIO], None, {RADIO: radio('VINYL', noise=1.6)})
preset(36, 'UNDERWATER', 'AMBIENT', [DOUBLER, REVERB], None,
       {DOUBLER: hm.doubler_params(18, 30, 25, 0.15, 0.7), REVERB: reverb('HALL', damp=0.7)}, note='tone very dark')
preset(37, 'SPACE RADIO', 'LO-FI / RADIO', [RADIO, REVERB], None,
       {RADIO: radio('WALKIE', noise=1.6), REVERB: reverb('ROOM')})
preset(38, 'DEMON CHOIR', 'MONSTER', [HARMONY, FORMANT, REVERB], None,
       {FORMANT: pm.params(1.0, 0.75), REVERB: reverb('HALL', damp=0.6)},
       harm=dict(v1=('st', -12), v2=('st', -5), mix1=0.5, mix2=0.4, dry=0.6))
preset(39, 'HELIUM', 'MONSTER', [FORMANT], None, {FORMANT: pm.params(1.9, 1.5)})
preset(40, 'LIVE CLEAN', 'STUDIO', [CLEAN], strip(gate=-50, deess=0.12, comp=0.3, mk=1.5))
preset(41, 'INFINITE HALL', 'AMBIENT', [REVERB], None, {REVERB: reverb('HALL', decay=0.98, damp=0.6, wet=0.5)},
       note='tone dark; B3 = FREEZE')
preset(42, 'FREEZE PAD', 'AMBIENT', [REVERB], None, {REVERB: reverb('HALL', decay=0.9, wet=0.6)},
       note='B3 = FREEZE: hold a note, freeze, sing over it')
preset(43, 'SHIMMER CLOUD', 'AMBIENT', [SHIMMER, REVERB], None,
       {SHIMMER: hm.shimmer_params(0.4, 12), REVERB: reverb('HALL', decay=0.85, wet=0.45)})
preset(44, 'REVERSE SWELL', 'AMBIENT', [SWELL, REVERSE, REVERB], None,
       {SWELL: sm.swell_params(), REVERB: reverb('PLATE', decay=0.8, wet=0.45)})
preset(45, 'TAPE LOOP', 'AMBIENT', [RADIO, DELAY], None,
       {RADIO: radio('CASSETTE'), DELAY: dm.PRESETS['TAPE']})
preset(46, 'VIOLIN VOX', 'AMBIENT', [SWELL, DOUBLER, REVERB], None,
       {SWELL: sm.swell_params(ms=350), DOUBLER: hm.doubler_params(), REVERB: reverb('HALL')})
preset(47, 'SUBMARINE', 'AMBIENT', [OCTAVE, REVERB], None,
       {OCTAVE: pm.params(0.5, 1.0, wet=0.5), REVERB: reverb('HALL', decay=0.9, damp=0.7, wet=0.45)},
       note='tone very dark')
preset(48, 'ANGEL CHOIR', 'HARMONY', [HARMONY, FORMANT, REVERB], None,
       {FORMANT: pm.params(1.0, 1.1), REVERB: reverb('HALL', decay=0.9, wet=0.45)},
       harm=dict(v1=('st', 12), v2=('st', 7), mix1=0.45, mix2=0.35, dry=0.8))
preset(49, 'DUB ECHO', 'AMBIENT', [DELAY, REVERB], None,
       {DELAY: dm.params(375, 0.65, 0.4, 0.3), REVERB: reverb('SPRING')})
preset(50, 'GRAIN CLOUD', 'AMBIENT', [GRAIN, REVERB], None, {GRAIN: gm.params(), REVERB: reverb('PLATE', wet=0.4)})
preset(51, 'DISTANT MEMORY', 'AMBIENT', [RADIO, REVERSE, REVERB], None,
       {RADIO: radio('VINYL', wet=0.8), REVERB: reverb('HALL', wet=0.4)})
preset(52, 'ECHO CANYON', 'AMBIENT', [DELAY, REVERB], None, {DELAY: dm.PRESETS['MULTI'], REVERB: reverb('HALL')})
preset(53, 'SLOWDIVE WASH', 'AMBIENT', [DOUBLER, SHIMMER, REVERB, REVERSE], None,
       {DOUBLER: hm.doubler_params(16, 28, 18, 0.12, 0.6), SHIMMER: hm.shimmer_params(0.3, 12),
        REVERB: reverb('PLATE', decay=0.85, wet=0.5)})
preset(54, 'AURORA', 'AMBIENT', [HARMONY, DOUBLER, REVERB], None,
       {DOUBLER: hm.doubler_params(16, 28, 15, 0.15, 0.5), REVERB: reverb('HALL', decay=0.88, wet=0.45)},
       harm=dict(v1=('dia', 4), v2=('st', 12), mix1=0.35, mix2=0.3, dry=0.8), note='B3 = FREEZE')
preset(55, 'VOID', 'AMBIENT', [FORMANT, REVERB], None,
       {FORMANT: pm.params(1.0, 0.78), REVERB: reverb('HALL', decay=0.92, damp=0.7, wet=0.5)}, note='B3 = FREEZE')
preset(56, 'CRYSTAL CAVE', 'HARMONY', [HARMONY, REVERB, DELAY], None,
       {REVERB: reverb('PLATE', size=0.5, damp=0.05), DELAY: dm.params(300, 0.35, 0.3, 0.8)},
       harm=dict(v1=('st', 12), v2=('st', 19), mix1=0.4, mix2=0.3, dry=0.8))
assert [p['n'] for p in P] == list(range(1, 57))


# ---------------------------------------------------------------- writes / cost
def writes(p):
    """(address, 24-bit value) pairs for one preset, in one halt"""
    w = [(MODE, 3), (CH_N, len(p['chain']))] + [(CH_N + 1 + i, fx) for i, fx in enumerate(p['chain'])]
    w.append((STRIP_FLAG, 1 if p['strip'] else 0))
    if p['strip']:
        w += [(STRIP_BASE + i, v & M24) for i, v in enumerate(p['strip'])]
    fx = dict(p['fx'])
    if HARMONY in p['chain']:
        hcfg = p['harmony']
        fx[HARMONY] = harmony(hcfg['v1'], hcfg.get('v2'), hcfg.get('mix1', 0.5), hcfg.get('mix2', 0.5),
                              hcfg.get('dry', 0.8))
    for fid, prm in sorted(fx.items()):
        w += [(BASE[fid] + i, v & M24) for i, v in enumerate(prm)]
    if p['tune']:
        w.append((TUNE_SPEED, tune_speed(p['tune']['speed'])))
        scale = p['tune']['scale']
        steps = range(12) if scale == 'chromatic' else (0, 2, 4, 5, 7, 9, 11)
        for pc in range(12):
            d = next(d for d in (0, -1, 1, -2, 2) if (pc + d) % 12 in steps)
            w.append((SNAP + pc, d & M24))
    return w


def cycles(p):
    c = KERNEL + PER_FX * len(p['chain']) + (STRIP_CY if p['strip'] else 0)
    c += sum(CYC[f] for f in p['chain'])
    if DETECT & set(p['chain']):
        c += DET
    return c


def check():
    for p in P:
        ids = set(p['chain'])
        assert not (ids & {HARMONY} and ids & {SHIMMER}), p['name']        # they share a ring
        assert not (ids & {GRAIN} and ids & {REVERSE}), p['name']          # they share a buffer
        assert len(p['chain']) <= 6 and len(ids) == len(p['chain']), p['name']
        assert cycles(p) <= BUDGET, '%s: ~%d cycles' % (p['name'], cycles(p))


check()
if __name__ == '__main__':
    if 'json' in sys.argv[1:]:
        out = [dict(n=p['n'], name=p['name'], type=p['type'], chain=[NAMES[f] for f in p['chain']],
                    strip=bool(p['strip']), tune=p['tune'], harmony=p['harmony'], note=p['note'],
                    writes=[['%04X' % a, '%06X' % v] for a, v in writes(p)]) for p in P]
        print(json.dumps(out, indent=1))
    else:
        for p in P:
            print('%2d %-15s %-13s %-34s %s ~%4d cyc  %d writes' % (
                p['n'], p['name'], p['type'], ' > '.join(NAMES[f] for f in p['chain']),
                'S' if p['strip'] else ' ', cycles(p), len(writes(p))))
