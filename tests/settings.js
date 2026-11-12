// Exercise the built companion, including the real Clay settings implementation.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const events = {}, messages = [], storage = {}, urls = [];
const context = {
  console: {log() {}}, setTimeout() {},
  localStorage: {getItem: k => storage[k] || null, setItem: (k,v) => {storage[k] = v;}},
  Pebble: {
    addEventListener: (name, fn) => { (events[name] ||= []).push(fn); },
    sendAppMessage: (payload, ok) => {messages.push(payload); if (ok) ok();},
    openURL: url => urls.push(url),
    getActiveWatchInfo: () => ({platform: 'emery'}),
    getAccountToken: () => 'test', getWatchToken: () => 'test'
  }
};
vm.runInNewContext(fs.readFileSync('build/pebble-js-app.js', 'utf8'), context);
const fire = (name, data) => (events[name] || []).forEach(fn => fn(data));
fire('ready');
assert.equal(messages[0].JS_READY, 1);
fire('showConfiguration');
assert(urls[0].startsWith('data:text/html'));
const config = JSON.parse(fs.readFileSync('src/pkjs/config.json'));
const items = config.filter(x => x.type === 'section').flatMap(x => x.items);
const timeFormat = items.find(x => x.messageKey === 'TIME_FORMAT');
assert.equal(timeFormat.defaultValue, '12');
assert.deepEqual(timeFormat.options.map(x => x.value), ['12', '24']);
const selectors = items.filter(x => x.messageKey.startsWith('FRAME_'));
assert.deepEqual(selectors.map(x => x.defaultValue), ['1', '2', '3']);
for (const selector of selectors) assert.deepEqual(selector.options.map(x => x.value), ['0','1','2','3','4']);
const before = messages.length;
fire('webviewclosed', {});
fire('webviewclosed', {response: ''});
fire('webviewclosed', {response: '%invalid'});
assert.equal(messages.length, before);
fire('webviewclosed', {response: encodeURIComponent(JSON.stringify({
  FRAME_LEFT: {value: '0'}, FRAME_MIDDLE: {value: '3'}, FRAME_RIGHT: {value: '3'}
}))});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_LEFT:0, FRAME_MIDDLE:3, FRAME_RIGHT:3}));
assert.deepEqual(JSON.parse(storage['clay-settings']), {FRAME_LEFT:'0', FRAME_MIDDLE:'3', FRAME_RIGHT:'3'});
fire('showConfiguration');
const html = decodeURIComponent(urls.at(-1));
assert(html.includes('FRAME_LEFT') && html.includes('"0"'));
fire('webviewclosed', {response: JSON.stringify({FRAME_LEFT:'5', FRAME_MIDDLE:'no', FRAME_RIGHT:'1'})});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_RIGHT:1}));
console.log('Settings page, cancellation, submission, persistence, and validation checks passed');

fire('webviewclosed', {response: JSON.stringify({FRAME_LEFT:'4', FRAME_MIDDLE:'4', FRAME_RIGHT:'4'})});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_LEFT:4, FRAME_MIDDLE:4, FRAME_RIGHT:4}));

for (const format of ['12', '24']) {
  fire('webviewclosed', {response: JSON.stringify({TIME_FORMAT: {value: format}})});
  assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({TIME_FORMAT: Number(format)}));
  assert.equal(JSON.parse(storage['clay-settings']).TIME_FORMAT, format);
  fire('showConfiguration');
  assert(new RegExp('TIME_FORMAT:\\s*"' + format + '"').test(decodeURIComponent(urls.at(-1))));
}
const beforeInvalidFormat = messages.length;
for (const value of ['0', '13', '24x', '', null]) {
  fire('webviewclosed', {response: JSON.stringify({TIME_FORMAT: value})});
}
assert.equal(messages.length, beforeInvalidFormat);
fire('webviewclosed', {response: JSON.stringify({TIME_FORMAT: '24', FRAME_LEFT: '2'})});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_LEFT: 2, TIME_FORMAT: 24}));
console.log('Time format selection, persistence, partial updates, and validation passed');

const unit = items.find(x => x.messageKey === 'TEMPERATURE_UNIT');
assert.equal(unit.defaultValue, '0');
assert.deepEqual(unit.options.map(x => x.value), ['0', '1']);
for (const value of ['0', '1']) {
  fire('webviewclosed', {response: JSON.stringify({TEMPERATURE_UNIT: {value}})});
  assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({TEMPERATURE_UNIT: Number(value)}));
  assert.equal(JSON.parse(storage['clay-settings']).TEMPERATURE_UNIT, value);
  fire('showConfiguration');
  assert(new RegExp('TEMPERATURE_UNIT:\\s*"' + value + '"').test(decodeURIComponent(urls.at(-1))));
}
const beforeInvalidUnit = messages.length;
for (const value of ['2', '-1', '1x', '', null]) {
  fire('webviewclosed', {response: JSON.stringify({TEMPERATURE_UNIT: value})});
}
assert.equal(messages.length, beforeInvalidUnit);
fire('webviewclosed', {response: JSON.stringify({TEMPERATURE_UNIT: '1', FRAME_LEFT: '3'})});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_LEFT: 3, TEMPERATURE_UNIT: 1}));
console.log('Temperature unit settings, persistence, and validation passed');

const battery = items.find(x => x.messageKey === 'BATTERY_SOURCE');
assert.equal(battery.defaultValue, '0');
assert.deepEqual(battery.options.map(x => x.value), ['0', '1']);
assert.deepEqual(battery.options.map(x => x.label), ['Watch battery', 'Phone battery']);
for (const value of ['0', '1']) {
  fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: {value}})});
  assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({BATTERY_SOURCE: Number(value)}));
  assert.equal(JSON.parse(storage['clay-settings']).BATTERY_SOURCE, value);
  fire('showConfiguration');
  assert(new RegExp('BATTERY_SOURCE:\\s*"' + value + '"').test(decodeURIComponent(urls.at(-1))));
}
const beforeInvalidBattery = messages.length;
for (const value of ['2', '-1', '1x', '', null]) {
  fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: value})});
}
assert.equal(messages.length, beforeInvalidBattery);
fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: '1', FRAME_LEFT: '3'})});
assert.equal(JSON.stringify(messages.at(-1)), JSON.stringify({FRAME_LEFT: 3, BATTERY_SOURCE: 1}));
console.log('Battery source setting, persistence, and validation passed');
