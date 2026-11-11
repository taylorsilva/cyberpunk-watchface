"""Exercise production time formatting and settings against a controlled store."""
from pathlib import Path
import subprocess
import tempfile

source = Path('src/c/cyberpunk.c').read_text()
settings = source[source.index('enum { TIME_FORMAT_12'):source.index('enum { TEMPERATURE_CELSIUS')]
start = source.index('static void update_time(struct tm *now) {')
formatting = source[start:source.index('\n}', start) + 2]
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#define MESSAGE_KEY_TIME_FORMAT 10007
#define TUPLE_INT 1
#define TUPLE_UINT 2
#define TUPLE_CSTRING 3
typedef union {int32_t int32;} Value;
typedef struct {int type, length; Value *value;} Tuple;
typedef struct {Tuple *format;} DictionaryIterator;
static char s_hour[3], s_minute[3], s_day[3];
static const char *s_weekday, *s_month;
static void *s_canvas = (void *)1;
static int redraws, writes, saved;
static bool exists;
static bool persist_exists(int key) {assert(key == 3); return exists;}
static int persist_read_int(int key) {assert(key == 3); return saved;}
static void persist_write_int(int key, int value) {
  assert(key == 3); saved = value; exists = true; ++writes;
}
static void layer_mark_dirty(void *layer) {assert(layer == s_canvas); ++redraws;}
static Tuple *dict_find(DictionaryIterator *iter, uint32_t key) {
  assert(key == MESSAGE_KEY_TIME_FORMAT); return iter->format;
}
'''
main = r'''
int main(void) {
  load_time_format(); assert(s_time_format == 12);
  struct tm now = {.tm_year=126, .tm_mon=9, .tm_mday=24, .tm_wday=6, .tm_min=5};
  const int hours[] = {0, 1, 9, 12, 13, 23};
  const char *hours12[] = {"12", "01", "09", "12", "01", "11"};
  const char *hours24[] = {"00", "01", "09", "12", "13", "23"};
  for (int mode = 12; mode <= 24; mode += 12) {
    s_time_format = mode;
    for (unsigned i=0; i<sizeof(hours)/sizeof(hours[0]); ++i) {
      now.tm_hour = hours[i]; update_time(&now);
      assert(strcmp(s_hour, mode == 12 ? hours12[i] : hours24[i]) == 0);
      assert(strcmp(s_minute, "05") == 0 && strcmp(s_day, "24") == 0);
      assert(strcmp(s_weekday, "SAT") == 0 && strcmp(s_month, "OCT") == 0);
    }
    now.tm_min=0; update_time(&now); assert(strcmp(s_minute, "00") == 0);
    now.tm_min=5;
  }
  s_time_format=12; redraws=0;
  Value value={24}; Tuple tuple={TUPLE_INT,4,&value}; DictionaryIterator iter={&tuple};
  receive_time_format(&iter);
  assert(s_time_format==24 && saved==24 && writes==1 && redraws==1);
  time_t clock_now=time(NULL); struct tm *current=localtime(&clock_now);
  char expected[3]; strftime(expected,sizeof(expected),"%H",current);
  assert(strcmp(s_hour,expected)==0);
  receive_time_format(&iter); assert(writes==1 && redraws==1);
  s_time_format=12; load_time_format(); assert(s_time_format==24);
  value.int32=12; tuple.type=TUPLE_UINT; receive_time_format(&iter);
  assert(s_time_format==12 && saved==12 && writes==2 && redraws==2);
  s_time_format=24; load_time_format(); assert(s_time_format==12);
  value.int32=13; receive_time_format(&iter);
  value.int32=-1; receive_time_format(&iter);
  value.int32=24; tuple.type=TUPLE_CSTRING; receive_time_format(&iter);
  tuple.type=TUPLE_INT; tuple.length=1; receive_time_format(&iter);
  iter.format=NULL; receive_time_format(&iter);
  assert(s_time_format==12 && writes==2 && redraws==2);
  saved=0; load_time_format(); assert(s_time_format==12);
  s_canvas=NULL; now.tm_hour=0; update_time(&now); assert(redraws==2);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(stub + settings + formatting + main)
    subprocess.run(['cc', '-o', str(path / 'test'), str(path / 'test.c')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Time format boundaries, immediate refresh, validation, and restart persistence passed')
