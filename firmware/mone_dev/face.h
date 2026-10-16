// Idle face: uwu, with orange cheeks (to match the knobs), drawn into an 8-bit sprite.
// No input for FACE_AFTER_MS -> the face replaces the live readout. It blinks, looks around, glances left when a pot
// moves (the knobs sit left of the screen) and right for buttons/encoder. No input for SLEEP_AFTER_MS -> it dozes.
// Any input wakes it (wide eyes toward the input for a moment), then the page comes back.
// DSP off (dspWatch in the .ino: power switch out) -> asleep no matter what; backlight off after 5 min without input.
// Never on the button test page.
#pragma once

const uint32_t FACE_AFTER_MS = 8000, SLEEP_AFTER_MS = 60000, SURPRISE_MS = 450;
const int FACE_Y = 40, FACE_H = 160;       // sprite band on screen (keeps pushes short: ~30 ms at 20 MHz)
const uint32_t C_CHEEK = 0xE8702A;

static LGFX_Sprite faceSpr(&tft);
static bool faceReady = false;
static float lookX = 0, tgtX = 0;
static uint32_t nextBlink = 0, nextLook = 0, blinkStart = 0, surpriseT = 0;
static bool blinking = false;
static uint32_t lastAsleepMs = 0;          // last frame drawn asleep (reset combo only works while asleep)
bool dspAwake = true;                      // set by dspWatch() in the .ino: false = DSP off -> face sleeps
const uint32_t BACKLIGHT_OFF_MS = 300000;  // DSP off and no input this long -> backlight off

void faceBegin() {
  faceSpr.setColorDepth(8);
  faceReady = faceSpr.createSprite(240, FACE_H) != nullptr;
  if (!faceReady) Serial.println("face: no RAM for sprite, face disabled");
}

static void faceDraw(uint32_t now) {
  bool asleep = !dspAwake || now - lastActivity > SLEEP_AFTER_MS;
  if (asleep) lastAsleepMs = now;
  bool surprised = surpriseT && now - surpriseT < SURPRISE_MS;
  // blink: the u's flatten to dashes for ~180 ms every few seconds
  if (!asleep && !surprised && !blinking && now > nextBlink) { blinking = true; blinkStart = now; }
  if (blinking && now - blinkStart > 180) { blinking = false; nextBlink = now + 2500 + random(4000); }
  // gentle sway; surprise looks toward the input
  if (surprised) tgtX = actLook * 26;
  else if (now > nextLook) { tgtX = asleep ? 0 : random(-16, 17); nextLook = now + 1500 + random(2500); }
  lookX += (tgtX - lookX) * 0.2f;
  int dx = (int)lookX, bob = asleep ? 0 : (int)(3 * sinf(now / 600.0f));

  faceSpr.fillScreen(0);
  for (int s = -1; s <= 1; s += 2) {      // eyes: "u" (open), "-" (blink / asleep), "o" (surprised)
    int cx = 120 + s * 56 + dx, cy = 66 + bob;
    if (surprised) { faceSpr.fillCircle(cx, cy, 22, C_YEL); faceSpr.fillCircle(cx, cy, 13, 0); }
    else if (blinking || asleep) faceSpr.fillRoundRect(cx - 22, cy + 4, 44, 8, 4, C_YEL);
    else {
      faceSpr.fillArc(cx, cy, 22, 13, 0, 180, C_YEL);          // bottom half ring
      faceSpr.fillRect(cx - 22, cy - 18, 9, 18, C_YEL);         // left stem
      faceSpr.fillRect(cx + 13, cy - 18, 9, 18, C_YEL);         // right stem
    }
    faceSpr.fillEllipse(120 + s * 84 + dx / 2, 104 + bob, 12, 6, C_CHEEK);
  }
  int mx = 120 + dx, my = 98 + bob;       // mouth: "w"
  faceSpr.fillArc(mx - 8, my, 9, 5, 0, 180, C_YEL);
  faceSpr.fillArc(mx + 8, my, 9, 5, 0, 180, C_YEL);
  if (asleep) {
    faceSpr.setFont(&fonts::FreeSansBold12pt7b);
    faceSpr.setTextColor(C_BLUE);
    faceSpr.setTextDatum(middle_center);
    for (int i = 0; i < 3; i++) {         // z's drifting up
      int p = (now / 30 + i * 40) % 120;
      faceSpr.drawString("z", 200 + p / 6 + i * 4, 60 - p / 3);
    }
  }
  faceSpr.pushSprite(0, FACE_Y);
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
    displayStatus("rebooting...", C_YEL);
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
  if (!dspAwake) {                         // DSP off: sleeping face, inputs only light the screen back up
    bool want = now - lastActivity < BACKLIGHT_OFF_MS;
    if (want != lit) { backlight(want); lit = want; }
    if (!faceOn) { faceOn = true; surpriseT = 0; tft.fillScreen(C_BG); }
    static uint32_t lastF = 0;
    if (want && now - lastF >= 40) { lastF = now; faceDraw(now); }
    return;
  }
  if (!lit) { backlight(true); lit = true; }  // DSP back
  if (!faceOn) {
    if (now - lastActivity < FACE_AFTER_MS) return;
    faceOn = true;
    surpriseT = 0;
    tft.fillScreen(C_BG);
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
  static uint32_t lastFrame = 0;
  if (now - lastFrame < 40) return;         // ~25 fps
  lastFrame = now;
  faceDraw(now);
}
