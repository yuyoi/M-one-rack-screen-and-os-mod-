"""Amp sim option B: LSTM capture (GuitarML / Proteus style: 1 input, LSTM hidden H, dense out + input skip).

Answers two questions without a trained model:
  1. cost on the DSP56362 per hidden size H (budget 2112 cycles/frame at 93.1 MHz, 1 MAC/cycle internal),
  2. does 24-bit fixed point with table activations track float? (random weights at trained-model scale)
Weights are stored /8 (|w| < 8 fits Q23 after scaling; the 56-bit accumulators have 8 guard bits), the cell state /16,
sigmoid/tanh are 256-entry tables over +/-8 with linear interpolation (~8 cycles each).
  py -3.10 lstm_model.py
"""
import numpy as np
import amp_model as am

BUDGET = 2112
CS = 16                             # cell-state headroom: stored /16 (trained cells can exceed +/-4)
TBL = 256                           # activation table entries over +/-8 (linear interpolation)


def cycles(H, act=8):
    macs = 4 * H * (H + 1)          # gate pre-activations (input + recurrent + bias)
    elem = 4 * H                    # c = f*c + i*g ; h = o*tanh(c)
    return macs + 5 * H * act + elem + H + 30   # 5 activations per unit, dense out, glue


def run(x, W, U, b, Wd, fixed):
    H = U.shape[1]
    h = np.zeros(H); c = np.zeros(H)
    out = np.zeros_like(x)
    if fixed:
        q = lambda v, s=23: np.round(np.clip(v, -1, 1 - 2.0 ** -s) * 2 ** s) / 2 ** s
        grid = np.linspace(-8, 8, TBL + 1)
        tsig, ttanh = q(1 / (1 + np.exp(-grid))), q(np.tanh(grid))
        lut = lambda t, v: np.interp(np.clip(v, -8, 8), grid, t)
        W8, U8, b8, Wd8 = q(W / 8) * 8, q(U / 8) * 8, q(b / 8) * 8, q(Wd / 8) * 8
        for n in range(len(x)):
            z = W8[:, 0] * q(x[n]) + U8 @ h + b8
            i, f, g, o = lut(tsig, z[:H]), lut(tsig, z[H:2 * H]), lut(ttanh, z[2 * H:3 * H]), lut(tsig, z[3 * H:])
            c = q((f * c + i * g) / CS) * CS                # cell state kept /CS
            h = q(o * lut(ttanh, c))
            out[n] = q(Wd8 @ h + x[n])
    else:
        sig = lambda v: 1 / (1 + np.exp(-v))
        for n in range(len(x)):
            z = W[:, 0] * x[n] + U @ h + b
            i, f, g, o = sig(z[:H]), sig(z[H:2 * H]), np.tanh(z[2 * H:3 * H]), sig(z[3 * H:])
            c = f * c + i * g
            h = o * np.tanh(c)
            out[n] = np.clip(Wd @ h + x[n], -1, 1 - 2.0 ** -23)   # the DSP output saturates the same way
    return out


if __name__ == '__main__':
    print('LSTM cost per frame (budget %d):' % BUDGET)
    for H in (8, 10, 12, 16, 20, 40):
        c = cycles(H)
        print('  H=%2d  %5d cycles  %4.0f%%  weights %4d words%s' % (
            H, c, 100 * c / BUDGET, 4 * H * (H + 2) + H, '' if c < 0.8 * BUDGET else '  <- does not fit'))
    rng = np.random.default_rng(1)
    x = am.di_riff()[:am.FS // 2] * 4                        # 0.5 s of the test DI at a hot input level
    for H in (8, 12):
        W = rng.normal(0, 1.0, (4 * H, 1)); U = rng.normal(0, 1.5 / np.sqrt(H), (4 * H, H))
        b = rng.normal(0, 0.5, 4 * H); b[H:2 * H] += 1.0     # forget-gate bias like a trained model
        Wd = rng.normal(0, 0.5, H)
        yf, yq = run(x, W, U, b, Wd, False), run(x, W, U, b, Wd, True)
        print('  H=%d: 24-bit fixed + table activations vs float: %.0f dB SNR' % (
            H, 10 * np.log10(np.sum(yf ** 2) / np.sum((yf - yq) ** 2))))
