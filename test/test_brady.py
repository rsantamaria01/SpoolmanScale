"""Host assertions for the actual Brady encoder, parser and bounded session."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).parents[1]
source = r'''
#include "services/brady.cpp"
#include <cassert>
#include <vector>
#include <string>
static bool connected=false;
static std::vector<uint8_t> incoming;
static std::string selected;
static unsigned sends=0;
static bool fail_send=false;
static int terminal=0;
static BradySession* active_session=nullptr;
static void queueStatus(const char* text);
bool bleTalkConnected(){return connected;}
bool bleTalkRxOverflowed(){return false;}
BleWriteResult bleTalkOpen(const char*,const BleTalkEndpoint&,BleProgressFn){connected=true;return BLE_WRITE_OK;}
BleWriteResult bleTalkClose(){connected=false;return BLE_WRITE_OK;}
bool bleTalkSelectWrite(const char* uuid,bool){selected=uuid;return connected;}
bool bleTalkSend(const uint8_t* data,size_t){
 ++sends;
 if(terminal && selected==BRADY_PRINT && data[0]==3){
 std::string text = terminal==1 ? std::string(active_session->job_name)+": Successful" : "old: Successful";
 queueStatus(text.c_str());
 }
 return connected && !fail_send;
}
size_t bleTalkMaxWrite(){return 182;}
size_t bleTalkRead(uint8_t* out,size_t n,uint32_t){
 n=std::min(n,incoming.size());memcpy(out,incoming.data(),n);incoming.erase(incoming.begin(),incoming.begin()+n);return n;
}
void bleTalkSetPhase(BleSessionPhase){}
void bleTalkSetProgress(size_t,size_t){}
static std::vector<uint8_t> packet(const char* text){
 std::vector<uint8_t> p(20+strlen(text));
 assert(bradyPiclPacket(text,p.data(),p.size())==p.size());return p;
}
static void queueStatus(const char* text){
 char json[256];snprintf(json,sizeof(json),"{\"PropertyGetResponses\":[{\"ID\":\"0029\",\"Value\":\"%s\",\"Status\":\"Successful\"}]}",text);
 auto p=packet(json);incoming.insert(incoming.end(),p.begin(),p.end());
}
static void property(BradySession& s,const char* id,const char* value,const char* status="Successful"){
 char json[256];snprintf(json,sizeof(json),"{\"PropertyGetResponses\":[{\"ID\":\"%s\",\"Value\":\"%s\",\"Status\":\"%s\"}]}",id,value,status);
 auto p=packet(json);assert(bradyReceive(s,p.data(),p.size()));
}
int main(){
 uint8_t guid[17];
 const uint8_t want[]={0x33,0x22,0x11,0,0x55,0x44,0x77,0x66,0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff,1};
 assert(bradyOwnershipBytes({"00112233-4455-6677-8899-aabbccddeeff",true},guid));
 assert(memcmp(guid,want,17)==0);
 assert(bradyOwnershipBytes({"00112233-4455-6677-8899-aabbccddeeff",false},guid)&&guid[16]==0);
 for(auto bad:{"", "00112233445566778899aabbccddeeff","00112233-4455-6677-8899-aabbccddeefg","00112233-4455-6677-8899-aabbccddeeff0"})
 assert(!bradyOwnershipBytes({bad,false},guid));
 std::vector<uint8_t> data(4200,0xaa); uint8_t out[151]; BradyChunks c{};
 assert(bradyChunksBegin(c,{data.data(),data.size()},182));
 unsigned count=0;size_t n;
 while((n=bradyChunkNext(c,out,sizeof(out)))){
 assert(n<=151 && out[1]==(count&255) && out[2]==(count>>8));
 if(count==27)assert(out[0]==2);
 else if(count==28)assert(out[0]==3 && n==59);
 else assert(out[0]==1);
 ++count;
 }
 assert(count==29);
 assert(!bradyChunksBegin(c,{data.data(),0},182));
 assert(!bradyChunksBegin(c,{data.data(),BRADY_MAX_JOB_BYTES+1},182));
 assert(!bradyChunksBegin(c,{data.data(),20},3));
 data.resize(4400);
 assert(bradyChunksBegin(c,{data.data(),4400},20));
 for(unsigned i=0;i<=256;++i){assert(bradyChunkNext(c,out,sizeof(out))<=20); if(i==256)assert(out[1]==0&&out[2]==1);}
 auto p=packet("{}");
 const uint8_t prefix[]={0x96,0xc2,0xf7,0x4a,0x1d,0x21,0x42,0x32,0x86,0x78,0x20,0xef,0xe9,0x7b,0xc2,0xd3,2,0,0,0};
 assert(memcmp(p.data(),prefix,20)==0);
 BradySession s{};
 p=packet("{\"PropertyGetResponses\":[{\"ID\":\"000C\",\"Value\":\"125\",\"Status\":\"Successful\"}]}");
 assert(bradyReceive(s,p.data(),19)&&s.status.valid==0);
 assert(bradyReceive(s,p.data()+19,p.size()-19)&&s.status.width==125);
 auto q=p;q.insert(q.end(),p.begin(),p.end());assert(bradyReceive(s,q.data(),q.size()));
 for(auto bad:{"-1","12junk","999999999999999999","0","1.5"," 125"}){
 property(s,"000C",bad);assert(!bradyReady(s.status));assert(!(s.status.valid&1));
 }
 property(s,"000C","75"); property(s,"000D","0"); property(s,"000E","0"); property(s,"000F","0");
 for(auto id:{"0005","0006","0009","000A","0021","0025","0027"})property(s,id,"False");
 assert(!bradyReady(s.status));
 property(s,"0013","False");property(s,"002A","M21-750-595-WT");
 property(s,"002A","","Failed");assert(!bradyReady(s.status));
 property(s,"002A","M21-750-595-WT");
 assert(bradyReady(s.status) && !s.status.die_cut && strcmp(s.status.cartridge,"M21-750-595-WT")==0);
 property(s,"0013","True");assert(s.status.die_cut && !bradyReady(s.status));
 property(s,"0013","unknown");assert(!bradyReady(s.status));
 property(s,"0013","False");
 property(s,"000C","95");assert(!bradyReady(s.status));property(s,"000C","75");
 property(s,"000D","20");assert(!bradyReady(s.status));property(s,"000D","0");
 property(s,"0005","False","Failed");assert(!bradyReady(s.status));
 property(s,"0005","False");assert(bradyReady(s.status));
 property(s,"0025","True");assert(!bradyReady(s.status));property(s,"0025","False");
 strcpy(s.job_name,"new-job");
 property(s,"0029","old-job: Successful");assert(s.status.job==BRADY_JOB_PENDING);
 property(s,"0029","old-job: Failed");assert(s.status.job==BRADY_JOB_PENDING);
 property(s,"0029","new-job:Successful");assert(s.status.job==BRADY_JOB_SUCCESS);
 s.status.job=BRADY_JOB_PENDING;
 for(auto bad:{"new-job-extra:Successful","new-job:  Successful","new-job:Successful junk","new:Successful","new-job"}){
 property(s,"0029",bad);assert(s.status.job==BRADY_JOB_PENDING);
 }
 property(s,"0029","new-job: Successful");assert(s.status.job==BRADY_JOB_SUCCESS);
 property(s,"0029","new-job:Failed");assert(s.status.job==BRADY_JOB_FAILED);
 property(s,"0029","new-job: Failed");assert(s.status.job==BRADY_JOB_FAILED);
 for(auto entry:{
 "{\"ID\":\"000C\",\"Value\":\"125\\u0000junk\",\"Status\":\"Successful\"}",
 "{\"ID\":\"0025\",\"Value\":\"False\\u0000True\",\"Status\":\"Successful\"}",
 "{\"ID\":\"0029\",\"Value\":\"new-job: Successful\\u0000junk\",\"Status\":\"Successful\"}"}){
 BradySession bad{};auto text=std::string("{\"PropertyGetResponses\":[")+entry+"]}";
 auto invalid=packet(text.c_str());assert(!bradyReceive(bad,invalid.data(),invalid.size()));
 }
 BradySession malformed{};p=packet("{}");p[16]=0xff;p[17]=0xff;
 assert(!bradyReceive(malformed,p.data(),p.size())&&malformed.status.valid==0);
 malformed={};p=packet("{}");p[0]=0;assert(!bradyReceive(malformed,p.data(),p.size()));
 uint8_t pixels[]={0x80,0x80,0,0};LabelRaster image{9,2,2,pixels,4,9};
 BradyStatus geometry=s.status;geometry.width=9;geometry.height=2;geometry.x=0;geometry.y=0;geometry.die_cut=true;
 std::vector<uint8_t> vgl(BRADY_MAX_JOB_BYTES);
 const char* wire="0123456789abcdef0123456789abcdef";
 n=bradyVgl(image,geometry,wire,vgl.data(),vgl.size());assert(n);
 const uint8_t expected[]={2,'K',0,10,
 '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',
 '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f',13,
 2,'K',0,9,'M','2','1','-','7','5','0',13,
 2,'p','+','0','0',2,'o','+','0','0',2,'O','+','0','0',2,'b','+','0','0',
 2,'M',1,2,'K',0,12,'0','0','0','9','0','0','0','2',2,'W',0,2,'A',2,'Q',2,'a',
 2,'I','B','U','l','b','l','0',13,'X',0,0,'Y',0,0,
 0x81,3,0x80,6,0x80,0x81,1,8,'Y',2,0,255,255,13,2,'a',2,'G',2,'A',2,'K',0,11};
 assert(n==sizeof(expected) && memcmp(vgl.data(),expected,n)==0);
 assert(!bradyVgl(image,geometry,wire,vgl.data(),n-1));
 assert(bradyVgl(image,geometry,wire,vgl.data(),n)==n);
 assert(!bradyVgl(image,geometry,"bad\rname",vgl.data(),vgl.size()));
 assert(!bradyVgl(image,geometry,wire,vgl.data(),10));
 pixels[1]=0x81;assert(!bradyVgl(image,geometry,wire,vgl.data(),vgl.size()));pixels[1]=0x80;
 image.width=0;assert(!bradyVgl(image,geometry,wire,vgl.data(),vgl.size()));image.width=9;
 image.length=BRADY_MAX_JOB_BYTES+1;assert(!bradyVgl(image,geometry,wire,vgl.data(),vgl.size()));image.length=4;
 uint8_t wide_pixels[19*56]{};LabelRaster wide{152,56,19,wide_pixels,sizeof(wide_pixels),152};
 BradyStatus converted{};converted.width=152;
 n=bradyVgl(wide,converted,wire,vgl.data(),vgl.size());assert(n);
 const uint8_t dims[]={2,'K',0,12,'0','1','5','2','0','0','5','6'};
 assert(memcmp(vgl.data()+72,dims,sizeof(dims))==0);
 const uint8_t blank_row[]={0x81,2,127,23};
 assert(memcmp(vgl.data()+108,blank_row,sizeof(blank_row))==0);
 memset(wide_pixels,0xff,sizeof(wide_pixels));
 n=bradyVgl(wide,converted,wire,vgl.data(),vgl.size());assert(n);
 const uint8_t black_row[]={0x81,2,255,151};
 assert(memcmp(vgl.data()+108,black_row,sizeof(black_row))==0);
 std::vector<uint8_t> noisy(19*300,0xaa);LabelRaster large{152,300,19,noisy.data(),noisy.size(),152};
 assert(!bradyVgl(large,converted,wire,vgl.data(),100));
 assert(!bradyVgl(large,converted,wire,vgl.data(),vgl.size()));
 converted.x=2;converted.y=3;
 assert(bradyVgl(wide,converted,wire,vgl.data(),vgl.size()));
 assert(vgl[103]==2 && vgl[104]==0 && vgl[106]==3 && vgl[107]==0);
 converted.x=41;assert(!bradyVgl(wide,converted,wire,vgl.data(),vgl.size()));
 converted.x=0;converted.y=1;assert(bradyVgl(wide,converted,wire,vgl.data(),vgl.size()));
 converted.y=0;converted.die_cut=true;converted.height=56;
 assert(bradyVgl(wide,converted,wire,vgl.data(),vgl.size()));
 wide.height=55;assert(!bradyVgl(wide,converted,wire,vgl.data(),vgl.size()));
 wide.height=56;converted.height=0;converted.die_cut=false;
 geometry=converted;BradyStatus rawPrint{};rawPrint.width=75;rawPrint.valid=REQUIRED;
 unsigned before=sends;assert(bradyPrint(s,wide,"offline")==BRADY_TRANSPORT&&sends==before);
 connected=true;s.open=true;s.status={};assert(bradyPrint(s,image,"unsafe")==BRADY_INVALID_STATUS&&sends==before);
 bradyClose(s);assert(!connected&&!s.open);
 connected=true;s.open=true;s.status=rawPrint;
 std::string harmless="{\"PropertyGetResponses\":[]}";harmless.resize(236,' ');
 auto queued=packet(harmless.c_str());incoming=queued;
 auto error=packet("{\"PropertyGetResponses\":[{\"ID\":\"0025\",\"Value\":\"True\",\"Status\":\"Successful\"}]}");
 incoming.insert(incoming.end(),error.begin(),error.end());before=sends;
 assert(bradyPrint(s,image,"unsafe-queue")==BRADY_INVALID_STATUS&&sends==before);
 s.status=rawPrint;incoming=queued;incoming.insert(incoming.end(),error.begin(),error.end());
 assert(bradyCut(s)==BRADY_INVALID_STATUS&&sends==before);
 s.status=rawPrint;
 incoming=packet("{\"PropertyGetResponses\":[{\"ID\":\"000C\",\"Value\":\"76\",\"Status\":\"Successful\"}]}");
 assert(bradyPrint(s,wide,"changed-media",&geometry)==BRADY_INVALID_STATUS && sends==before);
 s.status=rawPrint;terminal=1;active_session=&s;
 assert(bradyPrint(s,wide,"fresh")==BRADY_OK);
 s.status=rawPrint;before=sends;
 incoming=packet("{\"PropertyGetResponses\":[{\"ID\":\"002A\",\"Value\":\"OTHER\",\"Status\":\"Successful\"}]}");
 assert(bradyPrint(s,wide,"cartridge-change")==BRADY_INVALID_STATUS && sends==before);
 s.status=rawPrint;
 const std::string first_name=s.job_name;
 assert(first_name.size()==32 && first_name.find_first_not_of("0123456789abcdef")==std::string::npos);
 s.status=rawPrint;
 assert(bradyPrint(s,wide,"mapped",&geometry)==BRADY_OK && s.status.width==75);
 s.status=rawPrint;
 assert(bradyPrint(s,wide,"other")==BRADY_OK);
 assert(bradyPrint(s,wide,"fresh")==BRADY_OK);
 assert(first_name!=s.job_name);
 bradyClose(s);s={};s.open=true;connected=true;s.status=rawPrint;
 assert(bradyPrint(s,wide,"fresh")==BRADY_OK && first_name!=s.job_name);
 terminal=2;assert(bradyPrint(s,wide,"newer")==BRADY_UNCONFIRMED);
 fail_send=true;before=sends;assert(bradyPrint(s,wide,"ambiguous")==BRADY_UNCONFIRMED&&sends==before+1);
 bradyClose(s);fail_send=false;
 assert(bradyOpen("address",{"00112233-4455-6677-8899-aabbccddeeff",false},s)==BRADY_INVALID_STATUS);
 assert(s.open);bradyClose(s);
 fail_send=true;
 assert(bradyOpen("address",{"00112233-4455-6677-8899-aabbccddeeff",false},s)==BRADY_OWNERSHIP);
 assert(!connected&&!s.open);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "Arduino.h").write_text('#pragma once\n#include <cstdint>\ninline uint32_t ticks=0;\ninline uint32_t millis(){return ticks++;}\ninline void delay(uint32_t n){ticks+=n;}\n')
    (tmp / "esp_random.h").write_text('#pragma once\n#include <cstdint>\ninline uint32_t esp_random(){return 0x12345678;}\n')
    (tmp / "hardware").mkdir()
    (tmp / "hardware/sd_logger.h").write_text('#pragma once\ninline void logSD(const char*){}\ntemplate<class... T> void logSDf(const char*,T...){}\n')
    (tmp / "test.cpp").write_text(source)
    json_dir = root / ".pio/libdeps/wt32-sc01-plus/ArduinoJson/src"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(tmp),
                    "-I", str(root / "src"), "-I", str(json_dir), str(tmp / "test.cpp"),
                    "-o", str(tmp / "test")], check=True)
    subprocess.run([str(tmp / "test")], check=True)
print("Brady protocol tests passed")
