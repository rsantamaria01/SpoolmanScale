"""Run the actual BLE service against a fake radio, not a second transport."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).parents[1]
stub = r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
inline uint32_t clock_ms=0;
inline uint32_t millis(){return clock_ms++;}
inline void delay(uint32_t n){clock_ms+=n;}
using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) (void)(x)
#define portEXIT_CRITICAL(x) (void)(x)
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_8BIT 2
inline size_t heap_caps_get_free_size(int){return 100000;}
inline size_t heap_caps_get_largest_free_block(int){return 100000;}
using nvs_handle_t=int;
#define NVS_READONLY 0
#define ESP_OK 0
inline int nvs_open(const char*,int,int*){return 0;}
inline int nvs_get_u8(int,const char*,uint8_t* p){*p=1;return 0;}
inline void nvs_close(int){}
inline bool g_ble_enabled=true;
inline bool prefsPutBool(const char*,bool){return true;}
inline bool backendListBusy(){return false;}
inline void crumbSet(const char*){}
inline void logSD(const char*){}
template<class... T> void logSDf(const char*,T...){}
struct Wifi {void setSleep(bool){}};
inline Wifi WiFi;
class NimBLEUUID {
 std::string id;
 public:
 NimBLEUUID(const char* s):id(s){}
 NimBLEUUID(uint16_t n){char b[5];snprintf(b,5,"%04x",n);id=b;}
 std::string toString()const{return id;}
 bool operator==(const NimBLEUUID& b)const{return id==b.id;}
};
class NimBLEAddress {
 std::string id;
 public: NimBLEAddress(const char* s,int):id(s){} std::string toString()const{return id;}
};
struct NimBLEAdvertisedDevice {
 std::string service="fd1c";
 std::string getName()const{return "M211";}
 NimBLEAddress getAddress()const{return {"aa:bb:cc:dd:ee:ff",0};}
 int getRSSI()const{return -40;} int getAddressType()const{return 0;}
 bool isAdvertisingService(const NimBLEUUID& u)const{return u.toString()==service;}
};
struct NimBLEScanCallbacks {virtual ~NimBLEScanCallbacks()=default; virtual void onResult(const NimBLEAdvertisedDevice*){}};
struct NimBLEScan {
 NimBLEScanCallbacks* cb=nullptr; NimBLEAdvertisedDevice advertised;
 void setScanCallbacks(NimBLEScanCallbacks* p){cb=p;}
 void setActiveScan(bool){} void setDuplicateFilter(bool){} void setMaxResults(int){}
 void getResults(uint32_t,bool){if(cb)cb->onResult(&advertised);}
 void stop(){} void clearResults(){}
};
struct NimBLERemoteCharacteristic {
 const char* id; bool w=false,nr=false,n=false,i=false;
 bool subscribed=false,notifications=false,response=false,write_ok=true; unsigned writes=0;
 bool canRead()const{return false;} bool canWrite()const{return w;}
 bool canWriteNoResponse()const{return nr;} bool canNotify()const{return n;} bool canIndicate()const{return i;}
 NimBLEUUID getUUID()const{return id;}
 bool subscribe(bool notify,void(*)(NimBLERemoteCharacteristic*,uint8_t*,size_t,bool)){
 subscribed=true; notifications=notify;return notify?n:i;
 }
 bool writeValue(const uint8_t*,size_t,bool ack){response=ack;++writes;return write_ok;}
};
struct NimBLERemoteService {
 const char* id; std::vector<NimBLERemoteCharacteristic*> chars;
 NimBLEUUID getUUID()const{return id;}
 const auto& getCharacteristics(bool){return chars;}
 NimBLERemoteCharacteristic* getCharacteristic(const NimBLEUUID& u){
 for(auto c:chars)if(c->getUUID()==u)return c;return nullptr;}
};
struct NimBLEClient {
 bool connected=false; std::vector<NimBLERemoteService*> services;
 void setConnectTimeout(int){} bool connect(const NimBLEAddress&){connected=true;return true;}
 bool isConnected(){return connected;} void disconnect(){connected=false;}
 int getLastError(){return 1;} uint16_t getMTU(){return 185;}
 const auto& getServices(bool){return services;}
 NimBLERemoteService* getService(const NimBLEUUID& u){for(auto s:services)if(s->getUUID()==u)return s;return nullptr;}
};
struct NimBLEDevice {
 static inline NimBLEScan scan; static inline NimBLEClient client;
 static bool init(const char*){return true;} static void deinit(bool){} static void setMTU(int){}
 static NimBLEScan* getScan(){return &scan;} static NimBLEClient* createClient(){return &client;}
 static void deleteClient(NimBLEClient*){}
};
'''
source = r'''
#include "services/ble_service.cpp"
#include <cassert>
int main(){
 bleInUse();
 NimBLERemoteCharacteristic legacy{"legacy",false,true,true};
 NimBLERemoteCharacteristic claim{"claim",true,true};
 NimBLERemoteCharacteristic reply{"reply",false,false,false,true};
 NimBLERemoteService other{"other",{&legacy}};
 NimBLERemoteService brady{"fd1c",{&claim,&reply}};
 NimBLEDevice::client.services={&other,&brady};
 const char* addr="aa:bb:cc:dd:ee:ff";
 BleTalkEndpoint old{"absent",BLE_PROP_WRITE_NR|BLE_PROP_NOTIFY};
 assert(bleTalkOpen(addr,old,nullptr)==BLE_WRITE_OK);
 assert(legacy.subscribed && legacy.notifications);
 uint8_t b=0;
 assert(bleTalkSend(&b,1) && !legacy.response);
 bleTalkClose();
 BleTalkEndpoint explicit_ep{"fd1c",BLE_PROP_WRITE,"missing","reply"};
 assert(bleTalkOpen(addr,explicit_ep,nullptr)==BLE_WRITE_NO_CHARACTERISTIC);
 explicit_ep.write_uuid="claim";
 explicit_ep.notify_uuid="missing";
 assert(bleTalkOpen(addr,explicit_ep,nullptr)==BLE_WRITE_NO_CHARACTERISTIC);
 explicit_ep.notify_uuid="reply";
 assert(bleTalkOpen(addr,explicit_ep,nullptr)==BLE_WRITE_OK);
 assert(reply.subscribed && !reply.notifications);
 uint8_t flood[600]{};
 onTalkNotify(nullptr,flood,sizeof(flood),false);
 assert(bleTalkRxOverflowed());
 assert(bleTalkRead(flood,sizeof(flood),0)==0);
 assert(bleTalkRxOverflowed());
 bleTalkClose();
 assert(bleTalkOpen(addr,explicit_ep,nullptr)==BLE_WRITE_OK);
 assert(!bleTalkRxOverflowed());
 assert(bleTalkSelectWrite("claim",true));
 assert(bleTalkSend(&b,1) && claim.response);
 assert(!bleTalkSelectWrite("legacy",true));
 assert(!bleTalkSend(&b,1)); // failed selection must not write to the old endpoint
 assert(bleTalkSelectWrite("claim",true));
 claim.write_ok=false;
 assert(!bleTalkSend(&b,1) && claim.writes==2); // no replay of ambiguous acknowledged writes
 bleTalkClose();
 BleDevice found[2]{};
 BleScanConfig cfg{}; cfg.service_uuid="fd1c"; cfg.duration_ms=1;
 assert(bleScan(found,2,cfg)==1);
 NimBLEDevice::scan.advertised.service="other";
 assert(bleScan(found,2,cfg)==0);
 assert(bleScan(found,2,1,nullptr)==1);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "fake.h").write_text(stub)
    for name in ["Arduino.h", "NimBLEDevice.h", "WiFi.h", "esp_heap_caps.h", "nvs.h",
                 "hardware/sd_logger.h", "services/backend_job.h", "services/breadcrumb.h",
                 "services/prefs_store.h", "services/user_options.h"]:
        p = tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#include "fake.h"\n')
    (tmp / "test.cpp").write_text(source)
    subprocess.run(["c++", "-std=c++17", "-I", str(tmp), "-I", str(root / "src"),
                    str(tmp / "test.cpp"), "-o", str(tmp / "test")], check=True)
    subprocess.run([str(tmp / "test")], check=True)
print("Brady transport tests passed")
