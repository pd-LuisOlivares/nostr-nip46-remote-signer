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
  const STATE_LABEL = { idle: 'Detenido', starting: 'Iniciando', ready: 'Listo', reconnecting: 'Reconectando', stopping: 'Deteniendo', stopped: 'Detenido', failed: 'Fallido' };
  // Motivos de fin que merecen una explicación (el resto se muestra tal cual, con espacios).
  const END_LABEL = {
    reconexion_agotada: 'se agotaron los intentos de reconexión con el relay; pulse «Iniciar firmante» para reanudar (sus conexiones autorizadas se conservan)',
  };
  const endText = (reason) => (reason ? (END_LABEL[reason] || reason.replaceAll('_', ' ')) : '—');
  const KIND_LABEL = { connect: 'Conexión de un cliente', sign_event: 'Firma del evento de inicio de sesión' };
  const STATUS_LABEL = { pending: 'pendiente', approved: 'aprobada', denied: 'rechazada', expired: 'caducada', cancelled: 'cancelada' };
  // P-42: motivos (codigos fijos del servidor) de una firma aprobada que NO se realizo.
  const REASON_LABEL = {
    politica_incumplida: 'la política dejó de cumplirse (p. ej. la ventana de tiempo)', aprobacion_caducada: 'la aprobación caducó',
    aprobacion_consumida: 'la aprobación ya se había usado', aprobacion_no_vigente: 'la aprobación no estaba vigente',
    firmante_no_activo: 'el firmante ya no estaba activo', cliente_no_activo: 'la conexión del cliente ya no estaba activa',
    solicitud_alterada: 'lo que se iba a firmar no coincidía con lo aprobado', reutilizacion_o_tope: 'el reto ya se había firmado o se alcanzó el tope de firmas',
    autoverificacion: 'falló la autoverificación de la firma', sesion_terminada: 'la sesión terminó antes de obtener el resultado',
  };
  const ERRORS = {
    400: 'La clave no es válida.', 401: 'La sesión no es válida o caducó. Inicie sesión de nuevo.', 403: 'Solicitud no permitida.',
    404: 'No encontrado.', 409: 'La operación no es posible en el estado actual.', 422: 'Datos no válidos.',
    429: 'Demasiados intentos. Espere un minuto.', 502: 'El firmante no llegó a estar listo (revise el relay).',
  };

  let csrf = null;
  let pollTimer = null;
  let tickTimer = null;
  let sessionLeft = 0;
  let sessionTick = null;
  let bunkerTimer = null;
  let lastState = null;
  let primed = false; // el primer sondeo solo memoriza el historial: no anuncia resultados antiguos
  const announced = new Map(); // id de solicitud -> resultado ya anunciado
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
    $('login-password').value = '';
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
    primed = false;
    announced.clear();
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

  const LOGIN_ERRORS = {
    401: 'Usuario o contraseña incorrectos.', 422: 'Revise el usuario y la contraseña.',
    429: 'Demasiados intentos fallidos. Espere unos minutos antes de volver a intentarlo.', 503: 'El servicio está ocupado o no disponible. Espere unos segundos e inténtelo de nuevo; si persiste, revise la terminal de la aplicación.',
  };

  function setLoginBusy(busy) {
    $('login-btn').disabled = busy;
    $('login-username').disabled = busy;
    $('login-password').disabled = busy;
    $('login-form').setAttribute('aria-busy', busy ? 'true' : 'false');
    show('login-status', busy);
  }

  async function onLogin(event) {
    event.preventDefault();
    if ($('login-btn').disabled) return; // un envio en curso (doble Enter o doble clic)
    const username = $('login-username').value.trim();
    const password = $('login-password').value;
    $('login-password').value = ''; // la contrasena no permanece en el DOM
    show('login-error', false);
    setLoginBusy(true);
    try {
      // El servidor verifica las credenciales y fija la cookie HttpOnly con el JWT: esta pagina nunca recibe ni copia el token.
      const info = await api('POST', '/api/auth/login', { username, password });
      $('login-username').value = '';
      clearBanner();
      showApp(info);
    } catch (err) {
      $('login-error').textContent = (err instanceof ApiError && LOGIN_ERRORS[err.status]) || 'No se pudo iniciar sesión. Inténtelo de nuevo.';
      show('login-error', true);
      $('login-password').focus();
    } finally {
      setLoginBusy(false);
    }
  }

  async function onLogout() {
    try { await api('POST', '/api/auth/logout'); } catch (_e) { /* la sesion ya no era valida */ }
    wipeSecrets();
    showLogin();
    banner('ok', 'Sesión cerrada.');
  }

  // ------------------------------------------------------------------------------------------ sondeo
  function startPolling() { stopPolling(); refresh(); pollTimer = setInterval(refresh, POLL_MS); tickTimer = setInterval(tickCountdowns, 1000); }
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null; }
  }

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
    $('signer-signatures').textContent = sg.max_signatures === null
      ? `${sg.signatures} (cada una aprobada por una persona)`
      : `${sg.signatures} de ${sg.max_signatures} permitidas`;
    $('signer-end').textContent = endText(sg.end_reason);
    const running = ['starting', 'ready', 'reconnecting', 'stopping'].includes(sg.state); // «Detener» sigue disponible mientras se reconecta
    $('identity-create').disabled = running;
    $('identity-import').disabled = running;
    $('signer-start').disabled = running || !s.identity.present;
    $('signer-stop').disabled = !running;
    $('bunker-issue').disabled = sg.state !== 'ready';
    if (lastState === 'ready' && sg.state !== 'ready') {
      $('bunker-uri').value = '';
      show('bunker-box', false);
      banner('info', sg.state === 'reconnecting'
        ? 'Se perdió la conexión con el relay: reconectando. Sus conexiones autorizadas se conservan.'
        : `El firmante terminó: ${sg.end_reason ? endText(sg.end_reason) : 'detenido'}.`);
    } else if (lastState === 'reconnecting' && sg.state === 'ready') {
      banner('ok', 'Reconectado con el relay.');
    } else if (lastState === 'reconnecting' && sg.state === 'failed') {
      banner('error', `El firmante no pudo reconectar: ${endText(sg.end_reason)}.`);
    }
    lastState = sg.state;
  }

  function renderConnections(list) {
    const ul = $('connections-list');
    ul.replaceChildren(...list.map((c) => el('li', {}, el('span', { cls: 'mono', text: c.client }), el('span', { text: c.state }),
      c.state === 'active' ? el('span', { cls: 'muted', text: `expira en ${c.expires_in_s} s` }) : null,
      c.state === 'active' ? el('button', { type: 'button', cls: 'btn danger revoke-btn', text: 'Revocar', on: { click: () => onRevoke(c.id) } }) : null)));
    $('connections-empty').hidden = list.length > 0;
  }

  // Revocación individual: el id es OPACO (no es la clave del cliente). El servidor invalida la conexión al instante y cancela sus solicitudes pendientes.
  function onRevoke(id) {
    return guarded(() => api('DELETE', `/api/connections/${encodeURIComponent(id)}`), 'Conexión revocada. Para volver a usarla hay que emparejarla de nuevo.');
  }

  function summaryTable(summary) {
    const dl = el('dl', { cls: 'kv' });
    for (const [k, v] of Object.entries(summary)) {
      dl.append(el('dt', { text: k }), el('dd', { cls: 'mono wrap', text: typeof v === 'object' ? JSON.stringify(v) : v }));
    }
    return dl;
  }

  // P-42: lo que se muestra es el RESULTADO real del servidor. `approved` es solo la decision del operador; una firma NO esta hecha hasta `outcome === 'signed'`.
  function stateOf(r) {
    if (r.kind === 'sign_event' && r.status === 'approved') {
      const why = REASON_LABEL[r.outcome_reason] || r.outcome_reason || 'motivo no disponible';
      if (r.outcome === 'signed') return { text: 'Firmada correctamente', cls: 'res-ok' };
      if (r.outcome === 'refused') return { text: `Rechazada al firmar: ${why}`, cls: 'res-bad' };
      if (r.outcome === 'failed') return { text: `Fallida: ${why}`, cls: 'res-bad' };
      return { text: 'Aprobada por el operador; falta el resultado de la firma', cls: 'res-wait' };
    }
    return { text: STATUS_LABEL[r.status] || r.status, cls: '' };
  }

  function announceOutcomes(all) {
    for (const r of all) {
      if (r.kind !== 'sign_event' || r.status !== 'approved' || !r.outcome) continue;
      if (announced.get(r.id) === r.outcome) continue;
      announced.set(r.id, r.outcome);
      if (!primed) continue;
      if (r.outcome === 'signed') banner('ok', 'Firma realizada correctamente.');
      else banner('error', `La firma NO se realizó: ${REASON_LABEL[r.outcome_reason] || 'motivo no disponible'}.`);
    }
    primed = true;
  }

  function buildCard(req) {
    const allOk = req.checks.every((c) => c.ok);
    const countdown = el('span', { cls: 'muted' });
    const deadline = el('p', { cls: 'muted' }); // B6.1D-R3: plazo real de la politica (solo firmas)
    deadline.hidden = true;
    const approve = el('button', { type: 'button', cls: 'btn ok', text: 'Aprobar', on: { click: () => decide(req.id, 'approve') } });
    const deny = el('button', { type: 'button', cls: 'btn danger', text: 'Rechazar', on: { click: () => decide(req.id, 'deny') } });
    approve.id = `approve-${req.id}`;
    deny.id = `deny-${req.id}`;
    approve.disabled = !allOk; // nunca se ofrece aprobar una firma que incumple la politica
    const node = el('article', { cls: `req kind-${req.kind}` },
      el('header', {}, el('span', { text: KIND_LABEL[req.kind] || req.kind }), countdown),
      el('p', { cls: 'muted', text: `Cliente ${req.client}` }),
      deadline,
      summaryTable(req.summary));
    if (req.checks.length) {
      node.append(el('h3', { text: 'Comprobaciones de la política' }),
        el('ul', { cls: 'checks' }, ...req.checks.map((c) => el('li', { cls: c.ok ? 'pass' : 'fail', text: `${c.ok ? '✓' : '✗'} ${c.name}${c.ok || !c.detail ? '' : ` (${c.detail})`}` }))));
    }
    if (!allOk) node.append(el('p', { cls: 'error', text: 'Alguna comprobación falló: esta firma no puede aprobarse.' }));
    node.append(el('div', { cls: 'row' }, approve, deny));
    node.dataset.requestId = req.id;
    return { node, countdown, deadline, approve, allOk, kind: req.kind };
  }

  // B6.1D-R3: el plazo EFECTIVO para firmar es el MENOR entre la aprobacion (APPROVAL_TTL_S) y la ventana de la politica (SIGNER_WINDOW_S menos la
  // antiguedad de la plantilla). Los segundos vienen del servidor (reloj del servidor) y aqui solo se descuentan entre sondeos; no se amplia nada.
  function paintCountdown(entry) {
    if (!entry.base) return;
    const dt = Math.floor((Date.now() - entry.base.t) / 1000);
    const appr = Math.max(0, entry.base.appr - dt);
    if (entry.base.sign === null) { entry.countdown.textContent = `caduca en ${appr} s`; return; }
    const sign = Math.max(0, entry.base.sign - dt);
    const effective = Math.min(appr, sign);
    entry.signExpired = sign <= 0;
    entry.countdown.className = effective <= 10 ? 'res-bad' : 'res-wait';
    entry.countdown.textContent = effective > 0 ? `Plazo efectivo para firmar: ${effective} s` : 'Ya no puede firmarse';
    entry.deadline.hidden = false;
    entry.deadline.textContent = entry.signExpired
      ? 'La ventana de la política venció: aunque la apruebe, el firmante NO firmará esta solicitud. Recházela.'
      : `Ventana de la política: ${sign} s · La aprobación caduca en: ${appr} s${sign < appr ? ' (el plazo efectivo lo marca la ventana de la política)' : ''}`;
    // El boton NO se desactiva: el servidor es la autoridad (revalida la politica al firmar) y aprobar fuera de plazo debe poder verse como «Rechazada al firmar».
    // Solo se rotula con claridad para que nadie crea que va a firmar.
    entry.approve.textContent = entry.signExpired ? 'Aprobar (ya no firmará)' : 'Aprobar';
  }
  function tickCountdowns() { for (const entry of cards.values()) paintCountdown(entry); }

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
        entry = { sig, node: built.node, countdown: built.countdown, deadline: built.deadline, approve: built.approve, allOk: built.allOk, kind: built.kind, signExpired: false, base: null };
        cards.set(req.id, entry);
      }
      entry.base = { appr: req.expires_in_s, sign: typeof req.sign_expires_in_s === 'number' ? req.sign_expires_in_s : null, t: Date.now() };
      paintCountdown(entry);
    }
    $('pending-count').textContent = String(pending.length);
    $('pending-empty').hidden = pending.length > 0;
    const ul = $('recent-list');
    ul.replaceChildren(...recent.slice(0, 15).map((r) => {
      const st = stateOf(r);
      return el('li', {}, el('span', { cls: st.cls, text: st.text }), el('span', { text: KIND_LABEL[r.kind] || r.kind }), el('span', { cls: 'muted', text: r.reason || '' }));
    }));
    announceOutcomes(all);
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

  // P-37, defensa en profundidad: aunque el boton «Aprobar» este desactivado, un evento `click` sintetico llegaria hasta aqui. Una solicitud con
  // alguna comprobacion de la politica en rojo (o que la interfaz no conozca) NO se aprueba nunca desde esta pagina. El servidor sigue siendo la
  // autoridad: no crea solicitudes que incumplan la politica.
  const decide = (id, verdict) => {
    const entry = cards.get(id);
    if (verdict === 'approve' && !(entry && entry.allOk)) {
      banner('error', 'Esta solicitud incumple la política y no puede aprobarse.');
      return Promise.resolve(null);
    }
    const approved = entry && entry.kind === 'sign_event' ? 'Solicitud aprobada. Falta el resultado de la firma (vea «Recientes»).' : 'Solicitud aprobada.';
    return guarded(() => api('POST', `/api/requests/${encodeURIComponent(id)}/${verdict}`), verdict === 'approve' ? approved : 'Solicitud rechazada.');
  };

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
