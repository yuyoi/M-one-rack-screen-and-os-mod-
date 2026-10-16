"""Draws docs/wiring.png: J5, J8 and the ESP32-S3 DevKitC-1 pins, in the OS's heavy-metal theme.
    python tools/draw_wiring.py
Source of truth for the pins: USER_GUIDE.md (wiring sections). Edit the tables below if the wiring changes."""
import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'docs', 'wiring.png')
W, H = 2000, 1350
BLACK, STEEL_D, STEEL, STEEL_L = (8, 8, 12), (36, 34, 40), (72, 70, 80), (150, 146, 160)
ORANGE, YELLOW, RED, EMBER, WHITE = (255, 112, 0), (255, 204, 0), (232, 32, 16), (110, 26, 0), (240, 236, 224)
COL = {                                   # function colours (legend order)
    'JTAG': (255, 112, 0), 'POWER 5V': (232, 32, 16), 'GND': (110, 110, 120), 'DSP RESET / SENSE': (255, 60, 140),
    'SCREEN': (150, 80, 230), 'POTS': (255, 204, 0), 'LADDERS': (230, 170, 40), 'ENCODER': (40, 200, 230),
    'BUTTONS': (60, 210, 90), '3V3 (pots, screen)': (255, 240, 150),
}
F = lambda n, b=True: ImageFont.truetype('arialbd.ttf' if b else 'arial.ttf', n)
FM = lambda n: ImageFont.truetype('consolab.ttf', n)

# ESP32-S3-DevKitC-1 headers, top to bottom (USB at the bottom)
LEFT = ['3V3', '3V3', 'RST', '4', '5', '6', '7', '15', '16', '17', '18', '8', '3', '46', '9', '10', '11', '12', '13',
        '14', '5V', 'GND']
RIGHT = ['GND', 'TX', 'RX', '1', '2', '42', '41', '40', '39', '38', '37', '36', '35', '0', '45', '48', '47', '21', '20',
         '19', 'GND', 'GND']
USE = {                                   # ESP pin -> (function group, label)
    '4': ('JTAG', 'TRST  (J8-9)'), '10': ('JTAG', 'TDO  (J8-7)'), '11': ('JTAG', 'TDI  (J8-3)'),
    '12': ('JTAG', 'TCK  (J8-1)'), '13': ('JTAG', 'TMS  (J8-5)'),
    '5V': ('POWER 5V', '5V in  (J5-4)'), 'GND': ('GND', 'GND  (J8-2)'),
    '3': ('DSP RESET / SENSE', 'DSP SENSE  (switch pole B)'),
    '8': ('SCREEN', 'TFT SCL'), '9': ('SCREEN', 'TFT SDA'), '15': ('SCREEN', 'TFT RES'), '16': ('SCREEN', 'TFT DC'),
    '17': ('SCREEN', 'TFT BLK'), '18': ('SCREEN', 'TFT CS (held LOW)'),
    '5': ('POTS', 'POT 1  VOLUME'), '6': ('POTS', 'POT 2  MIX'), '7': ('POTS', 'POT 3  TONE'),
    '1': ('LADDERS', 'LADDER 1'), '2': ('LADDERS', 'LADDER 2'),
    '38': ('ENCODER', 'ENC A'), '39': ('ENCODER', 'ENC B'),
    '48': ('BUTTONS', 'BUTTON'), '47': ('BUTTONS', 'BUTTON'), '21': ('BUTTONS', 'BUTTON'), '20': ('BUTTONS', 'BUTTON'),
    '19': ('BUTTONS', 'BUTTON'), '40': ('BUTTONS', 'BUTTON'), '41': ('BUTTONS', 'BUTTON'), '42': ('BUTTONS', 'BUTTON'),
    '14': ('BUTTONS', 'BUTTON'), '3V3': ('3V3 (pots, screen)', '3V3 out'),
}
J8 = {1: 'TCK', 2: 'GND', 3: 'TDI', 4: '-', 5: 'TMS', 6: '-', 7: 'TDO', 8: '-', 9: 'TRST', 10: '3V3 NC'}
J5 = {1: '3V3', 2: 'MIDI TX', 3: 'MIDI RX', 4: '5V', 5: 'NC', 6: 'SPI CLK', 7: 'SPI MOSI', 8: 'PEDAL IMP', 9: 'SPI MISO',
      10: '+15V', 11: 'SPI DL', 12: 'GND', 13: '-15V', 14: 'A PEDAL', 15: 'D PEDAL', 16: 'DSP RESET', 17: '3V3',
      18: 'DSP SS', 19: 'NC', 20: 'PEDAL GND'}

img = Image.new('RGB', (W, H), BLACK)
d = ImageDraw.Draw(img)


def glow_bg():
    px = img.load()
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r = math.hypot((x - W * 0.55) / W, (y - H * 0.45) / H)
            t = max(0.0, 1 - r * 1.6) ** 2
            c = tuple(int(BLACK[i] + (60, 18, 0)[i] * t) for i in range(3))
            for dy in (0, 1):
                for dx in (0, 1):
                    if x + dx < W and y + dy < H: px[x + dx, y + dy] = c


def metal_text(xy, s, font, top=YELLOW, bot=ORANGE, anchor='la'):
    x, y = xy
    for dx in range(-3, 5):
        for dy in range(-3, 5):
            d.text((x + dx, y + dy), s, font=font, fill=BLACK, anchor=anchor)
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).text((x, y), s, font=font, fill=255, anchor=anchor)
    bb = mask.getbbox()
    g = Image.new('RGB', img.size)
    gd = ImageDraw.Draw(g)
    for yy in range(bb[1], bb[3] + 1):
        t = (yy - bb[1]) / max(bb[3] - bb[1], 1)
        gd.line((bb[0], yy, bb[2], yy), fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    img.paste(g, (0, 0), mask)


def bevel(box, fill, hi, lo, w=2):
    d.rectangle(box, fill=fill)
    x0, y0, x1, y1 = box
    for k in range(w):
        d.line([(x0 + k, y1 - k), (x0 + k, y0 + k), (x1 - k, y0 + k)], fill=hi)
        d.line([(x0 + k + 1, y1 - k), (x1 - k, y1 - k), (x1 - k, y0 + k + 1)], fill=lo)


def pin(x, y, col=None, r=11):
    if col:                                   # glow ring
        for k in range(10, 0, -2):
            c = tuple(int(col[i] * (0.25 + 0.06 * (10 - k))) for i in range(3))
            d.ellipse((x - r - k, y - r - k, x + r + k, y + r + k), fill=c)
    d.rectangle((x - r, y - r, x + r, y + r), fill=(200, 170, 60) if not col else col, outline=BLACK, width=2)
    d.rectangle((x - 4, y - 4, x + 4, y + 4), fill=BLACK if col else (120, 100, 40))


def wire(pts, col, w=6):
    for k, c in ((w + 4, BLACK), (w, col)):   # dark outline, then the colour
        d.line(pts, fill=c, width=k, joint='curve')
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - w, p[1] - w, p[0] + w, p[1] + w), fill=col, outline=BLACK, width=2)


glow_bg()
metal_text((W // 2, 22), 'M-ONE  //  ESP32-S3 WIRING', F(56), anchor='ma')
d.text((W // 2, 94), 'J8 = DSP JTAG/OnCE        J5 = front-panel ribbon        ESP32-S3-DevKitC-1 (USB at the bottom)',
       font=F(22, False), fill=STEEL_L, anchor='ma')


def gnd_tag(x, y, text_side='l'):
    """ground symbol + 'GND' label"""
    col = COL['GND']
    d.line((x, y, x, y + 14), fill=col, width=4)
    for k, w in enumerate((18, 12, 6)):
        d.line((x - w, y + 14 + k * 6, x + w, y + 14 + k * 6), fill=col, width=3)


# ---------------- ESP board (labels INSIDE the board, wires only outside)
EX0, EX1, EY, PITCH = 1020, 1580, 280, 40
LX, RX = EX0 + 40, EX1 - 40                       # pin columns
bevel((EX0, 140, EX1, EY + PITCH * 21 + 70), (18, 40, 32), (60, 110, 90), (6, 16, 12), 4)
bevel((EX0 + 170, 158, EX1 - 170, 248), (150, 150, 160), (220, 220, 230), (70, 70, 80), 3)    # RF can, above the pins
metal_text(((EX0 + EX1) // 2, 172), 'ESP32-S3', F(28), WHITE, STEEL_L, 'ma')
d.text(((EX0 + EX1) // 2, 214), 'N16R8  DevKitC-1', font=F(18), fill=(40, 40, 50), anchor='ma')
d.rounded_rectangle(((EX0 + EX1) // 2 - 28, EY + PITCH * 21 + 40, (EX0 + EX1) // 2 + 28, EY + PITCH * 21 + 76), 6,
                    fill=(170, 170, 180), outline=BLACK, width=2)                                    # USB
ESP = {}
for side, names, x in (('L', LEFT, LX), ('R', RIGHT, RX)):
    for i, n in enumerate(names):
        y = EY + i * PITCH
        use = USE.get(n)
        if n == 'GND' and side == 'R': use = None
        col = COL[use[0]] if use else None
        pin(x, y, col)
        ESP[(side, n)] = (x, y)
        if side == 'L':
            d.text((x + 24, y), n, font=FM(20), fill=WHITE if use else STEEL, anchor='lm')
            if use: d.text((x + 76, y), use[1], font=F(18), fill=col, anchor='lm')
        else:
            d.text((x - 24, y), n, font=FM(20), fill=WHITE if use else STEEL, anchor='rm')
            if use: d.text((x - 76, y), use[1], font=F(18), fill=col, anchor='rm')

# ---------------- J8 (2x5): odd row = signals (top here), pin 1 nearest J5
J8X, J8Y, P = 130, 330, 70
bevel((J8X - 45, J8Y - 40, J8X + 45 + 4 * P, J8Y + P + 70), (20, 20, 24), STEEL, BLACK, 3)
metal_text((J8X + 2 * P, J8Y - 118), 'J8  JTAG / OnCE', F(32), anchor='ma')
J8P = {}
for n, name in J8.items():
    col_i, row = (n - 1) // 2, (n - 1) % 2
    x, y = J8X + col_i * P, J8Y + row * P
    grp = 'JTAG' if name in ('TCK', 'TDI', 'TMS', 'TDO', 'TRST') else ('GND' if name == 'GND' else None)
    pin(x, y, COL[grp] if grp else None)
    J8P[n] = (x, y)
    d.text((x, y + 30), name, font=F(17), fill=WHITE if grp else STEEL, anchor='mm')
    d.text((x, y), str(n), font=F(12), fill=WHITE, anchor='mm')
d.text((J8X - 45, J8Y + P + 84), 'pin 10 (3V3) stays EMPTY', font=F(18), fill=(255, 80, 60))

# ---------------- J5 (2x10), as seen on the board: pin 1 bottom-left, even row on top
J5X, J5Y, P5 = 80, 800, 62
bevel((J5X - 40, J5Y - 62, J5X + 9 * P5 + 40, J5Y + P5 + 62), (20, 20, 24), STEEL, BLACK, 3)
metal_text((J5X + 4.5 * P5, J5Y - 150), 'J5  FRONT RIBBON', F(32), anchor='ma')
J5P = {}
for n, name in J5.items():
    col_i, top = (n - 1) // 2, n % 2 == 0
    x, y = J5X + col_i * P5, J5Y if top else J5Y + P5
    grp = {4: 'POWER 5V', 16: 'DSP RESET / SENSE', 17: 'DSP RESET / SENSE'}.get(n)
    danger = n in (10, 13)
    pin(x, y, COL[grp] if grp else ((255, 30, 20) if danger else None), 10)
    J5P[n] = (x, y)
    lab = name.replace(' ', '\n') + ('\nNEVER' if danger else '')
    d.multiline_text((x, y - 26 if top else y + 26), lab, font=F(13), anchor='md' if top else 'ma', align='center',
                     fill=(255, 70, 50) if danger else (WHITE if grp else STEEL), spacing=1)
    d.text((x, y), str(n), font=F(11), fill=WHITE, anchor='mm')

# ---------------- DPDT power switch (between J5 and the ESP)
SX, SY = 420, 1080
bevel((SX - 100, SY - 80, SX + 100, SY + 120), (28, 26, 32), STEEL, BLACK, 3)
metal_text((SX - 120, SY - 40), 'POWER', F(26), anchor='ra')
metal_text((SX - 120, SY - 6), 'SWITCH', F(26), anchor='ra')
d.text((SX - 120, SY + 34), 'DPDT', font=F(16), fill=STEEL_L, anchor='ra')
d.text((SX - 120, SY + 56), '(the old front button)', font=F(14), fill=STEEL_L, anchor='ra')
SA, SB = SY - 30, SY + 66
for lbl, yy in (('POLE A', SA), ('POLE B', SB)):
    d.text((SX - 92, yy + 12), lbl, font=F(15), fill=STEEL_L)
    for xx in (SX - 55, SX, SX + 55):
        d.ellipse((xx - 7, yy - 7, xx + 7, yy + 7), fill=(200, 170, 60), outline=BLACK, width=2)
    d.line((SX, yy, SX + 50, yy - 17), fill=WHITE, width=4)                       # lever

# ---------------- wires (later wires pass OVER earlier ones: the dark outline makes the gap)
jt = COL['JTAG']
for j8, gpio, lane, ch in ((9, '4', 258, 985), (7, '10', 268, 970), (3, '11', 278, 955), (1, '12', 288, 940),
                           (5, '13', 298, 925)):
    x0, y0 = J8P[j8]
    tx, ty = ESP[('L', gpio)]
    wire([(x0, y0), (x0, lane), (ch, lane), (ch, ty), (tx, ty)], jt)
red, pink = COL['POWER 5V'], COL['DSP RESET / SENSE']
x4, y4 = J5P[4]
wire([J5P[4], (x4, y4 - 16), (x4 + 31, y4 - 16), (x4 + 31, 700), (905, 700), (905, ESP[('L', '5V')][1]), ESP[('L', '5V')]], red)
x16, y16 = J5P[16]
wire([J5P[16], (x16, y16 - 16), (x16 + 31, y16 - 16), (x16 + 31, 720), (720, 720), (720, 990), (SX, 990), (SX, SA)], pink)   # pole A middle = DSP RESET
x17, y17 = J5P[17]
wire([J5P[17], (x17, y17 + 16), (x17 + 31, y17 + 16), (x17 + 31, 960), (SX - 55, 960), (SX - 55, SA)], pink)   # pole A side = 3V3
wire([(SX + 55, SB), (SX + 55, 1228), (1000, 1228), (1000, ESP[('L', '3')][1]), ESP[('L', '3')]], pink)  # -> GPIO 3
wire([(SX, SB), (SX, 1170)], COL['GND'])                                             # pole B middle -> GND
gnd_tag(SX - 0, 1170)

# ---------------- notes + legend
notes = [('Switch IN = DSP runs (GPIO 3 open).  Switch OUT = DSP held in reset, GPIO 3 = GND, the face sleeps.', STEEL_L),
         ('The ESP runs from J5-4 (5V) into its 5V pin; its ground is J8-2. Never feed it the M-One 3V3 while on USB.', STEEL_L),
         ('J5-10 / J5-13 are +/-15 V: never connect the ESP there.', (255, 80, 60))]
for i, (s, c) in enumerate(notes):
    d.text((40, 1270 + i * 26), s, font=F(18, False), fill=c)
lx, ly = 1640, 300
metal_text((lx, ly - 76), 'LEGEND', F(30), anchor='la')
for i, (name, col) in enumerate(COL.items()):
    y = ly + i * 42
    d.rounded_rectangle((lx, y, lx + 36, y + 24), 6, fill=col, outline=BLACK, width=2)
    d.text((lx + 50, y + 12), name, font=F(20), fill=WHITE, anchor='lm')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT)
print('saved', os.path.abspath(OUT))
