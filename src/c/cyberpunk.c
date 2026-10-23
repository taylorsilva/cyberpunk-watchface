#include <pebble.h>

static Window *s_window;
static Layer *s_canvas;
static GFont s_time_font, s_date_font, s_battery_font;
static char s_hour[3], s_minute[3], s_day[3];
static const char *s_weekday, *s_month;
static uint8_t s_battery;

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
  graphics_draw_line(ctx, GPoint(frame_left, frame_top), GPoint(frame_right, frame_top));
  graphics_draw_line(ctx, GPoint(frame_right, frame_top), GPoint(frame_right, frame_bottom - 10));
  graphics_draw_line(ctx, GPoint(frame_right, frame_bottom - 10), GPoint(frame_right - 10, frame_bottom));
  graphics_draw_line(ctx, GPoint(frame_right - 10, frame_bottom), GPoint(frame_left, frame_bottom));
  graphics_draw_line(ctx, GPoint(frame_left, frame_bottom), GPoint(frame_left, frame_top));

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
  const int ink_width = hour_width + colon_width + minute_width + 1 -
                        ink_left - ink_right;
  const int time_x = time_frame.origin.x +
                     (time_frame.size.w - ink_width) / 2 - ink_left;
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
  const int gap = 8;
  const int date_y = 88;
  int x = (w - weekday_width - month_width - day_width - 2 * gap) / 2;
  draw_text(ctx, s_weekday, s_date_font, GColorWhite, x, date_y,
            weekday_width + 2, 30);
  x += weekday_width + gap;
  draw_text(ctx, s_month, s_date_font, cyan(), x, date_y, month_width + 2, 30);
  x += month_width + gap;
  draw_text(ctx, s_day, s_date_font, GColorWhite, x, date_y, day_width + 2, 30);

  char percentage[5];
  snprintf(percentage, sizeof(percentage), "%u%%", (unsigned)s_battery);
  const int percentage_width = text_width(percentage, s_battery_font);
  const int percentage_x = w - 8 - percentage_width;

  // Clip the top-left corner and leave the percentage's corner open.
  graphics_context_set_stroke_color(ctx, red());
  graphics_context_set_stroke_width(ctx, 2);
  graphics_draw_line(ctx, GPoint(18, 126), GPoint(w - 9, 126));
  graphics_draw_line(ctx, GPoint(w - 9, 126), GPoint(w - 9, h - 50));
  graphics_draw_line(ctx, GPoint(8, 136), GPoint(18, 126));
  graphics_draw_line(ctx, GPoint(8, 136), GPoint(8, h - 33));
  graphics_draw_line(ctx, GPoint(8, h - 33), GPoint(percentage_x - 6, h - 33));

  graphics_context_set_stroke_width(ctx, 1);
  graphics_context_set_stroke_color(ctx, red());
  for (int i = 0; i < 3; ++i) {
    graphics_draw_line(ctx, GPoint(w - 26 + i * 5, 137),
                       GPoint(w - 30 + i * 5, 144));
  }
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
}

static void battery_handler(BatteryChargeState state) {
  s_battery = state.charge_percent > 100 ? 100 : state.charge_percent;
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
}

static void window_unload(Window *window) {
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
  s_window = window_create();
  if (!s_window)
    return 1;
  window_set_background_color(s_window, GColorBlack);
  window_set_window_handlers(
      s_window, (WindowHandlers){.load = window_load, .unload = window_unload});
  window_stack_push(s_window, false);
  tick_timer_service_subscribe(MINUTE_UNIT, tick_handler);
  battery_state_service_subscribe(battery_handler);
  app_event_loop();
  tick_timer_service_unsubscribe();
  battery_state_service_unsubscribe();
  window_destroy(s_window);
  return 0;
}
