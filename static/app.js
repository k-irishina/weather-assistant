const PUSH_ENABLED = true;

const els = {
  place: document.getElementById('place'),
  forecast: document.getElementById('forecast'),
  rain: document.getElementById('rain'),
  rightNow: document.getElementById('right-now'),
  rightNowText: document.getElementById('right-now-text'),
  rainUpdated: document.getElementById('rain-updated'),
  rainBars: document.getElementById('rain-bars'),
  rainTicks: document.getElementById('rain-ticks'),
  rainScale: document.getElementById('rain-scale'),
  status: document.getElementById('push-status'),
  button: document.getElementById('push-button'),
  pushSettings: document.getElementById('push-settings'),
  pushSummary: document.getElementById('push-summary'),
  pushToggle: document.getElementById('push-toggle'),
  iosHelp: document.getElementById('ios-help'),
  areaSelect: document.getElementById('area-select'),
  areaNote: document.getElementById('area-note'),
  testButton: document.getElementById('test-button'),
  rainAlerts: document.getElementById('rain-alerts'),
  rainAlertsToggle: document.getElementById('rain-alerts-toggle'),
  morningTime: document.getElementById('morning-time'),
  morningTimeSelect: document.getElementById('morning-time-select'),
  weekendMorning: document.getElementById('weekend-morning'),
  weekendMorningToggle: document.getElementById('weekend-morning-toggle'),
  glitterToggle: document.getElementById('glitter-toggle'),
  inApp: document.getElementById('in-app'),
  inAppText: document.getElementById('in-app-text'),
  inAppOpen: document.getElementById('in-app-open'),
  inAppCopy: document.getElementById('in-app-copy'),
  inAppNote: document.getElementById('in-app-note'),
  aboutToggle: document.getElementById('about-toggle'),
  about: document.getElementById('about'),
  changelog: document.getElementById('changelog'),
  changelogEntries: document.getElementById('changelog-entries'),
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
    const cells = periodCells(period);

    if (period.hours && period.hours.length) {
      const details = document.createElement('details');
      details.className = 'temp-period';
      const summary = document.createElement('summary');
      summary.append(...cells);
      details.append(summary, hourStrip(period.hours));
      row.append(details);
    } else {
      row.append(...cells);
    }
    list.append(row);
  }
  return list;
}

function periodCells(period) {
  const cells = [];
  if (period.icon) {
    const img = document.createElement('img');
    img.src = period.icon;
    img.width = 40;
    img.height = 40;
    img.alt = '';
    cells.push(img);
  }

  const label = document.createElement('span');
  label.className = 'temp-label';
  label.textContent = period.label;

  const value = document.createElement('span');
  value.className = 'temp-value';
  value.textContent = period.temperature === null
    ? 'no data'
    : `${period.temperature} °C`;

  cells.push(label, value);
  return cells;
}

function hourStrip(hours) {
  const strip = document.createElement('ol');
  strip.className = 'temp-hours';
  for (const { hour, temperature } of hours) {
    const item = document.createElement('li');
    const time = document.createElement('span');
    time.className = 'temp-hour';
    time.textContent = hour;
    const value = document.createElement('span');
    value.textContent = temperature === null ? '–' : `${temperature}°`;
    item.append(time, value);
    strip.append(item);
  }
  return strip;
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

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function shortDate(isoDay) {
  const [, month, day] = isoDay.split('-').map(Number);
  return `${day} ${MONTHS[month - 1]}`;
}

let forecastDay = 'today';
let forecastLoadedAt = 0;

async function loadForecast(day = 'today') {
  els.forecast.setAttribute('aria-busy', 'true');
  try {
    const params = new URLSearchParams();
    if (selectedArea !== null) params.set('area', selectedArea);
    if (day === 'tomorrow') params.set('day', 'tomorrow');
    const query = params.toString();
    const res = await fetch(query ? `/api/forecast?${query}` : '/api/forecast');
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const data = await res.json();
    forecastDay = day;

    els.place.textContent = `${data.area} · 🌅 ${data.sunrise}, 🌇 ${data.sunset}`;

    const dayLabel = shortDate(data.day);
    const heading = document.createElement('p');
    heading.className = 'forecast-day';
    heading.textContent = dayLabel;
    if (data.updated_at) {
      const updated = document.createElement('span');
      updated.className = 'muted updated-note';
      updated.textContent = `Updated ${data.updated_at}`;
      heading.append(updated);
    }

    const headingRow = document.createElement('div');
    headingRow.className = 'forecast-day-row';
    headingRow.append(heading);

    if (day === 'today' && data.tomorrow_available) {
      headingRow.append(dayFlipButton('Tomorrow ›', 'tomorrow'));
    } else if (day === 'tomorrow') {
      headingRow.append(dayFlipButton('‹ Today', 'today'));
    }

    els.forecast.classList.remove('page-flip');
    void els.forecast.offsetWidth;
    els.forecast.replaceChildren(
      headingRow,
      temperatureList(data.temperatures),
      conditionList(data.conditions),
    );
    els.forecast.classList.add('page-flip');
    forecastLoadedAt = Date.now();
  } catch (err) {
    els.place.textContent = '';
    els.forecast.textContent = `Could not load the forecast (${err.message}).`;
  } finally {
    els.forecast.setAttribute('aria-busy', 'false');
  }
}

function dayFlipButton(label, targetDay) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'day-flip';
  button.textContent = label;
  button.onclick = () => loadForecast(targetDay);
  return button;
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

let nearTermLoadedAt = 0;

async function loadNearTermForecast() {
  try {
    const url = selectedArea === null
      ? '/api/near-term-forecast'
      : `/api/near-term-forecast?area=${selectedArea}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const data = await res.json();
    nearTermLoadedAt = Date.now();
    // "Now" line switched off until reworked
    // renderRightNow(data.now);
    if (!data.available) {
      els.rain.hidden = true;
      return;
    }
    renderRainStrip(data);
    els.rain.hidden = false;
  } catch (err) {
    // renderRightNow(null);
    els.rain.hidden = true;
  }
}

function renderRightNow(text) {
  els.rightNowText.textContent = text || '';
  els.rightNow.hidden = !text;
}

const STALE_AFTER_MS = 15 * 60 * 1000;

function refreshIfStale() {
  if (document.visibilityState !== 'visible') return;
  const now = Date.now();
  if (now - forecastLoadedAt > STALE_AFTER_MS) {
    loadForecast(forecastDay);
    // also records last_seen for push subscribers
    if (registration) showSubscriptionOptions();
  }
  if (now - nearTermLoadedAt > STALE_AFTER_MS) loadNearTermForecast();
}

document.addEventListener('visibilitychange', refreshIfStale);
window.addEventListener('pageshow', (event) => {
  if (event.persisted) refreshIfStale();
});

function scheduleNearTermForecastPoll() {
  setTimeout(async () => {
    if (!inQuietHours(pollingRegionHour())) await loadNearTermForecast();
    scheduleNearTermForecastPoll();
  }, nextNearTermForecastPoll());
}

// tapping the graph explains the bars for a moment, instead of a permanent caption
const RAIN_SCALE_SHOWN_MS = 4000;
let rainScaleTimer = null;

els.rainBars.addEventListener('click', () => {
  clearTimeout(rainScaleTimer);
  els.rainScale.hidden = false;
  rainScaleTimer = setTimeout(() => { els.rainScale.hidden = true; }, RAIN_SCALE_SHOWN_MS);
});

function renderRainStrip(data) {
  els.rainUpdated.textContent = `Updated ${data.updated_at}`;
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

  els.rainTicks.replaceChildren(
    ...data.steps.map((step, index) => {
      const cell = document.createElement('div');
      cell.className = 'rain-tick';
      const [hour, minute] = step.time.split(':');
      const roundTime = Number(minute) % 30 < 5;
      if (index === 0 || (roundTime && index >= 3)) {
        const label = document.createElement('span');
        label.textContent = index === 0 ? step.time : `${hour}:${Number(minute) < 30 ? '00' : '30'}`;
        cell.append(label);
      }
      return cell;
    })
  );
}

function isIOS() {
  return /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

const SHARE_ICON = '<svg class="inline-icon" viewBox="0 0 24 24" aria-hidden="true">'
  + '<path d="M12 3v12M8 7l4-4 4 4M8 11H6a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-2"/></svg>';
const SHARE = `${SHARE_ICON} <strong>Share</strong>`;

function shareStepHtml() {
  const ua = navigator.userAgent;
  if (/CriOS/.test(ua)) return `Tap ${SHARE} at the top right, in the address bar`;
  if (/FxiOS|EdgiOS/.test(ua)) return `Open the browser menu and tap ${SHARE}`;
  if (/iPad/.test(ua) || navigator.platform === 'MacIntel') {
    return `Tap ${SHARE} at the top right of the screen`;
  }
  return `Tap ${SHARE} at the bottom of the screen. Don't see it? Tap `
    + '<span class="key">•••</span> next to the address bar first';
}


function inAppBrowser() {
  const ua = navigator.userAgent;
  if (/Instagram/.test(ua)) return 'Instagram';
  if (/MessengerForiOS|Orca-Android/.test(ua)) return 'Messenger';
  if (/FBAN|FBAV|FB_IAB/.test(ua)) return 'Facebook';
  if (/LinkedInApp/.test(ua)) return 'LinkedIn';
  if (/Snapchat/.test(ua)) return 'Snapchat';
  if (/Telegram/.test(ua) || window.TelegramWebviewProxy || window.TelegramWebview) return 'Telegram';
  return null;
}

function isAndroid() {
  return /Android/.test(navigator.userAgent);
}


// Undocumented schemes that hand the page to the real browser; they work in some
// apps and not others (Meta's are unreliable), so the menu route stays primary.
function escapeUrl() {
  const { host, pathname, search } = window.location;
  if (isIOS()) return `x-safari-https://${host}${pathname}${search}`;
  if (isAndroid()) {
    return `intent://${host}${pathname}${search}#Intent;scheme=https;package=com.android.chrome;end`;
  }
  return null;
}

async function copyLink() {
  const url = window.location.href;
  try {
    await navigator.clipboard.writeText(url);
    els.inAppNote.textContent =
      `Copied. Open your browser, paste it into the address bar and enjoy!`;
  } catch (err) {
    els.inAppNote.textContent = `Copy this link and open it in the browser: ${url}`;
  }
}

function showInAppBanner() {
  const app = inAppBrowser();
  if (!app) return;

  els.inAppText.innerHTML = `Weather Asst. is best enjoyed in a full browser. `
    + 'Tap <span class="key">•••</span> at the top, then '
    + '<strong>Open in (browser)</strong>';

  const url = escapeUrl();
  if (url) {
    els.inAppOpen.textContent = `Open in browser`;
    els.inAppOpen.onclick = () => {
      els.inAppNote.textContent = 'If nothing happens, use the ••• menu or Copy link.';
      window.location.href = url;
    };
    els.inAppOpen.hidden = false;
  }
  els.inAppCopy.onclick = copyLink;
  els.inApp.hidden = false;
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

  if (inAppBrowser()) {
    els.status.textContent =
      'Notifications need your normal browser. See the box at the top of the page.';
    return;
  }

  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    if (isIOS() && !isInstalled()) {
      els.status.textContent = 'Almost there..';
      document.getElementById('ios-share-step').innerHTML = shareStepHtml();
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
  els.status.hidden = true;
  els.button.hidden = true;
  els.pushToggle.checked = true;
  els.pushToggle.onchange = () => {
    if (!els.pushToggle.checked) unsubscribe();
  };
  updatePushSummary();
  els.pushSettings.hidden = false;
  showSubscriptionOptions();
}

function updatePushSummary() {
  const parts = ['🔔 On'];
  if (!els.morningTime.hidden) {
    const days = els.weekendMorningToggle.checked ? 'every day' : 'on weekdays';
    parts.push(`${els.morningTimeSelect.value} ${days}`);
  }
  if (!els.rainAlerts.hidden && els.rainAlertsToggle.checked) parts.push('rain alerts');
  els.pushSummary.replaceChildren(...parts.flatMap((part, index) => {
    const span = document.createElement('span');
    span.className = 'summary-part';
    span.textContent = part;
    return index === 0 ? [span] : [' · ', span];
  }));
}

function showUnsubscribed() {
  els.status.hidden = false;
  els.status.textContent = 'Off — turn them on for a morning forecast and sun updates.';
  setButton('Enable notifications', subscribe);
  els.pushSettings.hidden = true;
  els.pushSettings.open = false;
  els.testButton.hidden = true;
  els.rainAlerts.hidden = true;
  els.morningTime.hidden = true;
  els.weekendMorning.hidden = true;
}

function renderRainAlerts(enabled) {
  els.rainAlertsToggle.checked = enabled;
  els.rainAlertsToggle.onchange = () => saveRainAlerts(els.rainAlertsToggle.checked);
  els.rainAlerts.hidden = false;
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

    const {
      is_admin: isAdmin,
      rain_alerts: rainAlerts,
      morning_push_at: morningPushAt,
      morning_push_options: morningPushOptions,
      weekend_morning_push: weekendMorningPush,
    } = await res.json();

    renderRainAlerts(rainAlerts);
    renderMorningTime(morningPushAt, morningPushOptions);
    renderWeekendMorning(weekendMorningPush);
    updatePushSummary();

    if (!isAdmin) return;
    els.testButton.hidden = false;
    els.testButton.disabled = false;
    els.testButton.textContent = 'Send a test notification';
    els.testButton.onclick = sendTestPush;
  } catch (err) {
    console.warn('Could not check subscription options:', err);
  }
}

function renderMorningTime(selected, options) {
  els.morningTimeSelect.replaceChildren(
    ...options.map((value) => new Option(value, value, false, value === selected))
  );
  els.morningTimeSelect.onchange = () => saveMorningTime(els.morningTimeSelect.value, selected);
  els.morningTime.hidden = false;
}

async function saveMorningTime(time, previous) {
  els.morningTimeSelect.disabled = true;
  try {
    const subscription = await registration.pushManager.getSubscription();
    const res = await fetch('/api/morning-time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint, time }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
    els.morningTimeSelect.onchange = () => saveMorningTime(els.morningTimeSelect.value, time);
  } catch (err) {
    els.morningTimeSelect.value = previous;
    els.areaNote.textContent = `Could not save that: ${err.message}`;
  } finally {
    els.morningTimeSelect.disabled = false;
    updatePushSummary();
  }
}

function renderWeekendMorning(enabled) {
  els.weekendMorningToggle.checked = enabled;
  els.weekendMorningToggle.onchange = () => saveWeekendMorning(els.weekendMorningToggle.checked);
  els.weekendMorning.hidden = false;
}

async function saveWeekendMorning(enabled) {
  els.weekendMorningToggle.disabled = true;
  try {
    const subscription = await registration.pushManager.getSubscription();
    const res = await fetch('/api/weekend-morning', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint, enabled }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
  } catch (err) {
    els.weekendMorningToggle.checked = !enabled;
    els.areaNote.textContent = `Could not save that: ${err.message}`;
  } finally {
    els.weekendMorningToggle.disabled = false;
    updatePushSummary();
  }
}

async function saveRainAlerts(enabled) {
  els.rainAlertsToggle.disabled = true;
  try {
    const subscription = await registration.pushManager.getSubscription();
    const res = await fetch('/api/rain-alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint, enabled }),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);
  } catch (err) {
    els.rainAlertsToggle.checked = !enabled;
    els.areaNote.textContent = `Could not save that: ${err.message}`;
  } finally {
    els.rainAlertsToggle.disabled = false;
    updatePushSummary();
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
    els.pushToggle.checked = true;
    return;
  }
  els.pushToggle.disabled = true;
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
    els.pushToggle.checked = true;
    els.status.textContent = `Could not turn them off: ${err.message}`;
    els.status.hidden = false;
  } finally {
    els.pushToggle.disabled = false;
  }
}

const GLITTER_KEY = 'weather-assistant-glitter';

function setGlitter(enabled) {
  document.body.classList.toggle('glitter-mode', enabled);
  els.glitterToggle.setAttribute('aria-pressed', String(enabled));
}

try {
  setGlitter(localStorage.getItem(GLITTER_KEY) === 'on');
} catch (err) {
}

els.glitterToggle.onclick = () => {
  const enabled = !document.body.classList.contains('glitter-mode');
  setGlitter(enabled);
  try {
    localStorage.setItem(GLITTER_KEY, enabled ? 'on' : 'off');
  } catch (err) {
  }
};

// "What's new" dot for people to see the changelog updates
const SEEN_CHANGES_KEY = 'weather-assistant-seen-changes';
const RECENT_CHANGES_SHOWN = 5;
let changelog = [];

function newestChange() {
  return changelog.length ? changelog[0].date : null;
}

function showNewsDot(show) {
  els.aboutToggle.classList.toggle('has-news', show);
  els.aboutToggle.setAttribute('aria-label', show ? 'About this app, with new changes' : 'About this app');
}

function changeList(entries) {
  const list = document.createElement('ul');
  list.className = 'changelog';
  for (const { date, text } of entries) {
    const item = document.createElement('li');
    const when = document.createElement('time');
    when.dateTime = date;
    when.textContent = shortDate(date);
    item.append(when, ` ${text}`);
    list.append(item);
  }
  return list;
}

async function loadChangelog() {
  try {
    const res = await fetch('/changelog.json');
    if (!res.ok) return;
    changelog = await res.json();
  } catch (err) {
    return;
  }
  if (!changelog.length) return;

  const parts = [changeList(changelog.slice(0, RECENT_CHANGES_SHOWN))];
  if (changelog.length > RECENT_CHANGES_SHOWN) {
    const older = document.createElement('details');
    older.className = 'changelog-older';
    const summary = document.createElement('summary');
    summary.textContent = 'Older changes';
    older.append(summary, changeList(changelog.slice(RECENT_CHANGES_SHOWN)));
    parts.push(older);
  }
  els.changelogEntries.replaceChildren(...parts);
  els.changelog.hidden = false;

  try {
    const seen = localStorage.getItem(SEEN_CHANGES_KEY);
    showNewsDot(!els.about.hidden ? false : seen === null || seen < newestChange());
    if (!els.about.hidden) localStorage.setItem(SEEN_CHANGES_KEY, newestChange());
  } catch (err) {
  }
}

els.aboutToggle.onclick = () => {
  const open = els.about.hidden;
  els.about.hidden = !open;
  els.aboutToggle.setAttribute('aria-expanded', String(open));
  if (open && newestChange()) {
    showNewsDot(false);
    try {
      localStorage.setItem(SEEN_CHANGES_KEY, newestChange());
    } catch (err) {
    }
  }
};

showInAppBanner();
loadChangelog();

setUpAreas()
  .catch(() => { /* if can't load areas we don't crash the page*/ })
  .then(loadForecast)
  .then(loadNearTermForecast)
  .then(() => {
    setUpPush();
    scheduleNearTermForecastPoll();
  });
