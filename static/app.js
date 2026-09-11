const PUSH_ENABLED = true;

const els = {
  place: document.getElementById('place'),
  forecast: document.getElementById('forecast'),
  rain: document.getElementById('rain'),
  rainSummary: document.getElementById('rain-summary'),
  rainUpdated: document.getElementById('rain-updated'),
  rainBars: document.getElementById('rain-bars'),
  rainTicks: document.getElementById('rain-ticks'),
  status: document.getElementById('push-status'),
  button: document.getElementById('push-button'),
  iosHelp: document.getElementById('ios-help'),
  areaSelect: document.getElementById('area-select'),
  areaNote: document.getElementById('area-note'),
  testButton: document.getElementById('test-button'),
  rainOptIn: document.getElementById('rain-opt-in'),
  rainToggle: document.getElementById('rain-alerts-toggle'),
  glitterToggle: document.getElementById('glitter-toggle'),
  aboutToggle: document.getElementById('about-toggle'),
  about: document.getElementById('about'),
};

let registration = null;
let selectedArea = null;

// if not subscribed, enables us to keep users location in browser
const AREA_KEY = 'weather-assistant-area';

function rememberedArea() {
  try {
    const stored = localStorage.getItem(AREA_KEY);
    return stored === null ? null : Number(stored);
  } catch (err) {
    return null;
  }
}

function rememberArea(areaId) {
  try {
    localStorage.setItem(AREA_KEY, String(areaId));
  } catch (err) {
  }
}

async function setUpAreas() {
  const res = await fetch('/api/areas');
  if (!res.ok) return;
  const { areas, default: defaultArea } = await res.json();

  const remembered = rememberedArea();
  selectedArea = remembered === null ? defaultArea : remembered;
  if (!areas.some((a) => a.id === selectedArea)) selectedArea = defaultArea;

  els.areaSelect.replaceChildren(
    ...areas.map((a) => {
      const option = document.createElement('option');
      option.value = a.id;
      option.textContent = a.name;
      option.selected = a.id === selectedArea;
      return option;
    })
  );
  els.areaSelect.onchange = () => changeArea(Number(els.areaSelect.value));
}

async function changeArea(areaId) {
  selectedArea = areaId;
  rememberArea(areaId);
  els.areaNote.textContent = '';
  await loadForecast();
  await loadNearTermForecast();

  if (!registration) return;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;

  try {
    const res = await fetch('/api/area', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint, area: areaId }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const { area_name: areaName } = await res.json();
    els.areaNote.textContent = `Notifications now follow ${areaName}.`;
  } catch (err) {
    els.areaNote.textContent = `Could not move your notifications: ${err.message}`;
  }
}

function temperatureList(temperatures) {
  const list = document.createElement('ul');
  list.className = 'temps';

  for (const period of Object.values(temperatures || {})) {
    const row = document.createElement('li');

    if (period.icon) {
      const img = document.createElement('img');
      img.src = period.icon;
      img.width = 40;
      img.height = 40;
      img.alt = '';
      row.append(img);
    }

    const label = document.createElement('span');
    label.className = 'temp-label';
    label.textContent = period.label;

    const value = document.createElement('span');
    value.className = 'temp-value';
    value.textContent = period.temperature === null
      ? 'no data'
      : `${period.temperature} °C`;

    row.append(label, value);
    list.append(row);
  }
  return list;
}

function conditionList(items) {
  const list = document.createElement('ul');
  list.className = 'conditions';

  for (const item of items || []) {
    const row = document.createElement('li');
    row.dataset.kind = item.kind;

    const mark = document.createElement('span');
    mark.className = 'condition-mark';
    mark.textContent = item.emoji;

    const text = document.createElement('span');
    text.textContent = item.text;

    row.append(mark, text);
    list.append(row);
  }
  return list;
}

async function loadForecast() {
  try {
    const url = selectedArea === null
      ? '/api/forecast'
      : `/api/forecast?area=${selectedArea}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const data = await res.json();

    els.place.textContent = `${data.area} · 🌅 ${data.sunrise}, 🌇 ${data.sunset}`;

    const day = new Date(`${data.day}T12:00:00`).toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long',
    });
    const heading = document.createElement('p');
    heading.className = 'forecast-day';
    heading.textContent = day;

    els.forecast.replaceChildren(
      heading,
      temperatureList(data.temperatures),
      conditionList(data.conditions),
    );
  } catch (err) {
    els.place.textContent = '';
    els.forecast.textContent = `Could not load the forecast (${err.message}).`;
  } finally {
    els.forecast.setAttribute('aria-busy', 'false');
  }
}

const POLLING_REGION_TIME_ZONE = 'Europe/Oslo';
const ACTIVE_POLL_MS = 10 * 60 * 1000;
const SLEEP_CHECK_MS = 60 * 60 * 1000;

const QUIET_HOURS_START = 23;
const QUIET_HOURS_END = 6;

function inQuietHours(hour) {
  return hour >= QUIET_HOURS_START || hour < QUIET_HOURS_END;
}

function pollingRegionHour() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: POLLING_REGION_TIME_ZONE,
    hour: '2-digit',
    hour12: false,
  }).formatToParts(new Date());
  return Number(parts.find((part) => part.type === 'hour').value);
}

function nextNearTermForecastPoll() {
  return inQuietHours(pollingRegionHour()) ? SLEEP_CHECK_MS : ACTIVE_POLL_MS;
}

async function loadNearTermForecast() {
  try {
    const url = selectedArea === null
      ? '/api/near-term-forecast'
      : `/api/near-term-forecast?area=${selectedArea}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const data = await res.json();
    if (!data.available) {
      els.rain.hidden = true;
      return;
    }
    renderRainStrip(data);
    els.rain.hidden = false;
  } catch (err) {
    els.rain.hidden = true;
  }
}

function scheduleNearTermForecastPoll() {
  setTimeout(async () => {
    if (!inQuietHours(pollingRegionHour())) await loadNearTermForecast();
    scheduleNearTermForecastPoll();
  }, nextNearTermForecastPoll());
}

function renderRainStrip(data) {
  els.rainSummary.textContent = data.summary;
  els.rainUpdated.textContent = `Updated ${data.updated_at}.`;
  const scale = Math.max(data.peak_rate, data.scale_floor);

  els.rainBars.replaceChildren(
    ...data.steps.map((step) => {
      const bar = document.createElement('div');
      bar.className = `rain-bar rain-${step.level}`;
      if (step.level !== 'dry') {
        const share = Math.min(step.rate / scale, 1) * 100;
        bar.style.height = `max(3px, ${share}%)`;
      }
      bar.title = `${step.time} · ${step.rate.toFixed(1)} mm/h`;
      return bar;
    })
  );

  const steps = data.steps;
  const ticks = steps.length
    ? [steps[0], steps[Math.floor(steps.length / 2)], steps[steps.length - 1]]
    : [];
  els.rainTicks.replaceChildren(
    ...ticks.map((step) => {
      const span = document.createElement('span');
      span.textContent = step.time;
      return span;
    })
  );
}

function isIOS() {
  return /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function isInstalled() {
  return window.navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches;
}

function urlBase64ToUint8Array(base64url) {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function setButton(label, handler, secondary = false) {
  els.button.textContent = label;
  els.button.hidden = false;
  els.button.disabled = false;
  els.button.classList.toggle('secondary', secondary);
  els.button.onclick = handler;
}

async function setUpPush() {
  if (!PUSH_ENABLED) {
    els.status.textContent =
      'Coming soon — a morning forecast and a notification if sun pops up. ' +
      'For now, @WhisperWeatherBot on Telegram does this.';
    return;
  }

  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    if (isIOS() && !isInstalled()) {
      els.status.textContent = 'Almost there..';
      els.iosHelp.hidden = false;
    } else {
      els.status.textContent = 'This browser does not support push notifications.';
    }
    return;
  }

  registration = await navigator.serviceWorker.register('/sw.js');

  if (Notification.permission === 'denied') {
    els.status.textContent =
      'Notifications are blocked for this site. Re-allow them in your browser settings, then reload.';
    return;
  }

  const existing = await registration.pushManager.getSubscription();
  existing ? showSubscribed() : showUnsubscribed();
}

function showSubscribed() {
  els.status.textContent = 'On — you will get the morning forecast and sun updates.';
  setButton('Turn off notifications', unsubscribe, true);
  showSubscriptionOptions();
}

function showUnsubscribed() {
  els.status.textContent = 'Off — turn them on for a morning forecast and sun updates.';
  setButton('Enable notifications', subscribe);
  els.testButton.hidden = true;
  els.rainOptIn.hidden = true;
}

async function showSubscriptionOptions() {
  try {
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return;

    const res = await fetch('/api/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    if (!res.ok) return;

    const { is_admin: isAdmin, rain_alerts: rainAlerts } = await res.json();

    els.rainOptIn.hidden = false;
    els.rainToggle.checked = rainAlerts;
    els.rainToggle.onchange = () => saveRainAlerts(els.rainToggle.checked);

    if (!isAdmin) return;
    els.testButton.hidden = false;
    els.testButton.disabled = false;
    els.testButton.textContent = 'Send a test notification';
    els.testButton.onclick = sendTestPush;
  } catch (err) {
    console.warn('Could not check subscription options:', err);
  }
}

async function saveRainAlerts(enabled) {
  els.rainToggle.disabled = true;
  try {
    const subscription = await registration.pushManager.getSubscription();
    const res = await fetch('/api/rain-alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint, enabled }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
  } catch (err) {
    els.rainToggle.checked = !enabled;
    els.areaNote.textContent = `Could not save that: ${err.message}`;
  } finally {
    els.rainToggle.disabled = false;
  }
}

async function sendTestPush() {
  els.testButton.disabled = true;
  els.testButton.textContent = 'Sending…';
  try {
    const subscription = await registration.pushManager.getSubscription();
    const res = await fetch('/api/test-push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
    els.testButton.textContent = 'Sent';
  } catch (err) {
    els.testButton.textContent = `Failed: ${err.message}`;
  } finally {
    setTimeout(() => {
      els.testButton.disabled = false;
      els.testButton.textContent = 'Send a test notification';
    }, 4000);
  }
}

async function subscribe() {
  els.button.disabled = true;
  els.status.textContent = 'Waiting for permission…';
  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      els.status.textContent = permission === 'denied'
        ? 'Notifications blocked. You can re-allow them in your browser settings.'
        : 'Permission dismissed — tap the button to try again.';
      els.button.disabled = false;
      return;
    }

    const keyRes = await fetch('/api/vapid-key');
    if (!keyRes.ok) throw new Error('push is not configured on the server');
    const { public_key: publicKey } = await keyRes.json();

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });

    const res = await fetch('/api/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...subscription.toJSON(), area: selectedArea }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);

    showSubscribed();
  } catch (err) {
    els.status.textContent = `Could not enable notifications: ${err.message}`;
    els.button.disabled = false;
  }
}

async function unsubscribe() {
  if (!confirm('Are you sure you want to stop receiving notifications?')) {
    return;
  }
  els.button.disabled = true;
  try {
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await fetch('/api/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
      await subscription.unsubscribe();
    }
    showUnsubscribed();
  } catch (err) {
    els.status.textContent = `Could not turn them off: ${err.message}`;
    els.button.disabled = false;
  }
}

els.glitterToggle.onclick = () => {
  const enabled = !document.body.classList.contains('glitter-mode');
  document.body.classList.toggle('glitter-mode', enabled);
  els.glitterToggle.setAttribute('aria-pressed', String(enabled));
};

els.aboutToggle.onclick = () => {
  const open = els.about.hidden;
  els.about.hidden = !open;
  els.aboutToggle.setAttribute('aria-expanded', String(open));
};

setUpAreas()
  .catch(() => { /* if can't load areas we don't crash the page*/ })
  .then(loadForecast)
  .then(loadNearTermForecast)
  .then(() => {
    setUpPush();
    scheduleNearTermForecastPoll();
  });
