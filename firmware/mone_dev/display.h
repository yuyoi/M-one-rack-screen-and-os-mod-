// 1.54" 240x240 ST7789 IPS (SPI, no CS on most modules) via LovyanGFX.
// Firmware pins: SCLK=GPIO8 MOSI=GPIO9 RES=GPIO15 DC=GPIO16 BLK=GPIO17, CS not driven, VCC=3V3.
// Known quirks of these CS-less modules:
//  - no CS -> the panel only latches in SPI mode 3 on most boards (some want mode 0): 'm' toggles it at runtime
//  - BLK is active-HIGH; driven with plain digitalWrite here (no LEDC/PWM: core 3.x changed the LEDC API)
//  - long dupont leads: keep the SPI clock modest (20 MHz)
#pragma once
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

const int TFT_BLK = 17;

class LGFX_M1 : public lgfx::LGFX_Device {
 public:
  lgfx::Panel_ST7789 panel;
  lgfx::Bus_SPI bus;

  int sclk = 8, mosi = 9;    // moved from 7/6 (5/6/7 = pots); this order is the one that works

  void busSetup(int mode) {
    auto b = bus.config();
    b.spi_host = SPI3_HOST;  // SPI2 (FSPI) stays free for the J5 SHI link
    b.spi_mode = mode;
    b.freq_write = 20000000;
    b.pin_sclk = sclk;
    b.pin_mosi = mosi;
    b.pin_miso = -1;
    b.pin_dc = 16;
    bus.config(b);
  }

  LGFX_M1() {
    busSetup(3);
    panel.setBus(&bus);
    auto p = panel.config();
    p.pin_cs = -1;           // CS (GPIO18) is held LOW in displayBegin
    p.pin_rst = 15;
    p.panel_width = 240;
    p.panel_height = 240;
    p.memory_width = 240;
    p.memory_height = 320;
    p.invert = true;         // IPS ST7789 panels need inversion
    p.readable = false;
    panel.config(p);
    setPanel(&panel);
  }
};

static LGFX_M1 tft;
static int tftMode = 3;

// Palette: M-One yellow + Rosetta blue on black
static const uint32_t C_BG = 0x000000, C_YEL = 0xF2C200, C_BLUE = 0x3FA9F5, C_GREY = 0x606060, C_RED = 0xE03030, C_GRN = 0x30D060;

void displayStatus(const char *line, uint32_t col);

void backlight(bool on) {
  pinMode(TFT_BLK, OUTPUT);
  digitalWrite(TFT_BLK, on ? HIGH : LOW);
}

void displayBegin() {
  pinMode(18, OUTPUT);  // module CS wire: hold LOW = always selected (it only worked before by floating low)
  digitalWrite(18, LOW);
  backlight(true);
  tft.init();
  tft.setRotation(1);  // 90 deg clockwise (user mounting)
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, 240, 44, C_YEL);
  tft.setTextColor(0x000000);
  tft.setFont(&fonts::FreeSansBold18pt7b);
  tft.setTextDatum(middle_center);
  tft.drawString("M-ONE", 120, 23);
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextColor(C_BLUE);
  tft.drawString("new OS - dev build", 120, 64);
  tft.drawFastHLine(10, 82, 220, C_GREY);
  tft.setTextColor(C_GREY);
  tft.setTextDatum(top_left);
  tft.drawString("DSP  56362 via J8", 12, 92);
  displayStatus(tftMode == 3 ? "ready (spi mode 3)" : "ready (spi mode 0)", C_GRN);
}

// Switch SPI mode 3 <-> 0 and redraw (CS-less panels differ)
void displayToggleMode() {
  tftMode = tftMode == 3 ? 0 : 3;
  tft.busSetup(tftMode);
  displayBegin();
}

// Bottom status bar
void displayStatus(const char *line, uint32_t col) {
  tft.fillRect(0, 206, 240, 34, 0x101010);
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextDatum(middle_center);
  tft.setTextColor(col);
  tft.drawString(line, 120, 223);
}

// Key/value row (rows 0..4 between the header and the status bar)
void displayRow(int row, const char *key, const char *val, uint32_t col) {
  int y = 116 + row * 18;                  // no fillRect: text draws over its own background, so no flicker
  tft.setFont(&fonts::Font2);
  tft.setTextDatum(top_left);
  tft.setTextPadding(76);
  tft.setTextColor(C_GREY, C_BG);
  tft.drawString(key, 12, y);
  tft.setTextPadding(148);
  tft.setTextColor(col, C_BG);
  tft.drawString(val, 90, y);
  tft.setTextPadding(0);
}
