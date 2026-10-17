"""MOD (effect 18): modulated-delay pedals on one engine: CE-2 chorus, Dimension D, BF-2 flanger, TR-2 tremolo,
Leslie 122. Knobs -> physical settings (ms, Hz, gains) here; mod_ref.py turns them into Q23 words and mirrors the DSP.

Engine per 44.1 kHz sample:
  [drive: cubic soft clip, the Leslie's tube preamp] -> split biquad LP (BBD input filter / Leslie 800 Hz crossover)
  ring A <- KA * x + KL * lp + FB * voice-0 read  (512 words, 11.6 ms: BBD line / horn)   ring B <- lp (64: drum)
  2 voices: LFO (triangle, or sine for a rotor) with a ramped rate (rotor inertia), delay = BASE + DEPTH * lfo read
            with linear interpolation, AM by a second LFO tap (phase + AOFF: the rotor's cos), WG squares it (TR-2 WAVE)
  out = DRY * x + post biquad (BBD output filter / cabinet) of the voice sum, * OUT.
BBD clock noise and companders are left out (CE-2 has no compander; the BBD filters are the 2-pole LPs).
"""
import numpy as np

FS = 44100
RA, RB = 512, 64                 # ring sizes (samples)


class Voice:
    def __init__(self, hz=0.5, ramp_s=0.0, base_ms=5.0, depth_ms=0.0, wet=0.0, am=0.0, sine=False, aoff=0.0,
                 wave=1.0, ring='A', phase=0.0):
        self.hz, self.ramp_s, self.base_ms, self.depth_ms, self.wet = hz, ramp_s, base_ms, depth_ms, wet
        self.am, self.sine, self.aoff, self.wave, self.ring, self.phase = am, sine, aoff, wave, ring, phase


class ModVoicing:
    def __init__(self, voices, split=('lp', 7000, 0.6), ka=0.0, kl=1.0, fb=0.0, dry=1.0, post=('lp', 7000, 0.6),
                 out=1.0, drive=0.0):
        self.voices, self.split, self.ka, self.kl, self.fb, self.dry = voices, split, ka, kl, fb, dry
        self.post, self.out, self.drive = post, out, drive


PEDALS = {}


def pedal(name, knobs, colour):
    def reg(f):
        PEDALS[name] = dict(knobs=knobs, voice=f, colour=colour, src=f)
        return f
    return reg


def knobs_default(name):
    return {l: d for l, _, d in PEDALS[name]['knobs']}


def logmap(x, lo, hi):
    return lo * (hi / lo) ** min(max(x, 0.0), 1.0)


@pedal('CE-2', [('RATE', 'B', 0.35), ('DEPTH', 'B', 0.6)], 0x3B8ED8)
def ce2(k):
    # MN3007 BBD, ~4.5 ms centre, triangle LFO 0.1-7 Hz, swing up to +-2.5 ms, 2-pole BBD filters ~6 kHz, 1:1 mix
    v = Voice(hz=logmap(k['RATE'], 0.1, 7.0), base_ms=4.5, depth_ms=2.5 * k['DEPTH'], wet=1.0)
    return ModVoicing([v], split=('lp', 6000, 0.6), post=('lp', 6000, 0.6), dry=1.0, out=0.5)


DIM_MODES = [(0.25, 0.35), (0.25, 0.7), (0.25, 1.05), (0.5, 1.05)]   # (Hz, swing ms) for buttons 1-4 (~ SDD-320)


@pedal('DIMENSION D', [('MODE', 'M4', 0.0)], 0x9FB8C8)
def dimd(k):
    # two BBD lines, antiphase triangle LFOs, ~3.2 ms centre; mono out = dry + both wets (the antiphase pitch
    # wobble mostly cancels in the sum, which is the point of the box)
    hz, sw = DIM_MODES[min(int(k['MODE'] * 3 + 0.5), 3)]
    vs = [Voice(hz=hz, base_ms=3.2, depth_ms=sw, wet=0.7, phase=p) for p in (0.0, 1.0)]
    return ModVoicing(vs, split=('lp', 8000, 0.6), post=('lp', 8000, 0.6), dry=1.0, out=0.42)


@pedal('FLANGER', [('MANUAL', 'B', 0.5), ('DEPTH', 'B', 0.6), ('RATE', 'B', 0.3), ('RES', 'B', 0.5)], 0x7A3FA0)
def bf2(k):
    # BF-2: MN3207, MANUAL = centre 0.5-6 ms, DEPTH = sweep (fraction of centre), RATE 0.1-8 Hz, RES = regen 0-0.9
    c = logmap(k['MANUAL'], 0.5, 6.0)                              # ring A holds 11.6 ms: centre + sweep fit
    v = Voice(hz=logmap(k['RATE'], 0.1, 8.0), base_ms=c, depth_ms=c * 0.9 * k['DEPTH'], wet=1.0)
    return ModVoicing([v], split=('lp', 9000, 0.6), post=('lp', 9000, 0.6), fb=0.9 * k['RES'], dry=1.0, out=0.5)


@pedal('TREMOLO', [('RATE', 'B', 0.4), ('WAVE', 'B', 0.3), ('DEPTH', 'B', 0.7)], 0x2E9E6B)
def tr2(k):
    # TR-2: RATE 1-10 Hz, WAVE = triangle -> square (the LFO driven into a clip), DEPTH = AM depth
    v = Voice(hz=logmap(k['RATE'], 1.0, 10.0), base_ms=0.0, depth_ms=0.0, wet=1.0, am=k['DEPTH'],
              wave=1 + 7 * k['WAVE'] ** 2)
    return ModVoicing([v], split=('lp', 18000, 0.7), ka=1.0, kl=0.0, post=None, dry=0.0, out=1.0)


@pedal('LESLIE', [('SPEED', 'S', 0.0), ('DEPTH', 'B', 0.7), ('DRIVE', 'B', 0.2)], 0x8B5A2B)
def leslie(k):
    # 122: horn 0.83 / 6.75 Hz, drum 0.67 / 5.83 Hz, horn spins up in ~0.7 s, the drum in ~4 s; 800 Hz crossover;
    # Doppler = rotor radius / c (horn 0.15 m -> +-0.44 ms, drum +-0.6 ms), AM horn ~6 dB, drum ~3 dB (x DEPTH)
    fast = k['SPEED'] >= 0.5
    d = k['DEPTH']
    horn = Voice(hz=6.75 if fast else 0.83, ramp_s=0.7, base_ms=0.7, depth_ms=0.44 * d, wet=1.0, am=0.5 * d,
                 sine=True, aoff=0.5, ring='A')
    drum = Voice(hz=5.83 if fast else 0.67, ramp_s=4.0, base_ms=0.7, depth_ms=0.6 * d, wet=1.0, am=0.3 * d,
                 sine=True, aoff=0.5, ring='B', phase=0.3)
    return ModVoicing([horn, drum], split=('lp', 800, 0.7), ka=1.0, kl=-1.0, post=('lp', 7000, 0.7), dry=0.0,
                      out=0.8, drive=0.25 + 3.0 * k['DRIVE'] ** 2)
