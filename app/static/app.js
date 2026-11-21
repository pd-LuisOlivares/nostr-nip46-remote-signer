'use strict';
/*
 * Interfaz local del operador. Sin frameworks. Reglas de seguridad:
 *  - TODO el contenido dinamico se inserta con textContent / createElement (nunca como HTML).
 *  - Ningun secreto ni token se guarda en el navegador: el JWT va en una cookie HttpOnly que el JS no puede leer;
 *    el token CSRF y la URI bunker:// viven solo en variables en memoria y se borran al cerrar sesion o al ocultarlas.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 1500;
  const STATE_LABEL = { idle: 'Detenido', starting: 'Iniciando', ready: 'Listo', stopping: 'Deteniendo', stopped: 'Detenido', failed: 'Fallido' };
  const KIND_LABEL = { connect: 'Conexión de un cliente', sign_event: 'Firma del evento de inicio de sesión' };
  const STATUS_LABEL = { pending: 'pendiente', approved: 'aprobada', denied: 'rechazada', expired: 'caducada', cancelled: 'cancelada' };
  const ERRORS = {
    400: 'La clave no es válida.', 401: 'La sesión no es válida o caducó. Inicie sesión de nuevo.', 403: 'Solicitud no permitida.',
    404: 'No encontrado.', 409: 'La operación no es posible en el estado actual.', 422: 'Datos no válidos.',
    429: 'Demasiados intentos. Espere un minuto.', 502: 'El firmante no llegó a estar listo (revise el relay).',
  };

  let csrf = null;
  let pollTimer = null;
  let sessionLeft = 0;
  let sessionTick = null;
  let bunkerTimer = null;
  let lastState = null;
  const cards = new Map(); // id de solicitud -> { sig, node, expires }

  class ApiError extends Error {
    constructor(status) { super(`HTTP ${status}`); this.status = status; }
  }

  function el(tag, opts = {}, ...children) {
    const node = document.createElement(tag);
    if (opts.cls) node.className = opts.cls;
    if (opts.text !== undefined) node.textContent = String(opts.text);
    if (opts.id) node.id = opts.id;
    if (opts.type) node.type = opts.type;
    if (opts.on) for (const [k, v] of Object.entries(opts.on)) node.addEventListener(k, v);
    for (const child of children) if (child) node.append(child);
    return node;
  }

  function show(id, visible) { $(id).hidden = !visible; }

  function banner(kind, text) {
    const b = $('banner');
    b.className = `banner ${kind}`;
    b.textContent = text;
    b.hidden = false;
  }
  function clearBanner() { $('banner').hidden = true; }

  async function api(method, path, body, quiet = false) {
    const headers = {};
    if (csrf) headers['X-CSRF-Token'] = csrf;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const resp = await fetch(path, {
      method, headers, credentials: 'same-origin', cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    if (resp.status !== 204) { try { data = await resp.json(); } catch (_e) { data = null; } }
    if (!resp.ok) {
      if (resp.status === 401 && !quiet && path !== '/api/auth/login') sessionEnded('La sesión caducó o fue cerrada. Inicie sesión de nuevo.');
      throw new ApiError(resp.status);
    }
    return data;
  }

  function errorText(err) { return ERRORS[err.status] || 'Error inesperado.'; }

  // ------------------------------------------------------------------------------------------ sesión
  function wipeSecrets() {
    csrf = null;
    $('bunker-uri').value = '';
    show('bunker-box', false);
    $('identity-secret').value = '';
    $('login-code').value = '';
    if (bunkerTimer) { clearTimeout(bunkerTimer); bunkerTimer = null; }
  }

  function showLogin() {
    stopPolling();
    stopSessionClock();
    show('view-app', false);
    show('session-bar', false);
    show('view-login', true);
    cards.clear();
    $('pending-list').replaceChildren();
    lastState = null;
  }

  function sessionEnded(message) {
    wipeSecrets();
    showLogin();
    banner('info', message);
  }

  function showApp(info) {
    csrf = info.csrf_token;
    sessionLeft = info.expires_in_s;
    show('view-login', false);
    show('view-app', true);
    show('session-bar', true);
    startSessionClock();
    startPolling();
  }

  function startSessionClock() {
    stopSessionClock();
    const paint = () => {
      const m = Math.floor(sessionLeft / 60), s = sessionLeft % 60;
      $('session-timer').textContent = `Sesión: ${m}:${String(s).padStart(2, '0')}`;
    };
    paint();
    sessionTick = setInterval(() => { sessionLeft = Math.max(0, sessionLeft - 1); paint(); }, 1000);
  }
  function stopSessionClock() { if (sessionTick) { clearInterval(sessionTick); sessionTick = null; } }

  async function onLogin(event) {
    event.preventDefault();
    const input = $('login-code');
    const code = input.value;
    input.value = '';
    show('login-error', false);
    try {
      const info = await api('POST', '/api/auth/login', { code });
      delete info.token; // el JWT viaja en la cookie HttpOnly; esta pagina no lo conserva
      clearBanner();
      showApp(info);
    } catch (err) {
      $('login-error').textContent = errorText(err);
      show('login-error', true);
    }
  }

  async function onLogout() {
    try { await api('POST', '/api/auth/logout'); } catch (_e) { /* la sesion ya no era valida */ }
    wipeSecrets();
    showLogin();
    banner('ok', 'Sesión cerrada.');
  }

  // ------------------------------------------------------------------------------------------ sondeo
  function startPolling() { stopPolling(); refresh(); pollTimer = setInterval(refresh, POLL_MS); }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  async function refresh() {
    try {
      const [status, requests, connections, audit] = await Promise.all([
        api('GET', '/api/status'), api('GET', '/api/requests?scope=all'), api('GET', '/api/connections'), api('GET', '/api/audit?limit=40'),
      ]);
      renderStatus(status);
      renderRequests(requests);
      renderConnections(connections);
      renderAudit(audit.entries);
    } catch (_e) { /* 401 ya gestionado; otros fallos puntuales se reintentan en el siguiente ciclo */ }
  }

  // ------------------------------------------------------------------------------------------ render
  function renderStatus(s) {
    $('identity-pub').textContent = s.identity.public_key || '—';
    const sg = s.signer;
    const badge = $('signer-state');
    badge.textContent = STATE_LABEL[sg.state] || sg.state;
    badge.className = `badge ${sg.state}`;
    $('signer-relay').textContent = sg.relay_host || '—';
    $('signer-signatures').textContent = `${sg.signatures} de ${sg.max_signatures} permitidas`;
    $('signer-end').textContent = sg.end_reason ? sg.end_reason.replaceAll('_', ' ') : '—';
    const running = ['starting', 'ready', 'stopping'].includes(sg.state);
    $('identity-create').disabled = running;
    $('identity-import').disabled = running;
    $('signer-start').disabled = running || !s.identity.present;
    $('signer-stop').disabled = !running;
    $('bunker-issue').disabled = sg.state !== 'ready';
    if (lastState === 'ready' && sg.state !== 'ready') {
      $('bunker-uri').value = '';
      show('bunker-box', false);
      banner('info', `El firmante terminó: ${sg.end_reason ? sg.end_reason.replaceAll('_', ' ') : 'detenido'}.`);
    }
    lastState = sg.state;
  }

  function renderConnections(list) {
    const ul = $('connections-list');
    ul.replaceChildren(...list.map((c) => el('li', {}, el('span', { cls: 'mono', text: c.client }), el('span', { text: c.state }),
      c.state === 'active' ? el('span', { cls: 'muted', text: `expira en ${c.expires_in_s} s` }) : null)));
    $('connections-empty').hidden = list.length > 0;
  }

  function summaryTable(summary) {
    const dl = el('dl', { cls: 'kv' });
    for (const [k, v] of Object.entries(summary)) {
      dl.append(el('dt', { text: k }), el('dd', { cls: 'mono wrap', text: typeof v === 'object' ? JSON.stringify(v) : v }));
    }
    return dl;
  }

  function buildCard(req) {
    const allOk = req.checks.every((c) => c.ok);
    const countdown = el('span', { cls: 'muted' });
    const approve = el('button', { type: 'button', cls: 'btn ok', text: 'Aprobar', on: { click: () => decide(req.id, 'approve') } });
    const deny = el('button', { type: 'button', cls: 'btn danger', text: 'Rechazar', on: { click: () => decide(req.id, 'deny') } });
    approve.id = `approve-${req.id}`;
    deny.id = `deny-${req.id}`;
    approve.disabled = !allOk; // nunca se ofrece aprobar una firma que incumple la politica
    const node = el('article', { cls: `req kind-${req.kind}` },
      el('header', {}, el('span', { text: KIND_LABEL[req.kind] || req.kind }), countdown),
      el('p', { cls: 'muted', text: `Cliente ${req.client}` }),
      summaryTable(req.summary));
    if (req.checks.length) {
      node.append(el('h3', { text: 'Comprobaciones de la política' }),
        el('ul', { cls: 'checks' }, ...req.checks.map((c) => el('li', { cls: c.ok ? 'pass' : 'fail', text: `${c.ok ? '✓' : '✗'} ${c.name}${c.ok || !c.detail ? '' : ` (${c.detail})`}` }))));
    }
    if (!allOk) node.append(el('p', { cls: 'error', text: 'Alguna comprobación falló: esta firma no puede aprobarse.' }));
    node.append(el('div', { cls: 'row' }, approve, deny));
    node.dataset.requestId = req.id;
    return { node, countdown };
  }

  function renderRequests(all) {
    const pending = all.filter((r) => r.status === 'pending');
    const recent = all.filter((r) => r.status !== 'pending').reverse();
    const holder = $('pending-list');
    const keep = new Set(pending.map((r) => r.id));
    for (const [id, entry] of cards) if (!keep.has(id)) { entry.node.remove(); cards.delete(id); }
    for (const req of pending) {
      const sig = JSON.stringify([req.kind, req.client, req.summary, req.checks]);
      let entry = cards.get(req.id);
      if (!entry || entry.sig !== sig) {
        const built = buildCard(req);
        if (entry) entry.node.replaceWith(built.node); else holder.append(built.node);
        entry = { sig, node: built.node, countdown: built.countdown };
        cards.set(req.id, entry);
      }
      entry.countdown.textContent = `caduca en ${req.expires_in_s} s`;
    }
    $('pending-count').textContent = String(pending.length);
    $('pending-empty').hidden = pending.length > 0;
    const ul = $('recent-list');
    ul.replaceChildren(...recent.slice(0, 15).map((r) => el('li', {}, el('span', { text: STATUS_LABEL[r.status] || r.status }),
      el('span', { text: KIND_LABEL[r.kind] || r.kind }), el('span', { cls: 'muted', text: r.reason || '' }))));
    $('recent-empty').hidden = recent.length > 0;
  }

  function renderAudit(entries) {
    const body = $('audit-body');
    body.replaceChildren(...entries.slice().reverse().map((e) => {
      const { seq, ts, event, ...rest } = e;
      const detail = Object.entries(rest).map(([k, v]) => `${k}=${v}`).join(' · ');
      return el('tr', {}, el('td', { text: seq }), el('td', { text: new Date(ts * 1000).toLocaleTimeString() }), el('td', { text: event }), el('td', { cls: 'mono wrap', text: detail }));
    }));
  }

  // ------------------------------------------------------------------------------------------ acciones
  async function guarded(action, okMessage) {
    try {
      const result = await action();
      if (okMessage) banner('ok', okMessage);
      else clearBanner();
      await refresh();
      return result;
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) banner('error', errorText(err));
      return null;
    }
  }

  const decide = (id, verdict) => guarded(() => api('POST', `/api/requests/${encodeURIComponent(id)}/${verdict}`),
    verdict === 'approve' ? 'Solicitud aprobada.' : 'Solicitud rechazada.');

  async function onIssueBunker() {
    const data = await guarded(() => api('POST', '/api/connections'), 'URI emitida. Cópiela ahora: no se mostrará de nuevo.');
    if (!data) return;
    $('bunker-uri').value = data.uri;
    $('bunker-note').textContent = `Válida ${Math.round(data.expires_in_s / 60)} min · un solo uso`;
    show('bunker-box', true);
    if (bunkerTimer) clearTimeout(bunkerTimer);
    bunkerTimer = setTimeout(hideBunker, 120000);
  }
  function hideBunker() { $('bunker-uri').value = ''; show('bunker-box', false); }
  async function onCopyBunker() {
    try { await navigator.clipboard.writeText($('bunker-uri').value); banner('ok', 'URI copiada al portapapeles.'); }
    catch (_e) { $('bunker-uri').select(); banner('info', 'Seleccionada: copie con Ctrl+C.'); }
  }

  async function onImport(event) {
    event.preventDefault();
    const field = $('identity-secret');
    const secret = field.value;
    field.value = '';
    if (!secret) return;
    await guarded(() => api('PUT', '/api/identity', { secret }), 'Identidad importada.');
  }

  function bind() {
    $('login-form').addEventListener('submit', onLogin);
    $('logout-btn').addEventListener('click', onLogout);
    $('identity-create').addEventListener('click', () => guarded(() => api('POST', '/api/identity'), 'Identidad temporal creada.'));
    $('identity-import-form').addEventListener('submit', onImport);
    $('signer-start').addEventListener('click', () => guarded(() => api('POST', '/api/signer/start'), 'Firmante iniciado.'));
    $('signer-stop').addEventListener('click', () => guarded(() => api('POST', '/api/signer/stop'), 'Firmante detenido.'));
    $('bunker-issue').addEventListener('click', onIssueBunker);
    $('bunker-copy').addEventListener('click', onCopyBunker);
    $('bunker-hide').addEventListener('click', hideBunker);
  }

  async function init() {
    bind();
    try { showApp(await api('GET', '/api/auth/session', undefined, true)); } catch (_e) { showLogin(); }
  }

  init();
})();
