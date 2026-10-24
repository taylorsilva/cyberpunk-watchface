var Clay = require('pebble-clay');
var clay = new Clay(require('./config.json'), null, {autoHandleEvents: false});
var frameKeys = ['FRAME_LEFT', 'FRAME_MIDDLE', 'FRAME_RIGHT'];

Pebble.addEventListener('showConfiguration', function() {
  Pebble.openURL(clay.generateUrl());
});
Pebble.addEventListener('webviewclosed', function(event) {
  if (!event || !event.response) return;
  var settings;
  try {
    settings = clay.getSettings(event.response, false);
  } catch (error) {
    console.log('Invalid settings response: ' + error.message);
    return;
  }
  var payload = {};
  frameKeys.forEach(function(key) {
    var value = settings[key];
    if (value && typeof value === 'object') value = value.value;
    if (/^[0-4]$/.test(String(value))) payload[key] = Number(value);
  });
  var timeFormat = settings.TIME_FORMAT;
  if (timeFormat && typeof timeFormat === 'object') timeFormat = timeFormat.value;
  if (/^(12|24)$/.test(String(timeFormat))) payload.TIME_FORMAT = Number(timeFormat);
  if (!Object.keys(payload).length) return;
  Pebble.sendAppMessage(payload, function() {}, function(error) {
    console.log('Settings delivery failed: ' + JSON.stringify(error));
  });
});

/* Weather runs on the phone; the watch owns the refresh schedule. */
var fetching = false;

function unavailableWeather() {
  Pebble.sendAppMessage({WEATHER_CODE: -1}, function() {}, function(error) {
    console.log('Weather fallback delivery failed: ' + JSON.stringify(error));
  });
}

function getWeather() {
  if (fetching) return;
  fetching = true;
  function fail(reason) {
    fetching = false;
    console.log('Weather: ' + reason);
    unavailableWeather();
  }
  navigator.geolocation.getCurrentPosition(function(position) {
    var latitude = position.coords.latitude;
    var longitude = position.coords.longitude;
    if (!isFinite(latitude) || !isFinite(longitude)) {
      fail('invalid location');
      return;
    }
    var coordinates = 'latitude=' + encodeURIComponent(latitude) +
      '&longitude=' + encodeURIComponent(longitude);
    var remaining = 2;
    // Finish only after both independent requests (and their deliveries) settle.
    function request(url, key, readValue, readCode) {
      var finished = false;
      function done(reason) {
        if (finished) return;
        finished = true;
        if (reason) {
          console.log('Weather ' + key + ': ' + reason);
          if (readCode) unavailableWeather();
        }
        if (--remaining === 0) fetching = false;
      }
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, true);
      xhr.timeout = 20000;
      xhr.onerror = function() { done('network error'); };
      xhr.ontimeout = function() { done('request timed out'); };
      xhr.onload = function() {
        if (xhr.status !== 200) { done('HTTP ' + xhr.status); return; }
        var value, data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch (error) { done('invalid response'); return; }
        var payload = {};
        if (readCode) payload.WEATHER_CODE = readCode(data);
        try {
          value = readValue(data);
          if (typeof value !== 'number' || !isFinite(value))
            throw new Error('invalid value');
        } catch (error) {
          value = undefined;
          if (!readCode) { done('invalid response'); return; }
        }
        if (typeof value === 'number' && isFinite(value)) payload[key] = Math.round(value);
        Pebble.sendAppMessage(payload, function() { done(); },
          function(error) { done('delivery failed: ' + JSON.stringify(error)); });
      };
      xhr.send();
    }
    request('https://api.open-meteo.com/v1/forecast?' + coordinates +
      '&current=temperature_2m,weather_code&temperature_unit=celsius', 'TEMPERATURE', function(data) {
        var value = data.current.temperature_2m;
        if (value < -150 || value > 150) throw new Error('invalid temperature');
        return value;
      }, function(data) {
        var code = data && data.current && data.current.weather_code;
        return typeof code === 'number' && isFinite(code) &&
          code >= 0 && code <= 99 && Math.floor(code) === code ? code : -1;
      });
    request('https://air-quality-api.open-meteo.com/v1/air-quality?' + coordinates +
      '&hourly=uv_index&timeformat=unixtime&forecast_days=2', 'UV_INDEX', function(data) {
        var now = Math.floor(Date.now() / 1000);
        var times = data.hourly.time;
        var values = data.hourly.uv_index;
        for (var i = 0; i < times.length; ++i) {
          if (typeof times[i] === 'number' && times[i] <= now && now < times[i] + 3600) {
            var value = values[i];
            if (value < 0 || value > 100) throw new Error('invalid UV index');
            return value;
          }
        }
        throw new Error('current hour unavailable');
      });
  }, function(error) { fail('location failed: ' + error.message); },
  {enableHighAccuracy: false, timeout: 15000, maximumAge: 0});
}

function notifyReady() {
  Pebble.sendAppMessage({JS_READY: 1}, function() {}, function(error) {
    console.log('Weather readiness delivery failed: ' + JSON.stringify(error));
    // Startup may happen while Bluetooth is disconnected. Keep trying the
    // handshake so a later reconnect can unblock the watch's pending refresh.
    setTimeout(notifyReady, 5000);
  });
}
Pebble.addEventListener('ready', notifyReady);
Pebble.addEventListener('appmessage', function(event) {
  if (event.payload.REQUEST_WEATHER) getWeather();
});
