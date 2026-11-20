#include <Arduino.h>
#include <Preferences.h>
#include <esp_random.h>
#include "services/brady.h"
#include "labels.h"

static BradySession session;
static char ownership[37]{};
static bool identity_ok = false, first_claim = false;
static uint32_t boot_id = 0, job_id = 0;

static bool loadIdentity() {
  Preferences prefs;
  if (!prefs.begin("brady-test",false)) return false;
  String stored = prefs.getString("owner","");
  if (stored.isEmpty()) {
    // A present but unreadable identity must not silently be replaced.
    if (prefs.isKey("owner")) { prefs.end(); return false; }
    uint8_t id[16]; esp_fill_random(id,sizeof(id));
    id[6] = (id[6]&15)|64; id[8] = (id[8]&63)|128;
    snprintf(ownership,sizeof(ownership),
             "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             id[0],id[1],id[2],id[3],id[4],id[5],id[6],id[7],id[8],id[9],
             id[10],id[11],id[12],id[13],id[14],id[15]);
    if (prefs.putString("owner",ownership) != 36) { prefs.end(); return false; }
    stored = prefs.getString("owner","");
    if (stored != ownership) { prefs.end(); return false; }
    first_claim = true;
  }
  prefs.end();
  if (stored.length() != 36) return false;
  stored.toCharArray(ownership,sizeof(ownership));
  uint8_t wire[17];
  return bradyOwnershipBytes({ownership,first_claim},wire);
}
static void result(BradyResult value) {
  static const char* names[] = {"OK","Transport failure","Ownership failure","Invalid status",
                              "Invalid raster","Device error","Unconfirmed (do not replay automatically)"};
  Serial.printf("Brady result: %s\n",names[value]);
}
static void showStatus() {
  const BradyStatus& s = session.status;
  Serial.printf("PICL width=%u x=%u height=%u y=%u valid=%04x errors=%04x job=%u\n",
                s.width,s.x,s.height,s.y,s.valid,s.errors,unsigned(s.job));
}
static void printLabel(bool spool) {
  if (!session.open) { result(BRADY_TRANSPORT); return; }
  const BradyResult ready = bradyStatus(session,1000);
  if (ready != BRADY_OK) { result(ready); return; }
  BradyStatus geometry = session.status;
  if (!bradyGeometryExperiment(session.status,geometry)) { result(BRADY_INVALID_STATUS); return; }
  uint8_t* pixels = static_cast<uint8_t*>(malloc(8192));
  LabelRaster image{};
  if (!pixels || !bradyTestLabel(geometry,spool,{pixels,8192},image)) {
    free(pixels); result(BRADY_INVALID_RASTER); return;
  }
  char name[21]; snprintf(name,sizeof(name),"%08lx-%08lx",(unsigned long)boot_id,(unsigned long)++job_id);
  Serial.printf("Printing %s, job=%s, %ux%u dots\n",spool?"MAKER / PLA / BLUE / 123":"border / 1 mm grid / BRADY OK",
                name,image.width,image.height);
  result(bradyPrint(session,image,name,&geometry));
  free(pixels);
}
static bool addressValid(const char* address) {
  if (strlen(address) != 17) return false;
  for (unsigned i = 0; i < 17; ++i) {
    if (i%3 == 2) { if (address[i] != ':') return false; }
    else if (!isxdigit(static_cast<unsigned char>(address[i]))) return false;
  }
  return true;
}
static void command(const char* line) {
  if (strcmp(line,"scan") == 0) {
    if (session.open) { Serial.println("Disconnect before scanning"); return; }
    BleDevice devices[8]; BleScanConfig config{}; config.service_uuid="fd1c";
    const int count = bleScan(devices,8,config);
    Serial.printf("Scan: %d devices\n",count);
    for (int i=0;i<count;++i) Serial.printf("%s %s RSSI=%d\n",devices[i].address,devices[i].name,devices[i].rssi);
  } else if (strncmp(line,"connect ",8) == 0) {
    if (!identity_ok || !addressValid(line+8)) { Serial.println("Identity unavailable or invalid address"); return; }
    const BradyResult r = bradyOpen(line+8,{ownership,first_claim},session);
    if (session.open) first_claim=false;
    result(r);showStatus();
    if (r==BRADY_OWNERSHIP) Serial.println("Close Brady app; hold printer power 5 s until Bluetooth LED pulses");
  } else if (strcmp(line,"status")==0) { result(bradyStatus(session,1000));showStatus(); }
  else if (strcmp(line,"print test")==0) printLabel(false);
  else if (strcmp(line,"print spool")==0) printLabel(true);
  else if (strcmp(line,"cut")==0) result(bradyCut(session));
  else if (strcmp(line,"disconnect")==0) result(bradyClose(session));
  else Serial.println("Commands: scan | connect <address> | status | print test | print spool | cut | disconnect");
}
void setup() {
  Serial.begin(115200); delay(500);
  // The shared transport retains controller RAM only when its normal boot key is on.
  if (!bleStackAvailable()) {
    Preferences prefs;
    if (!prefs.begin("spoolscale",false) || prefs.putBool("ble_on",true)!=1) {
      Serial.println("Cannot persist BLE boot enable; stopped"); return;
    }
    prefs.end();Serial.println("BLE enabled for next boot; restarting once");delay(100);ESP.restart();
  }
  identity_ok=loadIdentity();boot_id=esp_random();
  Serial.printf("M211 harness ready; persisted ownership %s; no automatic print\n",identity_ok?"OK":"FAILED");
}
void loop() {
  static char line[80]; static size_t used=0; static bool overflow=false;
  while (Serial.available()) {
    const char c=char(Serial.read());
    if(c=='\r')continue;
    if(c=='\n') {
      line[used]=0;
      if(overflow)Serial.println("Command too long; discarded");
      else if(used)command(line);
      used=0;overflow=false;
    } else if(used+1<sizeof(line))line[used++]=c;
    else overflow=true;
  }
  if(session.open && bleTalkConnected()) bradyStatus(session,0);
  delay(10);
}
