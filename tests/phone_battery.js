// Exercise the companion's phone battery delivery and unavailable paths.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('src/pkjs/index.js', 'utf8');
const config = JSON.parse(fs.readFileSync('src/pkjs/config.json', 'utf8'));

function harness({getBattery} = {}) {
  const events = {}, messages = [], timers = [], logs = [], storage = {};
  const context = {
    require(name) {
      if (name === './config.json') return config;
      if (name === 'pebble-clay') return function Clay() {
        this.generateUrl = () => 'data:text/html';
        // Mirrors pebble-clay 1.0.4: decode non-JSON responses, return the raw
        // submission, and persist flattened values.
        this.getSettings = (response, convert) => {
          if (!/^\{/.test(response)) response = decodeURIComponent(response);
          const raw = JSON.parse(response);
          const flat = {};
          for (const key of Object.keys(raw)) {
            const value = raw[key];
            flat[key] = value && typeof value === 'object' ? value.value : value;
          }
          storage['clay-settings'] = JSON.stringify(flat);
          return raw;
        };
      };
      throw new Error(name);
    },
    console: {log(message) { logs.push(message); }},
    setTimeout(fn, delay) { fn.delay = delay; timers.push(fn); return fn; },
    clearTimeout(fn) { const i = timers.indexOf(fn); if (i >= 0) timers.splice(i, 1); },
    localStorage: {
      getItem(key) { return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null; },
      setItem(key, value) { storage[key] = value; }
    },
    navigator: {geolocation: {getCurrentPosition() {}}},
    XMLHttpRequest: function() { this.open = () => {}; this.send = () => {}; },
    Pebble: {
      addEventListener(name, handler) { events[name] = handler; },
      sendAppMessage(payload, ok) { messages.push(payload); if (ok) ok(); }
    }
  };
  if (getBattery) context.navigator.getBattery = getBattery;
  vm.runInNewContext(source, context);
  return {events, messages, timers, storage, logs,
    fire(name, data) { events[name](data); }};
}
function batteryAt(level) {
  return {level, charging: false, listeners: {},
    addEventListener(name, fn) { this.listeners[name] = fn; }};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const unavailable = harness();
  unavailable.fire('ready');
  await settle();
  assert.deepEqual(unavailable.messages, [{JS_READY: 1}]);
  assert(unavailable.logs.some(line => line.includes('unavailable')));

  const battery = batteryAt(0.62);
  const phone = harness({getBattery: () => Promise.resolve(battery)});
  phone.fire('ready');
  await settle();
  assert.deepEqual(phone.messages, [{JS_READY: 1}, {PHONE_BATTERY: 62}]);
  assert.equal(typeof battery.listeners.levelchange, 'function');

  battery.level = 0.275;
  battery.listeners.levelchange();
  assert.equal(phone.messages.at(-1).PHONE_BATTERY, 28);
  battery.level = 1.2;
  battery.listeners.levelchange();
  assert.equal(phone.messages.at(-1).PHONE_BATTERY, 100);
  battery.level = -0.1;
  battery.listeners.levelchange();
  assert.equal(phone.messages.at(-1).PHONE_BATTERY, 0);
  const beforeInvalid = phone.messages.length;
  battery.level = NaN;
  battery.listeners.levelchange();
  battery.level = '50';
  battery.listeners.levelchange();
  assert.equal(phone.messages.length, beforeInvalid);
  console.log('Phone battery availability, rounding, and clamping checks passed');

  const changing = harness({getBattery: () => Promise.resolve(batteryAt(0.4))});
  changing.fire('ready');
  await settle();
  assert.deepEqual(changing.messages, [{JS_READY: 1}, {PHONE_BATTERY: 40}]);
  changing.fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: '1'})});
  assert.deepEqual(changing.messages.at(-1), {BATTERY_SOURCE: 1});
  changing.fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: '0'})});
  assert.deepEqual(changing.messages.at(-1), {BATTERY_SOURCE: 0});
  console.log('Battery source setting and persistence checks passed');

  const invalid = harness({getBattery: () => Promise.resolve(batteryAt(0.4))});
  invalid.fire('ready');
  await settle();
  const beforeSettings = invalid.messages.length;
  for (const value of ['2', '-1', '1x', '', null, undefined]) {
    invalid.fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: value})});
  }
  assert.equal(invalid.messages.length, beforeSettings);
  invalid.fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: '1', FRAME_LEFT: '2'})});
  assert.deepEqual(invalid.messages.at(-1), {FRAME_LEFT: 2, BATTERY_SOURCE: 1});
  console.log('Battery source validation and combined settings checks passed');

  const rejecting = harness({getBattery: () => Promise.reject(new Error('denied'))});
  rejecting.fire('ready');
  await settle();
  assert.deepEqual(rejecting.messages, [{JS_READY: 1}]);
  assert(rejecting.logs.some(line => line.includes('denied')));
  console.log('Phone battery rejection checks passed');

  const throwing = harness({getBattery() { throw new Error('blocked'); }});
  throwing.fire('ready');
  await settle();
  assert.deepEqual(throwing.messages, [{JS_READY: 1}],
    'a broken battery API must not block readiness');
  assert(throwing.logs.some(line => line.includes('blocked')));

  const malformed = harness({getBattery: () => undefined});
  malformed.fire('ready');
  await settle();
  assert.deepEqual(malformed.messages, [{JS_READY: 1}]);

  let attempts = 0;
  const retrying = harness({getBattery() {
    attempts += 1;
    return attempts === 1 ? Promise.reject(new Error('transient'))
                          : Promise.resolve(batteryAt(0.5));
  }});
  retrying.fire('ready');
  await settle();
  assert.equal(attempts, 1);
  assert.deepEqual(retrying.messages, [{JS_READY: 1}]);
  retrying.fire('ready');
  await settle();
  assert.equal(attempts, 2, 'a rejected battery API must be retried');
  assert.deepEqual(retrying.messages, [{JS_READY: 1}, {PHONE_BATTERY: 50}]);
  console.log('Broken battery API and retry checks passed');

  let resolveBattery;
  const pending = harness({getBattery: () => new Promise(resolve => { resolveBattery = resolve; })});
  pending.fire('ready');
  assert.deepEqual(pending.messages, [{JS_READY: 1}]);
  pending.fire('webviewclosed', {response: JSON.stringify({BATTERY_SOURCE: '1'})});
  assert.deepEqual(pending.messages, [{JS_READY: 1}, {BATTERY_SOURCE: 1}]);
  resolveBattery(batteryAt(0.5));
  await settle();
  assert.deepEqual(pending.messages,
    [{JS_READY: 1}, {BATTERY_SOURCE: 1}, {PHONE_BATTERY: 50}]);
  console.log('Delayed phone battery availability checks passed');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
