"""Compile production icon selection/lifecycle against a controlled graphics API."""
from pathlib import Path
import json
import subprocess
import tempfile
source = Path('src/c/cyberpunk.c').read_text()
def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start)+2]
names = ['WEATHER','WEATHER_SUNNY','WEATHER_CLOUDY','WEATHER_CLOUDY_DAY',
         'WEATHER_LIGHT_RAIN','WEATHER_HEAVY_RAIN','WEATHER_RAIN_AND_SNOW',
         'WEATHER_LIGHT_SNOW','WEATHER_HEAVY_SNOW']
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef int GDrawCommandImage;
typedef struct {int w,h;} GSize;
#define GSize(w,h) ((GSize){w,h})
static GDrawCommandImage *s_weather_icon;
static uint32_t s_weather_resource;
static void *s_canvas=(void *)1;
static int loaded, destroyed, live, redraws, fail_resource;
static GDrawCommandImage image;
static void gdraw_command_image_destroy(GDrawCommandImage *p) {assert(live==1); --live; ++destroyed;}
static GDrawCommandImage *gdraw_command_image_create_with_resource(int resource) {
  ++loaded; if (resource==fail_resource) return NULL;
  assert(live==0); ++live; return &image;
}
static GSize gdraw_command_image_get_bounds_size(GDrawCommandImage *p) {return GSize(50,50);}
static void *gdraw_command_image_get_command_list(GDrawCommandImage *p) {return NULL;}
static int scale_icon;
static void gdraw_command_list_iterate(void *list, int cb, int *scale) {assert(scale[0]==50 && scale[1]==28);}
static void gdraw_command_image_set_bounds_size(GDrawCommandImage *p, GSize size) {assert(size.w==28 && size.h==28);}
static void layer_mark_dirty(void *p) {++redraws;}
'''
stub += '\n#define FRAME_TEMPERATURE 3\nstatic bool visible=true;\nstatic bool frame_displayed(unsigned c) {return visible;}\n'
stub += '\n'.join('#define RESOURCE_ID_'+name+' '+str(i+1) for i,name in enumerate(names))
groups = [[0,1],[2],[3,45,48],[51,53,55,61,63,80,81],[65,82,95,96,97,99],
          [56,57,66,67],[71,73,77,85],[75,86]]
main = '\nint main(void) {\n'
for name,codes in zip(names[1:],groups):
    for code in codes:
        main += f'assert(weather_resource({code})==RESOURCE_ID_{name});\n'
known = {code for group in groups for code in group}
for code in range(-1,101):
    if code not in known: main += f'assert(weather_resource({code})==RESOURCE_ID_WEATHER);\n'
main += '''
visible=false;
set_weather_icon(0); assert(redraws==0);
gdraw_command_image_destroy(s_weather_icon); s_weather_icon=NULL; loaded=destroyed=0;
visible=true;
set_weather_icon(-1); assert(loaded==1 && live==1);
set_weather_icon(-1); assert(loaded==1);
set_weather_icon(0); assert(loaded==2 && destroyed==1);
set_weather_icon(1); assert(loaded==2);
set_weather_icon(82); assert(loaded==3 && destroyed==2);
fail_resource=RESOURCE_ID_WEATHER_LIGHT_SNOW;
set_weather_icon(71); assert(s_weather_resource==RESOURCE_ID_WEATHER && live==1);
set_weather_icon(0); set_weather_icon(-1); assert(s_weather_resource==RESOURCE_ID_WEATHER);
gdraw_command_image_destroy(s_weather_icon); assert(live==0);
return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'test.c').write_text(stub+'\n'+function('static uint32_t weather_resource(')+'\n'+
                             function('static void set_weather_icon(int32_t code) {')+main)
    subprocess.run(['cc','-o',str(path/'test'),str(path/'test.c')],check=True)
    subprocess.run([str(path/'test')],check=True)
print('WMO mapping, unknown codes, resource reuse, fallback, and cleanup passed')
