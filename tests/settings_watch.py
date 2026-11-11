"""Compile the production settings handlers against a controlled dictionary/store."""
from pathlib import Path
import subprocess
import tempfile
source = Path('src/c/cyberpunk.c').read_text()
settings = source[source.index('enum { FRAME_NONE'):source.index('enum { TIME_FORMAT_12')]
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define MESSAGE_KEY_FRAME_LEFT 10003
#define MESSAGE_KEY_FRAME_MIDDLE 10004
#define MESSAGE_KEY_FRAME_RIGHT 10005
#define TUPLE_INT 1
#define TUPLE_UINT 2
#define TUPLE_CSTRING 3
typedef union {int32_t int32;} Value;
typedef struct {int type, length; Value *value;} Tuple;
typedef struct {Tuple *slots[3];} DictionaryIterator;
static void *s_canvas = (void *)1;
static int redraws, writes, saved[32];
static bool exists[32];
static bool persist_exists(int key) {return exists[key];}
static int persist_read_int(int key) {return saved[key];}
static void persist_write_int(int key, int value) {saved[key]=value; exists[key]=true; ++writes;}
static void layer_mark_dirty(void *layer) {++redraws;}
static Tuple *dict_find(DictionaryIterator *iter, uint32_t key) {return iter->slots[key-10003];}
'''
main = r'''
int main(void) {
  load_frame_settings();
  assert(s_frame_contents[0]==1 && s_frame_contents[1]==2 && s_frame_contents[2]==3);
  Value zero={0}, three={3}, bad={99};
  Tuple none={TUPLE_INT,4,&zero}, weather={TUPLE_UINT,4,&three}, invalid={TUPLE_INT,4,&bad};
  DictionaryIterator iter={{&none,&weather,&weather}};
  receive_frame_settings(&iter);
  assert(s_frame_contents[0]==0 && s_frame_contents[1]==3 && s_frame_contents[2]==3);
  assert(redraws==1 && writes==2);
  receive_frame_settings(&iter); assert(redraws==1 && writes==2);
  iter=(DictionaryIterator){{&invalid,NULL,NULL}};
  receive_frame_settings(&iter); assert(s_frame_contents[0]==0 && redraws==1);
  none.type=TUPLE_CSTRING; iter.slots[0]=&none;
  receive_frame_settings(&iter); assert(redraws==1);
  none.type=TUPLE_INT; none.length=1;
  receive_frame_settings(&iter); assert(redraws==1);
  s_frame_contents[0]=1; s_frame_contents[1]=2;
  load_frame_settings(); assert(s_frame_contents[0]==0 && s_frame_contents[1]==3);
  saved[10]=4; load_frame_settings(); assert(s_frame_contents[0]==4);
  saved[10]=-1; s_frame_contents[0]=1;
  load_frame_settings(); assert(s_frame_contents[0]==1);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.c').write_text(stub+settings+main)
    subprocess.run(['cc','-o',str(path/'test'),str(path/'test.c')],check=True)
    subprocess.run([str(path/'test')],check=True)
print('Watch settings defaults, validation, partial updates, and persistence passed')
