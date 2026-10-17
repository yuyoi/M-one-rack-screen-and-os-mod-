"""FILTER pedals: PHASER (effect 19: Phase 90) and WAH (effect 20: Cry Baby, Reso Wah). Knobs -> physical settings;
filt_ref.py makes the Q23 words and mirrors the DSP.

PHASE 90: four JFET all-pass stages (47n caps), one LFO. A JFET in its triode region is a resistor ~ R0 / (1 - Vgs/Vp),
so the stages' break frequency moves LINEARLY with the LFO voltage (not exponentially): ~90 Hz .. 2.4 kHz here. The
script-logo unit has less feedback around the chain than the block-logo one. Out = (dry + chain) / 2.
WAH: the Cry Baby's inductor tank as a resonant state-variable band-pass, swept ~350 Hz (heel) .. 2.2 kHz (toe), Q
rising toward the toe (~3 -> 6); a little low-pass leaks through like the real circuit. The treadle (a pot here) is
smoothed on the DSP (15 ms), so the ESP's 10 Hz knob writes never zipper. Reso Wah = the same with a high Q.
"""
import numpy as np

FS = 44100


def logmap(x, lo, hi):
    return lo * (hi / lo) ** min(max(x, 0.0), 1.0)


PEDALS = {}


def pedal(name, fx, knobs, colour):
    def reg(f):
        PEDALS[name] = dict(fx=fx, knobs=knobs, voice=f, colour=colour, src=f)
        return f
    return reg


def knobs_default(name):
    return {l: d for l, _, d in PEDALS[name]['knobs']}


def ap_coef(f):
    t = np.tan(np.pi * np.asarray(f, float) / FS)
    return (t - 1) / (t + 1)


@pedal('PHASE 90', 'phaser', [('SPEED', 'B', 0.35), ('BLOCK', 'S', 0.0)], 0xF26B1D)
def phase90(k):
    fmin, fmax = 90.0, 2400.0
    tri = np.linspace(-1, 1, 201)
    a = ap_coef(fmin + (fmax - fmin) * (tri + 1) / 2)
    c = np.polyfit(tri, a, 3)[::-1]                          # a(lfo) = c0 + c1 l + c2 l^2 + c3 l^3
    return dict(hz=logmap(k['SPEED'], 0.1, 8.0), coef=c, fb=0.55 if k['BLOCK'] >= 0.5 else 0.25,
                dry=0.5, wet=0.5)


def wah(fc0, fc1, q0, q1, lp_leak, gain):
    p = np.linspace(0, 1, 201)
    fc = fc0 * (fc1 / fc0) ** p
    f = 2 * np.sin(np.pi * fc / FS)                          # Chamberlin SVF frequency coefficient
    qq = 1 / (q0 + (q1 - q0) * p)                            # damping 1/Q
    return dict(fpoly=np.polyfit(p, f, 3)[::-1], qpoly=np.polyfit(p, qq, 2)[::-1], leak=lp_leak, gain=gain,
                smooth=1 - np.exp(-1 / (0.015 * FS)))


@pedal('CRYBABY', 'wah', [('PEDAL', 'B', 0.5)], 0x1A1A1A)
def crybaby(k):
    return dict(pos=k['PEDAL'], **wah(350, 2200, 3.0, 6.0, 0.15, 1.0))


@pedal('RESO WAH', 'wah', [('PEDAL', 'B', 0.5), ('RES', 'B', 0.5)], 0xB2163C)
def resowah(k):
    q = 6 + 12 * k['RES']
    return dict(pos=k['PEDAL'], **wah(300, 2600, q * 0.8, q, 0.08, 0.8))
