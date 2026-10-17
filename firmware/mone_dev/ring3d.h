// MODE ring (the boot screen; EXIT steps back to it): five low-poly 3D icons turning on a ring over the Castlevania
// night, Crash-Bandicoot-2 style. Flat shading + specular, 15-bit colour, painter's sort, scanline fill.
// Approved mockup: tc_mone/research/menu3d.gif (its Python twin, menu3d_mock.py, builds the same meshes).
#pragma once

namespace r3 {

struct V3 { float x, y, z; };
static inline V3 vadd(V3 a, V3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
static inline V3 vsub(V3 a, V3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
static inline V3 vmul(V3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
static inline float vdot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline V3 vnorm(V3 a) { float l = sqrtf(vdot(a, a)); return l > 1e-9f ? vmul(a, 1 / l) : a; }

const V3 CAM = {0.0f, 1.9f, -7.2f};
const float PITCH = 0.22f, F = 100.0f, RING = 2.7f, FLOOR_Y = -1.15f;
static V3 LIGHT;                                  // set in build()

static V3 toCam(V3 p) {                           // world -> camera (looking down a little)
  V3 q = vsub(p, CAM);
  float c = cosf(-PITCH), s = sinf(-PITCH);
  return {q.x, q.y * c - q.z * s, q.y * s + q.z * c};
}
static void project(V3 q, float &x, float &y) {
  float z = q.z > 0.1f ? q.z : 0.1f;
  x = 60 + F * q.x / z;
  y = 60 - F * q.y / z;
}

// ---- meshes: one vertex pool, every face owns its run of vertices (no sharing: flat shading)
const int MAXV = 1300, MAXF = 300;
struct Face { uint16_t first; uint8_t n; float shine, bias; uint32_t col; int16_t parent; };
static V3 pool[MAXV];
static Face faces[MAXF];
static int nPool = 0, nFace = 0;
static float curBias = 0;                         // parts mounted on a bigger face draw over it...
static int curParent = -1;                        // ...and only while that face is visible (no pop-through)
struct Mesh { uint16_t f0, nf; };

static void face(const V3 *v, int n, uint32_t col, float shine, float bias) {
  if (nFace >= MAXF || nPool + n > MAXV) return;
  faces[nFace++] = {(uint16_t)nPool, (uint8_t)n, shine, bias, col, (int16_t)curParent};
  for (int i = 0; i < n; i++) pool[nPool++] = v[i];
}
static void quad(V3 a, V3 b, V3 c, V3 d, uint32_t col, float shine) {
  V3 v[4] = {a, b, c, d};
  face(v, 4, col, shine, curBias);
}
static void box(float x0, float y0, float z0, float x1, float y1, float z1, uint32_t col, float shine) {
  V3 P[8] = {{x0, y0, z0}, {x1, y0, z0}, {x1, y1, z0}, {x0, y1, z0}, {x0, y0, z1}, {x1, y0, z1}, {x1, y1, z1}, {x0, y1, z1}};
  quad(P[0], P[1], P[2], P[3], col, shine);
  quad(P[5], P[4], P[7], P[6], col, shine);
  quad(P[4], P[0], P[3], P[7], col, shine);
  quad(P[1], P[5], P[6], P[2], col, shine);
  quad(P[3], P[2], P[6], P[7], col, shine);
  quad(P[4], P[5], P[1], P[0], col, shine);
}
// axis 'y': stands on (cx, cy, cz), height h; axis 'z': a disc facing the camera from z = cz back to cz + h
static void cylinder(float cx, float cy, float cz, float r, float h, int n, uint32_t col, float shine, char axis,
                     uint32_t topcol) {
  V3 r0[24], r1[24];
  for (int i = 0; i < n; i++) {
    float a = 2 * PI * i / n, c = r * cosf(a), s = r * sinf(a);
    if (axis == 'y') { r0[i] = {cx + c, cy, cz + s}; r1[i] = {cx + c, cy + h, cz + s}; }
    else { r0[i] = {cx + c, cy + s, cz}; r1[i] = {cx + c, cy + s, cz + h}; }
  }
  for (int i = 0; i < n; i++) quad(r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i], col, shine);
  V3 cap[24];
  if (axis == 'y') {
    face(r1, n, topcol, shine, curBias);                       // top, same winding as box() faces
    for (int i = 0; i < n; i++) cap[i] = r0[n - 1 - i];
    face(cap, n, col, shine, curBias);
  } else {
    face(r0, n, topcol, shine, curBias);                       // front
    for (int i = 0; i < n; i++) cap[i] = r1[n - 1 - i];
    face(cap, n, col, shine, curBias);
  }
}

static Mesh begin() { curBias = 0; curParent = -1; return {(uint16_t)nFace, 0}; }
static void end(Mesh &m) { m.nf = nFace - m.f0; }

static const uint32_t CHROME = 0xC4C8D6;
static Mesh buildCog() {                          // SETTINGS: a chrome gear, square teeth, a hole
  Mesh m = begin();
  const int T = 8;
  const float ro = 1.0f, ri = 0.78f, rh = 0.34f, t = 0.32f;
  static const float FR[5] = {0.0f, 0.07f, 0.43f, 0.5f, 0.75f};
  V3 out[T * 5], hole[12];
  int no = 0;
  for (int k = 0; k < T; k++)
    for (int j = 0; j < 5; j++) {
      float a = 2 * PI * (k + FR[j]) / T, r = (j == 1 || j == 2) ? ro : ri;
      out[no++] = {r * cosf(a), r * sinf(a), 0};
    }
  for (int i = 0; i < 12; i++) hole[i] = {rh * cosf(2 * PI * i / 12), rh * sinf(2 * PI * i / 12), 0};
  for (int i = 0; i < no; i++) {                  // rim
    V3 a = out[i], b = out[(i + 1) % no];
    quad({a.x, a.y, -t / 2}, {b.x, b.y, -t / 2}, {b.x, b.y, t / 2}, {a.x, a.y, t / 2}, CHROME, 0.9f);
  }
  for (int i = 0; i < 12; i++) {                  // hole wall
    V3 a = hole[i], b = hole[(i + 1) % 12];
    quad({b.x, b.y, -t / 2}, {a.x, a.y, -t / 2}, {a.x, a.y, t / 2}, {b.x, b.y, t / 2}, 0x5A5C68, 0.5f);
  }
  V3 f[T * 5];
  for (int side = 0; side < 2; side++) {          // faces: the outline as one concave polygon, the hole over it
    float z = side ? t / 2 : -t / 2;
    for (int i = 0; i < no; i++) f[i] = {out[side ? no - 1 - i : i].x, out[side ? no - 1 - i : i].y, z};
    face(f, no, CHROME, 0.9f, 0);
    curParent = nFace - 1;
    float hz = side ? z + 0.001f : z - 0.001f;
    for (int i = 0; i < 12; i++) f[i] = {hole[side ? 11 - i : i].x, hole[side ? 11 - i : i].y, hz};
    face(f, 12, 0x221E28, 0.0f, -0.05f);
    curParent = -1;
  }
  end(m);
  return m;
}

static Mesh buildPedal() {                        // PEDAL: a red stompbox with a white '69 (Fulltone style)
  Mesh m = begin();
  box(-0.62f, -0.22f, -0.85f, 0.62f, 0.18f, 0.85f, 0xD61E18, 0.35f);
  curParent = nFace - 2;                          // the top face
  for (int i = 0; i < 3; i++) {                   // knobs: black skirts, cream caps
    float x = -0.38f + 0.38f * i;
    curBias = -0.6f;
    cylinder(x, 0.18f, 0.5f, 0.19f, 0.12f, 10, 0x18161A, 0.3f, 'y', 0x242228);
    curBias = -0.7f;
    cylinder(x, 0.30f, 0.5f, 0.13f, 0.14f, 10, 0x28262C, 0.4f, 'y', 0xECE2C8);
  }
  curBias = -0.6f;
  cylinder(0.0f, 0.18f, -0.52f, 0.17f, 0.1f, 8, 0xC8C8D2, 0.9f, 'y', 0xC8C8D2);   // footswitch
  box(0.42f, 0.18f, -0.30f, 0.50f, 0.25f, -0.22f, 0xFF3C28, 0.2f);               // LED
  // "69": 7-segment blocks lying on the top face. Segments: a top, b/c right, d bottom, e/f left, g middle
  const float W = 0.24f, H = 0.40f, TT = 0.075f, cz = 0.03f, y = 0.183f;
  static const char *DIG[2] = {"afgedc", "abcdfg"};
  for (int d = 0; d < 2; d++) {
    float cx = d ? 0.17f : -0.17f;
    for (const char *s = DIG[d]; *s; s++) {
      float x0, x1, z0, z1;
      if (*s == 'a' || *s == 'g' || *s == 'd') {
        float zc = cz + (*s == 'a' ? H / 2 - TT / 2 : *s == 'd' ? -H / 2 + TT / 2 : 0);
        x0 = cx - W / 2; x1 = cx + W / 2; z0 = zc - TT / 2; z1 = zc + TT / 2;
      } else {
        bool right = *s == 'b' || *s == 'c', upper = *s == 'b' || *s == 'f';
        x0 = right ? cx + W / 2 - TT : cx - W / 2; x1 = x0 + TT;
        z0 = upper ? cz : cz - H / 2; z1 = upper ? cz + H / 2 : cz;
      }
      quad({x0, y, z0}, {x1, y, z0}, {x1, y, z1}, {x0, y, z1}, 0xF0ECE0, 0.2f);
    }
  }
  end(m);
  return m;
}

static Mesh buildBible() {                        // SYSTEM: a black bible, gold cross, pages on the right
  Mesh m = begin();
  box(-0.8f, -1.05f, -0.22f, 0.8f, 1.05f, 0.22f, 0x28222E, 0.25f);
  int cover = nFace - 6;
  box(-0.72f, -0.97f, -0.20f, 0.86f, 0.97f, 0.20f, 0xE8DCC0, 0.0f);
  curBias = -0.3f;
  curParent = cover;
  box(-0.07f, -0.65f, -0.26f, 0.07f, 0.65f, -0.22f, 0xFFCC00, 0.9f);
  box(-0.38f, 0.18f, -0.26f, 0.38f, 0.32f, -0.22f, 0xFFCC00, 0.9f);
  end(m);
  return m;
}

static Mesh buildVinyl() {                        // PRESETS: a record
  Mesh m = begin();
  cylinder(0, 0, 0, 1.0f, 0.08f, 20, 0x18161C, 0.8f, 'z', 0x18161C);
  curBias = -0.2f;
  curParent = nFace - 2;                          // the disc's front
  cylinder(0, 0, -0.01f, 0.36f, 0.1f, 12, 0xC81E28, 0.3f, 'z', 0xC81E28);
  cylinder(0, 0, -0.02f, 0.06f, 0.12f, 6, 0x0A080C, 0.0f, 'z', 0x0A080C);
  end(m);
  return m;
}

// ---- per frame: transform, cull, shade, sort, fill
struct Item { float depth; int16_t face; uint16_t pp; uint32_t col; };   // face < 0: a sprite / crown (see below)
const int MAXI = 340, MAXP = 1300;
static Item items[MAXI];
static float px[MAXP], py[MAXP];
static int nItem = 0, nP = 0;

static uint32_t shade(uint32_t col, V3 n, V3 view, float shine, float dim) {
  float lam = fmaxf(0.0f, vdot(n, LIGHT));
  V3 refl = vsub(vmul(n, 2 * vdot(n, LIGHT)), LIGHT);
  float sp = fmaxf(0.0f, vdot(refl, view));
  sp = powf(sp, 12) * shine;
  int r = ((col >> 16) & 255) * (0.28f + 0.8f * lam) + 255 * sp;
  int g = ((col >> 8) & 255) * (0.28f + 0.8f * lam) + 255 * sp;
  int b = (col & 255) * (0.28f + 0.8f * lam) + 255 * sp;
  uint32_t c = (uint32_t)min(r, 255) << 16 | (uint32_t)min(g, 255) << 8 | (uint32_t)min(b, 255);
  return th::p15(th::mix(c, 0, dim));
}

static uint8_t faceVis[MAXF];

static void drawMesh(const Mesh &m, V3 pos, float yaw, float tilt, float scale, float dim) {
  float cy = cosf(yaw), sy = sinf(yaw), ct = cosf(tilt), st = sinf(tilt);
  V3 w[48];
  for (int f = m.f0; f < m.f0 + m.nf; f++) {
    const Face &fc = faces[f];
    faceVis[f] = 0;
    if (fc.parent >= 0 && !faceVis[fc.parent]) continue;              // its face is turned away
    if (nItem >= MAXI || nP + fc.n > MAXP) return;
    for (int k = 0; k < fc.n; k++) {
      V3 v = pool[fc.first + k];
      v = {v.x, v.y * ct - v.z * st, v.y * st + v.z * ct};           // tilt (x axis)
      v = {v.x * cy + v.z * sy, v.y, -v.x * sy + v.z * cy};           // yaw (y axis)
      w[k] = vadd(vmul(v, scale), pos);
    }
    float nx = 0, ny = 0, nz = 0;                                      // Newell normal (concave faces too)
    for (int k = 0; k < fc.n; k++) {
      V3 a = w[k], b = w[(k + 1) % fc.n];
      nx += (a.y - b.y) * (a.z + b.z); ny += (a.z - b.z) * (a.x + b.x); nz += (a.x - b.x) * (a.y + b.y);
    }
    V3 n = vnorm({-nx, -ny, -nz});
    V3 c3 = vmul(vadd(vadd(w[0], w[1]), w[2]), 1.0f / 3);
    V3 view = vnorm(vsub(CAM, c3));
    if (vdot(n, view) <= 0) continue;                                  // back face
    faceVis[f] = 1;
    float depth = 0;
    for (int k = 0; k < fc.n; k++) {
      V3 q = toCam(w[k]);
      depth += q.z;
      project(q, px[nP + k], py[nP + k]);
    }
    items[nItem++] = {depth / fc.n + fc.bias, (int16_t)f, (uint16_t)nP, shade(fc.col, n, view, fc.shine, dim)};
    nP += fc.n;
  }
}

static void fillPoly(const float *x, const float *y, int n, uint32_t col) {   // even-odd scanline fill
  float ymin = y[0], ymax = y[0];
  for (int i = 1; i < n; i++) { ymin = fminf(ymin, y[i]); ymax = fmaxf(ymax, y[i]); }
  int y0 = max(0, (int)ceilf(ymin - 0.5f)), y1 = min(119, (int)floorf(ymax - 0.5f));
  float xs[48];
  for (int yy = y0; yy <= y1; yy++) {
    float sy = yy + 0.5f;
    int k = 0;
    for (int i = 0, j = n - 1; i < n && k < 48; j = i++)
      if ((y[i] <= sy) != (y[j] <= sy)) xs[k++] = x[j] + (sy - y[j]) * (x[i] - x[j]) / (y[i] - y[j]);
    for (int i = 1; i < k; i++)
      for (int j = i; j > 0 && xs[j - 1] > xs[j]; j--) { float t = xs[j]; xs[j] = xs[j - 1]; xs[j - 1] = t; }
    for (int p = 0; p + 1 < k; p += 2) {
      int xa = max(0, (int)ceilf(xs[p] - 0.5f)), xb = min(119, (int)floorf(xs[p + 1] - 0.5f));
      if (xb >= xa) th::cv.drawFastHLine(xa, yy, xb - xa + 1, col);
    }
  }
}

// A pixel sprite spun like a Crash pickup: squashed by cos(spin), darker from behind
static void billboard(const spr::Sprite &s, float cx, float cy, float size, float spin, float dim) {
  float c = cosf(spin), sx = size / s.w * c, sy = size / s.h;
  for (int j = 0; j < s.h; j++)
    for (int i = 0; i < s.w; i++) {
      char ch = s.rows[j][i];
      const char *k = ch == '.' ? nullptr : strchr(s.keys, ch);
      if (!k) continue;
      uint32_t col = s.pal[k - s.keys];
      if (c < 0) col = th::mix(col, 0x28140A, 0.2f);
      col = th::p15(th::mix(col, 0, dim));
      float xa = cx + (i - s.w / 2.0f) * sx, xb = cx + (i + 1 - s.w / 2.0f) * sx;
      int x0 = (int)floorf(fminf(xa, xb) + 0.5f), x1 = (int)floorf(fmaxf(xa, xb) + 0.5f);
      int y0 = (int)floorf(cy + (j - s.h / 2.0f) * sy + 0.5f), y1 = (int)floorf(cy + (j + 1 - s.h / 2.0f) * sy + 0.5f);
      if (x1 > x0 && y1 > y0) th::cv.fillRect(x0, y0, x1 - x0, y1 - y0, col);
    }
}

static void crown(float x, float y) {             // the mode that is playing
  float X[7] = {x - 5, x - 5, x - 2, x, x + 2, x + 5, x + 5}, Y[7] = {y + 2, y - 3, y, y - 4, y, y - 3, y + 2};
  fillPoly(X, Y, 7, th::p15(th::YELLOW));
  for (int i = 0; i < 7; i++) th::cv.drawLine(X[i], Y[i], X[(i + 1) % 7], Y[(i + 1) % 7], th::BLACK);
}

// ---- the night: sky, moon and castle cached in a sprite once; stars twinkle on top every frame
static LGFX_Sprite sky(&tft);
static bool skyOk = false;
static void drawNight(LovyanGFX &g) {
  static const uint32_t st[3] = {0x06061A, 0x140C30, 0x3A1640};
  for (int y = 0; y < 108; y++)
    for (int x = 0; x < 120; x++) g.drawPixel(x, y, th::gradAt(x, y, y / 100.0f, st, 3));
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

static Mesh M_COG, M_PEDAL, M_BIBLE, M_VINYL;
static bool built = false;
static void build() {
  if (built) return;
  LIGHT = vnorm({-0.5f, 0.8f, -0.6f});
  M_COG = buildCog(); M_PEDAL = buildPedal(); M_BIBLE = buildBible(); M_VINYL = buildVinyl();
  sky.setColorDepth(16);
  skyOk = sky.createSprite(120, 120) != nullptr;
  if (skyOk) drawNight(sky);
  built = true;
}

// The ring. pos = which item faces front (animated, may be fractional), active = the playing mode (crown),
// arrive 0..1 = the front item's arrival spin, names[5] = item titles.
static void drawRing(uint32_t now, float pos, int active, float arrive, const char *const *names) {
  build();
  if (skyOk) sky.pushSprite(&th::cv, 0, 0); else drawNight(th::cv);
  for (int i = 0; i < 30; i++) {
    uint32_t h = th::hash32(i * 2654435761u);
    th::cv.drawPixel(h % 120, (h >> 8) % 60, th::p15((i + now / 300) % 7 == 0 ? th::WHITE : 0x6E6496));
  }
  float tx[49], ty[49];                           // the glowing floor ring
  for (int i = 0; i <= 48; i++) {
    float a = 2 * PI * i / 48;
    project(toCam({RING * cosf(a), FLOOR_Y, RING * sinf(a)}), tx[i], ty[i]);
  }
  for (int i = 0; i < 48; i++)
    for (int o = -1; o <= 1; o++) th::cv.drawLine(tx[i], ty[i] + o, tx[i + 1], ty[i + 1] + o, th::p15(th::EMBER));
  for (int i = 0; i < 48; i++) th::cv.drawLine(tx[i], ty[i], tx[i + 1], ty[i + 1], th::p15(th::ORANGE));
  nItem = nP = 0;
  struct Spr { float depth, x, y, size, spin, dim; int kind; } sp[6];
  int nsp = 0;
  const Mesh *MESH[5] = {nullptr, &M_VINYL, &M_PEDAL, &M_COG, &M_BIBLE};   // 0 = the cat (a sprite)
  static const float TILT[5] = {0, 0.25f, -0.85f, 0, 0};
  for (int i = 0; i < 5; i++) {
    float a = -PI / 2 + (i - pos) * 2 * PI / 5;
    V3 p0 = {RING * cosf(a), 0, RING * sinf(a)};
    float wrap = fmodf(i - pos + 2.5f, 5.0f);
    if (wrap < 0) wrap += 5;
    float front = fmaxf(0.0f, 1 - fabsf(wrap - 2.5f));
    float dim = (p0.z + RING) / (2 * RING) * 0.45f;
    float bob = 0.08f * sinf(now * 0.004f + i);
    V3 p = {p0.x, bob + 0.15f * front, p0.z};
    float shx, shy;                               // shadow on the floor
    V3 sq = toCam({p0.x, FLOOR_Y, p0.z});
    project(sq, shx, shy);
    float rs = F * 0.9f / sq.z;
    th::cv.fillEllipse(shx, shy, rs, rs * 0.3f, th::p15(0x08040C));
    float spin = 0.45f * sinf(now * 0.002f + i) + (front > 0.5f ? -2 * PI * (1 - arrive) : 0);
    float scale = 0.95f + 0.35f * front;
    if (!MESH[i]) {
      V3 q = toCam(p);
      float sx, syy;
      project(q, sx, syy);
      sp[nsp++] = {q.z, sx, syy, F * 2.2f * scale / q.z, spin, dim, 0};
    } else drawMesh(*MESH[i], p, spin, TILT[i], scale, dim);
    if (i == active) {
      V3 q = toCam({p.x, p.y + 1.25f * scale, p.z});
      float cx, cy;
      project(q, cx, cy);
      sp[nsp++] = {q.z - 0.01f, cx, cy, 0, 0, 0, 1};
    }
  }
  for (int s = 0; s < nsp && nItem < MAXI; s++) items[nItem++] = {sp[s].depth, (int16_t)(-1 - s), 0, 0};
  for (int i = 1; i < nItem; i++)                 // far first
    for (int j = i; j > 0 && items[j - 1].depth < items[j].depth; j--) { Item t = items[j]; items[j] = items[j - 1]; items[j - 1] = t; }
  for (int i = 0; i < nItem; i++) {
    const Item &it = items[i];
    if (it.face >= 0) fillPoly(px + it.pp, py + it.pp, faces[it.face].n, it.col);
    else {
      const Spr &s = sp[-1 - it.face];
      if (s.kind) crown(s.x, s.y); else billboard(spr::CAT, s.x, s.y, s.size, s.spin, s.dim);
    }
  }
  int k = ((int)lroundf(pos) % 5 + 5) % 5;
  th::metal(60, 4, names[k], 2, th::WHITE, th::YELLOW, 'm');
}

}  // namespace r3
