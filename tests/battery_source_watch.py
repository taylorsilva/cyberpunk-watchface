"""Exercise battery-source selection, message dispatch, persistence, and bar drawing."""
from pathlib import Path
import subprocess
import tempfile
source = Path('src/c/cyberpunk.c').read_text()
battery = source[source.index('enum { BATTERY_SOURCE_WATCH'):source.index('static void weather_received')]

def function(name, kind='void'):
    marker = 'static ' + kind + ' ' + name + '('
    start = 0
    while True:
        start = source.index(marker, start)
        if ';' not in source[start:source.index('\n', start)]:
            return source[start:source.index('\n}', start)+2]
        start += 1

bar_drawing = function('bar_color', 'GColor') + function('draw_battery_bar')

stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define TUPLE_INT 1
#define TUPLE_UINT 2
#define TUPLE_CSTRING 3
#define MESSAGE_KEY_BATTERY_SOURCE 100
#define MESSAGE_KEY_PHONE_BATTERY 101
typedef union {int32_t int32;} Value;
typedef struct {int type, length; Value *value;} Tuple;
typedef struct {Tuple *source; Tuple *phone;} DictionaryIterator;
static Tuple *dict_find(DictionaryIterator *iter, int key) {
  return key == MESSAGE_KEY_BATTERY_SOURCE ? iter->source :
         key == MESSAGE_KEY_PHONE_BATTERY ? iter->phone : NULL;
}
static int saved[32], writes, redraws;
static bool exists[32];
static bool persist_exists(int key) {return exists[key];}
static int persist_read_int(int key) {return saved[key];}
static void persist_write_int(int key, int value) {
  saved[key]=value; exists[key]=true; ++writes;
}
static void *s_canvas = (void *)1;
static void layer_mark_dirty(void *layer) {++redraws;}
typedef int GColor;
#define BAR_CYAN 101
#define BAR_RED 202
static GColor cyan(void) {return BAR_CYAN;}
static GColor red(void) {return BAR_RED;}
static uint8_t s_battery = 42;
static bool s_connected = true;
/* Graphics recorder: the bar must use the phone value and color when selected. */
typedef struct {int x, y;} GPoint;
typedef struct {int w, h;} GSize;
typedef struct {GPoint origin; GSize size;} GRect;
#define GRect(x, y, w, h) ((GRect){{(x), (y)}, {(w), (h)}})
typedef struct {int unused;} GContext;
#define GCornerNone 0
static int stroke_color, fill_color, stroke_width, fills, outlines;
static int filled_color, outlined_color;
static GRect fill_rect, outline_rect;
static void graphics_context_set_stroke_width(GContext *ctx, int width) {stroke_width=width;}
static void graphics_context_set_stroke_color(GContext *ctx, int color) {stroke_color=color;}
static void graphics_context_set_fill_color(GContext *ctx, int color) {fill_color=color;}
static void graphics_fill_rect(GContext *ctx, GRect rect, int radius, int corners) {
  ++fills; fill_rect=rect; filled_color=fill_color;
}
static void graphics_draw_rect(GContext *ctx, GRect rect) {
  ++outlines; outline_rect=rect; outlined_color=stroke_color;
}
'''

main = r'''
static void reset(void) {
  s_battery_source=BATTERY_SOURCE_WATCH;
  s_phone_battery=0; s_has_phone_battery=false;
  s_battery=42; s_connected=true; s_canvas=(void *)1;
  writes=redraws=fills=outlines=0;
  for (int i=0; i<32; ++i) exists[i]=false;
}
int main(void) {
  GContext ctx;
  reset();
  assert(s_battery_source==BATTERY_SOURCE_WATCH && bar_battery()==42);

  exists[5]=true; saved[5]=1; load_battery_source();
  assert(s_battery_source==BATTERY_SOURCE_PHONE);
  s_battery_source=BATTERY_SOURCE_WATCH; saved[5]=7; load_battery_source();
  assert(s_battery_source==BATTERY_SOURCE_WATCH);
  exists[5]=false; saved[5]=1; load_battery_source();
  assert(s_battery_source==BATTERY_SOURCE_WATCH);

  reset();
  Value value={1}; Tuple source={TUPLE_INT,4,&value}; DictionaryIterator iter={&source};
  receive_battery_source(&iter);
  assert(s_battery_source==BATTERY_SOURCE_PHONE && saved[5]==1);
  assert(writes==1 && redraws==1);
  receive_battery_source(&iter);
  assert(writes==1 && redraws==1); // Unchanged source must not rewrite or redraw.
  assert(bar_battery()==42); // Watch battery is the fallback until a phone reading arrives.

  Value phone={73}; Tuple reading={TUPLE_INT,4,&phone}; iter.phone=&reading;
  receive_phone_battery(&iter);
  assert(s_has_phone_battery && s_phone_battery==73 && bar_battery()==73);
  assert(writes==1 && redraws==2); // Phone readings update the bar without persistence.
  assert(bar_color()==BAR_CYAN);

  s_connected=false;
  assert(bar_battery()==42); // Disconnection falls back to the watch battery.
  assert(bar_color()==BAR_RED);
  s_connected=true;
  assert(bar_battery()==73 && bar_color()==BAR_CYAN);

  phone.int32=0; receive_phone_battery(&iter); assert(bar_battery()==0);
  assert(bar_color()==BAR_RED);
  phone.int32=40; receive_phone_battery(&iter);
  assert(bar_battery()==40 && bar_color()==BAR_RED);
  phone.int32=41; receive_phone_battery(&iter);
  assert(bar_battery()==41 && bar_color()==BAR_CYAN);
  phone.int32=100; receive_phone_battery(&iter); assert(bar_battery()==100);
  assert(bar_color()==BAR_CYAN);
  int old_writes=writes, old_redraws=redraws;
  phone.int32=101; receive_phone_battery(&iter); assert(bar_battery()==100);
  phone.int32=-1; receive_phone_battery(&iter); assert(bar_battery()==100);
  reading.type=TUPLE_CSTRING; receive_phone_battery(&iter); assert(bar_battery()==100);
  reading.type=TUPLE_INT; reading.length=1; receive_phone_battery(&iter);
  assert(bar_battery()==100);
  iter.phone=NULL; receive_phone_battery(&iter); assert(bar_battery()==100);

  old_writes=writes; old_redraws=redraws;
  value.int32=2; receive_battery_source(&iter);
  value.int32=-1; receive_battery_source(&iter);
  source.type=TUPLE_CSTRING; receive_battery_source(&iter);
  source.type=TUPLE_INT; source.length=1; receive_battery_source(&iter);
  iter.source=NULL; receive_battery_source(&iter);
  assert(s_battery_source==BATTERY_SOURCE_PHONE && writes==old_writes &&
         redraws==old_redraws);
  iter.source=&source;
  source.type=TUPLE_INT; source.length=4;
  reading.type=TUPLE_INT; reading.length=4;

  value.int32=0; receive_battery_source(&iter);
  assert(s_battery_source==BATTERY_SOURCE_WATCH && saved[5]==0 && bar_battery()==42);
  s_battery=100;
  assert(bar_battery()==100 && bar_color()==BAR_RED); // Watch fallback never turns cyan.
  s_battery=42;
  iter.phone=&reading;
  phone.int32=88; receive_phone_battery(&iter);
  int watch_redraws=redraws;
  assert(bar_battery()==42);
  value.int32=1; receive_battery_source(&iter);
  assert(bar_battery()==88 && redraws==watch_redraws+1); // Use the latest cached reading.
  assert(bar_color()==BAR_CYAN);

  s_canvas=NULL;
  old_writes=writes;
  value.int32=0; receive_battery_source(&iter);
  phone.int32=55; receive_phone_battery(&iter);
  assert(writes==old_writes+1 && s_battery_source==BATTERY_SOURCE_WATCH);

  /* The bar itself must render the selected value and color. */
  reset();
  s_canvas=(void *)1; s_battery=42;
  draw_battery_bar(&ctx, GRect(8, 182, 184, 10));
  assert(fills==1 && outlines==1 && stroke_width==1);
  assert(filled_color==BAR_RED && outlined_color==BAR_RED);
  assert(fill_rect.origin.x==9 && fill_rect.origin.y==183 &&
         fill_rect.size.w==182*42/100 && fill_rect.size.h==8);
  assert(outline_rect.origin.x==8 && outline_rect.size.w==184);

  reset();
  s_battery=42; s_battery_source=BATTERY_SOURCE_PHONE;
  phone.int32=73; receive_phone_battery(&iter);
  draw_battery_bar(&ctx, GRect(8, 182, 184, 10));
  assert(filled_color==BAR_CYAN && outlined_color==BAR_CYAN);
  assert(fill_rect.size.w==182*73/100);

  reset();
  s_battery_source=BATTERY_SOURCE_PHONE; phone.int32=100;
  receive_phone_battery(&iter);
  draw_battery_bar(&ctx, GRect(8, 182, 184, 10));
  assert(fill_rect.origin.x+fill_rect.size.w==191); // Stays inside the outline.

  reset();
  s_battery=0;
  draw_battery_bar(&ctx, GRect(8, 182, 184, 10));
  assert(fills==0 && outlines==1); // Empty bar keeps the outline.

  exists[5]=true; saved[5]=1; load_battery_source();
  assert(s_battery_source==BATTERY_SOURCE_PHONE);
  return 0;
}
'''

dispatch_stub = r'''
#include <stdio.h>
#include <string.h>
#define MESSAGE_KEY_TEMPERATURE 1
#define MESSAGE_KEY_WEATHER_CODE 2
#define MESSAGE_KEY_UV_INDEX 3
#define MESSAGE_KEY_JS_READY 4
#define FRAME_UV_INDEX 4
#define WEATHER_PERSIST_KEY 1
#define UV_PERSIST_KEY 2
static bool s_js_ready, s_weather_pending, s_has_temperature;
static void *s_weather_timeout;
static int32_t s_temperature_celsius;
static char s_temperature[16]="--°C", s_uv_index[12];
static uint32_t displayed_contents(void) {return 0;}
static bool frame_displayed(unsigned content) {return false;}
static void refresh_card_services(uint32_t previous) {}
static void receive_frame_settings(DictionaryIterator *iter) {}
static void receive_time_format(DictionaryIterator *iter) {}
static void receive_temperature_unit(DictionaryIterator *iter) {}
static void set_weather_icon(int32_t code) {}
static void app_timer_cancel(void *timer) {}
static void format_temperature(void) {}
static void request_weather(void) {}
'''

dispatch_main = r'''
int main(void) {
  GContext ctx;
  Value source={1}, phone={78};
  Tuple s={TUPLE_INT,4,&source}, p={TUPLE_INT,4,&phone};
  DictionaryIterator iter={&s,&p};
  /* One settings submission carries both battery keys through the real inbox handler. */
  weather_received(&iter, NULL);
  assert(s_battery_source==BATTERY_SOURCE_PHONE && saved[5]==1);
  assert(s_has_phone_battery && s_phone_battery==78);
  assert(bar_battery()==78 && bar_color()==BAR_CYAN);
  draw_battery_bar(&ctx, GRect(8, 182, 184, 10));
  assert(filled_color==BAR_CYAN && fill_rect.size.w==182*78/100);

  phone.int32=55; iter.source=NULL;
  weather_received(&iter, NULL); // A phone-only update must also reach the bar.
  assert(bar_battery()==55);

  source.int32=0; iter.source=&s;
  weather_received(&iter, NULL);
  assert(s_battery_source==BATTERY_SOURCE_WATCH && saved[5]==0);
  assert(bar_battery()==42 && bar_color()==BAR_RED);
  return 0;
}
'''

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    for name, text in (('unit', stub), ('dispatch', stub + dispatch_stub)):
        body = main if name == 'unit' else dispatch_main
        receipt = '' if name == 'unit' else source[
            source.index('static void weather_received('):
            source.index('\n}', source.index('static void weather_received('))+2]
        (path / (name + '.c')).write_text(text + battery + bar_drawing + receipt + body)
        subprocess.run(['cc', '-o', str(path / name), str(path / (name + '.c'))], check=True)
        subprocess.run([str(path / name)], check=True)
print('Battery source, dispatch, persistence, and bar drawing passed')
