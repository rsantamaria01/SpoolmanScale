"""The serial harness rasters stay in the live printable rectangle."""
import subprocess
import tempfile
from pathlib import Path
root = Path(__file__).parents[1]
source = r'''
#include "fork/brady-test/labels.h"
#include <cassert>
#include <vector>
int main(){
 BradyStatus s{};s.width=125;s.height=240;
 std::vector<uint8_t> bytes(8194,0x55);LabelRaster image{};
 assert(bradyTestLabel(s,false,{bytes.data()+1,8192},image));
 assert(image.width==125&&image.height==240&&image.row_bytes==16&&image.length==3840);
 assert(bytes.front()==0x55&&bytes.back()==0x55);
 assert(image.pixels[0]&0x80);assert(image.pixels[15]&8);
 for(unsigned y=0;y<image.height;++y)assert(!(image.pixels[(y+1)*16-1]&7));
 assert(bradyGridDot(20)==160 && bradyGridDot(30)==240 && bradyGridDot(100)==799);
 s.height=0;assert(bradyTestLabel(s,true,{bytes.data()+1,8192},image));
 assert(image.height==320);
 unsigned ink=0;for(size_t i=0;i<image.length;++i)ink+=image.pixels[i]!=0;
 assert(ink>30 && ink<image.length/2);
 s.width=60;s.height=100;assert(bradyTestLabel(s,true,{bytes.data()+1,8192},image));
 s.width=30;assert(!bradyTestLabel(s,true,{bytes.data()+1,8192},image));
 s.width=125;s.height=10;assert(!bradyTestLabel(s,true,{bytes.data()+1,8192},image));
 s.height=240;assert(!bradyTestLabel(s,false,{bytes.data()+1,100},image));
 s.width=0;assert(!bradyTestLabel(s,false,{bytes.data()+1,8192},image));
}
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp=Path(tmp)/"test.cpp"
    cpp.write_text(source)
    binary=Path(tmp)/"test"
    subprocess.run(["c++","-std=c++17","-Wall","-Wextra","-Werror","-I",str(root),"-I",str(root/"src"),str(cpp),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print("Brady label tests passed")
