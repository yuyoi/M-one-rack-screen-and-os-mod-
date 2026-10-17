// PS1 heavy-metal theme: black + molten orange/yellow, 15-bit colour, Bayer-dithered gradients, a 5x7 pixel font and
// chunky metal titles (approved mockup: tc_mone/research/theme_mockup.png).
// Pages draw into a 120x120 canvas pushed at 2x: chunky pixels like a PS1 menu, one full push per frame.
// Animated parts take a phase (millis()): the header lava flows, flames flicker, the selection bar shimmers, rows slide in.
#pragma once
#include "sprites.h"               // generated: tools/gen_sprites.py

namespace th {

const uint32_t BLACK = 0x08080C, STEEL_D = 0x242228, STEEL = 0x484650, STEEL_L = 0x8C8896, ORANGE = 0xFF7000,
               YELLOW = 0xFFCC00, RED = 0xE82010, EMBER = 0x6E1A00, WHITE = 0xF0ECE0, ASH = 0x1C0C04;
// preset type colours: STUDIO, TUNE, HARMONY, LO-FI, MONSTER, AMBIENT
const uint32_t TYPE_COL[6] = {0xFF7000, 0xFFCC00, 0xE6AA28, 0xAA4614, 0xE82010, 0x963CDC};

static LGFX_Sprite cv(&tft);               // the 120x120 canvas
static bool ready = false;

bool begin() {
  cv.setColorDepth(16);
  ready = cv.createSprite(120, 120) != nullptr;
  return ready;
}

void present() { cv.pushRotateZoom(&tft, 119.5f, 119.5f, 0.0f, 2.0f, 2.0f); }   // whole 240x240 screen

// ---------------------------------------------------------------- colour
static inline uint32_t p15(uint32_t c) { return c & 0xF8F8F8; }   // PS1-style 15-bit colour

static inline uint32_t mix(uint32_t a, uint32_t b, float t) {
  t = constrain(t, 0.0f, 1.0f);
  int r = ((a >> 16) & 255) + (int)((((int)(b >> 16) & 255) - (int)((a >> 16) & 255)) * t);
  int g = ((a >> 8) & 255) + (int)((((int)(b >> 8) & 255) - (int)((a >> 8) & 255)) * t);
  int bl = (a & 255) + (int)(((int)(b & 255) - (int)(a & 255)) * t);
  return (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)bl;
}

static const uint8_t BAYER[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};

// Colour of a multi-stop gradient at t (0..1) for pixel x,y: Bayer-dithered, 4 bands per stop pair
static uint32_t gradAt(int x, int y, float t, const uint32_t *st, int n) {
  float tt = constrain(t, 0.0f, 1.0f) * (n - 1);
  int seg = min((int)tt, n - 2);
  float lt = tt - seg + (BAYER[y & 3][x & 3] / 16.0f - 0.5f) * 0.35f;
  lt = roundf(constrain(lt, 0.0f, 1.0f) * 4) / 4;
  return p15(mix(st[seg], st[seg + 1], lt));
}

void grad(int x0, int y0, int x1, int y1, const uint32_t *st, int n, bool vert = true) {
  int span = max((vert ? y1 - y0 : x1 - x0) - 1, 1);
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) cv.drawPixel(x, y, gradAt(x, y, (vert ? y - y0 : x - x0) / (float)span, st, n));
}

void bevel(int x0, int y0, int x1, int y1, uint32_t fill, uint32_t hi = STEEL_L, uint32_t lo = BLACK) {
  cv.fillRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, fill);
  cv.drawFastHLine(x0, y0, x1 - x0 + 1, hi);
  cv.drawFastVLine(x0, y0, y1 - y0 + 1, hi);
  cv.drawFastHLine(x0 + 1, y1, x1 - x0, lo);
  cv.drawFastVLine(x1, y0 + 1, y1 - y0, lo);
}

// Dithered radial ember glow behind the face/pedal; amount 0..1 (can pulse with the audio level)
void vignette(float amount, int cx = 60, int cy = 64) {
  for (int y = 0; y < 120; y++)
    for (int x = 0; x < 120; x++) {
      float r = sqrtf((float)((x - cx) * (x - cx) + (y - cy) * (y - cy))) / 70.0f;
      float t = (1 - r) * (1 - r) * amount + (BAYER[y & 3][x & 3] / 16.0f - 0.5f) * 0.12f;
      cv.drawPixel(x, y, r >= 1 ? BLACK : p15(mix(BLACK, 0x3C1200, t)));
    }
}

// ---------------------------------------------------------------- 5x7 pixel font (ASCII 32-95, lower case folds up)
static const uint8_t FONT[64][7] = {
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},  // ' '
  {0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04},  // '!'
  {0x0A, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00},  // '"'
  {0x0A, 0x0A, 0x1F, 0x0A, 0x1F, 0x0A, 0x0A},  // '#'
  {0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04},  // '$'
  {0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13},  // '%'
  {0x0C, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0D},  // '&'
  {0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00},  // "'"
  {0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02},  // '('
  {0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08},  // ')'
  {0x00, 0x15, 0x0E, 0x1F, 0x0E, 0x15, 0x00},  // '*'
  {0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00},  // '+'
  {0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08},  // ','
  {0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00},  // '-'
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C},  // '.'
  {0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10},  // '/'
  {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E},  // '0'
  {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E},  // '1'
  {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F},  // '2'
  {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E},  // '3'
  {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02},  // '4'
  {0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E},  // '5'
  {0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E},  // '6'
  {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08},  // '7'
  {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E},  // '8'
  {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E},  // '9'
  {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00},  // ':'
  {0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x04, 0x08},  // ';'
  {0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02},  // '<'
  {0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00},  // '='
  {0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08},  // '>'
  {0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04},  // '?'
  {0x0E, 0x11, 0x17, 0x15, 0x17, 0x10, 0x0E},  // '@'
  {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},  // 'A'
  {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E},  // 'B'
  {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E},  // 'C'
  {0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C},  // 'D'
  {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F},  // 'E'
  {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10},  // 'F'
  {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F},  // 'G'
  {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},  // 'H'
  {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E},  // 'I'
  {0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C},  // 'J'
  {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11},  // 'K'
  {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F},  // 'L'
  {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11},  // 'M'
  {0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11},  // 'N'
  {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E},  // 'O'
  {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10},  // 'P'
  {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D},  // 'Q'
  {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11},  // 'R'
  {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E},  // 'S'
  {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04},  // 'T'
  {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E},  // 'U'
  {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04},  // 'V'
  {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A},  // 'W'
  {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11},  // 'X'
  {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04},  // 'Y'
  {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F},  // 'Z'
  {0x0E, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0E},  // '['
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00},  // '\\'
  {0x0E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0E},  // ']'
  {0x04, 0x0A, 0x11, 0x00, 0x00, 0x00, 0x00},  // '^'
  {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F},  // '_'
};

static const uint8_t *glyph(char c) {
  if (c >= 'a' && c <= 'z') c -= 32;
  if (c < 32 || c > 95) c = '?';
  return FONT[c - 32];
}

int textW(const char *s, int sc = 1) { int n = strlen(s); return n ? (n * 6 - 1) * sc : 0; }

void text(int x, int y, const char *s, uint32_t col, int sc = 1, char anchor = 'l') {
  if (anchor == 'm') x -= textW(s, sc) / 2;
  else if (anchor == 'r') x -= textW(s, sc);
  for (; *s; s++, x += 6 * sc) {
    const uint8_t *g = glyph(*s);
    for (int j = 0; j < 7; j++)
      for (int i = 0; i < 5; i++)
        if (g[j] & (0x10 >> i)) {
          if (sc == 1) cv.drawPixel(x + i, y + j, col);
          else cv.fillRect(x + i * sc, y + j * sc, sc, sc, col);
        }
  }
}

// Chunky metal title: hard black outline + drop shadow, each glyph row graded top -> bottom
void metal(int x, int y, const char *s, int sc = 2, uint32_t top = WHITE, uint32_t bot = YELLOW, char anchor = 'l') {
  if (anchor == 'm') x -= textW(s, sc) / 2;
  else if (anchor == 'r') x -= textW(s, sc);
  int o = sc > 1 ? 2 : 1;                              // outline + shadow: thinner at small size
  for (int dy = -1; dy <= o; dy++)
    for (int dx = -1; dx <= o; dx++)
      if ((dx || dy) && (sc > 1 || dx < 1 || dy < 1 || (dx == 1 && dy == 1))) text(x + dx, y + dy, s, BLACK, sc);
  for (const char *p = s; *p; p++, x += 6 * sc) {
    const uint8_t *g = glyph(*p);
    for (int j = 0; j < 7; j++) {
      uint32_t c = p15(mix(top, bot, j / 6.0f));
      for (int i = 0; i < 5; i++)
        if (g[j] & (0x10 >> i)) cv.fillRect(x + i * sc, y + j * sc, sc, sc, c);
    }
  }
}

// ---------------------------------------------------------------- page furniture
static uint32_t hash32(uint32_t v) { v ^= v >> 16; v *= 0x7FEB352D; v ^= v >> 15; v *= 0x846CA68B; return v ^ (v >> 16); }

// Molten header band (rows 0-18): the lava waves slowly, flame licks flicker below it. dot >= 0 lights a page dot.
void header(const char *title, uint32_t ph, int dot = -1, int nDots = 3) {
  static const uint32_t st[3] = {YELLOW, ORANGE, EMBER};
  for (int y = 0; y < 19; y++)
    for (int x = 0; x < 120; x++)
      cv.drawPixel(x, y, gradAt(x, y, y / 18.0f + 0.09f * sinf(x * 0.21f + ph * 0.004f), st, 3));
  cv.fillRect(0, 19, 120, 4, BLACK);
  static const uint8_t H[6] = {0, 0, 1, 1, 2, 3};
  for (int x = 0; x < 120; x++) {
    int h = H[hash32(x * 7919 + (ph / 90) * 104729) % 6];
    for (int k = 0; k < h; k++) cv.drawPixel(x, 19 + k, p15(k ? RED : ORANGE));
  }
  int sc = textW(title, 2) <= (dot >= 0 ? 88 : 108) ? 2 : 1;
  metal(5, sc == 2 ? 3 : 6, title, sc, WHITE, YELLOW);
  for (int i = 0; dot >= 0 && i < nDots; i++)
    cv.fillRect(118 - (nDots - i) * 7, 8, 5, 5, i == dot ? BLACK : EMBER);
}

void status(const char *s, uint32_t col = YELLOW) {
  cv.fillRect(0, 108, 120, 12, BLACK);
  cv.drawFastHLine(0, 108, 120, p15(ORANGE));
  text(60, 111, s, p15(col), 1, 'm');
}

// Slide-in offset for row i of a page opened at t0 (PS1 menus: rows fly in from the right, staggered)
int slide(uint32_t now, uint32_t t0, int i) {
  int t = (int)(now - t0) - i * 45;
  return t >= 160 ? 0 : (t <= 0 ? 120 : (int)(120 * (1 - t / 160.0f) * (1 - t / 160.0f)));
}

// Menu row (15 px tall): a steel plate, or the lava selection bar with a shimmer sweep and a pulsing cursor
void row(int y, const char *key, const char *val, bool sel, bool dim, uint32_t ph, int dx = 0) {
  int x0 = 3 + dx, x1 = 116 + dx;
  if (sel) {
    bevel(x0, y, x1, y + 14, p15(EMBER), p15(YELLOW), BLACK);
    int sweep = (int)((ph / 7) % 220) - 50;            // bright band crossing every ~1.5 s
    for (int x = x0 + 1; x < x1; x++) {
      float t = (x - x0) / (float)(x1 - x0) - 0.35f * expf(-(float)((x - x0 - sweep) * (x - x0 - sweep)) / 90.0f);
      for (int yy = y + 1; yy < y + 14; yy++) {
        static const uint32_t st[2] = {ORANGE, EMBER};
        cv.drawPixel(x, yy, gradAt(x, yy, t, st, 2));
      }
    }
    int p = (ph / 260) % 2;                            // cursor pulse
    cv.fillTriangle(x0 + 2 - p, y + 3 - p, x0 + 2 - p, y + 11 + p, x0 + 6 + p, y + 7, p15(YELLOW));
    text(x0 + 10, y + 4, key, BLACK);
    metal(x1 - 3, y + 4, val, 1, WHITE, YELLOW, 'r');
  } else {
    bevel(x0, y, x1, y + 14, p15(STEEL_D), p15(STEEL), BLACK);
    text(x0 + 10, y + 4, key, p15(dim ? STEEL : STEEL_L));
    text(x1 - 3, y + 4, val, p15(dim ? STEEL : WHITE), 1, 'r');
  }
}

// ---------------------------------------------------------------- mock pedal (idle screen when a PEDAL effect is on)
static void knob(int cx, int cy, int r, float v, const char *label) {
  cv.fillCircle(cx, cy, r, p15(0x141418));
  cv.drawCircle(cx, cy, r, p15(STEEL));
  cv.drawCircle(cx, cy, r - 2, p15(STEEL_D));
  float a = (-135 + 270 * constrain(v, 0.0f, 1.0f)) * 0.0174533f;   // 7 o'clock .. 5 o'clock
  int ex = cx + (int)((r - 2) * sinf(a)), ey = cy - (int)((r - 2) * cosf(a));
  cv.drawLine(cx, cy, ex, ey, p15(YELLOW));
  cv.drawLine(cx + 1, cy, ex + 1, ey, p15(YELLOW));
  text(cx, cy + r + 3, label, BLACK, 1, 'm');
}

// nk knobs (0..1 each, up to 6: one row up to 3, else two rows), led 0..1 (lit when active; flicker it with the audio
// level). dx shifts the whole pedal (the PEDAL board slides one out and the next in); bg = false skips the background.
void pedal(const char *name, uint32_t col, int nk, const float *knobs, const char *const *labels, float led, uint32_t ph,
           int dx = 0, bool bg = true) {
  if (bg) vignette(0.5f);
  const uint32_t body[3] = {mix(col, WHITE, 0.25f), col, mix(col, BLACK, 0.25f)};
  bevel(14 + dx, 4, 106 + dx, 116, p15(col), p15(mix(col, WHITE, 0.5f)), p15(mix(col, BLACK, 0.5f)));
  grad(15 + dx, 5, 106 + dx, 116, body, 3);
  bool two = nk > 3;
  int sy = two ? 10 : 18;                              // hazard stripe band (clipped to the body)
  for (int k = -20; k < 100; k += 12)
    for (int y = sy; y <= sy + 8; y++)
      for (int x = 15 + k + (sy + 8 - y); x < 21 + k + (sy + 8 - y); x++)
        if (x >= 15 && x < 106) cv.drawPixel(x + dx, y, p15(BLACK));
  for (int s = 0; s < 4; s++) cv.fillCircle((s & 1 ? 102 : 18) + dx, s & 2 ? 112 : 8, 2, p15(STEEL_L));   // screws
  for (int i = 0; i < nk; i++) {
    int row = two && i >= 3, inRow = two ? (row ? nk - 3 : 3) : nk, j = row ? i - 3 : i;
    int x = 60 + (int)((j - (inRow - 1) / 2.0f) * 29) + dx;
    knob(x, two ? (row ? 56 : 30) : 42, two ? 7 : 9, knobs[i], labels[i]);
  }
  int py = two ? 76 : 66;                              // name plate, LED, footswitch
  bevel(26 + dx, py, 94 + dx, py + 16, BLACK, p15(STEEL), p15(STEEL_D));
  metal(60 + dx, py + 2, name, textW(name, 2) <= 64 ? 2 : 1, YELLOW, RED, 'm');
  float l = constrain(led, 0.0f, 1.0f);
  int ly = two ? 97 : 90, lr = two ? 4 : 6;
  cv.fillCircle(60 + dx, ly, lr, p15(mix(0x200402, 0x5A0A04, l)));   // LED glow rings
  cv.fillCircle(60 + dx, ly, lr - 2, p15(mix(0x300604, RED, l)));
  cv.fillCircle(60 + dx, ly, max(lr - 4, 1), p15(mix(0x400806, 0xFF785A, l)));
  int fy = two ? 108 : 106;
  cv.fillEllipse(60 + dx, fy, 10, 7, p15(STEEL_L));   // footswitch
  cv.drawEllipse(60 + dx, fy, 10, 7, BLACK);
  cv.fillEllipse(60 + dx, fy, 6, 4, p15(STEEL));
}

// ---------------------------------------------------------------- pixel-art sprites (sprites.h)
// 16x16 at scale sc, top-left x,y. tint = the colour for the 'P' keys (darker / lighter variants too); dim 0..1
// darkens the whole sprite (ring-menu items at the back).
void sprite(int x, int y, const spr::Sprite &s, int sc = 1, uint32_t tint = RED, float dim = 0) {
  for (int j = 0; j < 16; j++)
    for (int i = 0; i < 16; i++) {
      char ch = s.rows[j][i];
      if (ch == '.') continue;
      const char *k = strchr(s.keys, ch);
      if (!k) continue;
      uint32_t c = s.pal[k - s.keys];
      if (c == 0xFFFFFFFF) c = tint;
      else if (c == 0xFFFFFFFE) c = mix(tint, BLACK, 0.4f);
      else if (c == 0xFFFFFFFD) c = mix(tint, WHITE, 0.3f);
      if (dim > 0) c = mix(c, BLACK, dim);
      if (sc == 1) cv.drawPixel(x + i, y + j, p15(c));
      else cv.fillRect(x + i * sc, y + j * sc, sc, sc, p15(c));
    }
}

// ---------------------------------------------------------------- boot splash: spinning flat-shaded low-poly diamond
void bootSplash(uint32_t ms = 1600) {
  if (!ready) return;
  static const float V[6][3] = {{0, 1.3f, 0}, {0, -1.3f, 0}, {1, 0, 0}, {-1, 0, 0}, {0, 0, 1}, {0, 0, -1}};
  static const uint8_t F[8][3] = {{0, 2, 4}, {0, 4, 3}, {0, 3, 5}, {0, 5, 2}, {1, 4, 2}, {1, 3, 4}, {1, 5, 3}, {1, 2, 5}};
  uint32_t t0 = millis();
  while (millis() - t0 < ms) {
    uint32_t now = millis();
    float a = (now - t0) * 0.0035f, ca = cosf(a), sa = sinf(a), cb = cosf(0.45f), sb = sinf(0.45f);
    float P[6][3];
    int S[6][2];
    for (int i = 0; i < 6; i++) {                      // spin around Y, tilt around X, project
      float x = V[i][0] * ca + V[i][2] * sa, z = -V[i][0] * sa + V[i][2] * ca, y = V[i][1];
      float y2 = y * cb - z * sb, z2 = y * sb + z * cb;
      P[i][0] = x; P[i][1] = y2; P[i][2] = z2;
      float k = 62.0f / (3.2f - z2);
      S[i][0] = 60 + (int)(x * k);                     // whole-pixel snap = PS1 vertex wobble for free
      S[i][1] = 44 - (int)(y2 * k);
    }
    int order[8];
    float depth[8];
    for (int f = 0; f < 8; f++) {
      order[f] = f;
      depth[f] = P[F[f][0]][2] + P[F[f][1]][2] + P[F[f][2]][2];
    }
    for (int i = 0; i < 8; i++)                         // painter's sort, far faces first
      for (int j = i + 1; j < 8; j++)
        if (depth[order[j]] < depth[order[i]]) { int t = order[i]; order[i] = order[j]; order[j] = t; }
    vignette(1.0f, 60, 44);
    for (int k = 0; k < 8; k++) {
      const uint8_t *f = F[order[k]];
      float ux = P[f[1]][0] - P[f[0]][0], uy = P[f[1]][1] - P[f[0]][1], uz = P[f[1]][2] - P[f[0]][2];
      float vx = P[f[2]][0] - P[f[0]][0], vy = P[f[2]][1] - P[f[0]][1], vz = P[f[2]][2] - P[f[0]][2];
      float nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      float len = sqrtf(nx * nx + ny * ny + nz * nz) + 1e-6f;
      float lit = fabsf((nx * -0.4f + ny * 0.6f + nz * 0.7f) / len);   // flat shading
      cv.fillTriangle(S[f[0]][0], S[f[0]][1], S[f[1]][0], S[f[1]][1], S[f[2]][0], S[f[2]][1],
                      p15(lit > 0.66f ? YELLOW : lit > 0.33f ? ORANGE : EMBER));
    }
    metal(60, 84, "M-ONE", 2, YELLOW, ORANGE, 'm');
    float pr = (now - t0) / (float)ms;                 // flame progress bar
    static const uint32_t st[3] = {YELLOW, ORANGE, RED};
    cv.drawRect(19, 102, 82, 7, p15(STEEL));
    grad(20, 103, 20 + (int)(80 * pr), 108, st, 3, false);
    present();
  }
}

}  // namespace th
