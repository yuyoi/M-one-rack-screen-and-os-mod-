// Idle screen. No input for FACE_AFTER_MS -> it replaces the page (theme.h canvas, PS1 look):
//  - a VOCAL effect selected: the uwu face, orange cheeks, ember glow that pulses with the sound. It blinks, looks around,
//    glances left when a pot moves (the knobs sit left of the screen) and right for buttons/encoder.
//    No input for SLEEP_AFTER_MS -> it dozes. Any input wakes it (wide eyes toward the input), then the page comes back.
//    It SINGS along with the audio: the kernel's output envelope (read over JTAG without halting the DSP) opens the
//    mouth, loud parts close the eyes to ^ ^, the head lifts with the level and music notes float up. Sound keeps it
//    from dozing, but doesn't bring the menu back.
//  - a PEDAL effect selected (menu.h FX_PEDAL): a mock pedal instead; its knobs follow the pots, its LED flickers with
//    the signal (dark when bypassed).
// DSP off (dspWatch in the .ino: power switch out) -> asleep no matter what; backlight off after 5 min without input.
// Never on the button test page.
#pragma once

uint32_t dspLevel();                       // .ino: output envelope from the kernel (OGDB), no halt

const uint32_t FACE_AFTER_MS = 8000, SLEEP_AFTER_MS = 60000, SURPRISE_MS = 450;
const uint32_t C_CHEEK = 0xE8702A;

static bool faceReady = false;
static float lookX = 0, tgtX = 0;
static uint32_t nextBlink = 0, nextLook = 0, blinkStart = 0, surpriseT = 0;
static bool blinking = false;
static uint32_t lastAsleepMs = 0;          // last frame drawn asleep (reset combo only works while asleep)
bool dspAwake = true;                      // set by dspWatch() in the .ino: false = DSP off -> face sleeps
const uint32_t BACKLIGHT_OFF_MS = 300000;  // DSP off and no input this long -> backlight off

void faceBegin() {
  faceReady = th::ready;                   // draws into the theme canvas (th::begin in setup)
  if (!faceReady) Serial.println("face: no canvas, face disabled");
}

// ---- Singing
static float singLev = 0;                  // 0..1: -48 dBFS = mouth closed, -6 dBFS = wide open
static uint32_t lastSoundMs = 0;           // last frame the output was audible
struct FaceNote { float x, y; uint32_t t; bool on; };
static FaceNote faceNotes[4];
static uint32_t nextNote = 0;
static int noteSide = 1;

static void singTick(uint32_t now) {       // one JTAG read per frame (~2 ms, the DSP keeps running)
  float target = 0;
  if (dspAwake) {
    uint32_t v = dspLevel();
    float lin = (v & 0x800000) ? 0.0f : v / 8388608.0f;   // the envelope is |out|: never negative
    float db = lin > 1e-6f ? 20.0f * log10f(lin) : -120.0f;
    target = constrain((db + 48.0f) / 42.0f, 0.0f, 1.0f);
  }
  singLev = target > singLev ? target : singLev * 0.8f + target * 0.2f;   // opens at once, closes softly
  if (singLev > 0.12f) lastSoundMs = now;
}

static void drawNote(int x, int y, uint32_t c) {          // an eighth note: head, stem, flag
  th::cv.fillEllipse(x, y, 3, 2, c);
  th::cv.fillRect(x + 2, y - 9, 1, 9, c);
  th::cv.fillTriangle(x + 3, y - 9, x + 6, y - 6, x + 3, y - 5, c);
}

static void notesTick(uint32_t now, bool singing, int mx, int my) {
  if (singing && now > nextNote) {         // a new note from the side of the mouth
    for (auto &n : faceNotes) if (!n.on) {
      n = {(float)(mx + noteSide * 19), (float)(my + 2), now, true};
      noteSide = -noteSide;
      break;
    }
    nextNote = now + 450 + random(500) - (uint32_t)(singLev * 250);
  }
  for (auto &n : faceNotes) {
    if (!n.on) continue;
    float age = (now - n.t) / 1400.0f;     // rises ~31 px over 1.4 s with a little wiggle
    if (age >= 1) { n.on = false; continue; }
    int x = (int)(n.x + 3 * sinf(age * 9) + (n.x > 60 ? 10 : -10) * age), y = (int)(n.y - 31 * age);
    drawNote(x, y, th::p15(age < 0.7f ? (n.x > 60 ? th::ORANGE : th::YELLOW) : th::EMBER));   // dims before it vanishes
  }
}

// A pedal as drawn on the PEDAL board (its own knobs) or, for any other pedal-type effect, LEVEL / MIX / TONE
static void pedalBody(uint32_t now, int fx, int idx, int dx, bool bg) {
  bool byp = fx == menu.fx1 ? menu.byp1 : menu.byp2;
  float led = byp || !dspAwake ? 0.0f : 0.45f + 0.55f * singLev;
  if (idx >= 0) {
    const PedalDef &pd = PEDALS[idx];
    float k[6];
    const char *lab[6];
    for (int i = 0; i < pd.nk; i++) { k[i] = pedalKnobVal(pd.k[i]); lab[i] = pd.k[i].label; }
    th::pedal(pd.name, pd.col, pd.nk, k, lab, led, now, dx, bg);
    return;
  }
  float k[3];
  for (int i = 0; i < 3; i++) k[i] = constrain(sysMv[i] / 3100.0f, 0.0f, 1.0f);
  static const char *const L[3] = {"LEVEL", "MIX", "TONE"};
  th::pedal(FX_NAMES[fx], FX_COL[fx], 3, k, L, led, now, dx, bg);
}

static int pedalIndexOf(int fx) {
  for (int i = 0; i < N_PEDALS; i++) if (PEDALS[i].fx == fx) return i;
  return -1;
}

static void pedalDraw(uint32_t now, int fx) { pedalBody(now, fx, pedalIndexOf(fx), 0, true); }

// The PEDAL board page: the pedal, sliding out for the next one when the knob swaps (arrows at the edges)
void pedalPageDraw(uint32_t now) {
  singTick(now);                             // keeps the LED flickering with the output
  float t = constrain((now - pedalSwapT) / 220.0f, 0.0f, 1.0f);
  t = 1 - (1 - t) * (1 - t);
  if (pedalPrev >= 0 && t < 1) {
    int off = (int)(120 * t) * pedalDir;
    pedalBody(now, PEDALS[pedalPrev].fx, pedalPrev, -off, true);
    pedalBody(now, PEDALS[pedalIdx].fx, pedalIdx, 120 * pedalDir - off, false);
  } else pedalBody(now, PEDALS[pedalIdx].fx, pedalIdx, 0, true);
  for (int s = -1; s <= 1; s += 2) {         // swap arrows
    int x = s < 0 ? 5 : 114;
    th::cv.fillTriangle(x - 2 * s, 56, x + 2 * s, 60, x - 2 * s, 64, th::p15(th::YELLOW));
  }
}

static void faceDraw(uint32_t now) {
  singTick(now);
  bool asleep = !dspAwake || (now - lastActivity > SLEEP_AFTER_MS && now - lastSoundMs > 4000);
  if (asleep) lastAsleepMs = now;
  int ped = idlePedal();
  if (ped >= 0) { pedalDraw(now, ped); th::present(); return; }
  bool surprised = surpriseT && now - surpriseT < SURPRISE_MS;
  bool singing = !asleep && !surprised && singLev > 0.12f;
  bool belting = singing && singLev > 0.5f;
  // blink: the u's flatten to dashes for ~180 ms every few seconds
  if (!asleep && !surprised && !belting && !blinking && now > nextBlink) { blinking = true; blinkStart = now; }
  if (blinking && now - blinkStart > 180) { blinking = false; nextBlink = now + 2500 + random(4000); }
  // gentle sway; surprise looks toward the input
  if (surprised) tgtX = actLook * 26;
  else if (now > nextLook) { tgtX = asleep ? 0 : random(-16, 17); nextLook = now + 1500 + random(2500); }
  lookX += (tgtX - lookX) * 0.2f;
  int dx = (int)lookX / 2, bob = asleep ? 0 : (int)(1.5f * sinf(now / 600.0f)) - (singing ? (int)(singLev * 4) : 0);

  th::vignette(asleep ? 0.25f : 0.35f + 0.65f * singLev);
  const uint32_t Y = th::p15(th::YELLOW), B = th::BLACK;
  for (int s = -1; s <= 1; s += 2) {      // eyes: "u" (open), "-" (blink / asleep), "o" (surprised), "^" (belting)
    int cx = 60 + s * 28 + dx, cy = 53 + bob;
    if (surprised) { th::cv.fillCircle(cx, cy, 11, Y); th::cv.fillCircle(cx, cy, 6, B); }
    else if (belting) th::cv.fillArc(cx, cy + 4, 11, 6, 180, 360, Y);       // top half ring: happy closed eyes
    else if (blinking || asleep) th::cv.fillRoundRect(cx - 11, cy + 2, 22, 4, 2, Y);
    else {
      th::cv.fillArc(cx, cy, 11, 6, 0, 180, Y);                            // bottom half ring
      th::cv.fillRect(cx - 11, cy - 9, 5, 9, Y);                           // left stem
      th::cv.fillRect(cx + 6, cy - 9, 5, 9, Y);                            // right stem
    }
    th::cv.fillEllipse(60 + s * 42 + dx / 2, 72 + bob, 6, 3, th::p15(C_CHEEK));
  }
  int mx = 60 + dx, my = 69 + bob;
  if (singing) {                          // mouth: open "o", height follows the level, little tongue
    int mh = 2 + (int)(singLev * 9), mw = 4 + (int)(singLev * 3), cy = my + 1 + mh;
    th::cv.fillEllipse(mx, cy, mw, mh, Y);
    th::cv.fillEllipse(mx, cy, max(mw - 2, 1), max(mh - 2, 1), B);
    if (mh > 4) th::cv.fillEllipse(mx, cy + mh - 3, max(mw / 2, 1), 2, th::p15(th::RED));
  } else {                                // mouth: "w"
    th::cv.fillArc(mx - 4, my, 4, 2, 0, 180, Y);
    th::cv.fillArc(mx + 4, my, 4, 2, 0, 180, Y);
  }
  notesTick(now, singing, mx, my);
  if (asleep)
    for (int i = 0; i < 3; i++) {          // z's drifting up
      int p = (now / 30 + i * 40) % 120;
      th::text(100 + p / 12 + i * 2, 50 - p / 6, "Z", th::p15(0x5AA0FF), 1 + (i == 1));
    }
  th::text(60, 104, "M-ONE", th::p15(th::EMBER), 1, 'm');
  th::present();
}

// Reset combo: hold R1 + T6 (both on direct pins) for 3 s while the face is asleep -> the ESP reboots.
// "Asleep" = DSP switched off, or the idle doze was on screen when the combo started (the first touch wakes it).
void comboTick() {
  static uint32_t since = 0;
  static bool armed = false;
  if (btnMap.src[K_R1] != 3 || btnMap.src[K_T6] != 3) return;
  if (uiPage == PAGE_TEST) { since = 0; armed = false; return; }   // testing presses, never reboot
  bool both = !digitalRead(btnMap.val[K_R1]) && !digitalRead(btnMap.val[K_T6]);
  uint32_t now = millis();
  if (!both) { since = 0; armed = false; return; }
  if (!since) {
    since = now;
    armed = !dspAwake || now - lastAsleepMs < 1500;
    if (armed) Serial.println("COMBO R1+T6: keep holding 3 s to reboot");
  }
  if (armed && now - since > 3000) {
    Serial.println("COMBO: rebooting");
    backlight(true);
    if (th::ready) { th::status("REBOOTING...", th::YELLOW); th::present(); }
    delay(300);
    ESP.restart();
  }
}

// Call every loop
void faceTick() {
  comboTick();
  if (!faceReady) return;
  uint32_t now = millis();
  if (!liveOn || learnIdx >= 0) { faceOn = false; return; }   // serial command / button learn owns the screen
  static bool lit = true;
  if (uiPage == PAGE_TEST) {               // button test owns the screen: no face, backlight stays on
    if (!lit) { backlight(true); lit = true; }
    return;
  }
  static uint32_t lastFrame = 0;
  if (!dspAwake) {                         // DSP off: sleeping face, inputs only light the screen back up
    bool want = now - lastActivity < BACKLIGHT_OFF_MS;
    if (want != lit) { backlight(want); lit = want; }
    if (!faceOn) { faceOn = true; surpriseT = 0; }
    if (want && now - lastFrame >= 60) { lastFrame = now; faceDraw(now); }
    return;
  }
  if (!lit) { backlight(true); lit = true; }  // DSP back
  if (!faceOn) {
    if (now - lastActivity < FACE_AFTER_MS) return;
    faceOn = true;
    surpriseT = 0;
    nextBlink = now + 800;
  } else if (now - lastActivity < 200 && !surpriseT) {
    surpriseT = now;                         // woken: look toward the input, then hand back
  }
  if (surpriseT && now - surpriseT > SURPRISE_MS) {
    faceOn = false;
    surpriseT = 0;
    uiShow();
    return;
  }
  if (now - lastFrame < 60) return;         // ~16 fps (one canvas push per frame)
  lastFrame = now;
  faceDraw(now);
}
