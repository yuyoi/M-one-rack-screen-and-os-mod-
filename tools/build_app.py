"""Rebuild the M-One app's P-memory image from YOUR flash dump and disassemble it.

    python tools/build_app.py dumps/m1_flash.bin  ->  dumps/app.lst   (never committed)

Flash format (see FLASH_MAP.md): a Mode-1 boot record at 0 (TC's loader), then [count][addr][words] records
(bytes, words little-endian) at the flash offsets listed in the loader table at P:$4D-$51.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dis56k import disasm  # noqa: E402

SECTIONS = (0x00000, 0x00B94, 0x08991, 0x105ED, 0x12AF5, 0x12B16)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'dumps', 'm1_flash.bin')
    d = open(path, 'rb').read()
    le = lambda o: d[o] | d[o + 1] << 8 | d[o + 2] << 16
    img = {}
    for o in SECTIONS:
        n, a = le(o), le(o + 3)
        for i in range(n):
            img[a + i] = le(o + 6 + 3 * i)
    addrs = sorted(img)
    blocks, s, p = [], addrs[0], addrs[0]
    for a in addrs[1:]:
        if a != p + 1:
            blocks.append((s, p))
            s = a
        p = a
    blocks.append((s, p))
    out = []
    for s, e in blocks:
        w = [img[a] for a in range(s, e + 1)]
        i = 0
        while i < len(w):
            try:
                t, n = disasm(w, i, s + i)
            except Exception as ex:  # keep going on odd data
                t, n = 'DC $%06X ; !%s' % (w[i], ex), 1
            out.append('P:%06X  %-14s %s' % (s + i, ' '.join('%06X' % x for x in w[i:i + n]), t))
            i += n
    dst = os.path.join(os.path.dirname(path), 'app.lst')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('blocks', ['P:%06X-%06X' % b for b in blocks], '->', dst, len(out), 'lines')


if __name__ == '__main__':
    main()
