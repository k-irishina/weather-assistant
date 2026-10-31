const locateButton = document.getElementById('locate-button');
const locationRequest = document.getElementById('location-request');
const locationRequestButton = document.getElementById('location-request-button');
const locationRequestClose = document.getElementById('location-request-close');

// rounded to about 1km
let requestedPlace = null;

function locateMe() {
  els.areaNote.textContent = 'Finding your location…';
  locationRequest.hidden = true;
  navigator.geolocation.getCurrentPosition(async (position) => {
    requestedPlace = {
      latitude: Math.round(position.coords.latitude * 100) / 100,
      longitude: Math.round(position.coords.longitude * 100) / 100,
    };
    try {
      const res = await fetch('/api/closest-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestedPlace),
      });
      if (!res.ok) throw new Error(`server said ${res.status}`);
      const { area, area_name: areaName, distance_km: distanceKm } = await res.json();
      if (area === null) {
        els.areaNote.textContent = '';
        locationRequestButton.disabled = false;
        locationRequestButton.textContent = 'Send request';
        locationRequest.hidden = false;
        return;
      }
      els.areaSelect.value = area;
      await changeArea(area);
      els.areaNote.textContent = `Closest: ${areaName}, ${distanceKm} km away. ${els.areaNote.textContent}`;
    } catch (err) {
      els.areaNote.textContent = `Could not find the closest location: ${err.message}`;
    }
  }, () => {
    els.areaNote.textContent = 'Could not get your location. Check that location access is allowed.';
  });
}

async function sendLocationRequest() {
  locationRequestButton.disabled = true;
  try {
    const res = await fetch('/api/location-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestedPlace),
    });
    if (res.status === 429) throw new Error('too many requests - try again later');
    if (!res.ok) throw new Error(`server responded with ${res.status}`);
    locationRequestButton.textContent = 'Request sent, thank you!';
  } catch (err) {
    locationRequestButton.disabled = false;
    els.areaNote.textContent = `Could not send the request: ${err.message}`;
  }
}

locateButton.onclick = locateMe;
locationRequestButton.onclick = sendLocationRequest;
locationRequestClose.onclick = () => { locationRequest.hidden = true; };
