"""Exercise production temperature settings, receipt, formatting, and cache loading."""
from pathlib import Path
import subprocess
import tempfile
source = Path('src/c/cyberpunk.c').read_text()
settings = source[source.index('enum { TEMPERATURE_CELSIUS'):source.index('static void request_weather')]
start = source.index('static void weather_received(')
receipt = source[start:source.index('\n}', start)+2]
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define TUPLE_INT 1
#define TUPLE_UINT 2
#define MESSAGE_KEY_TEMPERATURE_UNIT 0
#define MESSAGE_KEY_TEMPERATURE 1
#define MESSAGE_KEY_WEATHER_CODE 2
#define MESSAGE_KEY_UV_INDEX 3
#define MESSAGE_KEY_JS_READY 4
#define WEATHER_PERSIST_KEY 1
#define UV_PERSIST_KEY 2
typedef union {int32_t int32;} Value;
typedef struct {int type,length; Value *value;} Tuple;
typedef struct {Tuple *items[5];} DictionaryIterator;
static Tuple *dict_find(DictionaryIterator *i, int key) {return i->items[key];}
static int saved[5], writes, redraws;
static bool exists[5];
static bool persist_exists(int key) {return exists[key];}
static int persist_read_int(int key) {return saved[key];}
static void persist_write_int(int key, int value) {saved[key]=value; exists[key]=true; ++writes;}
static void *s_canvas=(void *)1, *s_weather_timeout;
static bool s_has_temperature, s_js_ready, s_weather_pending;
static int32_t s_temperature_celsius;
static char s_temperature[16]="--°C", s_uv_index[12];
static void layer_mark_dirty(void *canvas) {++redraws;}
static void receive_frame_settings(DictionaryIterator *i) {}
static void receive_time_format(DictionaryIterator *i) {}
static void request_weather(void) {}
static void set_weather_icon(int32_t code) {}
static void app_timer_cancel(void *timer) {}
'''
stub += r'''
#define FRAME_TEMPERATURE 3
#define FRAME_UV_INDEX 4
static bool visible = true;
static bool frame_displayed(unsigned content) {return visible;}
static uint32_t displayed_contents(void) {return 0;}
static void refresh_card_services(uint32_t previous) {}
'''
main = r'''
static void restart(void) {
  s_temperature_unit=0; s_has_temperature=false; s_temperature_celsius=0;
  load_temperature();
}
int main(void) {
  restart(); assert(strcmp(s_temperature,"--°C")==0);
  Value unit={1}, temp={20}; Tuple u={TUPLE_INT,4,&unit}, t={TUPLE_INT,4,&temp};
  DictionaryIterator iter={{&u}};
  weather_received(&iter,NULL); assert(strcmp(s_temperature,"--°F")==0 && saved[4]==1);
  restart(); assert(strcmp(s_temperature,"--°F")==0);
  iter.items[1]=&t;
  const int c[]={0,20,-40,1,-1,-18,-19,40,150,-150};
  const char *f[]={"32°F","68°F","-40°F","34°F","30°F","0°F","-2°F","104°F","302°F","-238°F"};
  for (unsigned i=0;i<sizeof(c)/sizeof(c[0]);++i) {
    temp.int32=c[i]; weather_received(&iter,NULL);
    assert(strcmp(s_temperature,f[i])==0 && saved[1]==c[i]);
    restart(); assert(strcmp(s_temperature,f[i])==0);
  }
  unit.int32=0; temp.int32=20; weather_received(&iter,NULL);
  assert(strcmp(s_temperature,"20°C")==0 && saved[4]==0);
  iter.items[1]=NULL; unit.int32=1; weather_received(&iter,NULL);
  assert(strcmp(s_temperature,"68°F")==0);
  int old_writes=writes, old_redraws=redraws;
  receive_temperature_unit(&iter); assert(writes==old_writes && redraws==old_redraws);
  unit.int32=2; receive_temperature_unit(&iter);
  unit.int32=-1; receive_temperature_unit(&iter);
  unit.int32=0; u.type=3; receive_temperature_unit(&iter);
  u.type=TUPLE_UINT; u.length=1; receive_temperature_unit(&iter);
  iter.items[0]=NULL; receive_temperature_unit(&iter);
  assert(writes==old_writes && redraws==old_redraws && s_temperature_unit==1);
  iter.items[1]=&t; temp.int32=151; weather_received(&iter,NULL);
  assert(strcmp(s_temperature,"68°F")==0 && saved[1]==20);
  saved[4]=99; restart(); assert(strcmp(s_temperature,"20°C")==0);
  exists[4]=false; restart(); assert(strcmp(s_temperature,"20°C")==0);
  saved[1]=151; restart(); assert(strcmp(s_temperature,"--°C")==0);
  iter.items[0]=&u; iter.items[1]=NULL; u.length=4; unit.int32=1;
  s_canvas=NULL; receive_temperature_unit(&iter); assert(strcmp(s_temperature,"--°F")==0);
  visible=false; s_canvas=(void *)1;
  int before_hidden=redraws;
  iter.items[0]=NULL; iter.items[1]=&t; temp.int32=25;
  weather_received(&iter,NULL);
  assert(redraws==before_hidden && saved[1]==25 && strcmp(s_temperature,"77°F")==0);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'test.c').write_text(stub+settings+receipt+main)
    subprocess.run(['cc','-o',str(path/'test'),str(path/'test.c')],check=True)
    subprocess.run([str(path/'test')],check=True)
print('Temperature conversion, settings, validation, combined updates, and restart persistence passed')
