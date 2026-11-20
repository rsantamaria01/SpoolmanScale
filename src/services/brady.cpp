#include "services/brady.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_random.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "hardware/sd_logger.h"

static const char* BRADY_SERVICE = "fd1c";
static const char* BRADY_SESSION = "fc0018d8-cf12-46be-87b1-cce29b1e6c34";
static const char* BRADY_REQUEST = "a61ae408-3273-420c-a9db-0669f4f23b69";
static const char* BRADY_RESPONSE = "786af345-1b68-c594-c643-e2867da117e3";
static const char* BRADY_PRINT = "7d9d9a4d-b530-4d13-8d61-e0ff445add19";
static const uint8_t PICL_GUID[] = {
  0x96, 0xc2, 0xf7, 0x4a, 0x1d, 0x21, 0x42, 0x32,
  0x86, 0x78, 0x20, 0xef, 0xe9, 0x7b, 0xc2, 0xd3
};
static const char* PROPERTY_IDS[] = {
  "000C", "000D", "000E", "000F", "0005", "0006", "0009", "000A", "0021", "0025", "0027"
};
constexpr uint16_t REQUIRED = (1u << 11) - 1;
constexpr uint32_t STATUS_WAIT_MS = 12000, PRINT_WAIT_MS = 60000;

static uint32_t readU32(const uint8_t* p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
static void writeU32(uint8_t* p, uint32_t v) {
  for (unsigned i = 0; i < 4; ++i) p[i] = uint8_t(v >> (8 * i));
}
static int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
bool bradyOwnershipBytes(const BradyOwnership& ownership, uint8_t out[17]) {
  if (!out || !ownership.guid || strlen(ownership.guid) != 36) return false;
  uint8_t rfc[16];
  size_t pos = 0;
  for (unsigned i = 0; i < 16; ++i) {
    if (pos == 8 || pos == 13 || pos == 18 || pos == 23)
      if (ownership.guid[pos++] != '-') return false;
    int hi = hexDigit(ownership.guid[pos++]), lo = hexDigit(ownership.guid[pos++]);
    if (hi < 0 || lo < 0) return false;
    rfc[i] = uint8_t(hi * 16 + lo);
  }
  static const uint8_t order[] = {3, 2, 1, 0, 5, 4, 7, 6, 8, 9, 10, 11, 12, 13, 14, 15};
  for (unsigned i = 0; i < 16; ++i) out[i] = rfc[order[i]];
  out[16] = ownership.first_claim ? 1 : 0;
  return true;
}
bool bradyChunksBegin(BradyChunks& chunks, BleBlock payload, size_t max_write) {
  chunks = {};
  if (!payload.data || !payload.len || payload.len > BRADY_MAX_JOB_BYTES || max_write <= 3) return false;
  chunks.payload = payload;
  chunks.capacity = max_write - 3 < 148 ? max_write - 3 : 148;
  return (payload.len + chunks.capacity - 1) / chunks.capacity <= 65536;
}
size_t bradyChunkNext(BradyChunks& c, uint8_t* out, size_t capacity) {
  if (!out || c.offset >= c.payload.len || !c.capacity) return 0;
  const size_t left = c.payload.len - c.offset;
  const size_t n = left < c.capacity ? left : c.capacity;
  if (capacity < n + 3) return 0;
  const bool last = n == left, flush = c.since_flush + n >= 4096;
  out[0] = last ? 3 : flush ? 2 : 1;
  out[1] = uint8_t(c.sequence); out[2] = uint8_t(c.sequence >> 8);
  memcpy(out + 3, c.payload.data + c.offset, n);
  c.offset += n; ++c.sequence;
  c.since_flush = last || flush ? 0 : c.since_flush + n;
  return n + 3;
}
size_t bradyPiclPacket(const char* json, uint8_t* out, size_t capacity) {
  if (!json || !out) return 0;
  const size_t n = strlen(json);
  if (!n || n > BRADY_PICL_BYTES || capacity < n + 20) return 0;
  memcpy(out, PICL_GUID, 16); writeU32(out + 16, n); memcpy(out + 20, json, n);
  return n + 20;
}

static bool number(const char* text, uint16_t max, uint16_t& out) {
  if (!text || !*text) return false;
  uint32_t value = 0;
  for (const char* p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    value = value * 10 + unsigned(*p - '0');
    if (value > max) return false;
  }
  out = value;
  return true;
}
static void applyProperty(BradySession& s, JsonObjectConst item) {
  const char* id = item["ID"], *value = item["Value"], *status = item["Status"];
  if (!id) return;
  const bool success = status && strcmp(status, "Successful") == 0 && value;
  logSDf("Brady: PICL %s value=%s status=%s", id, value ? value : "?", status ? status : "?");
  if (strcmp(id, "0029") == 0) {
    if (!success || !s.job_name[0]) return;
    const size_t n = strlen(s.job_name);
    if (strncmp(value, s.job_name, n) != 0 || value[n] != ':') return;
    const char* result = value + n + 1;
    if (*result == ' ') ++result;
    if (strcmp(result, "Successful") == 0) s.status.job = BRADY_JOB_SUCCESS;
    if (strcmp(result, "Failed") == 0) s.status.job = BRADY_JOB_FAILED;
    return;
  }
  for (unsigned i = 0; i < 11; ++i) {
    if (strcmp(id, PROPERTY_IDS[i]) != 0) continue;
    const uint16_t bit = 1u << i;
    s.status.valid &= ~bit;
    if (!success) return;
    if (i < 4) {
      uint16_t parsed;
      if (!number(value, i == 0 ? 192 : 7310, parsed) || (i == 0 && !parsed)) return;
      uint16_t* fields[] = {&s.status.width, &s.status.x, &s.status.height, &s.status.y};
      *fields[i] = parsed;
    } else {
      if (strcmp(value, "True") == 0) s.status.errors |= bit;
      else if (strcmp(value, "False") == 0) s.status.errors &= ~bit;
      else return;
    }
    s.status.valid |= bit;
    return;
  }
}
static bool parsePicl(BradySession& s, const uint8_t* json, size_t length) {
  JsonDocument doc;
  if (deserializeJson(doc, json, length, DeserializationOption::NestingLimit(5))) return false;
  if (!doc["PropertyGetResponses"].is<JsonArray>()) return false;
  for (JsonObjectConst item : doc["PropertyGetResponses"].as<JsonArrayConst>()) {
    for (const char* key : {"ID", "Value", "Status"}) {
      const JsonString text = item[key].as<JsonString>();
      if (text && strlen(text.c_str()) != text.size()) return false;
    }
    applyProperty(s, item);
  }
  return true;
}
bool bradyReceive(BradySession& s, const uint8_t* data, size_t length) {
  if (s.malformed || (!data && length)) return false;
  for (size_t i = 0; i < length; ++i) {
    s.rx[s.received++] = data[i];
    if (s.received <= 16 && s.rx[s.received - 1] != PICL_GUID[s.received - 1]) s.malformed = true;
    if (s.received >= 20) {
      const uint32_t n = readU32(s.rx + 16);
      if (!n || n > BRADY_PICL_BYTES) s.malformed = true;
      else if (s.received == n + 20) {
        if (!parsePicl(s, s.rx + 20, n)) s.malformed = true;
        s.received = 0;
      }
    }
    if (s.malformed) { s.status.valid = 0; return false; }
  }
  return true;
}
bool bradyReady(const BradyStatus& s) {
  return s.valid == REQUIRED && !s.errors && s.width && s.width <= 192 &&
         uint32_t(s.width) + s.x <= 9999 && uint32_t(s.height) + 2u * s.y <= 9999;
}

static bool rasterValid(const LabelRaster& image) {
  if (!image.pixels || !image.width || image.width > 192 || !image.height || image.height > 7310 ||
      image.row_bytes != (image.width + 7) / 8 || image.length > BRADY_MAX_JOB_BYTES ||
      image.length != size_t(image.row_bytes) * image.height) return false;
  const uint8_t mask = (1u << ((8 - image.width % 8) % 8)) - 1;
  for (unsigned y = 0; y < image.height; ++y)
    if (image.pixels[size_t(y + 1) * image.row_bytes - 1] & mask) return false;
  return true;
}
static bool jobNameValid(const char* name) {
  if (!name || !*name || strlen(name) > 32) return false;
  for (const char* p = name; *p; ++p)
    if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
          (*p >= '0' && *p <= '9') || *p == '-')) return false;
  return true;
}
size_t bradyVgl(const LabelRaster& image, const BradyStatus& s, const char* name,
               uint8_t* out, size_t capacity) {
  if (!out || !rasterValid(image) || !jobNameValid(name) || strlen(name) != 32 ||
      image.width != s.width || s.x || s.y || (s.height && image.height != s.height)) return 0;
  for (const char* p = name; *p; ++p) if (hexDigit(*p) < 0) return 0;
  size_t n = 0;
  bool fits = true;
  if (capacity > BRADY_MAX_JOB_BYTES) capacity = BRADY_MAX_JOB_BYTES;
  auto append = [&](const void* bytes, size_t size) {
    if (size > capacity - n) { fits = false; return; }
    memcpy(out + n, bytes, size); n += size;
  };
  // The successful app BLE stream starts with JobName, not a file-container header.
  static const uint8_t name_cmd[] = {2,'K',0,10};
  append(name_cmd,sizeof(name_cmd)); append(name,32);
  static const uint8_t settings[] = {13,2,'K',0,9,'M','2','1','-','7','5','0',13,
    2,'p','+','0','0',2,'o','+','0','0',2,'O','+','0','0',2,'b','+','0','0',2,'M',1,2,'K',0,12};
  append(settings,sizeof(settings));
  char digits[11]; snprintf(digits,sizeof(digits),"%04u%04u",image.width,image.height);
  append(digits,8);
  static const uint8_t image_start[] = {2,'W',0,2,'A',2,'Q',2,'a',
    2,'I','B','U','l','b','l','0',13,'X',0,0,'Y',0,0};
  append(image_start,sizeof(image_start));
  for (unsigned y = 0; y < image.height && fits; ++y) {
    uint8_t row[194] = {0x81,0};
    const uint8_t* pixels = image.pixels + size_t(y) * image.row_bytes;
    for (unsigned x = 0; x < image.width;) {
      const bool black = pixels[x / 8] & (0x80u >> (x % 8));
      unsigned run = 1;
      while (run < 128 && x + run < image.width &&
             bool(pixels[(x + run) / 8] & (0x80u >> ((x + run) % 8))) == black) ++run;
      row[2 + row[1]++] = (black ? 0x80 : 0) | uint8_t(run - 1);
      x += run;
    }
    append(row,size_t(row[1]) + 2);
  }
  const uint8_t end[] = {'Y',uint8_t(image.height),uint8_t(image.height >> 8),255,255,13,
                         2,'a',2,'G',2,'A',2,'K',0,11};
  append(end,sizeof(end));
  return fits ? n : 0;
}

static bool pump(BradySession& s, uint32_t wait_ms) {
  uint8_t bytes[256];
  const size_t n = bleTalkRead(bytes,sizeof(bytes),wait_ms);
  if (bleTalkRxOverflowed()) { s.malformed = true; s.status.valid = 0; return false; }
  return bradyReceive(s,bytes,n) && bleTalkConnected();
}
static bool drain(BradySession& s) {
  const uint32_t from = millis();
  uint8_t bytes[256];
  do {
    const size_t n = bleTalkRead(bytes,sizeof(bytes),0);
    if (bleTalkRxOverflowed() || !bradyReceive(s,bytes,n) || !bleTalkConnected()) return false;
    if (!n) return !s.received;
  } while (millis() - from < 1000);
  return false;
}
static bool sendChunks(BradySession& s, const char* characteristic, BleBlock block) {
  if (!bleTalkSelectWrite(characteristic,true)) return false;
  BradyChunks chunks;
  if (!bradyChunksBegin(chunks,block,bleTalkMaxWrite())) return false;
  uint8_t packet[151]; size_t n;
  const uint32_t from = millis();
  while ((n = bradyChunkNext(chunks,packet,sizeof(packet)))) {
    if (millis() - from >= PRINT_WAIT_MS || !bleTalkSend(packet,n) || !pump(s,0)) return false;
    if (s.status.errors) return false;
    if (packet[0] == 2) delay(10);
  }
  return true;
}
static bool request(BradySession& s, const char* json) {
  uint8_t bytes[512];
  const size_t n = bradyPiclPacket(json,bytes,sizeof(bytes));
  return n && sendChunks(s,BRADY_REQUEST,{bytes,n});
}
BradyResult bradyStatus(BradySession& s, uint32_t wait_ms) {
  if (!s.open || !bleTalkConnected()) return BRADY_TRANSPORT;
  if (wait_ms > STATUS_WAIT_MS) wait_ms = STATUS_WAIT_MS;
  const uint32_t from = millis();
  do {
    if (!pump(s,10)) return s.malformed ? BRADY_INVALID_STATUS : BRADY_TRANSPORT;
    if (s.status.errors) return BRADY_DEVICE_ERROR;
    if (bradyReady(s.status) && !s.received) return BRADY_OK;
  } while (millis() - from < wait_ms);
  return BRADY_INVALID_STATUS;
}
BradyResult bradyOpen(const char* address, const BradyOwnership& ownership, BradySession& s) {
  if (s.open || bleTalkConnected()) return BRADY_TRANSPORT;
  s = {};
  uint8_t bytes[17];
  if (!bradyOwnershipBytes(ownership,bytes)) return BRADY_OWNERSHIP;
  const BleTalkEndpoint ep{BRADY_SERVICE,BLE_PROP_WRITE,BRADY_SESSION,BRADY_RESPONSE};
  if (bleTalkOpen(address,ep,nullptr) != BLE_WRITE_OK) return BRADY_TRANSPORT;
  s.open = true;
  logSD("Brady: connected");
  if (!bleTalkSelectWrite(BRADY_SESSION,true) || !bleTalkSend(bytes,sizeof(bytes))) {
    bradyClose(s); return BRADY_OWNERSHIP;
  }
  logSDf("Brady: session claim written, flag=%u",unsigned(bytes[16]));
  static const char subscribe[] = "{\"PropertySubscribeRequests\":[{\"ID\":\"000C\"},{\"ID\":\"000D\"},"
      "{\"ID\":\"000E\"},{\"ID\":\"000F\"},{\"ID\":\"0005\"},{\"ID\":\"0006\"},{\"ID\":\"0009\"},"
      "{\"ID\":\"000A\"},{\"ID\":\"0021\"},{\"ID\":\"0025\"},{\"ID\":\"0027\"},{\"ID\":\"0029\"}]}";
  if (!request(s,subscribe)) { bradyClose(s); return BRADY_TRANSPORT; }
  return bradyStatus(s,STATUS_WAIT_MS);
}
BradyResult bradyPrint(BradySession& s, const LabelRaster& image, const char* name,
                       const BradyStatus* geometry) {
  if (!s.open || !bleTalkConnected()) return BRADY_TRANSPORT;
  const BradyStatus raw = s.status;
  if (!drain(s) || s.malformed || !bradyReady(s.status)) return BRADY_INVALID_STATUS;
  if (raw.width != s.status.width || raw.height != s.status.height ||
      raw.x != s.status.x || raw.y != s.status.y) return BRADY_INVALID_STATUS;
  if (!jobNameValid(name)) return BRADY_INVALID_RASTER;
  // A boot nonce plus monotonic counter survives session reopen and caller name reuse.
  static const uint32_t nonce[] = {esp_random(),esp_random(),esp_random()};
  static uint32_t sequence = 0;
  if (sequence == UINT32_MAX) return BRADY_INVALID_RASTER;
  char wire_name[33];
  snprintf(wire_name,sizeof(wire_name),"%08lx%08lx%08lx%08lx",(unsigned long)nonce[0],
           (unsigned long)nonce[1],(unsigned long)nonce[2],(unsigned long)++sequence);
  uint8_t* bytes = static_cast<uint8_t*>(malloc(BRADY_MAX_JOB_BYTES));
  if (!bytes) return BRADY_INVALID_RASTER;
  const size_t n = bradyVgl(image,geometry ? *geometry : s.status,wire_name,bytes,BRADY_MAX_JOB_BYTES);
  if (!n) { free(bytes); return BRADY_INVALID_RASTER; }
  snprintf(s.job_name,sizeof(s.job_name),"%s",wire_name); s.status.job = BRADY_JOB_PENDING;
  logSDf("Brady: submit %s as job %s",name,s.job_name);
  const bool sent = sendChunks(s,BRADY_PRINT,{bytes,n});
  free(bytes);
  // Some bytes may have landed even on failure; never replay this job automatically.
  if (!sent) return BRADY_UNCONFIRMED;
  const uint32_t from = millis();
  while (millis() - from < PRINT_WAIT_MS) {
    if (!pump(s,50)) return BRADY_UNCONFIRMED;
    if (s.status.errors || s.status.job == BRADY_JOB_FAILED) return BRADY_DEVICE_ERROR;
    if (s.status.job == BRADY_JOB_SUCCESS) {
      logSDf("Brady: job %s Successful",s.job_name); return BRADY_OK;
    }
  }
  return BRADY_UNCONFIRMED;
}
BradyResult bradyCut(BradySession& s) {
  if (!s.open || !bleTalkConnected()) return BRADY_TRANSPORT;
  if (!drain(s) || !bradyReady(s.status)) return BRADY_INVALID_STATUS;
  return request(s,"{\"PropertySetRequests\":[{\"ID\":\"0004\",\"Value\":\"True\"}]}")
      ? BRADY_UNCONFIRMED : BRADY_TRANSPORT;
}
BradyResult bradyClose(BradySession& s) {
  s.open = false; s.status.valid = 0;
  return bleTalkClose() == BLE_WRITE_OK ? BRADY_OK : BRADY_TRANSPORT;
}
