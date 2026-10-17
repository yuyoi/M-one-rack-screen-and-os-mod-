"""Pixel-art sprites for the panel (up to 24x24, Castlevania / PS1 style) -> firmware/mone_dev/sprites.h.
py -3.10 tools/gen_sprites.py [preview.png]  writes the header and, with a path, an 8x preview sheet.
Each sprite: rows of equal length (up to 24x24); '.' = transparent, every other char a palette key. In a palette,
the colour None means "the tint" (the firmware passes it, e.g. the current pedal's colour): 'P' = tint, 'Q' = darker,
'q' = lighter."""
import os
import sys

K = 0x140C18                                        # outline
SPRITES = {                                         # doom / church / metal set
    'SKULL': ({'k': K, 'b': 0xE8DCC0, 'B': 0xA89878, 'h': 0x2A2228, 'H': 0x6A5A50, 'r': 0xFF2010,
               'R': 0x801008}, [
        'k..................k',
        'kk................kk',
        'kHk..............kHk',
        'kHhk............khHk',
        '.kHhk...kkkk...khHk.',
        '.kHhhk.kbbbbk.khhHk.',
        '..kHhhkbbbbbbkhhHk..',
        '...kkkbbbbbbbbkkk...',
        '....kbbbbbbbbbbBk...',
        '....kbkkkbbkkkbBk...',
        '....kbkrRkkRrkbBk...',
        '....kbkRRkbkRRkBk...',
        '....kbbkkbbbkkbBk...',
        '.....kbbbbkbbbBk....',
        '.....kBbbbbbbbBk....',
        '......kbkbkbkbk.....',
        '......kbkbkbkbk.....',
        '.......kkkkkkk......',
        '....................',
        '....................']),
    'TOME': ({'k': K, 'L': 0x2C2834, 'l': 0x1A161E, 'i': 0x8890A0, 'I': 0x50586A, 'g': 0xFFCC00, 'G': 0xB08000,
              'p': 0xE8DCC0, 'P': 0xA89878, 'r': 0xC01010}, [
        '....................',
        '..kkkkkkkkkkkkkkkk..',
        '..kiiLLLLLLLLiipPk..',
        '..kiLLLLLLLLLLipPk..',
        '..kLLLLLggLLLLLpPk..',
        '..kLLlLLgGLLlLLpPk..',
        '..kLLLggggggLLLpPk..',
        '..kLLLGGgGGGLLLpPk..',
        '..kLLLLLgGLLLLLpPk..',
        '..kLlLLLgGLLLlLpPk..',
        '..kLLLLLgGLLLLLpPk..',
        '..kLLLLLgGLLLLLpPk..',
        '..kLLlLLgGLLlLLpPk..',
        '..kLLLLLGGLLLLLpPk..',
        '..kiLLLLLLLLLLipPk..',
        '..kiiLLLLLLLLiipPk..',
        '..kkkkkkkkkkkkkPPk..',
        '...kkkkkkkrkkkkkk...',
        '..........r.........',
        '.........r.r........']),
    'COFFIN': ({'k': K, 'P': None, 'Q': None, 'q': None, 's': 0xD8D8E0, 'S': 0x808088, 'n': 0x303034}, [
        '....kkkkkk....',
        '...kqqqqPQk...',
        '..kqPPPPPPQk..',
        '.kqPPPssPPPQk.',
        'kqnPPPssPPPnQk',
        'kqPPssssssPPQk',
        'kqPPSSssSSPPQk',
        'kqPPPPssPPPPQk',
        'kqPPPPssPPPPQk',
        '.kqPPPssPPPQk.',
        '.kqPPPSSPPPQk.',
        '.kqPPPPPPPPQk.',
        '..kqPPPPPPQk..',
        '..kqPPPPPPQk..',
        '..kqnPPPPnQk..',
        '..kqPPPPPPQk..',
        '...kqPPPPQk...',
        '...kqPPPPQk...',
        '...kQQQQQQk...',
        '....kkkkkk....']),
    'BELL': ({'k': K, 'b': 0xC88838, 'B': 0x7A4A18, 'h': 0xF0C070, 'c': 0x302820, 'w': 0x6A4020,
              'y': 0xFFCC00}, [
        '........kkkk........',
        '.......kwwwwk.......',
        '........kwwk........',
        '......kkkbbkkk......',
        '.....khhbbbbbBk.....',
        '....khhbbbbbbbBk....',
        '....khbbbbbbbbBk....',
        '....khbbbbbbbbBk....',
        '..y.khbbbbbbbbBk.y..',
        '....khbbbbbbbbBk....',
        '.y..khbbbbbbbbBk..y.',
        '....khbbbbbbbbBk....',
        '...khbbbbbbbbbbBk...',
        '..khhbbbbbbbbbbbBk..',
        '.khhbbbbbbbbbbbbbBk.',
        'kBBBBBBBBBBBBBBBBBBk',
        '.kkkkkkkkkkkkkkkkkk.',
        '.........kck........',
        '.........kck........',
        '..........k.........']),
    'HALO': ({'k': K, 'w': 0xF0ECE0, 'W': 0xA8B0C8, 'y': 0xFFCC00, 'Y': 0xFFF0A0}, [
        '......kkkkkkkk......',
        '.....kyyyyyyyyk.....',
        '....kyk......kyk....',
        '.....kyyyyyyyyk.....',
        '......kkkkkkkk......',
        '.kk..............kk.',
        'kwwk............kwwk',
        'kwwwk..........kwwwk',
        'kwWwwk...kk...kwwWwk',
        '.kwWwwk.kyyk.kwwWwk.',
        '.kwwWwwkyYYykwwWwwk.',
        '..kwwWwkyYYykwWwwk..',
        '...kwwWwkyykwWwwk...',
        '....kwwwWkkWwwwk....',
        '.....kkwwwwwwwkk....',
        '.......kkkkkkk......',
        '....................',
        '....................',
        '....................',
        '....................']),
    'DEMON': ({'k': K, 'R': 0xC01810, 'D': 0x601008, 'y': 0xFFCC00, 'w': 0xF0ECE0, 'h': 0x2A2228,
               'H': 0x6A5A50}, [
        'k..................k',
        'kk................kk',
        'kHk..............kHk',
        'kHhk............khHk',
        '.kHhk...kkkk...khHk.',
        '.kHhhk.kRRRRk.khhHk.',
        '..kHhhkRRRRRRkhhHk..',
        '...kkkRRRRRRRRkkk...',
        '....kRRRRRRRRRRDk...',
        '....kRkkRRRRkkRDk...',
        '....kRRykkRkkyRDk...',
        '....kRRyyRRRyyRDk...',
        '....kRRRRRkRRRRDk...',
        '.....kRkkkkkkkDk....',
        '.....kRkwkkkwkDk....',
        '......kRRRRRRDk.....',
        '.......kkkkkkk......',
        '....................',
        '....................',
        '....................']),
    'ANVIL': ({'k': K, 'a': 0x7A7888, 'A': 0x403E4C, 'h': 0xB8B4C4, 'w': 0x8A5A30, 'm': 0x5A5A68,
               'f': 0xFF7000, 'F': 0xFFCC00}, [
        '....................',
        '..F......kkkk.......',
        '.....f..kmmmmk..F...',
        '...F....kmmmmk......',
        '.........kkwk.f.....',
        '...........wk.......',
        '..kkkkkkkkkwkkkkkk..',
        '.khhhhhhhhhhhhhhhhk.',
        'khaaaaaaaaaaaaaaaaAk',
        '.kkkkAaaaaaaaaAkkkk.',
        '.....kAaaaaaaAk.....',
        '.....kAaaaaaaAk.....',
        '.....kAaaaaaaAk.....',
        '....kAaaaaaaaaAk....',
        '...kAaaaaaaaaaaAk...',
        '..kAAAAAAAAAAAAAAk..',
        '..kkkkkkkkkkkkkkkk..',
        '....................',
        '....................',
        '....................']),
}


def cat_rows():
    """Tuxedo cat (black + white), singing: happy closed eyes, open mouth. The VOCAL FX icon on the MODE ring."""
    S = 24
    g = [['.'] * S for _ in range(S)]
    for y in range(S):
        for x in range(S):
            if ((x - 11.5) / 10.2) ** 2 + ((y - 13.5) / 8.6) ** 2 <= 1:
                g[y][x] = 'o'
    for c in (4.5, 18.5):                            # ears, pink inside
        for y in range(1, 8):
            w = (y - 1) * 0.75
            for x in range(S):
                if abs(x - c) <= w:
                    g[y][x] = 'p' if abs(x - c) <= w - 1.6 and y > 3 else 'o'
    for y in range(S):                               # rim light top-left, deeper black bottom-right
        for x in range(S):
            if g[y][x] == 'o' and (x - 11.5) + (y - 13.5) * 1.2 > 9:
                g[y][x] = 'O'
            elif g[y][x] == 'o' and (x - 11.5) + (y - 13.5) < -10:
                g[y][x] = 'l'
    for y in range(S):                               # white muzzle + the blaze up the forehead
        for x in range(S):
            if g[y][x] in 'oOl':
                muzzle = ((x - 11.5) / 6.2) ** 2 + ((y - 17.0) / 4.4) ** 2 <= 1
                blaze = 6 <= y <= 14 and abs(x - 11.5) <= 0.6 + (y - 6) * 0.28
                if muzzle or blaze:
                    g[y][x] = 'W' if (x - 11.5) + (y - 17) < 3 else 'V'
    for cx in (7, 16):                               # happy closed eyes ^ ^ (light, on black fur)
        g[11][cx] = 'e'; g[12][cx - 1] = 'e'; g[12][cx + 1] = 'e'; g[13][cx - 2] = 'e'; g[13][cx + 2] = 'e'
    g[14][11] = g[14][12] = 'n'                      # pink nose
    for (x, y, c) in ((11, 15, 'k'), (12, 15, 'k'), (10, 16, 'k'), (11, 16, 'm'), (12, 16, 'm'), (13, 16, 'k'),
                      (10, 17, 'k'), (11, 17, 't'), (12, 17, 't'), (13, 17, 'k'), (11, 18, 'k'), (12, 18, 'k')):
        g[y][x] = c                                  # singing mouth
    for y, x0, x1 in ((15, 0, 4), (16, 1, 4), (15, 19, 23), (16, 19, 22)):
        for x in range(x0, x1 + 1):
            if g[y][x] == '.':
                g[y][x] = 'w'                        # whiskers
    out = [row[:] for row in g]
    for y in range(S):
        for x in range(S):
            if g[y][x] == '.' and any(0 <= y + dy < S and 0 <= x + dx < S and g[y + dy][x + dx] not in '.w'
                                      for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0))):
                out[y][x] = 'k'
    return [''.join(r) for r in out]


SPRITES['CAT'] = ({'k': 0x968CAA, 'o': 0x221E28, 'O': 0x100C14, 'l': 0x4E485C, 'p': 0xFF8CA0, 'n': 0xF06E8C,
                   'm': 0x6E1020, 't': 0xFF6E82, 'w': 0xF0ECE6, 'W': 0xF4F0E8, 'V': 0xB8B4C4, 'e': 0xC8F05A},
                  cat_rows())


def rgb(c):
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def check():
    for name, (pal, rows) in SPRITES.items():
        assert len(rows) <= 24, name
        for i, r in enumerate(rows):
            assert len(r) == len(rows[0]) <= 24, (name, i, r, len(r))
            for ch in r:
                assert ch == '.' or ch in pal, (name, i, ch)


def header():
    out = ['// Generated by tools/gen_sprites.py: pixel-art sprites (\'.\' = transparent, palette keys below).',
           '// A palette colour of 0xFFFFFFFF = the tint passed by the caller (\'P\'), 0xFFFFFFFE = darker, '
           '0xFFFFFFFD = lighter.',
           '#pragma once', '', 'namespace spr {', '',
           'struct Sprite { uint8_t w, h; const char *const *rows; const char *keys; const uint32_t *pal; };', '']
    tint = {'P': 0xFFFFFFFF, 'Q': 0xFFFFFFFE, 'q': 0xFFFFFFFD}
    for name, (pal, rows) in SPRITES.items():
        keys = ''.join(pal)
        cols = ', '.join('0x%06X' % pal[k] if pal[k] is not None else '0x%08X' % tint[k] for k in pal)
        out.append('static const uint32_t %s_PAL[] = {%s};' % (name, cols))
        out.append('static const char *const %s_ROWS[] = {' % name)
        out += ['  "%s",' % r for r in rows]
        out.append('};')
        out.append('static const Sprite %s = {%d, %d, %s_ROWS, "%s", %s_PAL};' % (name, len(rows[0]), len(rows),
                                                                                  name, keys, name))
        out.append('')
    out.append('}  // namespace spr')
    return '\n'.join(out) + '\n'


def preview(path, tint=0xE01818):
    from PIL import Image
    S, names = 8, list(SPRITES)
    img = Image.new('RGB', (len(names) * 26 * S, 26 * S), (12, 10, 20))
    for n, name in enumerate(names):
        pal, rows = SPRITES[name]
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch == '.':
                    continue
                c = pal[ch]
                if c is None:
                    f = {'P': 1.0, 'Q': 0.6, 'q': 1.3}[ch]
                    col = tuple(min(255, int(v * f)) for v in rgb(tint))
                else:
                    col = rgb(c)
                for dy in range(S):
                    for dx in range(S):
                        img.putpixel(((n * 26 + 1 + x) * S + dx, (1 + y) * S + dy), col)
    img.save(path)


if __name__ == '__main__':
    check()
    here = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.join(here, '..', 'firmware', 'mone_dev', 'sprites.h')
    tmp = dst + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(header())
    os.replace(tmp, dst)
    print('wrote', os.path.normpath(dst), len(SPRITES), 'sprites')
    if len(sys.argv) > 1:
        preview(sys.argv[1])
        print('preview', sys.argv[1])
