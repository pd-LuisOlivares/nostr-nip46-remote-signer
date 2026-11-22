'use strict';
/*
 * Cliente de demostracion NIP-46 (laboratorio). Sin frameworks. Reglas de seguridad:
 *  - TODO el contenido dinamico se inserta con textContent / createElement (nunca como HTML).
 *  - El token de la sesion del cliente y todo lo demas viven SOLO en variables en memoria: nada en el almacenamiento del navegador, ni en cookies ni en la URL.
 *  - Esta pagina NO tiene forma de aprobar nada: solo habla con su propio servicio (mismo origen) y este solo habla con el relay local.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 700;
  const STATE = {
    pending: { text: 'Pendiente de aprobación', cls: 'st-pending' },
    ok: { text: 'Completada', cls: 'st-ok' },
    signed: { text: 'Firmada y verificada', cls: 'st-signed' },
    rejected: { text: 'Rechazada', cls: 'st-rejected' },
    expired: { text: 'Expirada', cls: 'st-expired' },
    invalid: { text: 'Respuesta inválida', cls: 'st-invalid' },
  };
  const CHECKS = {
    json_valido: 'la respuesta es un evento JSON', campos_validos: 'campos y formatos válidos', id_ok: 'id = SHA-256 del evento',
    sig_ok: 'firma BIP-340 válida', pubkey_es_la_identidad: 'firmada con la identidad del firmante (get_public_key)',
    plantilla_coincide: 'contenido idéntico a lo solicitado', reto_coincide: 'reto idéntico al enviado',
  };
  let token = null;
  let timer = null;
  let busy = false;

  function el(tag, opts = {}, ...children) {
    const node = document.createElement(tag);
    if (opts.cls) node.className = opts.cls;
    if (opts.text !== undefined) node.textContent = String(opts.text);
    for (const child of children) if (child) node.append(child);
    return node;
  }

  async function api(method, path, body) {
    const headers = { 'X-Lab-Client': '1' };
    if (token) headers['X-Lab-Token'] = token;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const resp = await fetch(path, { method, headers, cache: 'no-store', credentials: 'omit', body: body === undefined ? undefined : JSON.stringify(body) });
    let data = null;
    if (resp.status !== 204) { try { data = await resp.json(); } catch (_e) { data = null; } }
    if (!resp.ok) { const err = new Error((data && data.error) || `Error ${resp.status}`); err.status = resp.status; throw err; }
    return data;
  }

  function showError(text) { $('session-error').textContent = text; $('session-error').hidden = !text; }

  function renderSession(s) {
    $('session-info').hidden = false;
    $('info-state').textContent = s.connected ? 'Conectado (aprobado por el operador)' : 'Sesión creada · sin conectar todavía';
    $('info-identity').textContent = s.identity8 ? `${s.identity8}…` : '— (conéctese primero)';
    $('info-bunker').textContent = `${s.bunker_pub8}…`;
    $('info-client').textContent = `${s.client_pub8}… (efímera)`;
    $('info-relay').textContent = s.relay_hosts.join(', ');
    $('info-ndk').textContent = `NDK ${s.ndk_version} (real) · origen de la firma ${s.origin} · el cliente espera una respuesta hasta ${s.op_timeout_s} s`;
    const select = $('variant');
    if (!select.options.length) for (const [key, label] of Object.entries(s.variants)) { const o = document.createElement('option'); o.value = key; o.textContent = label; select.append(o); }
  }

  function checkList(op) {
    if (!op.checks) return null;
    return el('ul', { cls: 'checks' }, ...Object.entries(op.checks).map(([k, v]) => el('li', { cls: v ? 'pass' : 'fail', text: `${v ? '✓' : '✗'} ${CHECKS[k] || k}` })));
  }

  function detailText(op) {
    const parts = [];
    const d = op.detail || {};
    if (d.identidad8) parts.push(`identidad ${d.identidad8}…`);
    if (d.reto_sha16) parts.push(`reto sha16 ${d.reto_sha16}`);
    if (d.evento_id16) parts.push(`evento ${d.evento_id16}…`);
    if (op.request_id) parts.push(`id de solicitud ${op.request_id}`);
    return parts.join(' · ');
  }

  function renderOps(ops) {
    $('ops-empty').hidden = ops.length > 0;
    $('ops-body').replaceChildren(...ops.slice().reverse().map((op) => {
      const st = STATE[op.state] || { text: op.state, cls: '' };
      const tr = el('tr', { cls: `op-row ${st.cls}` });
      tr.dataset.opId = op.id;
      tr.dataset.opType = op.type;
      tr.dataset.state = op.state;
      const detail = el('td', { cls: 'detail' }, el('div', { text: op.message }), el('div', { cls: 'muted mono', text: detailText(op) }), checkList(op),
        op.late ? el('div', { cls: 'warn', text: op.late.ok ? 'Llegó una respuesta tardía (tras expirar): NO se trata como firma ni como éxito.' : 'Llegó una respuesta tardía de rechazo.' }) : null);
      tr.append(el('td', { text: op.id.replace('op', '') }), el('td', { text: op.label }), el('td', {}, el('span', { cls: `badge ${st.cls}`, text: st.text })),
        el('td', { text: `${op.elapsed_s} s` }), detail);
      return tr;
    }));
  }

  async function poll() {
    if (!token || busy) return;
    busy = true;
    try {
      const data = await api('GET', '/api/state');
      renderSession(data.session);
      renderOps(data.ops);
    } catch (err) {
      if (err.status === 401) { endSession('La sesión del cliente se cerró o caducó.'); }
    } finally { busy = false; }
  }

  function endSession(message) {
    token = null;
    if (timer) { clearInterval(timer); timer = null; }
    for (const id of ['panel-ops', 'panel-log', 'session-info', 'close-btn']) $(id).hidden = true;
    $('session-btn').hidden = false;
    $('uri').disabled = false;
    $('ops-body').replaceChildren();
    showError(message || '');
  }

  async function onCreate(event) {
    event.preventDefault();
    const uri = $('uri').value.trim();
    $('uri').value = ''; // la URI no permanece en el campo
    showError('');
    if (!uri) return;
    try {
      const data = await api('POST', '/api/session', { uri });
      token = data.token;
      renderSession(data.session);
      for (const id of ['panel-ops', 'panel-log']) $(id).hidden = false;
      $('close-btn').hidden = false;
      $('session-btn').hidden = true;
      $('uri').disabled = true;
      if (timer) clearInterval(timer);
      timer = setInterval(poll, POLL_MS);
      poll();
    } catch (err) { showError(err.message); }
  }

  async function start(body) {
    try { await api('POST', '/api/op', body); poll(); } catch (err) { showError(err.message); }
  }

  async function onClose() {
    try { await api('DELETE', '/api/session'); } catch (_e) { /* ya cerrada */ }
    endSession('');
  }

  function bind() {
    $('session-form').addEventListener('submit', onCreate);
    $('close-btn').addEventListener('click', onClose);
    $('op-connect').addEventListener('click', () => start({ type: 'connect' }));
    $('op-pubkey').addEventListener('click', () => start({ type: 'get_public_key' }));
    $('op-ping').addEventListener('click', () => start({ type: 'ping' }));
    $('op-sign').addEventListener('click', () => start({ type: 'sign_valid' }));
    $('op-invalid').addEventListener('click', () => start({ type: 'sign_invalid', variant: $('variant').value }));
    // Al cerrar la pestana se libera la sesion del servicio (la memoria con la URI y las claves se borra).
    window.addEventListener('pagehide', () => { if (token) fetch('/api/session', { method: 'DELETE', headers: { 'X-Lab-Client': '1', 'X-Lab-Token': token }, keepalive: true, credentials: 'omit' }).catch(() => {}); });
  }

  bind();
})();
