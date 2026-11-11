"""Exercise production UV receipt and cache restoration with a controlled store."""
from pathlib import Path
import subprocess
import tempfile
source = Path('src/c/cyberpunk.c').read_text()
def function(name):
    start = source.index('static void ' + name + '(')
    return source[start:source.index('\n}', start)+2]
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define TUPLE_INT 1
#define TUPLE_UINT 2
typedef int AppTimer;
static AppTimer *s_weather_timeout;
static void app_timer_cancel(AppTimer *timer) {}
static int icon_updates, last_code;
static void set_weather_icon(int32_t code) {++icon_updates; last_code=code;}
#define MESSAGE_KEY_WEATHER_CODE 100
#define MESSAGE_KEY_TEMPERATURE 1
#define MESSAGE_KEY_UV_INDEX 2
#define MESSAGE_KEY_JS_READY 3
#define WEATHER_PERSIST_KEY 1
#define UV_PERSIST_KEY 2
typedef union {int32_t int32;} Value;
typedef struct {int type,length; Value *value;} Tuple;
typedef struct {Tuple *uv; Tuple *code;} DictionaryIterator;
static char s_uv_index[12]="--", s_temperature[16];
static void *s_canvas=(void *)1;
static bool s_js_ready, s_weather_pending;
static int redraws, writes, saved;
static bool exists;
static bool persist_exists(int key) {return exists;}
static int persist_read_int(int key) {return saved;}
static void persist_write_int(int key, int value) {assert(key==UV_PERSIST_KEY); saved=value; exists=true; ++writes;}
static void layer_mark_dirty(void *layer) {++redraws;}
static void receive_frame_settings(DictionaryIterator *iter) {}
static void receive_time_format(DictionaryIterator *iter) {}
static void receive_temperature_unit(DictionaryIterator *iter) {}
static int32_t s_temperature_celsius;
static bool s_has_temperature;
static void format_temperature(void) {layer_mark_dirty(s_canvas);}
static void request_weather(void) {}
static Tuple *dict_find(DictionaryIterator *iter, int key) {return key==MESSAGE_KEY_UV_INDEX ? iter->uv : key==MESSAGE_KEY_WEATHER_CODE ? iter->code : NULL;}
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
int main(void) {
  load_uv_index(); assert(strcmp(s_uv_index,"--")==0);
  Value value={6}; Tuple tuple={TUPLE_INT,4,&value}; DictionaryIterator iter={&tuple};
  weather_received(&iter,NULL); assert(strcmp(s_uv_index,"6")==0 && saved==6);
  strcpy(s_uv_index,"--"); load_uv_index(); assert(strcmp(s_uv_index,"6")==0);
  value.int32=0; weather_received(&iter,NULL); assert(strcmp(s_uv_index,"0")==0 && saved==0);
  strcpy(s_uv_index,"--"); load_uv_index(); assert(strcmp(s_uv_index,"0")==0);
  value.int32=-1; weather_received(&iter,NULL); assert(writes==2 && redraws==2);
  value.int32=101; weather_received(&iter,NULL); assert(writes==2);
  value.int32=6; tuple.type=3; weather_received(&iter,NULL); assert(writes==2);
  tuple.type=TUPLE_INT; tuple.length=1; weather_received(&iter,NULL); assert(writes==2);
  iter.uv=NULL; weather_received(&iter,NULL); assert(writes==2);
  assert(icon_updates==0); // UV-only messages preserve the weather icon.
  iter.code=&tuple; tuple.type=TUPLE_INT; tuple.length=4; value.int32=0;
  weather_received(&iter,NULL); assert(icon_updates==1 && last_code==0);
  value.int32=-1; weather_received(&iter,NULL); assert(last_code==-1);
  tuple.length=1; value.int32=3; weather_received(&iter,NULL); assert(last_code==-1);
  tuple.length=4; tuple.type=3; weather_received(&iter,NULL); assert(last_code==-1);
  saved=-1; load_uv_index(); assert(strcmp(s_uv_index,"0")==0);
  visible=false; s_canvas=(void *)1;
  int before_hidden=redraws;
  iter.code=NULL; iter.uv=&tuple; tuple.type=TUPLE_INT; tuple.length=4; value.int32=7;
  weather_received(&iter,NULL);
  assert(redraws==before_hidden && saved==7 && strcmp(s_uv_index,"7")==0);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'test.c').write_text(stub+function('load_uv_index')+function('weather_received')+main)
    subprocess.run(['cc','-o',str(path/'test'),str(path/'test.c')],check=True)
    subprocess.run([str(path/'test')],check=True)
print('Watch UV receipt, validation, zero, and cache restoration passed')
