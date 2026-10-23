#include <pebble.h>
#include "message_keys.auto.h"

static Window *s_window;
static Layer *s_canvas;
static GFont s_time_font, s_date_font, s_battery_font;
static char s_hour[3], s_minute[3], s_day[3];
static const char *s_weekday, *s_month;
static uint8_t s_battery;
static bool s_charging;
static GDrawCommandImage *s_charging_icon;
static GDrawCommandImage *s_shoe;
static GDrawCommandImage *s_heart;
static GDrawCommandImage *s_bluetooth_disconnected;
static bool s_connected;
static GDrawCommandImage *s_weather_icon;
static char s_temperature[16] = "--°C";
static char s_uv_index[12] = "--";
static bool s_js_ready;
static bool s_weather_pending = true;
static time_t s_weather_attempt;
enum { WEATHER_PERSIST_KEY = 1, UV_PERSIST_KEY = 2, WEATHER_INTERVAL = 60 * 60 };

static void load_uv_index(void) {
  if (persist_exists(UV_PERSIST_KEY)) {
    int32_t value = persist_read_int(UV_PERSIST_KEY);
    if (value >= 0 && value <= 100)
      snprintf(s_uv_index, sizeof(s_uv_index), "%ld", (long)value);
  }
}

enum { FRAME_NONE, FRAME_STEPS, FRAME_HEART_RATE, FRAME_TEMPERATURE, FRAME_UV_INDEX,
       FRAME_CONTENT_COUNT, FRAME_SLOT_COUNT = 3, FRAME_PERSIST_BASE = 10 };
static uint8_t s_frame_contents[FRAME_SLOT_COUNT] = {
    FRAME_STEPS, FRAME_HEART_RATE, FRAME_TEMPERATURE};

static void load_frame_settings(void) {
  for (unsigned i = 0; i < FRAME_SLOT_COUNT; ++i) {
    if (persist_exists(FRAME_PERSIST_BASE + i)) {
      int32_t value = persist_read_int(FRAME_PERSIST_BASE + i);
      if (value >= FRAME_NONE && value < FRAME_CONTENT_COUNT)
        s_frame_contents[i] = value;
    }
  }
}

static void receive_frame_settings(DictionaryIterator *iter) {
  const uint32_t frame_keys[FRAME_SLOT_COUNT] = {
    MESSAGE_KEY_FRAME_LEFT, MESSAGE_KEY_FRAME_MIDDLE, MESSAGE_KEY_FRAME_RIGHT};
  bool changed = false;
  for (unsigned i = 0; i < FRAME_SLOT_COUNT; ++i) {
    Tuple *tuple = dict_find(iter, frame_keys[i]);
    if (!tuple || (tuple->type != TUPLE_INT && tuple->type != TUPLE_UINT) ||
        tuple->length != 4)
      continue;
    int32_t value = tuple->value->int32;
    if (value >= FRAME_NONE && value < FRAME_CONTENT_COUNT &&
        value != s_frame_contents[i]) {
      s_frame_contents[i] = value;
      persist_write_int(FRAME_PERSIST_BASE + i, value);
      changed = true;
    }
  }
  if (changed && s_canvas)
    layer_mark_dirty(s_canvas);
}

static void request_weather(void) {
  s_weather_pending = true;
  if (!s_connected || !s_js_ready)
    return;
  DictionaryIterator *iter;
  AppMessageResult result = app_message_outbox_begin(&iter);
  if (result == APP_MSG_OK) {
    dict_write_uint8(iter, MESSAGE_KEY_REQUEST_WEATHER, 1);
    result = app_message_outbox_send();
  }
  if (result == APP_MSG_OK) {
    s_weather_pending = false;
    s_weather_attempt = time(NULL);
    APP_LOG(APP_LOG_LEVEL_DEBUG, "Weather refresh requested");
  } else {
    APP_LOG(APP_LOG_LEVEL_WARNING, "Weather request failed: %d", result);
  }
}

static void weather_received(DictionaryIterator *iter, void *context) {
  receive_frame_settings(iter);
  Tuple *temperature = dict_find(iter, MESSAGE_KEY_TEMPERATURE);
  if (temperature && (temperature->type == TUPLE_INT || temperature->type == TUPLE_UINT) &&
      temperature->length == 4) {
    int32_t value = temperature->value->int32;
    if (value >= -150 && value <= 150) {
      snprintf(s_temperature, sizeof(s_temperature), "%ld°C", (long)value);
      persist_write_int(WEATHER_PERSIST_KEY, value);
      if (s_canvas)
        layer_mark_dirty(s_canvas);
    }
  }
  Tuple *uv = dict_find(iter, MESSAGE_KEY_UV_INDEX);
  if (uv && (uv->type == TUPLE_INT || uv->type == TUPLE_UINT) && uv->length == 4) {
    int32_t value = uv->value->int32;
    if (value >= 0 && value <= 100) {
      snprintf(s_uv_index, sizeof(s_uv_index), "%ld", (long)value);
      persist_write_int(UV_PERSIST_KEY, value);
      if (s_canvas)
        layer_mark_dirty(s_canvas);
    }
  }
  if (dict_find(iter, MESSAGE_KEY_JS_READY)) {
    bool was_ready = s_js_ready;
    s_js_ready = true;
    if (!was_ready || s_weather_pending)
      request_weather();
  }
}

static void weather_outbox_failed(DictionaryIterator *iter,
                                  AppMessageResult reason, void *context) {
  APP_LOG(APP_LOG_LEVEL_WARNING, "Weather message failed: %d", reason);
  s_weather_pending = true;
}
static GFont s_steps_small_font, s_steps_tiny_font;
static char s_steps[12] = "--";
static char s_heart_rate[12] = "--";
enum { SHOE_SIZE = 28, HEART_SIZE = 28, BLUETOOTH_SIZE = 20,
       CHARGING_HEIGHT = 20 };

static bool scale_icon(GDrawCommand *command, uint32_t index, void *context) {
  if (gdraw_command_get_stroke_color(command).a != 0) {
    gdraw_command_set_stroke_color(command, GColorCyan);
  }
  const int source_size = ((int *)context)[0];
  const int target_size = ((int *)context)[1];
  for (uint16_t i = 0; i < gdraw_command_get_num_points(command); ++i) {
    GPoint point = gdraw_command_get_point(command, i);
    point.x = (point.x * target_size + source_size / 2) / source_size;
    point.y = (point.y * target_size + source_size / 2) / source_size;
    gdraw_command_set_point(command, i, point);
  }
  const uint8_t stroke = gdraw_command_get_stroke_width(command);
  if (stroke) {
    int scaled = (stroke * target_size + source_size / 2) / source_size;
    gdraw_command_set_stroke_width(command, scaled > 0 ? scaled : 1);
  }
  return true;
}

static void update_steps(void) {
  time_t now = time(NULL);
  HealthServiceAccessibilityMask access = health_service_metric_accessible(
      HealthMetricStepCount, time_start_of_today(), now);
  if (access & HealthServiceAccessibilityMaskAvailable) {
    HealthValue steps = health_service_sum_today(HealthMetricStepCount);
    if (steps >= 1000) {
      snprintf(s_steps, sizeof(s_steps), "%ld.%ldk", (long)(steps / 1000),
               (long)((steps % 1000) / 100));
    } else {
      snprintf(s_steps, sizeof(s_steps), "%ld", (long)(steps < 0 ? 0 : steps));
    }
  } else {
    snprintf(s_steps, sizeof(s_steps), "--");
  }
  if (s_canvas)
    layer_mark_dirty(s_canvas);
}

static void update_heart_rate(void) {
  time_t now = time(NULL);
  HealthServiceAccessibilityMask access = health_service_metric_accessible(
      HealthMetricHeartRateBPM, now, now);
  HealthValue heart_rate = 0;
  if (access & HealthServiceAccessibilityMaskAvailable)
    heart_rate = health_service_peek_current_value(HealthMetricHeartRateBPM);
  if (heart_rate > 0)
    snprintf(s_heart_rate, sizeof(s_heart_rate), "%ld", (long)heart_rate);
  else
    snprintf(s_heart_rate, sizeof(s_heart_rate), "--");
  if (s_canvas)
    layer_mark_dirty(s_canvas);
}

static void health_handler(HealthEventType event, void *context) {
  if (event == HealthEventMovementUpdate || event == HealthEventSignificantUpdate)
    update_steps();
  if (event == HealthEventHeartRateUpdate || event == HealthEventSignificantUpdate)
    update_heart_rate();
}

static GColor cyan(void) { return GColorFromHEX(0x00ffff); }
static GColor red(void) { return GColorFromHEX(0xff0000); }

static int text_width(const char *text, GFont font) {
  return graphics_text_layout_get_content_size(
             text, font, GRect(0, 0, 200, 100), GTextOverflowModeWordWrap,
             GTextAlignmentLeft)
      .w;
}

static void draw_text(GContext *ctx, const char *text, GFont font, GColor color,
                      int x, int y, int width, int height) {
  graphics_context_set_text_color(ctx, color);
  graphics_draw_text(ctx, text, font, GRect(x, y, width, height),
                     GTextOverflowModeWordWrap, GTextAlignmentLeft, NULL);
}

// Renderers receive canvas coordinates and must keep content within the frame,
// allowing clearance for its clipped bottom-right corner.
typedef void (*FrameContentRenderer)(GContext *ctx, GRect bounds, void *context);
typedef struct {
  FrameContentRenderer render;
  void *context;
} FrameSlot;

static GRect cyan_frame_bounds(unsigned index) {
  return GRect(18 + index * 57, 125, 50, 60);
}

static void draw_cyan_frame(GContext *ctx, GRect bounds) {
  const int left = bounds.origin.x, top = bounds.origin.y;
  const int right = left + bounds.size.w - 1;
  const int bottom = top + bounds.size.h - 1;
  const int clip = 6;
  graphics_context_set_stroke_color(ctx, cyan());
  graphics_context_set_stroke_width(ctx, 1);
  graphics_draw_line(ctx, GPoint(left, top), GPoint(right, top));
  graphics_draw_line(ctx, GPoint(right, top), GPoint(right, bottom - clip));
  graphics_draw_line(ctx, GPoint(right, bottom - clip),
                     GPoint(right - clip, bottom));
  graphics_draw_line(ctx, GPoint(right - clip, bottom), GPoint(left, bottom));
  graphics_draw_line(ctx, GPoint(left, bottom), GPoint(left, top));
}

static void draw_frame_value(GContext *ctx, GRect bounds,
                             GDrawCommandImage *icon, const char *value,
                             bool shrink_to_fit) {
  if (icon)
    gdraw_command_image_draw(ctx, icon,
                            GPoint(bounds.origin.x + 11, bounds.origin.y + 6));
  const int width = bounds.size.w - 4;
  GFont font = s_battery_font;
  int y = bounds.origin.y + 31;
  if (shrink_to_fit && text_width(value, font) > width) {
    font = s_steps_small_font;
    y = bounds.origin.y + 35;
  }
  if (shrink_to_fit && text_width(value, font) > width) {
    font = s_steps_tiny_font;
    y = bounds.origin.y + 41;
  }
  graphics_context_set_text_color(ctx, cyan());
  graphics_draw_text(ctx, value, font,
                     GRect(bounds.origin.x + 2, y, width, 27),
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);
}

static void draw_steps_content(GContext *ctx, GRect bounds, void *context) {
  (void)context;
  draw_frame_value(ctx, bounds, s_shoe, s_steps, true);
}

static void draw_heart_rate_content(GContext *ctx, GRect bounds, void *context) {
  (void)context;
  draw_frame_value(ctx, bounds, s_heart, s_heart_rate, false);
}

static void draw_weather_content(GContext *ctx, GRect bounds, void *context) {
  (void)context;
  draw_frame_value(ctx, bounds, s_weather_icon, s_temperature, true);
}

static void draw_uv_content(GContext *ctx, GRect bounds, void *context) {
  (void)context;
  graphics_context_set_text_color(ctx, cyan());
  graphics_draw_text(ctx, "UV", s_date_font,
                     GRect(bounds.origin.x + 2, bounds.origin.y + 1,
                           bounds.size.w - 4, 30),
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentCenter, NULL);
  draw_frame_value(ctx, bounds, NULL, s_uv_index, true);
}

// Indexed by the persisted frame content IDs. None skips border and content.
static const FrameSlot s_frame_renderers[FRAME_CONTENT_COUNT] = {
    {NULL, NULL},
    {draw_steps_content, NULL},
    {draw_heart_rate_content, NULL},
    {draw_weather_content, NULL},
    {draw_uv_content, NULL},
};

static void draw_face(Layer *layer, GContext *ctx) {
  const GRect bounds = layer_get_bounds(layer);
  const int w = bounds.size.w, h = bounds.size.h;
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_fill_rect(ctx, bounds, 0, GCornerNone);

  const GRect time_frame = GRect(8, 8, w - 16, 75);
  const int frame_left = time_frame.origin.x;
  const int frame_top = time_frame.origin.y;
  const int frame_right = frame_left + time_frame.size.w - 1;
  const int frame_bottom = frame_top + time_frame.size.h - 1;
  // A closed time frame with a clipped bottom-right corner.
  graphics_context_set_stroke_color(ctx, red());
  graphics_context_set_stroke_width(ctx, 2);
  graphics_draw_line(ctx, GPoint(frame_left, frame_top),
                     GPoint(frame_right, frame_top));
  graphics_draw_line(ctx, GPoint(frame_right, frame_top),
                     GPoint(frame_right, frame_bottom - 10));
  graphics_draw_line(ctx, GPoint(frame_right, frame_bottom - 10),
                     GPoint(frame_right - 10, frame_bottom));
  graphics_draw_line(ctx, GPoint(frame_right - 10, frame_bottom),
                     GPoint(frame_left, frame_bottom));
  graphics_draw_line(ctx, GPoint(frame_left, frame_bottom),
                     GPoint(frame_left, frame_top));

  const int hour_width = text_width(s_hour, s_time_font);
  const int colon_width = text_width(":", s_time_font);
  const int minute_width = text_width(s_minute, s_time_font);
  // Ink margins of digits 0-9 in BLENDER_BOOK_68, excluding advance padding.
  // Recheck these metrics if the time font or its resource size changes.
  static const uint8_t left_bearing[] = {3, 4, 3, 3, 2, 3, 3, 2, 3, 3};
  static const uint8_t right_padding[] = {6, 7, 6, 6, 4, 6, 6, 6, 6, 6};
  const int ink_left = left_bearing[s_hour[0] - '0'];
  const int ink_right = right_padding[s_minute[1] - '0'];
  // Include the extra pixel used for the synthetic bold hours.
  const int ink_width =
      hour_width + colon_width + minute_width + 1 - ink_left - ink_right;
  const int time_x =
      time_frame.origin.x + (time_frame.size.w - ink_width) / 2 - ink_left;
  // All digits have visible rows 27-67 relative to the text origin.
  const int time_y = time_frame.origin.y + (time_frame.size.h - 41) / 2 - 27;
  draw_text(ctx, s_hour, s_time_font, cyan(), time_x, time_y, hour_width + 2,
            70);
  // Synthetic bold preserves the supplied Book letterforms.
  draw_text(ctx, s_hour, s_time_font, cyan(), time_x + 1, time_y,
            hour_width + 2, 70);
  draw_text(ctx, ":", s_time_font, GColorWhite, time_x + hour_width + 1, time_y,
            colon_width + 1, 70);
  draw_text(ctx, s_minute, s_time_font, GColorWhite,
            time_x + hour_width + colon_width + 1, time_y, minute_width + 2,
            70);

  const int weekday_width = text_width(s_weekday, s_date_font);
  const int month_width = text_width(s_month, s_date_font);
  const int day_width = text_width(s_day, s_date_font);
  const bool show_charging = s_charging && s_charging_icon;
  const bool show_disconnected = !s_connected && s_bluetooth_disconnected;
  const int charging_width = show_charging
      ? gdraw_command_image_get_bounds_size(s_charging_icon).w : 0;
  const int date_left = show_charging ? 8 + charging_width + 6 : 0;
  const int bluetooth_x = w - 28;
  const int date_right = show_disconnected ? bluetooth_x - 6 : w;
  int gap = 8;
  const int text_total = weekday_width + month_width + day_width;
  if (text_total + 2 * gap + 2 > date_right - date_left)
    gap = (date_right - date_left - text_total - 2) / 2;
  if (gap < 0)
    gap = 0;
  const int date_y = 82;
  const int date_width = weekday_width + month_width + day_width + 2 * gap;
  int x = (w - date_width) / 2;
  if (x + date_width + 2 > date_right)
    x = date_right - date_width - 2;
  if (x < date_left)
    x = date_left;
  if (show_charging)
    gdraw_command_image_draw(ctx, s_charging_icon, GPoint(8, 88));
  draw_text(ctx, s_weekday, s_date_font, GColorWhite, x, date_y,
            weekday_width + 2, 30);
  x += weekday_width + gap;
  draw_text(ctx, s_month, s_date_font, cyan(), x, date_y, month_width + 2, 30);
  x += month_width + gap;
  draw_text(ctx, s_day, s_date_font, GColorWhite, x, date_y, day_width + 2, 30);
  if (!s_connected && s_bluetooth_disconnected)
    gdraw_command_image_draw(ctx, s_bluetooth_disconnected,
                            GPoint(bluetooth_x, 88));

  char percentage[5];
  snprintf(percentage, sizeof(percentage), "%u%%", (unsigned)s_battery);
  const int percentage_width = text_width(percentage, s_battery_font);
  const int percentage_x = w - 8 - percentage_width;

  // Clip the top-left corner and leave the percentage's corner open.
  graphics_context_set_stroke_color(ctx, red());
  graphics_context_set_stroke_width(ctx, 2);
  graphics_draw_line(ctx, GPoint(18, 114), GPoint(w - 9, 114));
  graphics_draw_line(ctx, GPoint(w - 9, 114), GPoint(w - 9, h - 50));
  graphics_draw_line(ctx, GPoint(8, 124), GPoint(18, 114));
  graphics_draw_line(ctx, GPoint(8, 124), GPoint(8, h - 33));
  graphics_draw_line(ctx, GPoint(8, h - 33), GPoint(percentage_x - 6, h - 33));

  for (unsigned i = 0; i < FRAME_SLOT_COUNT; ++i) {
    const FrameSlot *slot = &s_frame_renderers[s_frame_contents[i]];
    if (!slot->render)
      continue;
    draw_cyan_frame(ctx, cyan_frame_bounds(i));
    slot->render(ctx, cyan_frame_bounds(i), slot->context);
  }

  graphics_context_set_stroke_width(ctx, 1);
  graphics_context_set_stroke_color(ctx, red());
  // The outline remains visible even when the battery is empty.
  const GRect bar = GRect(8, h - 18, w - 16, 10);
  const int interior_width = bar.size.w - 2;
  const int fill_width = interior_width * s_battery / 100;
  graphics_context_set_fill_color(ctx, red());
  if (fill_width > 0) {
    graphics_fill_rect(
        ctx,
        GRect(bar.origin.x + 1, bar.origin.y + 1, fill_width, bar.size.h - 2),
        0, GCornerNone);
  }
  graphics_context_set_stroke_color(ctx, red());
  graphics_context_set_stroke_width(ctx, 1);
  graphics_draw_rect(ctx, bar);
  draw_text(ctx, percentage, s_battery_font, GColorWhite, percentage_x, h - 46,
            percentage_width + 1, 26);
}

static void update_time(struct tm *now) {
  static const char *weekdays[] = {"SUN", "MON", "TUE", "WED",
                                   "THU", "FRI", "SAT"};
  static const char *months[] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                 "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
  strftime(s_hour, sizeof(s_hour), "%I", now);
  strftime(s_minute, sizeof(s_minute), "%M", now);
  strftime(s_day, sizeof(s_day), "%d", now);
  s_weekday = weekdays[now->tm_wday];
  s_month = months[now->tm_mon];
  if (s_canvas)
    layer_mark_dirty(s_canvas);
}

static void tick_handler(struct tm *now, TimeUnits changed) {
  update_time(now);
  if (s_weather_pending || time(NULL) - s_weather_attempt >= WEATHER_INTERVAL)
    request_weather();
  update_steps();
  update_heart_rate();
}

static void battery_handler(BatteryChargeState state) {
  s_battery = state.charge_percent > 100 ? 100 : state.charge_percent;
  s_charging = state.is_charging;
  if (s_canvas)
    layer_mark_dirty(s_canvas);
}

static void connection_handler(bool connected) {
  if (s_connected && !connected)
    vibes_short_pulse();
  bool reconnected = !s_connected && connected;
  s_connected = connected;
  if (reconnected)
    request_weather();
  if (s_canvas)
    layer_mark_dirty(s_canvas);
}

static void window_load(Window *window) {
  s_time_font =
      fonts_load_custom_font(resource_get_handle(RESOURCE_ID_BLENDER_BOOK_68));
  s_date_font =
      fonts_load_custom_font(resource_get_handle(RESOURCE_ID_BLENDER_HEAVY_24));
  s_battery_font =
      fonts_load_custom_font(resource_get_handle(RESOURCE_ID_BLENDER_BOOK_22));
  s_steps_small_font =
      fonts_load_custom_font(resource_get_handle(RESOURCE_ID_BLENDER_BOOK_18));
  s_steps_tiny_font =
      fonts_load_custom_font(resource_get_handle(RESOURCE_ID_BLENDER_BOOK_12));
  s_shoe = gdraw_command_image_create_with_resource(RESOURCE_ID_SHOE);
  s_charging_icon = gdraw_command_image_create_with_resource(RESOURCE_ID_CHARGING);
  if (s_charging_icon) {
    GSize size = gdraw_command_image_get_bounds_size(s_charging_icon);
    if (size.h > 0) {
      int scale[] = {size.h, CHARGING_HEIGHT};
      gdraw_command_list_iterate(
          gdraw_command_image_get_command_list(s_charging_icon), scale_icon, scale);
      gdraw_command_image_set_bounds_size(s_charging_icon,
          GSize((size.w * CHARGING_HEIGHT + size.h / 2) / size.h,
                CHARGING_HEIGHT));
    }
  }
  if (s_shoe) {
    GSize size = gdraw_command_image_get_bounds_size(s_shoe);
    int source_size = size.w > size.h ? size.w : size.h;
    if (source_size > 0) {
      int scale[] = {source_size, SHOE_SIZE};
      gdraw_command_list_iterate(gdraw_command_image_get_command_list(s_shoe),
                                scale_icon, scale);
      gdraw_command_image_set_bounds_size(s_shoe, GSize(SHOE_SIZE, SHOE_SIZE));
    }
  }
  s_weather_icon = gdraw_command_image_create_with_resource(RESOURCE_ID_WEATHER);
  if (s_weather_icon) {
    GSize size = gdraw_command_image_get_bounds_size(s_weather_icon);
    int source_size = size.w > size.h ? size.w : size.h;
    if (source_size > 0) {
      int scale[] = {source_size, 28};
      gdraw_command_list_iterate(gdraw_command_image_get_command_list(s_weather_icon),
                                scale_icon, scale);
      gdraw_command_image_set_bounds_size(s_weather_icon, GSize(28, 28));
    }
  }
  s_heart = gdraw_command_image_create_with_resource(RESOURCE_ID_HEART);
  if (s_heart) {
    GSize size = gdraw_command_image_get_bounds_size(s_heart);
    int source_size = size.w > size.h ? size.w : size.h;
    if (source_size > 0) {
      int scale[] = {source_size, HEART_SIZE};
      gdraw_command_list_iterate(gdraw_command_image_get_command_list(s_heart),
                                scale_icon, scale);
      gdraw_command_image_set_bounds_size(s_heart, GSize(HEART_SIZE, HEART_SIZE));
    }
  }
  s_bluetooth_disconnected = gdraw_command_image_create_with_resource(
      RESOURCE_ID_BLUETOOTH_DISCONNECTED);
  if (s_bluetooth_disconnected) {
    GSize size = gdraw_command_image_get_bounds_size(s_bluetooth_disconnected);
    int source_size = size.w > size.h ? size.w : size.h;
    if (source_size > 0) {
      int scale[] = {source_size, BLUETOOTH_SIZE};
      gdraw_command_list_iterate(
          gdraw_command_image_get_command_list(s_bluetooth_disconnected),
          scale_icon, scale);
      gdraw_command_image_set_bounds_size(
          s_bluetooth_disconnected, GSize(BLUETOOTH_SIZE, BLUETOOTH_SIZE));
    }
  }
  Layer *root = window_get_root_layer(window);
  s_canvas = layer_create(layer_get_bounds(root));
  if (!s_canvas) {
    APP_LOG(APP_LOG_LEVEL_ERROR, "Unable to allocate watchface canvas");
    return;
  }
  layer_set_update_proc(s_canvas, draw_face);
  layer_add_child(root, s_canvas);
  time_t now = time(NULL);
  update_time(localtime(&now));
  battery_handler(battery_state_service_peek());
  update_steps();
  update_heart_rate();
}

static void window_unload(Window *window) {
  if (s_weather_icon) {
    gdraw_command_image_destroy(s_weather_icon);
    s_weather_icon = NULL;
  }
  if (s_charging_icon) {
    gdraw_command_image_destroy(s_charging_icon);
    s_charging_icon = NULL;
  }
  if (s_heart) {
    gdraw_command_image_destroy(s_heart);
    s_heart = NULL;
  }
  if (s_bluetooth_disconnected) {
    gdraw_command_image_destroy(s_bluetooth_disconnected);
    s_bluetooth_disconnected = NULL;
  }
  if (s_shoe) {
    gdraw_command_image_destroy(s_shoe);
    s_shoe = NULL;
  }
  if (s_steps_small_font)
    fonts_unload_custom_font(s_steps_small_font);
  if (s_steps_tiny_font)
    fonts_unload_custom_font(s_steps_tiny_font);
  if (s_canvas) {
    layer_destroy(s_canvas);
    s_canvas = NULL;
  }
  if (s_time_font)
    fonts_unload_custom_font(s_time_font);
  if (s_date_font)
    fonts_unload_custom_font(s_date_font);
  if (s_battery_font)
    fonts_unload_custom_font(s_battery_font);
}

int main(void) {
  load_frame_settings();
  if (persist_exists(WEATHER_PERSIST_KEY)) {
    int32_t value = persist_read_int(WEATHER_PERSIST_KEY);
    if (value >= -150 && value <= 150)
      snprintf(s_temperature, sizeof(s_temperature), "%ld°C", (long)value);
  }
  load_uv_index();
  app_message_register_inbox_received(weather_received);
  app_message_register_outbox_failed(weather_outbox_failed);
  app_message_open(128, 128);
  s_connected = connection_service_peek_pebble_app_connection();
  s_window = window_create();
  if (!s_window)
    return 1;
  window_set_background_color(s_window, GColorBlack);
  window_set_window_handlers(
      s_window, (WindowHandlers){.load = window_load, .unload = window_unload});
  window_stack_push(s_window, false);
  tick_timer_service_subscribe(MINUTE_UNIT, tick_handler);
  battery_state_service_subscribe(battery_handler);
  health_service_events_subscribe(health_handler, NULL);
  connection_service_subscribe((ConnectionHandlers){
      .pebble_app_connection_handler = connection_handler});
  app_event_loop();
  connection_service_unsubscribe();
  health_service_events_unsubscribe();
  tick_timer_service_unsubscribe();
  battery_state_service_unsubscribe();
  app_message_deregister_callbacks();
  window_destroy(s_window);
  return 0;
}
