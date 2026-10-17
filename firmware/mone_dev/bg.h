// MODE ring backgrounds (SETTINGS > SCENE, NVS "ui"/"bg"): each one is drawn once into the ring's cached sky
// sprite, so they cost nothing per frame. Approved mockups: tc_mone/research/backgrounds.png + backgrounds2.png
// (research/menu_mock/bg_mock.py, bg_mock2.py: the same drawing in Python).
#pragma once
#include <Preferences.h>

namespace bg {

struct Scene { const char *name; uint32_t accent, ember; bool stars; };   // accent / ember: the floor ring's colours
static const Scene SCENES[] = {
  {"NIGHT", 0xFF7000, 0x6E1A00, true},       {"DUNGEON PRP", 0xDC5AFF, 0x50206E, false},
  {"DUNGEON BLU", 0x3CC8FF, 0x163C64, false}, {"THRONE HALL", 0xB4A0FF, 0x3C2878, false},
  {"CRYSTALS", 0x5ADCFF, 0x283C78, false},    {"CASTLE DUSK", 0xFF82A0, 0x6E285A, true},
  {"CASTLE BLUE", 0x96B4FF, 0x283C78, true},  {"OUTRUN", 0xFF28C8, 0x5A0A50, false},
  {"VAPORWAVE", 0xFF96D2, 0x5A3C8C, false},   {"CYBER CITY", 0x50E6FF, 0x5A1450, false},
  {"MATRIX", 0x28FF5A, 0x0A3C14, false},      {"TRON", 0x28BEFF, 0x0A2850, false},
  {"NEON PINK", 0xFF78E6, 0x50145A, false},   {"INFERNO", 0xFFC828, 0x6E0A06, false}};
static const int N_SCENES = sizeof SCENES / sizeof SCENES[0];
const int W = 120, HZ = 64;                  // HZ: the horizon of the 80s scenes

static inline uint32_t C(int r, int g, int b) { return (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b; }
static inline float dith(int x, int y) { return th::BAYER[y & 3][x & 3] / 16.0f - 0.5f; }
static inline uint32_t rd(LovyanGFX &g, int x, int y) {
  RGBColor c = g.readPixelRGB(x, y);
  return C(c.R8(), c.G8(), c.B8());
}

static void vgrad(LovyanGFX &g, int x0, int y0, int x1, int y1, const uint32_t *st, int n) {
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) {
      float t = (y - y0) / (float)max(1, y1 - y0 - 1) + dith(x, y) * 0.08f;
      t = constrain(t, 0.0f, 1.0f) * (n - 1);
      int k = min((int)t, n - 2);
      g.drawPixel(x, y, th::p15(th::mix(st[k], st[k + 1], roundf((t - k) * 4) / 4)));
    }
}

static void glow(LovyanGFX &g, float cx, float cy, float r, uint32_t col, float amt, int h = 108) {
  for (int y = max(0, (int)(cy - r)); y <= min(h - 1, (int)(cy + r)); y++)
    for (int x = max(0, (int)(cx - r)); x <= min(W - 1, (int)(cx + r)); x++) {
      float d = sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy)) / r;
      if (d >= 1) continue;
      float t = (1 - d) * (1 - d) * amt + dith(x, y) * 0.15f;
      if (t > 0) g.drawPixel(x, y, th::p15(th::mix(rd(g, x, y), col, fminf(1.0f, roundf(t * 5) / 5))));
    }
}

// even-odd scanline fill; with top != bot the colour runs top -> bot between y = ya and y = yb
static void fill(LovyanGFX &g, const float *x, const float *y, int n, uint32_t top, uint32_t bot = 0xFFFFFFFF,
                 float ya = 0, float yb = 1) {
  float ymin = y[0], ymax = y[0];
  for (int i = 1; i < n; i++) { ymin = fminf(ymin, y[i]); ymax = fmaxf(ymax, y[i]); }
  int y0 = max(0, (int)ceilf(ymin - 0.5f)), y1 = min(119, (int)floorf(ymax - 0.5f));
  float xs[16];
  for (int yy = y0; yy <= y1; yy++) {
    float sy = yy + 0.5f;
    int k = 0;
    for (int i = 0, j = n - 1; i < n && k < 16; j = i++)
      if ((y[i] <= sy) != (y[j] <= sy)) xs[k++] = x[j] + (sy - y[j]) * (x[i] - x[j]) / (y[i] - y[j]);
    for (int i = 1; i < k; i++)
      for (int j = i; j > 0 && xs[j - 1] > xs[j]; j--) { float t = xs[j]; xs[j] = xs[j - 1]; xs[j - 1] = t; }
    uint32_t c = bot == 0xFFFFFFFF ? top : th::mix(top, bot, constrain((yy - ya) / (yb - ya), 0.0f, 1.0f));
    for (int p = 0; p + 1 < k; p += 2) {
      int xa = max(0, (int)ceilf(xs[p] - 0.5f)), xb = min(119, (int)floorf(xs[p + 1] - 0.5f));
      if (xb >= xa) g.drawFastHLine(xa, yy, xb - xa + 1, th::p15(c));
    }
  }
}
static void rectI(LovyanGFX &g, int x0, int y0, int x1, int y1, uint32_t c) {   // PIL-style inclusive corners
  g.fillRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, th::p15(c));
}

// ---------------------------------------------------------------- NIGHT (the Castlevania one)
static void night(LovyanGFX &g) {
  static const uint32_t st[3] = {0x06061A, 0x140C30, 0x3A1640};
  for (int y = 0; y < 108; y++)
    for (int x = 0; x < W; x++) g.drawPixel(x, y, th::gradAt(x, y, y / 100.0f, st, 3));
  static const int MOON_R[3] = {11, 9, 8};
  static const uint32_t MOON_C[3] = {0x3C141E, 0xC8AA96, 0xECD6BE};
  for (int k = 0; k < 3; k++) g.fillCircle(98, 30, MOON_R[k], th::p15(MOON_C[k]));
  uint32_t sil = th::p15(0x0E0816);
  g.fillRect(0, 99, 120, 9, sil);
  for (int x = 0; x < 120; x += 6) g.fillRect(x, 96, 3, 3, sil);
  static const int TW[2][3] = {{2, 12, 88}, {106, 117, 90}};
  for (int t = 0; t < 2; t++) {
    g.fillRect(TW[t][0], TW[t][2], TW[t][1] - TW[t][0] + 1, 99 - TW[t][2], sil);
    for (int x = TW[t][0]; x <= TW[t][1]; x += 4) g.fillRect(x, TW[t][2] - 3, 2, 3, sil);
  }
}

// ---------------------------------------------------------------- DUNGEON: a stone corridor, torches
static void dungeon(LovyanGFX &g, bool blue) {
  uint32_t wall = blue ? C(54, 76, 128) : C(92, 58, 128), wallD = blue ? C(20, 30, 60) : C(40, 24, 64);
  uint32_t mortar = blue ? C(110, 140, 200) : C(150, 110, 190), floorC = blue ? C(40, 56, 96) : C(70, 44, 96);
  uint32_t fire = blue ? C(60, 200, 255) : C(220, 90, 255), fireHi = blue ? C(210, 250, 255) : C(255, 200, 255);
  const int VX = 60, VY = 48, BX0 = 44, BX1 = 76, BY0 = 34, BY1 = 62;
  for (int y = 0; y < 108; y++)
    for (int x = 0; x < W; x++) {
      uint32_t c;
      if (x >= BX0 && x <= BX1 && y >= BY0 && y <= BY1) c = th::mix(wallD, 0, 0.55f);       // far end
      else if (y > VY && abs(x - VX) <= (y - VY) * (float)(BX1 - VX) / (BY1 - VY)) {         // floor
        float depth = (float)(BY1 - VY) / max(1, y - VY);
        c = th::mix(floorC, 0, fminf(1, depth * 0.9f));
        float zz = 1 / fmaxf(0.05f, (y - VY) / 60.0f);
        if ((int)(zz * 6) % 2 == 0 && y > BY1) c = th::mix(c, 0, 0.25f);                    // flagstone bands
      } else if (y < VY && abs(x - VX) <= (VY - y) * (float)(BX1 - VX) / (VY - BY0)) {       // ceiling
        float depth = (float)(VY - BY0) / max(1, VY - y);
        c = th::mix(wallD, 0, fminf(1, 0.3f + depth * 0.6f));
      } else {                                                                                // side walls
        int dx = abs(x - VX);
        float depth = (float)(BX1 - VX) / max(1, dx);
        c = th::mix(wall, 0, fminf(1, depth * 0.85f));
        float u = 1 / fmaxf(0.02f, dx / 60.0f), u1 = 1 / fmaxf(0.02f, (dx + 1) / 60.0f);
        float v = (float)(y - VY) / max(1, dx) * 8;
        if ((int)(u * 5) != (int)(u1 * 5) || fabsf(v * 2 - roundf(v * 2)) < 0.12f) c = th::mix(c, mortar, 0.5f);   // bricks
      }
      g.drawPixel(x, y, th::p15(th::mix(c, 0, fmaxf(0, dith(x, y) * 0.1f))));
    }
  for (int y = BY0; y <= BY1; y += 4) g.drawFastHLine(BX0, y, BX1 - BX0 + 1, th::p15(th::mix(mortar, 0, 0.5f)));
  static const int T[4][2] = {{16, 46}, {104, 46}, {32, 50}, {88, 50}};
  for (int k = 0; k < 4; k++) {                                                             // torches
    int tx = T[k][0], ty = T[k][1], s = k >= 2;
    glow(g, tx, ty, s ? 14 : 26, fire, 0.75f);
    rectI(g, tx - 1, ty, tx + 1, ty + 6 - s * 2, C(40, 30, 30));
    g.fillTriangle(tx - 2, ty, tx, ty - 6 + s * 2, tx + 2, ty, th::p15(fire));
    g.drawPixel(tx, ty - 2, th::p15(fireHi));
  }
  glow(g, 60, 48, 14, th::mix(fire, 0, 0.4f), 0.6f);
  for (int a = 180; a <= 360; a += 3) {                                                     // the arch at the far end
    float r = a * PI / 180;
    int x = 60 + (int)(12 * cosf(r)), y = 41 + (int)(11 * sinf(r));
    g.fillRect(x, y, 2, 2, th::p15(mortar));
  }
}

// ---------------------------------------------------------------- THRONE HALL: gothic windows, moon shafts
static void throne(LovyanGFX &g) {
  static const uint32_t st[3] = {C(18, 10, 34), C(34, 18, 58), C(14, 8, 24)};
  vgrad(g, 0, 0, W, 108, st, 3);
  static const int WX[3] = {14, 46, 78};
  for (int w = 0; w < 3; w++) {
    int x0 = WX[w];
    float X[7] = {(float)x0, (float)x0, x0 + 6.0f, x0 + 13.0f, x0 + 20.0f, x0 + 26.0f, x0 + 26.0f};
    float Y[7] = {70, 28, 16, 10, 16, 28, 70};
    fill(g, X, Y, 7, C(200, 210, 255), C(90, 80, 200), 10, 70);
    g.drawFastVLine(x0 + 13, 12, 59, th::p15(C(30, 20, 50)));                                // mullions
    g.drawFastHLine(x0 + 1, 40, 25, th::p15(C(30, 20, 50)));
  }
  for (int w = 0; w < 3; w++) {                                                             // light shafts
    int x0 = WX[w];
    for (int y = 70; y < 108; y++) {
      float spread = (y - 70) * 0.6f;
      for (int x = (int)(x0 - spread * 0.5f); x < (int)(x0 + 26 + spread); x++)
        if (x >= 0 && x < W && (x + y) % 2 == 0 && th::BAYER[y & 3][x & 3] < 6)
          g.drawPixel(x, y, th::p15(th::mix(rd(g, x, y), C(170, 170, 255), 0.35f)));
    }
  }
  static const int PX[4] = {0, 40, 72, 108};
  for (int p = 0; p < 4; p++) {                                                             // pillars
    rectI(g, PX[p], 4, PX[p] + 5, 108, C(26, 16, 42));
    g.drawFastVLine(PX[p] + 1, 4, 104, th::p15(C(60, 40, 90)));
  }
  static const int BXs[2] = {6, 102};
  for (int b = 0; b < 2; b++) {                                                             // banners, gold crosses
    int x0 = BXs[b];
    rectI(g, x0, 8, x0 + 10, 44, C(110, 30, 140));
    g.fillTriangle(x0, 44, x0 + 5, 50, x0 + 10, 44, th::p15(C(110, 30, 140)));
    rectI(g, x0 + 4, 14, x0 + 6, 30, C(255, 204, 0));
    rectI(g, x0 + 1, 18, x0 + 9, 20, C(255, 204, 0));
  }
}

// ---------------------------------------------------------------- CRYSTALS: a cave of glowing crystals
static void crystals(LovyanGFX &g) {
  static const uint32_t st[3] = {C(6, 8, 22), C(14, 16, 40), C(8, 6, 20)};
  vgrad(g, 0, 0, W, 108, st, 3);
  for (int i = 0; i < 70; i++) {                                                            // rock lumps
    uint32_t h = th::hash32(i * 7919u + 13);
    int cx = h % 120, cy = (h >> 8) % 108, r = 6 + (h >> 16) % 12;
    g.fillEllipse(cx, cy, r, (int)(r * 0.7f), th::p15(th::mix(C(20, 22, 46), C(34, 30, 62), ((h >> 20) % 8) / 8.0f)));
  }
  struct Cr { float cx, cy, w, h, ang; uint32_t col; };
  static const Cr S[7] = {{10, 100, 9, 34, 0.15f, 0x5ADCFF}, {24, 104, 6, 22, -0.2f, 0xAA6EFF}, {104, 102, 8, 30, -0.1f, 0xAA6EFF},
                          {94, 104, 5, 18, 0.3f, 0x5ADCFF}, {60, 18, 5, 16, 3.14f, 0x5ADCFF}, {30, 10, 4, 14, 3.0f, 0xAA6EFF},
                          {88, 14, 6, 18, 3.3f, 0xAA6EFF}};
  for (const Cr &c : S) glow(g, c.cx + sinf(c.ang) * c.h * 0.5f, c.cy - cosf(c.ang) * c.h * 0.5f, c.h * 0.9f, c.col, 0.45f);
  for (const Cr &c : S) {
    float ca = cosf(c.ang), sa = sinf(c.ang);
    auto rx = [&](float x, float y) { return c.cx + x * ca - y * sa; };
    auto ry = [&](float x, float y) { return c.cy + x * sa + y * ca; };
    float X1[5] = {rx(-c.w, 0), rx(-c.w * 0.7f, -c.h * 0.8f), rx(0, -c.h), rx(c.w * 0.7f, -c.h * 0.8f), rx(c.w, 0)};
    float Y1[5] = {ry(-c.w, 0), ry(-c.w * 0.7f, -c.h * 0.8f), ry(0, -c.h), ry(c.w * 0.7f, -c.h * 0.8f), ry(c.w, 0)};
    fill(g, X1, Y1, 5, th::mix(c.col, 0, 0.35f));
    float X2[5] = {rx(-c.w * 0.2f, 0), rx(-c.w * 0.15f, -c.h * 0.85f), rx(0, -c.h), rx(c.w * 0.7f, -c.h * 0.8f), rx(c.w, 0)};
    float Y2[5] = {ry(-c.w * 0.2f, 0), ry(-c.w * 0.15f, -c.h * 0.85f), ry(0, -c.h), ry(c.w * 0.7f, -c.h * 0.8f), ry(c.w, 0)};
    fill(g, X2, Y2, 5, c.col);
    g.drawLine(rx(0, -c.h * 0.95f), ry(0, -c.h * 0.95f), rx(0, -2), ry(0, -2), th::p15(th::mix(c.col, 0xFFFFFF, 0.6f)));
  }
}

// ---------------------------------------------------------------- CASTLE: an anime castle on a cliff (dusk / blue)
static void castle(LovyanGFX &g, bool blue) {
  static const uint32_t stB[3] = {C(20, 26, 70), C(60, 70, 150), C(150, 130, 200)};
  static const uint32_t stP[3] = {C(30, 12, 60), C(110, 40, 130), C(240, 130, 160)};
  vgrad(g, 0, 0, W, 108, blue ? stB : stP, 3);
  for (int i = 0; i < 24; i++) {
    uint32_t h = th::hash32(i * 2654435761u + 7);
    g.drawPixel(h % 120, (h >> 8) % 40, th::p15(i % 6 == 0 ? 0xFFFFFF : C(200, 190, 230)));
  }
  uint32_t mc = blue ? C(230, 236, 255) : C(255, 236, 220);
  glow(g, 92, 26, 22, mc, 0.5f);
  g.fillCircle(92, 26, 10, th::p15(mc));
  uint32_t cl[2] = {blue ? C(60, 80, 150) : C(90, 60, 140), blue ? C(44, 60, 120) : C(70, 40, 110)};
  for (int b = 0; b < 2; b++) {                                                             // cloud bands
    int y0 = b ? 60 : 52;
    for (int x = 0; x < W; x++) g.drawFastVLine(x, y0 + (int)(3 * sinf(x * 0.12f + y0)), 4, th::p15(cl[b]));
  }
  uint32_t sil = blue ? C(14, 18, 40) : C(26, 12, 40), lit = C(255, 200, 120);
  float CX[7] = {0, 0, 20, 34, 40, 120, 120}, CY[7] = {108, 86, 80, 84, 78, 74, 108};
  fill(g, CX, CY, 7, sil);                                                                  // the cliff
  static const int T[5][4] = {{30, 10, 42, 16}, {44, 16, 30, 22}, {64, 12, 38, 16}, {80, 8, 50, 12}, {18, 6, 56, 10}};
  for (int t = 0; t < 5; t++) {
    int x0 = T[t][0], w = T[t][1], top = T[t][2], sp = T[t][3];
    rectI(g, x0, top, x0 + w, 84, sil);
    g.fillTriangle(x0 - 1, top, x0 + w / 2, top - sp, x0 + w + 1, top, th::p15(sil));
    for (int k = 0; k < 2; k++)
      if ((x0 + k) % 4) rectI(g, x0 + w / 2 - 1, top + 8 + k * 10, x0 + w / 2, top + 10 + k * 10, lit);
  }
  rectI(g, 40, 60, 70, 84, sil);
}

// ---------------------------------------------------------------- the 80s: grid floors, striped suns, wireframe hills
static void grid(LovyanGFX &g, uint32_t line, uint32_t top, uint32_t bot) {
  uint32_t st[2] = {top, bot};
  vgrad(g, 0, HZ, W, 108, st, 2);
  for (int k = -14; k <= 14; k++) g.drawLine(60 + k * 3, HZ, 60 + k * 22, 108, th::p15(line));
  for (int j = 0; j < 12; j++) {
    float y = HZ + 44.0f / (j + 1) * 0.9f;
    if (y > HZ && y < 108) g.drawFastHLine(0, (int)y, W, th::p15(line));
  }
  g.drawFastHLine(0, HZ, W, th::p15(th::mix(line, 0xFFFFFF, 0.5f)));
}

static void sun(LovyanGFX &g, int cx, int cy, int r, uint32_t top, uint32_t bot, bool stripes = true) {
  for (int y = cy - r; y <= cy + r; y++)
    for (int x = cx - r; x <= cx + r; x++) {
      if ((x - cx) * (x - cx) + (y - cy) * (y - cy) > r * r || y < 0 || y >= 108) continue;
      int dy = y - cy, m = ((dy % 5) + 5) % 5, fd = dy >= 0 ? dy / 6 : -((-dy + 5) / 6);   // Python's % and //
      if (stripes && y > cy - 2 && m < 1 + fd) continue;                                    // the slits
      g.drawPixel(x, y, th::p15(th::mix(top, bot, roundf((y - (cy - r)) / (2.0f * r) * 6) / 6)));
    }
}

static void hills(LovyanGFX &g, uint32_t col, uint32_t fillC) {
  static const float A[2][6][2] = {{{0, 0}, {10, -12}, {22, -4}, {34, -16}, {44, -6}, {52, 0}},
                                   {{68, 0}, {78, -10}, {90, -18}, {102, -7}, {112, -13}, {120, 0}}};
  for (int h = 0; h < 2; h++) {
    float X[6], Y[6];
    for (int i = 0; i < 6; i++) { X[i] = A[h][i][0]; Y[i] = HZ + A[h][i][1]; }
    fill(g, X, Y, 6, fillC);
    for (int i = 0; i < 5; i++) g.drawLine(X[i], Y[i], X[i + 1], Y[i + 1], th::p15(col));
    for (int i = 1; i < 5; i++) g.drawLine(X[i], Y[i], X[i] + (i % 2 ? 3 : -3), HZ, th::p15(th::mix(col, fillC, 0.5f)));
  }
}

static void palm(LovyanGFX &g, int x, int y, int h, uint32_t col) {
  uint32_t c = th::p15(col);
  for (int k = 0; k < h; k++) {
    int px = x + (int)(3 * sinf((float)k / h * 1.6f));
    g.drawPixel(px, y - k, c);
    g.drawPixel(px + 1, y - k, c);
  }
  int tx = x + (int)(3 * sinf(1.6f)), ty = y - h;
  static const float AN[6] = {-2.6f, -2.0f, -1.2f, -0.5f, 0.2f, 0.9f};
  for (float a : AN)
    for (int r = 1; r < 12; r++) {
      int fx = tx + (int)(r * cosf(a)), fy = ty + (int)(r * sinf(a) * 0.6f + r * r * 0.04f);
      g.drawPixel(fx, fy, c);
      g.drawPixel(fx, fy + 1, c);
    }
}

static void outrun(LovyanGFX &g) {
  static const uint32_t st[3] = {C(10, 4, 30), C(60, 10, 90), C(200, 40, 140)};
  vgrad(g, 0, 0, W, HZ, st, 3);
  sun(g, 60, 46, 22, C(255, 230, 80), C(255, 40, 140));
  hills(g, C(255, 60, 200), C(30, 6, 50));
  grid(g, C(255, 40, 200), C(40, 4, 60), C(10, 0, 20));
}

static void vaporwave(LovyanGFX &g) {
  static const uint32_t st[3] = {C(250, 170, 210), C(255, 200, 190), C(140, 230, 230)};
  vgrad(g, 0, 0, W, HZ, st, 3);
  sun(g, 60, 44, 18, C(255, 250, 200), C(255, 130, 190));
  static const uint32_t fl[2] = {C(120, 220, 230), C(90, 60, 160)};
  vgrad(g, 0, HZ, W, 108, fl, 2);
  for (int y = HZ; y < 108; y++) {                                                          // checker floor
    float z = 40.0f / max(1, y - HZ + 4);
    for (int x = 0; x < W; x++)
      if (((int)floorf((x - 60) * z * 0.25f) + (int)floorf(z * 6)) % 2)
        g.drawPixel(x, y, th::p15(th::mix(C(255, 150, 210), 0, fminf(0.4f, z * 0.1f))));
  }
  palm(g, 14, 96, 34, C(60, 20, 80));
  palm(g, 104, 100, 30, C(60, 20, 80));
}

static void cyberCity(LovyanGFX &g) {
  static const uint32_t st[3] = {C(8, 6, 24), C(30, 14, 60), C(70, 20, 90)};
  vgrad(g, 0, 0, W, 108, st, 3);
  glow(g, 60, 70, 60, C(255, 40, 160), 0.35f);
  static const int L[2][4] = {{0x1A143C, 30, 60, 10}, {0x0E0A22, 44, 80, 14}};
  for (int layer = 0; layer < 2; layer++) {
    int x = -4 + layer * 5, i = 0;
    while (x < W) {
      uint32_t h = th::hash32(i * 977u + layer * 31);
      int bw = L[layer][3] - 3 + h % 7, top = L[layer][1] + (h >> 8) % (L[layer][2] - L[layer][1]);
      rectI(g, x, top, x + bw, 108, L[layer][0]);
      for (int wy = top + 3; wy < 104; wy += 4)                                             // windows
        for (int wx = x + 2; wx < x + bw - 1; wx += 3) {
          uint32_t hh = th::hash32(wx * 31u + wy * 17u + layer);
          if (hh % 5 == 0 && wx >= 0 && wx < W) g.drawPixel(wx, wy, th::p15(hh % 2 ? C(80, 230, 255) : C(255, 80, 200)));
        }
      if (h % 3 == 0) rectI(g, x + 2, top + 6, x + bw - 2, top + 9, h % 2 ? C(255, 60, 180) : C(60, 230, 255));   // neon sign
      x += bw + 1;
      i++;
    }
  }
  for (int i = 0; i < 70; i++) {                                                            // rain
    uint32_t h = th::hash32(i * 2654435761u);
    int x = h % 120, y = (h >> 8) % 100;
    g.drawLine(x, y, x - 2, y + 6, th::p15(C(120, 140, 200)));
  }
}

static void matrix(LovyanGFX &g) {
  g.fillRect(0, 0, W, 108, th::p15(C(0, 6, 2)));
  for (int col = 0; col < W; col += 4) {
    int head = th::hash32(col * 97u + 3) % 140 - 20;
    for (int k = 0; k < 40; k += 4) {
      int y = head - k;
      if (y < 0 || y >= 106) continue;
      uint32_t gl = th::hash32(col * 13u + y * 7u);
      uint32_t c = k == 0 ? C(200, 255, 200) : th::mix(C(40, 255, 90), C(0, 40, 10), k / 40.0f);
      for (int b = 0; b < 6; b++)
        if ((gl >> b) & 1) g.drawPixel(col + b % 3, y + b / 3, th::p15(c));
    }
  }
  static const uint32_t st[2] = {C(0, 6, 2), C(0, 30, 10)};
  vgrad(g, 0, 96, W, 108, st, 2);
}

static void tron(LovyanGFX &g) {
  static const uint32_t st[3] = {C(0, 4, 16), C(0, 20, 50), C(20, 90, 160)};
  vgrad(g, 0, 0, W, HZ, st, 3);
  glow(g, 60, HZ, 50, C(60, 200, 255), 0.5f);
  hills(g, C(80, 220, 255), C(0, 12, 30));
  grid(g, C(40, 190, 255), C(0, 20, 50), C(0, 4, 14));
}

static void neonPink(LovyanGFX &g) {
  static const uint32_t st[3] = {C(40, 0, 50), C(120, 20, 120), C(255, 90, 180)};
  vgrad(g, 0, 0, W, HZ, st, 3);
  sun(g, 60, 50, 16, C(255, 200, 240), C(200, 40, 255));
  grid(g, C(255, 120, 230), C(60, 10, 80), C(20, 0, 30));
  palm(g, 12, 100, 36, C(20, 0, 26));
  palm(g, 108, 104, 40, C(20, 0, 26));
}

static void inferno(LovyanGFX &g) {
  static const uint32_t st[3] = {C(6, 0, 0), C(90, 6, 6), C(255, 80, 20)};
  vgrad(g, 0, 0, W, HZ, st, 3);
  sun(g, 60, 48, 22, C(255, 240, 60), C(255, 60, 20));
  hills(g, C(255, 200, 40), C(16, 0, 0));
  grid(g, C(255, 40, 30), C(40, 0, 0), C(6, 0, 0));
}

static void draw(LovyanGFX &g, int id) {
  g.fillRect(0, 0, 120, 120, th::BLACK);
  switch (id) {
    case 1: dungeon(g, false); break;
    case 2: dungeon(g, true); break;
    case 3: throne(g); break;
    case 4: crystals(g); break;
    case 5: castle(g, false); break;
    case 6: castle(g, true); break;
    case 7: outrun(g); break;
    case 8: vaporwave(g); break;
    case 9: cyberCity(g); break;
    case 10: matrix(g); break;
    case 11: tron(g); break;
    case 12: neonPink(g); break;
    case 13: inferno(g); break;
    default: night(g);
  }
}

// The chosen scene (NVS "ui"/"bg"); dirty = the cached sky must be redrawn
static int sel = 0;
static bool dirty = true;
// The menu theme (NVS "ui"/"theme"): -1 = MATCH SCENE (each scene brings its own), else a fixed th::THEMES entry
static const uint8_t SCENE_THEME[N_SCENES] = {0, 2, 4, 3, 5, 6, 4, 7, 8, 9, 10, 11, 12, 1};
static int theme = -1;
static void applyTheme() { th::applyTheme(theme < 0 ? SCENE_THEME[sel] : theme); }
static const char *themeName() { return theme < 0 ? "MATCH SCENE" : th::THEMES[theme].name; }
static void load() {
  Preferences pr;
  pr.begin("ui", true);
  sel = constrain(pr.getInt("bg", 0), 0, N_SCENES - 1);
  theme = constrain(pr.getInt("theme", -1), -1, th::N_THEMES - 1);
  pr.end();
  applyTheme();
  dirty = true;
}
static void setTheme(int id) {
  int n = th::N_THEMES + 1;
  theme = ((id + 1) % n + n) % n - 1;
  applyTheme();
  dirty = true;
  Preferences pr;
  pr.begin("ui", false);
  pr.putInt("theme", theme);
  pr.end();
}
static void set(int id) {
  sel = ((id % N_SCENES) + N_SCENES) % N_SCENES;
  applyTheme();
  dirty = true;
  Preferences pr;
  pr.begin("ui", false);
  pr.putInt("bg", sel);
  pr.end();
}

}  // namespace bg
