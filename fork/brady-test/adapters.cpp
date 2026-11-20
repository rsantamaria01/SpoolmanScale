// Fork-only adapters: no display, backend worker or SD card on the test board.
#include <Arduino.h>
#include <Preferences.h>
#include <stdarg.h>
#include "hardware/sd_logger.h"
#include "services/backend_job.h"
#include "services/breadcrumb.h"
#include "services/prefs_store.h"
#include "services/user_options.h"

bool g_ble_enabled = true;
bool backendListBusy() { return false; }
void crumbSet(const char*) {}
void logSD(const char* text) { Serial.println(text); }
void logSDf(const char* format, ...) {
  char text[256]; va_list args;
  va_start(args,format); vsnprintf(text,sizeof(text),format,args); va_end(args);
  Serial.println(text);
}
bool prefsPutBool(const char* key, bool value) {
  Preferences prefs;
  if (!prefs.begin("spoolscale",false)) return false;
  const bool ok = prefs.putBool(key,value) == 1;
  prefs.end();
  return ok;
}
