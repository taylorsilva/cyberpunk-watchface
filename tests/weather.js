const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('src/pkjs/index.js', 'utf8');
function harness() {
  const events = {}, locations = [], requests = [], messages = [], timers = [];
  const context = {
    require(name) {
      if (name === './config.json') return JSON.parse(fs.readFileSync('src/pkjs/config.json'));
      if (name === 'pebble-clay') return function() {};
      throw new Error(name);
    },
    console: {log() {}},
    setTimeout(fn) { timers.push(fn); },
    navigator: {geolocation: {getCurrentPosition(ok, fail, options) {
      locations.push({ok, fail, options});
    }}},
    XMLHttpRequest: function() {
      requests.push(this);
      this.open = (method, url) => { this.url = url; };
      this.send = () => {};
    },
    Pebble: {
      addEventListener(name, handler) { events[name] = handler; },
      sendAppMessage(payload, ok, fail) { messages.push({payload, ok, fail}); }
    }
  };
  vm.runInNewContext(source, context);
  return {events, locations, requests, messages, timers,
    refresh(fields = 3) { events.appmessage({payload: {REQUEST_WEATHER: fields}}); },
    locate() { locations.at(-1).ok({coords: {latitude: 45, longitude: -63}}); },
    respond(value, uvValue = 6.3, times, code = 2) {
      const hour = Math.floor(Date.now()/3600000)*3600;
      const temp = requests.at(-2), uv = requests.at(-1);
      temp.status = uv.status = 200;
      temp.responseText = JSON.stringify({current: {temperature_2m: value, weather_code: code}});
      temp.onload();
      uv.responseText = JSON.stringify({hourly: {time: times || [hour-3600, hour, hour+3600],
        uv_index: [99, uvValue, 98]}});
      if (times) uv.responseText = JSON.stringify({hourly: {time: times, uv_index: [uvValue]}});
      uv.onload();
    }};
}
function settle(h) { h.messages.forEach(m => m.ok()); }
const h = harness();
h.events.ready();
assert.equal(h.messages[0].payload.JS_READY, 1);
assert.equal(h.locations.length, 0);
h.messages[0].fail({message: 'offline'}); h.timers.shift()();
assert.equal(h.messages.at(-1).payload.JS_READY, 1);
h.refresh(); h.refresh();
assert.equal(h.locations.length, 1, 'overlapping requests coalesce');
h.locate();
assert(h.requests[0].url.includes('current=temperature_2m,weather_code'));
assert(h.requests[0].url.includes('temperature_unit=celsius'));
assert(h.requests[1].url.includes('hourly=uv_index&timeformat=unixtime'));
h.respond(20.7);
assert.equal(h.messages.at(-2).payload.TEMPERATURE, 21);
assert.equal(h.messages.at(-1).payload.UV_INDEX, 6, 'select current hour, not first or next');
settle(h);
for (const [temp, uv, expectedTemp, expectedUv] of [[0,0,0,0],[-10.7,6.7,-11,7],[-0.1,12.2,0,12]]) {
  h.refresh(); h.locate(); h.respond(temp, uv);
  assert.equal(h.messages.at(-2).payload.TEMPERATURE, expectedTemp);
  assert.equal(h.messages.at(-1).payload.UV_INDEX, expectedUv);
  settle(h);
}
for (const bad of [null, '6', -1, 101]) {
  const t = harness(); t.refresh(); t.locate(); t.respond(21, bad);
  assert.equal(t.messages.length, 1); assert.equal(t.messages[0].payload.TEMPERATURE, 21);
  settle(t); t.refresh(); assert.equal(t.locations.length, 2);
}
for (const bad of [null, '21', 151]) {
  const t = harness(); t.refresh(); t.locate(); t.respond(bad, 6);
  assert.equal(t.messages.length, 2); assert.equal(t.messages[0].payload.WEATHER_CODE, 2);
  assert(!('TEMPERATURE' in t.messages[0].payload));
  assert.equal(t.messages[1].payload.UV_INDEX, 6);
  settle(t); t.refresh(); assert.equal(t.locations.length, 2);
}
for (const mode of ['onerror','ontimeout','http','json']) {
  for (const failedIndex of [0,1]) {
    const t = harness(); t.refresh(); t.locate();
    const failed = t.requests[failedIndex], good = t.requests[1-failedIndex];
    if (mode === 'http') { failed.status=500; failed.onload(); }
    else if (mode === 'json') { failed.status=200; failed.responseText='!'; failed.onload(); }
    else failed[mode]();
    good.status=200;
    good.responseText=JSON.stringify(failedIndex === 0 ?
      {hourly:{time:[Math.floor(Date.now()/3600000)*3600],uv_index:[5]}} :
      {current:{temperature_2m:21}});
    good.onload(); assert.equal(t.messages.length,failedIndex === 0 ? 2 : 1);
    if (failedIndex === 0) assert.equal(t.messages[0].payload.WEATHER_CODE,-1);
    settle(t); t.refresh(); assert.equal(t.locations.length,2);
  }
}
const stale = harness(); stale.refresh(); stale.locate(); stale.respond(21, 6, [1]);
assert.equal(stale.messages.length,1,'no stale UV hour accepted');
const denied = harness(); denied.refresh(); denied.locations[0].fail({message:'denied'});
denied.refresh(); assert.equal(denied.locations.length,2);
const delivery = harness(); delivery.refresh(); delivery.locate(); delivery.respond(21,6);
delivery.messages.forEach(m => m.fail({message:'offline'}));
delivery.refresh(); assert.equal(delivery.locations.length,2);
console.log('Temperature and UV companion checks passed');

for (const code of [0, 1, 45, 67, 86, 99, null, '0', -1, 100, 2.5]) {
  const t = harness(); t.refresh(); t.locate(); t.respond(21, 6, null, code);
  assert.equal(t.messages[0].payload.WEATHER_CODE,
    typeof code === 'number' && Number.isInteger(code) && code >= 0 && code <= 99 ? code : -1);
}
const missing = harness(); missing.refresh(); missing.locate();
missing.requests[0].status = 200; missing.requests[0].responseText = 'null';
missing.requests[0].onload(); assert.equal(missing.messages[0].payload.WEATHER_CODE,-1);
console.log('Weather code validation and fallback checks passed');

const absent = harness(); absent.refresh(); absent.locate();
absent.requests[0].status = 200;
absent.requests[0].responseText = JSON.stringify({current:{temperature_2m:21}});
absent.requests[0].onload();
assert.equal(absent.messages[0].payload.WEATHER_CODE,-1);
assert.equal(absent.messages[0].payload.TEMPERATURE,21);
assert.equal(denied.messages[0].payload.WEATHER_CODE,-1);
console.log('Missing-code and location-failure fallback checks passed');

for (const fields of [1, 2, 3]) {
  const t = harness(); t.refresh(fields); t.refresh(fields); t.locate();
  assert.equal(t.locations.length, 1);
  assert.equal(t.requests.length, fields === 3 ? 2 : 1);
  assert.equal(t.requests.some(r => r.url.includes('air-quality-api')), !!(fields & 2));
  assert.equal(t.requests.some(r => r.url.includes('current=temperature')), !!(fields & 1));
  t.requests.forEach(r => r.onerror()); settle(t);
  t.refresh(fields); assert.equal(t.locations.length, 2, 'single-field failures release fetch lock');
}
for (const fields of [0, -1, 4, 1.5, '1', null, undefined]) {
  const t = harness(); t.events.appmessage({payload: {REQUEST_WEATHER: fields}});
  assert.equal(t.locations.length, 0);
}
const uvOnly = harness(); uvOnly.refresh(2);
uvOnly.locations[0].fail({message: 'denied'});
assert.equal(uvOnly.messages.length, 0, 'UV failure does not change temperature icon');
const switched = harness(); switched.refresh(1); switched.locate();
switched.refresh(3); switched.refresh(3);
assert.equal(switched.locations.length, 1);
switched.requests[0].onerror(); settle(switched);
assert.equal(switched.locations.length, 2, 'newly enabled UV is queued once');
switched.locate(); assert.equal(switched.requests.length, 2);
assert(switched.requests[1].url.includes('air-quality-api'));
switched.requests[1].onerror(); switched.refresh(2);
assert.equal(switched.locations.length, 3);
console.log('Displayed weather selection, overlap, validation, and selective failure checks passed');
