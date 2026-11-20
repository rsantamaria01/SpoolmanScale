#pragma once

#include "services/ble_service.h"
#include "services/label_raster.h"

// ============================================================
//  BRADY M211 OVER BLE
//
//  Protocol facts from JonBons/hacs-brady (MIT), spec and Python
//  reference at 19ed2251a1e95bcb102a1fc40ad48c960291d0cd,
//  cross-referenced there to ggiesen/pybrady. No vendor code.
//  BLE VGL ordering corrected from an official-app M211 capture
//  whose TEST output Raul confirmed (2026-11-20). Two generated
//  152x56 RLE labels also confirmed on M21-750-595-WT stock.
//  General media units and physical feed remain unverified. No UI profile.
// ============================================================

constexpr size_t BRADY_MAX_JOB_BYTES = 32768;
constexpr size_t BRADY_PICL_BYTES = 4096;
enum BradyResult : uint8_t {
  BRADY_OK, BRADY_TRANSPORT, BRADY_OWNERSHIP, BRADY_INVALID_STATUS,
  BRADY_INVALID_RASTER, BRADY_DEVICE_ERROR, BRADY_UNCONFIRMED
};
enum BradyJobResult : uint8_t { BRADY_JOB_PENDING, BRADY_JOB_SUCCESS, BRADY_JOB_FAILED };
struct BradyStatus {
  uint16_t width = 0, x = 0, height = 0, y = 0;
  uint16_t valid = 0, errors = 0;
  bool die_cut = false;
  char cartridge[65]{};
  BradyJobResult job = BRADY_JOB_PENDING;
};
// PICL units are a 1/100-inch hypothesis; only 75/0/0/0 -> 152 dots is verified.
inline bool bradyGeometryExperiment(const BradyStatus& raw, BradyStatus& dots) {
  auto convert = [](uint16_t value) { return (uint32_t(value) * 203 + 50) / 100; };
  const uint32_t width = convert(raw.width), x = convert(raw.x);
  const uint32_t height = convert(raw.height), y = convert(raw.y);
  if (!width || width + x > 192 || height > 7310 || y + height > 7310 ||
      (raw.die_cut && !height) || (!raw.die_cut && height)) return false;
  dots = raw;
  dots.width = width; dots.x = x; dots.height = height; dots.y = y;
  return true;
}
struct BradyOwnership { const char* guid; bool first_claim; };
struct BradySession {
  BradyStatus status{};
  bool open = false, malformed = false;
  char job_name[33]{};
  uint8_t rx[BRADY_PICL_BYTES + 20]{};
  size_t received = 0;
};
struct BradyChunks {
  BleBlock payload{};
  size_t offset = 0, capacity = 0, since_flush = 0;
  uint16_t sequence = 0;
};

bool bradyOwnershipBytes(const BradyOwnership& ownership, uint8_t out[17]);
bool bradyChunksBegin(BradyChunks& chunks, BleBlock payload, size_t max_write);
size_t bradyChunkNext(BradyChunks& chunks, uint8_t* out, size_t capacity);
size_t bradyPiclPacket(const char* json, uint8_t* out, size_t capacity);
bool bradyReceive(BradySession& session, const uint8_t* data, size_t length);
bool bradyReady(const BradyStatus& status);
size_t bradyVgl(const LabelRaster& image, const BradyStatus& status, const char* job_name,
               uint8_t* out, size_t capacity);
BradyResult bradyOpen(const char* address, const BradyOwnership& ownership, BradySession& session);
BradyResult bradyStatus(BradySession& session, uint32_t wait_ms);
// job_name is a log label; session.job_name holds the unique wire correlation name.
// Optional raster geometry must match converted raw PICL; media changes are refused.
BradyResult bradyPrint(BradySession& session, const LabelRaster& image, const char* job_name,
                       const BradyStatus* geometry = nullptr);
BradyResult bradyCut(BradySession& session);
BradyResult bradyClose(BradySession& session);
