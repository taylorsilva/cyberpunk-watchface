"""Exercise production watch scheduling functions with a controlled clock/transport."""
from pathlib import Path
import subprocess
import tempfile

source = Path('src/c/cyberpunk.c').read_text()
def function(name):
    start = source.index('static void ' + name + '(')
    if ';' in source[start:source.index('\n', start)]:
        start = source.index('static void ' + name + '(', start+1)
    end = source.index('\n}', start) + 2
    return source[start:end]

stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include <stddef.h>
typedef int DictionaryIterator;
typedef int AppMessageResult;
typedef int TimeUnits;
typedef int AppTimer;
static AppTimer *s_weather_timeout;
static int last_code=0, timers_started, timers_cancelled;
static void set_weather_icon(int32_t code) {last_code=code;}
static AppTimer *app_timer_register(int ms, void (*cb)(void *), void *ctx) {
  static AppTimer timer; ++timers_started; assert(ms == 60000); return &timer;
}
static void app_timer_cancel(AppTimer *t) {++timers_cancelled;}
#define APP_MSG_OK 0
#define APP_LOG(...) ((void)0)
#define MESSAGE_KEY_REQUEST_WEATHER 10000
#define WEATHER_INTERVAL 3600
static bool s_weather_pending = true, s_js_ready, s_connected;
static time_t s_weather_attempt, clock_now = 100000;
static int sent, vibration, transport_result, last_fields, redraws;
static void *s_canvas;
#define time(x) (clock_now)
static int app_message_outbox_begin(DictionaryIterator **iter) {
  static int dictionary; *iter = &dictionary; return transport_result;
}
static void dict_write_uint8(DictionaryIterator *iter, int key, int value) {
  assert(key == MESSAGE_KEY_REQUEST_WEATHER); last_fields=value;
}
static int app_message_outbox_send(void) { ++sent; return APP_MSG_OK; }
static void update_time(struct tm *t) {}

#include <stdio.h>
#include <string.h>
typedef int HealthServiceAccessibilityMask;
typedef int HealthValue;
typedef int HealthEventType;
enum {HealthMetricStepCount, HealthMetricHeartRateBPM,
      HealthServiceAccessibilityMaskAvailable=1,
      HealthEventMovementUpdate=10, HealthEventSignificantUpdate, HealthEventHeartRateUpdate};
static int step_reads, heart_reads, subscriptions, unsubscriptions;
static char s_steps[12], s_heart_rate[12];
static int health_service_metric_accessible(int m, time_t start, time_t end) {return 1;}
static time_t time_start_of_today(void) {return 0;}
static int health_service_sum_today(int metric) {++step_reads; return 1234;}
static int health_service_peek_current_value(int metric) {++heart_reads; return 72;}
static bool health_service_events_subscribe(void (*handler)(HealthEventType,void *), void *ctx) {++subscriptions; return true;}
static void health_service_events_unsubscribe(void) {++unsubscriptions;}

static void vibes_short_pulse(void) { ++vibration; }
static void layer_mark_dirty(void *layer) {++redraws;}
'''
main = r'''
int main(void) {
  refresh_card_services(0);
  assert(subscriptions==1 && step_reads==1 && heart_reads==1);
  s_connected = true;
  request_weather(); assert(sent == 0 && s_weather_pending && timers_started==0);
  s_js_ready = true;
  request_weather(); assert(sent == 1 && !s_weather_pending && last_fields==1 && timers_started==1);
  clock_now += 3599; tick_handler(NULL, 0); assert(sent == 1);
  clock_now += 1; tick_handler(NULL, 0); assert(sent == 2);
  connection_handler(false); assert(vibration == 1);
  clock_now += 3600; tick_handler(NULL, 0); assert(sent == 2 && s_weather_pending);
  connection_handler(true); assert(sent == 3 && !s_weather_pending);
  connection_handler(true); assert(sent == 3);
  transport_result = 1;
  request_weather(); assert(sent == 3 && s_weather_pending);
  transport_result = 0;
  tick_handler(NULL, 0); assert(sent == 4 && !s_weather_pending);
  weather_timed_out(NULL); assert(s_weather_timeout==NULL && last_code==-1);

  uint32_t previous=displayed_contents();
  s_frame_contents[0]=s_frame_contents[1]=s_frame_contents[2]=FRAME_NONE;
  refresh_card_services(previous);
  assert(unsubscriptions==1 && !s_health_subscribed && !s_weather_pending);
  int old_steps=step_reads, old_heart=heart_reads, old_sent=sent;
  clock_now+=3600; tick_handler(NULL,0);
  health_handler(HealthEventSignificantUpdate,NULL);
  connection_handler(false); connection_handler(true);
  assert(step_reads==old_steps && heart_reads==old_heart && sent==old_sent);
  for (int content=FRAME_STEPS; content<FRAME_CONTENT_COUNT; ++content) {
    previous=displayed_contents();
    s_frame_contents[0]=s_frame_contents[1]=s_frame_contents[2]=content;
    old_steps=step_reads; old_heart=heart_reads; old_sent=sent;
    refresh_card_services(previous);
    assert(step_reads-old_steps==(content==FRAME_STEPS));
    assert(heart_reads-old_heart==(content==FRAME_HEART_RATE));
    assert(sent-old_sent==(content==FRAME_TEMPERATURE || content==FRAME_UV_INDEX));
    if (content==FRAME_TEMPERATURE) assert(last_fields==1 && s_weather_timeout);
    if (content==FRAME_UV_INDEX) assert(last_fields==2 && !s_weather_timeout && timers_cancelled==1);
    old_steps=step_reads; old_heart=heart_reads;
    tick_handler(NULL,0);
    assert(step_reads-old_steps==(content==FRAME_STEPS));
    assert(heart_reads-old_heart==(content==FRAME_HEART_RATE));
  }
  previous=displayed_contents(); s_frame_contents[0]=FRAME_TEMPERATURE;
  refresh_card_services(previous); assert(last_fields==3);
  old_sent=sent; previous=displayed_contents();
  s_frame_contents[1]=FRAME_NONE; // UV still displayed in slot 2
  refresh_card_services(previous); assert(sent==old_sent);
  assert(subscriptions==2 && unsubscriptions==2);
  return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    frames = source[source.index('enum { FRAME_NONE'):source.index('static void load_frame_settings')]
    (path / 'test.c').write_text(stub + frames + 'static bool s_health_subscribed;\n' + '\n'.join(function(n) for n in
        ['weather_timed_out', 'request_weather', 'update_steps', 'update_heart_rate', 'health_handler', 'refresh_card_services', 'tick_handler', 'connection_handler']) + main)
    subprocess.run(['cc', '-o', str(path / 'test'), str(path / 'test.c')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('Watch startup, hourly, reconnect, offline, and transport checks passed')
