"""Pick a PEDAL-board sim from the PC (until the panel's PEDAL board knows them): builds the pick's X writes from the
same tables as firmware/mone_dev/pedals_dsp.h (tools/gen_pedals.py) and hands them to the FX lab's poke loader (tools/poke.py: table at X:$028000, stub at P:$0950, back into the kernel loop).

  py -3.10 tools/pedal_try.py list
  py -3.10 tools/pedal_try.py dry "TUBE SCREAMER" DRIVE=70 LEVEL=40      the writes, no hardware
  py -3.10 tools/pedal_try.py PORT "TUBE SCREAMER" DRIVE=70             (knobs 0..100; the rest at their defaults)

A pick = the init writes (param block + start states), every knob table at its position, the curves, INITF = 0 (the
engine re-inits on its next call), then the routing: one id = SINGLE (X:$20 = 0, X:$21 = id), more = CHAIN (X:$20 = 3, X:$0200 = n,
$0201.. = ids), written last so nothing plays half-written.
"""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_pedals as G  # noqa: E402

MODE, FX1, CH_N = 0x20, 0x21, 0x0200


def writes(name, pos=None):
    e = G.engine_of(name)
    p = e.pedals[name]
    labels = [k[0] for k in p['knobs']]
    d = e.defaults(name)
    kn = {**d, **{k: v / 100 for k, v in (pos or {}).items()}}
    for k in kn:
        assert k in labels, '%s has no knob %s (it has %s)' % (name, k, ' '.join(labels))
    out = dict(sorted({**e.words(name, d), **e.extra(name)}.items()))
    for tb in G.knob_tables(name):
        st = [round(kn[labels[k]] * (n - 1)) for k, n in zip(tb['knobs'], tb['steps'])]
        row = tb['val'][st[0] * tb['steps'][1] + st[1]] if len(st) == 2 else tb['val'][st[0]]
        out.update(zip(tb['addr'], row))
    last = {a: out.pop(a) for a in (G.DIRT_INITF, G.MOD_INITF) if a in out}   # INITF = 0 goes in last
    w = list(out.items())
    for addr, tv in sorted(e.curves(name).items()):
        w += [(addr + i, v) for i, v in enumerate(tv)]
    w += list(last.items())
    w += [(0x2F, 0), (0x3D, 0x7FFFFF)]          # output stage: all wet (dry gain 0, wet 1), like the board's pedals;
    ch = e.chain(name)                          # volume (POT1, X:$3C) and tone stay where the panel has them
    if len(ch) == 1:
        w += [(MODE, 0), (FX1, ch[0])]
    else:
        w += [(CH_N, len(ch))] + [(CH_N + 1 + i, f) for i, f in enumerate(ch)] + [(MODE, 3)]
    return w


def main():
    a = sys.argv[1:]
    if not a or a[0] == 'list':
        for e in G.ENGINES:
            for n, p in e.pedals.items():
                print('%-14s %s' % (n, ' '.join(k[0] for k in p['knobs'])))
        return
    port, name = a[0], a[1]
    pos = dict((kv.split('=')[0].upper(), float(kv.split('=')[1])) for kv in a[2:])
    w = writes(name, pos)
    if port == 'dry':
        for addr, v in w:
            print('X:$%06X = $%06X' % (addr, v))
        print('%d writes' % len(w))
        return
    import poke                                                    # the FX lab's loader (tools/poke.py)
    poke.poke(port, w, meter=False)
    print('%s: %d writes poked' % (name, len(w)))


if __name__ == '__main__':
    main()
