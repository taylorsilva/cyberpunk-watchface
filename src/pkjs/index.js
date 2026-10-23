/* Weather runs on the phone; the watch owns the refresh schedule. */
var fetching = false;

function getWeather() {
  if (fetching) return;
  fetching = true;
  function fail(reason) {
    fetching = false;
    console.log('Weather: ' + reason);
  }
  navigator.geolocation.getCurrentPosition(function(position) {
    var latitude = position.coords.latitude;
    var longitude = position.coords.longitude;
    if (!isFinite(latitude) || !isFinite(longitude)) {
      fail('invalid location');
      return;
    }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://api.open-meteo.com/v1/forecast?latitude=' +
      encodeURIComponent(latitude) + '&longitude=' + encodeURIComponent(longitude) +
      '&current=temperature_2m&temperature_unit=celsius', true);
    xhr.timeout = 20000;
    xhr.onerror = function() { fail('network error'); };
    xhr.ontimeout = function() { fail('request timed out'); };
    xhr.onload = function() {
      if (xhr.status !== 200) { fail('HTTP ' + xhr.status); return; }
      var value;
      try {
        value = JSON.parse(xhr.responseText).current.temperature_2m;
        if (typeof value !== 'number' || !isFinite(value) || value < -150 || value > 150)
          throw new Error('invalid temperature');
      } catch (error) { fail('invalid response'); return; }
      Pebble.sendAppMessage({TEMPERATURE: Math.round(value)}, function() {
        fetching = false;
      }, function(error) { fail('delivery failed: ' + JSON.stringify(error)); });
    };
    xhr.send();
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
