const PUSH_ENABLED = true;

const els = {
  place: document.getElementById('place'),
  forecast: document.getElementById('forecast'),
  status: document.getElementById('push-status'),
  button: document.getElementById('push-button'),
  iosHelp: document.getElementById('ios-help'),
  testButton: document.getElementById('test-button'),
};

let registration = null;

async function loadForecast() {
  try {
    const res = await fetch('/api/forecast');
    if (!res.ok) throw new Error(`server said ${res.status}`);
    const data = await res.json();

    els.place.textContent = `${data.area} · sunrise ${data.sunrise}, sunset ${data.sunset}`;
    const pre = document.createElement('pre');
    pre.textContent = data.text.trim();
    els.forecast.replaceChildren(pre);
  } catch (err) {
    els.place.textContent = '';
    els.forecast.textContent = `Could not load the forecast (${err.message}).`;
  } finally {
    els.forecast.setAttribute('aria-busy', 'false');
  }
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
  showTestButton();
}

function showUnsubscribed() {
  els.status.textContent = 'Off — turn them on for a morning forecast and sun updates.';
  setButton('Enable notifications', subscribe);
  els.testButton.hidden = true;
}

async function showTestButton() {
  try {
    const subscription = await registration.pushManager.getSubscription();
    if (!subscription) return;

    const res = await fetch('/api/me', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    if (!res.ok) return;

    const { is_admin: isAdmin } = await res.json();
    if (!isAdmin) return;

    els.testButton.hidden = false;
    els.testButton.disabled = false;
    els.testButton.textContent = 'Send a test notification';
    els.testButton.onclick = sendTestPush;
  } catch (err) {
    console.warn('Could not check test-device status:', err);
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
      body: JSON.stringify(subscription),
    });
    if (!res.ok) throw new Error(`server said ${res.status}`);

    showSubscribed();
  } catch (err) {
    els.status.textContent = `Could not enable notifications: ${err.message}`;
    els.button.disabled = false;
  }
}

async function unsubscribe() {
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

loadForecast();
setUpPush();
