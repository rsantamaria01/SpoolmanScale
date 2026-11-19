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
static void queueStatus(const char* text);
bool bleTalkConnected(){return connected;}
bool bleTalkRxOverflowed(){return false;}
BleWriteResult bleTalkOpen(const char*,const BleTalkEndpoint&,BleProgressFn){connected=true;return BLE_WRITE_OK;}
BleWriteResult bleTalkClose(){connected=false;return BLE_WRITE_OK;}
bool bleTalkSelectWrite(const char* uuid,bool){selected=uuid;return connected;}
bool bleTalkSend(const uint8_t* data,size_t){
 ++sends;
 if(terminal && selected==BRADY_PRINT && data[0]==3){
 queueStatus(terminal==1 ? "fresh: Successful" : "old: Successful");
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
 for(auto bad:{"-1","12junk","999999999999999999","0","193","1.5"," 125"}){
 property(s,"000C",bad);assert(!bradyReady(s.status));assert(!(s.status.valid&1));
 }
 property(s,"000C","125"); property(s,"000D","0"); property(s,"000E","0"); property(s,"000F","88");
 for(auto id:{"0005","0006","0009","000A","0021","0025","0027"})property(s,id,"False");
 assert(bradyReady(s.status));
 property(s,"0005","False","Failed");assert(!bradyReady(s.status));
 property(s,"0005","False");assert(bradyReady(s.status));
 property(s,"0025","True");assert(!bradyReady(s.status));property(s,"0025","False");
 strcpy(s.job_name,"new-job");
 property(s,"0029","old-job: Successful");assert(s.status.job==BRADY_JOB_PENDING);
 property(s,"0029","old-job: Failed");assert(s.status.job==BRADY_JOB_PENDING);
 property(s,"0029","new-job: Successful");assert(s.status.job==BRADY_JOB_SUCCESS);
 property(s,"0029","new-job: Failed");assert(s.status.job==BRADY_JOB_FAILED);
 BradySession malformed{};p=packet("{}");p[16]=0xff;p[17]=0xff;
 assert(!bradyReceive(malformed,p.data(),p.size())&&malformed.status.valid==0);
 malformed={};p=packet("{}");p[0]=0;assert(!bradyReceive(malformed,p.data(),p.size()));
 uint8_t pixels[]={0x80,0x80,0,0};LabelRaster image{9,2,2,pixels,4,9};
 BradyStatus geometry=s.status;geometry.width=9;geometry.height=2;geometry.x=0;geometry.y=0;
 std::vector<uint8_t> vgl(BRADY_MAX_JOB_BYTES);
 n=bradyVgl(image,geometry,"job-1",vgl.data(),vgl.size());assert(n>100);
 assert(readU32(vgl.data())==1 && readU32(vgl.data()+4)==n-8);
 size_t job=8+readU32(vgl.data()+8);assert(memcmp(vgl.data()+job,"\x02K\0\x0a" "job-1\r",10)==0);
 const uint8_t rows[]={0x80,2,0x80,0x80,0x80,2,0,0,0xff,0xff,13,2,65,2,71};
 assert(memcmp(vgl.data()+n-sizeof(rows),rows,sizeof(rows))==0);
 assert(!bradyVgl(image,geometry,"bad\rname",vgl.data(),vgl.size()));
 assert(!bradyVgl(image,geometry,"ok",vgl.data(),10));
 pixels[1]=0x81;assert(!bradyVgl(image,geometry,"ok",vgl.data(),vgl.size()));pixels[1]=0x80;
 image.width=0;assert(!bradyVgl(image,geometry,"ok",vgl.data(),vgl.size()));image.width=9;
 image.length=BRADY_MAX_JOB_BYTES+1;assert(!bradyVgl(image,geometry,"ok",vgl.data(),vgl.size()));image.length=4;
 unsigned before=sends;assert(bradyPrint(s,image,"offline")==BRADY_TRANSPORT&&sends==before);
 connected=true;s.open=true;s.status={};assert(bradyPrint(s,image,"unsafe")==BRADY_INVALID_STATUS&&sends==before);
 bradyClose(s);assert(!connected&&!s.open);
 connected=true;s.open=true;s.status=geometry;terminal=1;
 assert(bradyPrint(s,image,"fresh")==BRADY_OK);
 terminal=2;assert(bradyPrint(s,image,"newer")==BRADY_UNCONFIRMED);
 fail_send=true;before=sends;assert(bradyPrint(s,image,"ambiguous")==BRADY_UNCONFIRMED&&sends==before+1);
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
    (tmp / "hardware").mkdir()
    (tmp / "hardware/sd_logger.h").write_text('#pragma once\ninline void logSD(const char*){}\ntemplate<class... T> void logSDf(const char*,T...){}\n')
    (tmp / "test.cpp").write_text(source)
    json_dir = root / ".pio/libdeps/wt32-sc01-plus/ArduinoJson/src"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(tmp),
                    "-I", str(root / "src"), "-I", str(json_dir), str(tmp / "test.cpp"),
                    "-o", str(tmp / "test")], check=True)
    subprocess.run([str(tmp / "test")], check=True)
print("Brady protocol tests passed")
