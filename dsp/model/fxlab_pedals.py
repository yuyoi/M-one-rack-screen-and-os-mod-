"""The board's delay and reverb pedals: the FX lab's own engines (REVERB 12, DELAY 13, SHIMMER 14, SWELL 15) with
pedal knobs. No DSP code here: every knob is a table of those engines' param words (reverb_model.params,
delay_model.params, harmony_model.shimmer_params, strip_model.swell_params), and a pedal that needs two engines
runs them as a CHAIN (X:$20 = 3, X:$0200 = n, X:$0201.. = ids).

Space Echo is the DELAY's TAPE mode (wow, saturation, dark repeats); its heads are approximated by the time
multiplier of the MODE knob (head 1 / 2 / 3, and 1+3 / 2+3 with the DELAY's tap mode) until the FX lab's DELAY gets
a real 3-head mode (FX lab: HEADS param, coming). Its spring is a small bright REVERB after the DELAY: SPRING
(effect 21) is built but has no P RAM (sim only), so the SPRING pedal is the same REVERB stopgap.
"""
import numpy as np
import reverb_model as rv
import delay_model as dl
import harmony_model as hm
import strip_model as sm

REVERB, DELAY, SHIMMER, SWELL = 12, 13, 14, 15
ADDR = {REVERB: 0x0280, DELAY: 0x0290, SHIMMER: 0x02A0, SWELL: 0x02B0}
PEDALS = {}


def lin(x, lo, hi):
    return lo + (hi - lo) * min(max(x, 0.0), 1.0)


def logmap(x, lo, hi):
    return lo * (hi / lo) ** min(max(x, 0.0), 1.0)


def pedal(name, chain, knobs, colour):
    def reg(f):
        PEDALS[name] = dict(chain=chain, knobs=knobs, voice=f, colour=colour, src=f)
        return f
    return reg


def knobs_default(name):
    return {l: d for l, _, d in PEDALS[name]['knobs']}


def words(name, kn=None):
    """-> {X address: 24-bit int} for every engine in the pedal's chain"""
    blocks = PEDALS[name]['voice']({**knobs_default(name), **(kn or {})})
    out = {}
    for fx, vals in blocks.items():
        for i, v in enumerate(vals):
            out[ADDR[fx] + i] = int(v) & 0xFFFFFF
    return out


REV_K = [('DECAY', 'B', 0.5), ('TONE', 'B', 0.5), ('PRE-DLY', 'B', 0.3), ('LEVEL', 'B', 0.5)]


def room(k, size, dec, damp, pre, wet):
    """DECAY / TONE / PRE-DLY / LEVEL over a space's ranges: (lo, hi) each; TONE = damping (lo = dark)"""
    return {REVERB: rv.params(size=size, decay=lin(k['DECAY'], *dec), damp=lin(k['TONE'], *damp),
                              pre_ms=lin(k['PRE-DLY'], *pre), wet=lin(k['LEVEL'], *wet))}


@pedal('HALL/PLATE', [REVERB], REV_K, 0x5B6EE1)
def hallplate(k):
    return room(k, 0.75, (0.35, 0.88), (0.6, 0.08), (0, 60), (0, 0.6))


@pedal('CATHEDRAL', [REVERB], REV_K, 0xC9B037)
def cathedral(k):
    return room(k, 1.0, (0.6, 0.95), (0.65, 0.25), (15, 90), (0, 0.6))


@pedal('CHURCH', [REVERB], REV_K, 0x8C5A3C)
def church(k):
    return room(k, 0.9, (0.5, 0.9), (0.8, 0.4), (10, 60), (0, 0.6))                # warm: always a bit dark


@pedal('STAGE', [REVERB], REV_K, 0x3C8C7A)
def stage(k):
    return room(k, 0.5, (0.3, 0.75), (0.55, 0.1), (0, 35), (0, 0.55))


@pedal('CAVE', [DELAY, REVERB], [('DECAY', 'B', 0.6), ('ECHO', 'B', 0.4), ('TONE', 'B', 0.4), ('LEVEL', 'B', 0.5)],
       0x4A4A5A)
def cave(k):
    # wet rock walls: a long dark slap (the DELAY, 230 ms, some feedback) into a big damped room
    r = rv.params(size=1.0, decay=lin(k['DECAY'], 0.55, 0.92), damp=lin(k['TONE'], 0.85, 0.35), pre_ms=25,
                  wet=lin(k['LEVEL'], 0, 0.6))
    d = dl.params(230, fb=lin(k['ECHO'], 0, 0.55), wet=lin(k['ECHO'], 0, 0.45), tone=lin(k['TONE'], 0.25, 0.6))
    return {DELAY: d, REVERB: r}


@pedal('AMBIENT', [SWELL, REVERB], [('DECAY', 'B', 0.7), ('SWELL', 'B', 0.5), ('TONE', 'B', 0.5),
                                    ('LEVEL', 'B', 0.6)], 0x7FA7C9)
def ambient(k):
    # near-freeze wash: SWELL fades each note in (50 ms .. 1.5 s), the hall holds it (decay up to 0.985)
    r = rv.params(size=1.0, decay=lin(k['DECAY'], 0.8, 0.985), damp=lin(k['TONE'], 0.7, 0.15), pre_ms=30,
                  wet=lin(k['LEVEL'], 0, 0.7))
    return {SWELL: sm.swell_params(-45, logmap(k['SWELL'], 50, 1500)), REVERB: r}


@pedal('SHIMMER', [SHIMMER, REVERB], [('DECAY', 'B', 0.6), ('SHIMMER', 'B', 0.4), ('TONE', 'B', 0.5),
                                      ('LEVEL', 'B', 0.5)], 0xE0D0FF)
def shimmer(k):
    r = rv.params(size=1.0, decay=lin(k['DECAY'], 0.6, 0.93), damp=lin(k['TONE'], 0.6, 0.1), pre_ms=20,
                  wet=lin(k['LEVEL'], 0, 0.6))
    return {SHIMMER: hm.shimmer_params(lin(k['SHIMMER'], 0, 0.6), 12), REVERB: r}


@pedal('SPRING', [REVERB], [('DWELL', 'B', 0.5), ('TONE', 'B', 0.5), ('MIX', 'B', 0.4)], 0xA7B8A0)
def spring(k):
    # STOPGAP: SPRING (effect 21, the dispersive two-spring model) is built but has no P RAM; a small bright REVERB
    return {REVERB: rv.params(size=0.3, decay=lin(k['DWELL'], 0.4, 0.8), damp=lin(k['TONE'], 0.4, 0.02), pre_ms=2,
                              wet=lin(k['MIX'], 0, 0.6))}


@pedal('SLAPBACK', [DELAY], [('TIME', 'B', 0.4), ('LEVEL', 'B', 0.5)], 0xD94F2B)
def slapback(k):
    # 50s tape slap: one dark, slightly saturated repeat, 60-180 ms
    return {DELAY: dl.params(lin(k['TIME'], 60, 180), fb=0.08, wet=lin(k['LEVEL'], 0, 0.7), tone=0.55, sat=1)}


@pedal('DIGITAL DLY', [DELAY], [('LEVEL', 'B', 0.4), ('FEEDBACK', 'B', 0.35), ('TIME', 'B', 0.45)], 0xE8E8E8)
def digital(k):
    # DD-3 style: clean repeats, 20-720 ms (the DELAY's ring holds ~740 ms)
    return {DELAY: dl.params(logmap(k['TIME'], 20, 720), fb=lin(k['FEEDBACK'], 0, 0.85),
                             wet=lin(k['LEVEL'], 0, 0.7), tone=0.95)}


SE_HEADS = [(1, 0), (2, 0), (3, 0), (3, 1), (2, 1)]            # (head, tap mode) for MODE 1-5 (~ RE-201 selector)


@pedal('SPACE ECHO', [DELAY, REVERB], [('MODE', 'M5', 0.0), ('RATE', 'B', 0.5), ('INTENSITY', 'B', 0.45),
                                       ('ECHO', 'B', 0.5), ('REVERB', 'B', 0.3), ('TONE', 'B', 0.4)], 0x2F6B3A)
def spaceecho(k):
    # RE-201: RATE = tape speed (head 1 at ~60-190 ms), INTENSITY = feedback (self-oscillates near the top), ECHO =
    # level, REVERB = the spring's level, TONE = treble of the repeats; wow + tape saturation always on
    head, taps = SE_HEADS[min(int(k['MODE'] * 4 + 0.5), 4)]
    t1 = lin(1 - k['RATE'], 60, 190)
    spring = rv.params(size=0.3, decay=0.55, damp=lin(k['TONE'], 0.4, 0.05), pre_ms=2, wet=lin(k['REVERB'], 0, 0.5))
    return {DELAY: dl.params(min(t1 * head, 720), fb=lin(k['INTENSITY'], 0, 0.95), wet=lin(k['ECHO'], 0, 0.7),
                             tone=lin(k['TONE'], 0.2, 0.6), wow=6, sat=1, taps=taps, wow_hz=0.9), REVERB: spring}
