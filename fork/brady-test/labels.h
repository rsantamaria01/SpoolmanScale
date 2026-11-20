#pragma once
#include "services/brady.h"

// Original 3x5 diagnostic glyphs, GPL-3.0 like this repository; no vendor font.
inline uint16_t bradyGlyph(char c) {
  static const char letters[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  static const uint16_t glyphs[] = {
    0, 0x5F6D,0x6BAE,0x3923,0x6B6E,0x79A7,0x79A4,0x396B,0x5BED,0x7497,
    0x126A,0x5BAD,0x4927,0x5FED,0x5F7D,0x2B6A,0x6BA4,0x2B7B,0x6BAD,
    0x388E,0x7492,0x5B6F,0x5B6A,0x5BFD,0x5AAD,0x5A92,0x72A7,
    0x7B6F,0x3497,0x62A7,0x628E,0x5BC9,0x798E,0x79EF,0x7249,0x7BEF,0x7BCF
  };
  const char* p = strchr(letters,c);
  return p ? glyphs[p-letters] : 0;
}
inline unsigned bradyGridDot(unsigned mm) { return (mm * 2030u + 127u) / 254u; }
struct BradyCanvas { uint8_t* pixels; size_t capacity; };
inline void bradyDot(LabelRaster& image, unsigned x, unsigned y) {
  if (x < image.width && y < image.height) image.pixels[y*image.row_bytes+x/8] |= 0x80u >> (x%8);
}
inline void bradyText(LabelRaster& image, const char* text, unsigned y, unsigned scale) {
  unsigned x = 3;
  for (const char* p = text; *p; ++p, x += 4*scale) {
    const uint16_t glyph = bradyGlyph(*p);
    for (unsigned row = 0; row < 5; ++row)
      for (unsigned col = 0; col < 3; ++col)
        if (glyph & (1u << (14-row*3-col)))
          for (unsigned dy = 0; dy < scale; ++dy)
            for (unsigned dx = 0; dx < scale; ++dx) bradyDot(image,x+col*scale+dx,y+row*scale+dy);
  }
}
inline bool bradyTestLabel(const BradyStatus& status, bool spool, BradyCanvas canvas, LabelRaster& image) {
  const uint16_t width = status.width, height = status.height ? status.height : 56;
  const uint16_t row = (width+7)/8;
  if (!canvas.pixels || width < 39 || width > 192 || height < 50 || height > 7310 ||
      size_t(row)*height > canvas.capacity) return false;
  image = {width,height,row,canvas.pixels,size_t(row)*height,width};
  memset(image.pixels,0,image.length);
  if (spool) {
    bradyText(image,"MAKER",3,1); bradyText(image,"PLA",13,1);
    bradyText(image,"BLUE",23,1);
    const unsigned scale = width >= 70 && height >= 56 ? 4 : 2;
    bradyText(image,"123",35,scale);
  } else {
    for (unsigned x = 0; x < width; ++x) { bradyDot(image,x,0); bradyDot(image,x,height-1); }
    for (unsigned y = 0; y < height; ++y) { bradyDot(image,0,y); bradyDot(image,width-1,y); }
    for (unsigned mm = 1; bradyGridDot(mm) < height-1u; ++mm)
      for (unsigned x = 1; x < width-1u; ++x) bradyDot(image,x,bradyGridDot(mm));
    for (unsigned mm = 1; bradyGridDot(mm) < width-1u; ++mm)
      for (unsigned y = 1; y < height-1u; ++y) bradyDot(image,bradyGridDot(mm),y);
    for (unsigned y = 2; y < 10; ++y)
      for (unsigned x = 2; x < 36; ++x) image.pixels[y*row+x/8] &= ~(0x80u >> (x%8));
    bradyText(image,"BRADY OK",3,1);
  }
  return true;
}
