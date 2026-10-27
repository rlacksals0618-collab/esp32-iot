(() => {
  const POLL_MS = 3000;
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // localStorage는 막혀 있을 수 있으므로(시크릿 창 등) 항상 try/catch
  const storage = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* 무시 */ } },
    del: (k) => { try { localStorage.removeItem(k); } catch { /* 무시 */ } },
  };

  const state = {
    apiBase: (storage.get('apiBase') || window.APP_CONFIG?.API_BASE_URL || '').replace(/\/+$/, ''),
    session: JSON.parse(storage.get('session') || 'null'), // { access_token, refresh_token, user }
    devices: [],
    selectedId: storage.get('selectedDevice'),
    readings: [],
    readingsFor: null,
    revealedKey: null, // { deviceId, key } 등록·재발급 직후에만 보여 줌
    ledBusy: false,
    confirmDelete: false,
    pollTimer: null,
  };

  // ───────────────────────── API
  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  const formatDetail = (detail) => {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => `${(d.loc || []).slice(-1)[0] ?? ''}: ${d.msg}`).join(', ');
    return JSON.stringify(detail);
  };

  let refreshing = null;
  async function refreshSession() {
    // 여러 요청이 동시에 401을 받아도 refresh는 한 번만 한다
    refreshing ??= (async () => {
      try {
        const data = await api('/api/auth/refresh', { method: 'POST', body: { refresh_token: state.session.refresh_token }, auth: false });
        saveSession(data);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => { refreshing = null; }, 0);
      }
    })();
    return refreshing;
  }

  async function api(path, { method = 'GET', body, auth = true, retry = true } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && state.session) headers.Authorization = `Bearer ${state.session.access_token}`;
    let res;
    try {
      res = await fetch(state.apiBase + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    } catch {
      throw new ApiError(0, '서버에 연결할 수 없습니다. 서버 주소와 실행 여부를 확인하세요.');
    }
    if (res.status === 401 && auth && retry && state.session?.refresh_token) {
      if (await refreshSession()) return api(path, { method, body, auth, retry: false });
      logout('로그인이 만료되었습니다. 다시 로그인하세요.');
      throw new ApiError(401, '로그인이 만료되었습니다.');
    }
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, formatDetail(data?.detail) || `요청 실패 (${res.status})`);
    return data;
  }

  // ───────────────────────── 공통 UI
  let toastTimer;
  function toast(msg, bad = false) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.toggle('bad', bad);
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
  }

  function ago(iso) {
    if (!iso) return '보고 없음';
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 60) return `${s}초 전`;
    if (s < 3600) return `${Math.floor(s / 60)}분 전`;
    if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
    return new Date(iso).toLocaleString('ko-KR');
  }

  // ───────────────────────── 로그인 / 회원가입
  let authMode = 'login';

  function showAuth() {
    stopPolling();
    $('#app-view').hidden = true;
    $('#auth-view').hidden = false;
  }

  function setAuthMode(mode) {
    authMode = mode;
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t.dataset.mode === mode));
    $('#auth-submit').textContent = mode === 'login' ? '로그인' : '가입하고 시작하기';
    $('#pw-hint').hidden = mode === 'login';
    $('#password').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
    $('#auth-error').textContent = '';
  }

  function saveSession(data) {
    state.session = { access_token: data.access_token, refresh_token: data.refresh_token, user: data.user };
    storage.set('session', JSON.stringify(state.session));
  }

  function logout(message) {
    state.session = null;
    state.devices = [];
    state.revealedKey = null;
    storage.del('session');
    showAuth();
    if (message) $('#auth-error').textContent = message;
  }

  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => setAuthMode(t.dataset.mode)));

  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = $('#email').value.trim();
    const password = $('#password').value;
    const err = $('#auth-error');
    if (!email || !password) { err.textContent = '이메일과 비밀번호를 입력하세요.'; return; }
    if (authMode === 'signup' && password.length < 8) { err.textContent = '비밀번호는 8자 이상이어야 합니다.'; return; }

    const btn = $('#auth-submit');
    btn.disabled = true;
    err.textContent = '';
    try {
      const path = authMode === 'login' ? '/api/auth/login' : '/api/auth/signup';
      saveSession(await api(path, { method: 'POST', body: { email, password }, auth: false }));
      $('#password').value = '';
      showApp();
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      btn.disabled = false;
    }
  });

  // ───────────────────────── 대시보드
  function showApp() {
    $('#auth-view').hidden = true;
    $('#app-view').hidden = false;
    $('#user-email').textContent = state.session?.user?.email || '';
    renderPanel();
    checkServer();
    tick();
    startPolling();
  }

  $('#logout').addEventListener('click', () => logout());

  async function checkServer() {
    const el = $('#server-status');
    const label = el.querySelector('span');
    label.textContent = '연결 중…';
    // Render 무료 플랜은 잠들어 있다가 깨어나는 데 최대 1분쯤 걸린다
    const slow = setTimeout(() => { label.textContent = '서버 깨우는 중 (최대 1분)'; }, 3000);
    try {
      await api('/health', { auth: false });
      el.className = 'server-status up';
      label.textContent = '서버 연결됨';
    } catch {
      el.className = 'server-status down';
      label.textContent = '서버 연결 안 됨';
    } finally {
      clearTimeout(slow);
    }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => { if (!document.hidden) tick(); }, POLL_MS);
  }
  function stopPolling() {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  async function tick() {
    try {
      state.devices = await api('/api/devices');
      if (!state.devices.some((d) => d.id === state.selectedId)) state.selectedId = state.devices[0]?.id || null;
      await loadReadings();
      renderDeviceList();
      renderPanel();
    } catch (ex) {
      if (ex.status !== 401) $('#server-status').className = 'server-status down';
    }
  }

  async function loadReadings() {
    const id = state.selectedId;
    if (!id) { state.readings = []; return; }
    if (state.readingsFor !== id) {
      state.readings = await api(`/api/devices/${id}/readings?limit=120`);
      state.readingsFor = id;
      return;
    }
    // 마지막으로 받은 값 이후만 받아서 이어 붙인다
    const last = state.readings[state.readings.length - 1];
    const query = last ? `&since=${encodeURIComponent(last.created_at)}` : '';
    const fresh = await api(`/api/devices/${id}/readings?limit=120${query}`);
    state.readings = state.readings.concat(fresh).slice(-120);
  }

  function selectDevice(id) {
    state.selectedId = id;
    state.confirmDelete = false;
    storage.set('selectedDevice', id);
    renderDeviceList();
    renderPanel();
    loadReadings().then(renderPanel).catch(() => {});
  }

  function renderDeviceList() {
    $('#device-list').innerHTML = state.devices.map((d) => `
      <li><button class="device-item ${d.id === state.selectedId ? 'on' : ''}" data-id="${esc(d.id)}">
        <span class="dot ${d.online ? 'online' : ''}" title="${d.online ? '온라인' : '오프라인'}"></span>
        <span class="name">${esc(d.name)}</span>
        <span class="led-mini ${d.led_reported ? 'lit' : ''}" title="보드 LED ${d.led_reported ? '켜짐' : '꺼짐'}"></span>
      </button></li>`).join('') || '<li class="muted small">아직 등록한 기기가 없어요.</li>';
  }

  $('#device-list').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-id]');
    if (btn) selectDevice(btn.dataset.id);
  });

  $('#add-device').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#device-name');
    const name = input.value.trim();
    if (!name) return;
    try {
      const device = await api('/api/devices', { method: 'POST', body: { name } });
      input.value = '';
      state.revealedKey = { deviceId: device.id, key: device.device_key };
      state.devices.push(device);
      selectDevice(device.id);
      toast('기기를 등록했어요. 아래 키를 펌웨어에 넣으세요.');
    } catch (ex) {
      toast(ex.message, true);
    }
  });

  function renderPanel() {
    const panel = $('#panel');
    const d = state.devices.find((x) => x.id === state.selectedId);
    if (!d) {
      panel.innerHTML = `
        <div class="card empty">
          <div class="big">🔌</div>
          <h2>기기를 등록하세요</h2>
          <p class="muted">왼쪽에서 이름을 입력하고 등록하면 보드에 넣을 키가 나옵니다.</p>
        </div>`;
      return;
    }

    const r = d.latest;
    const pending = d.led_reported !== null && d.led_reported !== d.led_on;
    const ledLine = d.led_reported === null
      ? '<span class="muted">보드가 아직 LED 상태를 보고하지 않았어요</span>'
      : pending
        ? `<span class="pending">보드에 반영 대기 중… (요청: ${d.led_on ? '켜기' : '끄기'})</span>`
        : `<span>보드 LED ${d.led_reported ? '켜짐' : '꺼짐'} ✓</span>`;
    const key = state.revealedKey?.deviceId === d.id ? state.revealedKey.key : null;

    panel.innerHTML = `
      <div class="card panel-head">
        <div>
          <h1>${esc(d.name)}</h1>
          <p class="muted small">마지막 보고: ${ago(d.last_seen_at)}</p>
        </div>
        <span class="badge ${d.online ? 'online' : ''}">● ${d.online ? '온라인' : '오프라인'}</span>
      </div>

      ${key ? `
        <div class="card key-box">
          <strong>🔑 기기 키 (지금만 보여요)</strong>
          <p class="small">펌웨어의 <code>secrets.h</code>에 아래 두 줄을 넣으세요. 이 화면을 벗어나면 다시 볼 수 없고, 잃어버리면 "키 재발급"을 하면 됩니다.</p>
          <pre id="key-snippet">#define API_BASE_URL "${esc(state.apiBase)}"
#define DEVICE_KEY   "${esc(key)}"</pre>
          <div class="actions">
            <button class="btn sm" id="copy-key">복사</button>
            <button class="btn ghost sm" id="hide-key">다 넣었어요</button>
          </div>
        </div>` : ''}

      <div class="grid-top">
        <div class="card led-card">
          <h3>LED 제어</h3>
          <button class="led-button ${d.led_on ? 'lit' : ''}" id="led-toggle" ${state.ledBusy ? 'disabled' : ''} aria-pressed="${d.led_on}">
            ${d.led_on ? 'ON' : 'OFF'}
          </button>
          <div class="led-state">${ledLine}</div>
          ${!d.online ? '<p class="muted small">보드가 오프라인이에요. 켜지면 이 상태가 적용됩니다.</p>' : ''}
        </div>
        <div class="card">
          <h3 style="margin-bottom:12px">현재 센서값</h3>
          <div class="metrics">
            ${metric('온도', r?.temperature?.toFixed(1), '°C', 'ESP32 내부 온도')}
            ${metric('밝기', r?.light, '', 'A0 아날로그 (0~4095)')}
            ${metric('WiFi', r?.rssi, 'dBm', signalLabel(r?.rssi))}
          </div>
          <p class="muted small" style="margin-top:10px">${r ? `측정: ${ago(r.created_at)}` : '아직 받은 센서값이 없어요. 보드를 켜 보세요.'}</p>
        </div>
      </div>

      <div class="charts">
        <div class="card chart-card"><h3>온도 <span class="muted small">°C · 최근 ${state.readings.length}개</span></h3><canvas id="chart-temp"></canvas></div>
        <div class="card chart-card"><h3>밝기 <span class="muted small">A0 · 최근 ${state.readings.length}개</span></h3><canvas id="chart-light"></canvas></div>
      </div>

      <div class="card actions">
        <button class="btn sm" id="regen-key">키 재발급</button>
        <button class="btn sm danger ${state.confirmDelete ? 'confirm' : ''}" id="delete-device">${state.confirmDelete ? '정말 삭제할까요? (센서 기록도 삭제)' : '기기 삭제'}</button>
      </div>`;

    drawChart($('#chart-temp'), state.readings.map((x) => x.temperature), '--chart-1');
    drawChart($('#chart-light'), state.readings.map((x) => x.light), '--chart-2');

    $('#led-toggle').addEventListener('click', () => toggleLed(d));
    $('#regen-key').addEventListener('click', () => regenerateKey(d));
    $('#delete-device').addEventListener('click', () => deleteDevice(d));
    $('#copy-key')?.addEventListener('click', copyKey);
    $('#hide-key')?.addEventListener('click', () => { state.revealedKey = null; renderPanel(); });
  }

  const metric = (label, value, unit, sub) => `
    <div class="metric">
      <div class="label">${label}</div>
      <div class="value">${value ?? '–'}${value != null && unit ? `<span class="unit">${unit}</span>` : ''}</div>
      <div class="sub">${esc(sub)}</div>
    </div>`;

  function signalLabel(rssi) {
    if (rssi == null) return '신호 세기';
    if (rssi >= -60) return '신호 좋음';
    if (rssi >= -75) return '신호 보통';
    return '신호 약함';
  }

  async function toggleLed(d) {
    state.ledBusy = true;
    renderPanel();
    try {
      const updated = await api(`/api/devices/${d.id}/led`, { method: 'PUT', body: { on: !d.led_on } });
      Object.assign(d, updated);
      toast(updated.led_on ? 'LED 켜기 요청을 보냈어요' : 'LED 끄기 요청을 보냈어요');
    } catch (ex) {
      toast(ex.message, true);
    } finally {
      state.ledBusy = false;
      renderDeviceList();
      renderPanel();
    }
  }

  async function regenerateKey(d) {
    try {
      const res = await api(`/api/devices/${d.id}/key`, { method: 'POST' });
      state.revealedKey = { deviceId: d.id, key: res.device_key };
      toast('새 키를 발급했어요. 이전 키는 더 이상 쓸 수 없어요.');
      renderPanel();
    } catch (ex) {
      toast(ex.message, true);
    }
  }

  let deleteTimer;
  async function deleteDevice(d) {
    if (!state.confirmDelete) {
      state.confirmDelete = true;
      renderPanel();
      clearTimeout(deleteTimer);
      deleteTimer = setTimeout(() => { state.confirmDelete = false; renderPanel(); }, 4000);
      return;
    }
    clearTimeout(deleteTimer);
    state.confirmDelete = false;
    try {
      await api(`/api/devices/${d.id}`, { method: 'DELETE' });
      state.devices = state.devices.filter((x) => x.id !== d.id);
      state.selectedId = state.devices[0]?.id || null;
      state.readingsFor = null;
      toast('기기를 삭제했어요');
      renderDeviceList();
      await loadReadings().catch(() => {});
      renderPanel();
    } catch (ex) {
      toast(ex.message, true);
    }
  }

  async function copyKey() {
    const text = $('#key-snippet').textContent;
    try {
      await navigator.clipboard.writeText(text);
      toast('복사했어요');
    } catch {
      const range = document.createRange();
      range.selectNodeContents($('#key-snippet'));
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      toast('선택했어요. Ctrl+C로 복사하세요.');
    }
  }

  // ───────────────────────── 그래프 (canvas)
  function drawChart(canvas, raw, colorVar) {
    const css = getComputedStyle(document.documentElement);
    const color = css.getPropertyValue(colorVar).trim();
    const muted = css.getPropertyValue('--muted').trim();
    const grid = css.getPropertyValue('--grid').trim();
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.font = '11px ui-monospace, Consolas, monospace';

    const values = raw.filter((v) => v != null);
    if (values.length < 2) {
      ctx.fillStyle = muted;
      ctx.textAlign = 'center';
      ctx.fillText('데이터를 모으는 중…', w / 2, h / 2);
      return;
    }

    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.1;
    min -= pad; max += pad;

    const left = 44, right = 8, top = 8, bottom = 8;
    const x = (i) => left + (i / (values.length - 1)) * (w - left - right);
    const y = (v) => top + (1 - (v - min) / (max - min)) * (h - top - bottom);

    // 눈금 3개
    ctx.strokeStyle = grid;
    ctx.fillStyle = muted;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let k = 0; k <= 2; k++) {
      const v = min + ((max - min) * k) / 2;
      ctx.beginPath();
      ctx.moveTo(left, y(v));
      ctx.lineTo(w - right, y(v));
      ctx.stroke();
      ctx.fillText(Math.abs(max - min) < 10 ? v.toFixed(1) : Math.round(v), left - 6, y(v));
    }

    // 면 + 선
    ctx.beginPath();
    values.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.lineTo(x(values.length - 1), h - bottom);
    ctx.lineTo(x(0), h - bottom);
    ctx.closePath();
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;

    // 마지막 값 강조
    const lx = x(values.length - 1);
    const ly = y(values[values.length - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  window.addEventListener('resize', () => { if (state.session && !$('#app-view').hidden) renderPanel(); });

  // ───────────────────────── 서버 주소 변경 (브라우저마다 저장)
  $('#change-api').addEventListener('click', () => {
    const footer = $('.footer');
    if (footer.querySelector('form')) return;
    const form = document.createElement('form');
    form.className = 'row';
    form.innerHTML = `
      <input id="api-input" value="${esc(state.apiBase)}" placeholder="https://xxx.onrender.com" style="min-width:260px">
      <button class="btn sm primary" type="submit">저장</button>
      <button class="btn sm" type="button" id="api-reset">기본값</button>`;
    footer.appendChild(form);
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      setApiBase($('#api-input').value);
      form.remove();
    });
    form.querySelector('#api-reset').addEventListener('click', () => {
      storage.del('apiBase');
      setApiBase(window.APP_CONFIG?.API_BASE_URL || '', false);
      form.remove();
    });
  });

  function setApiBase(url, remember = true) {
    state.apiBase = url.trim().replace(/\/+$/, '');
    if (remember) storage.set('apiBase', state.apiBase);
    $('#api-base').textContent = state.apiBase;
    // 서버가 바뀌면 이전 서버의 로그인은 쓸 수 없다
    logout(`서버 주소를 ${state.apiBase}(으)로 바꿨어요. 로그인하세요.`);
  }

  // ───────────────────────── 시작
  $('#api-base').textContent = state.apiBase || '(설정 안 됨)';
  if (state.session) showApp();
  else showAuth();
})();
