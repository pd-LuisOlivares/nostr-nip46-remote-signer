// B6.1D-R3: cliente NIP-46 de DEMOSTRACION para el navegador (laboratorio). Hace de «Stacker News» frente al firmante, usando NDK 2.12.2 REAL
// (NDKNip46Signer + NDKNostrRpc: la misma capa de protocolo que usa Stacker News). NO simula respuestas del firmante.
//
// Limites deliberados (ver docs/phase-1.0B-B6.1D-R3-web-client.md):
//  - NO aprueba nada y NO tiene credenciales, cookies ni endpoints de aprobacion del firmante: la aprobacion humana solo existe en el panel del firmante.
//  - Solo se conecta a relays LOCALES (relay, localhost, 127.0.0.1, [::1], ws://). Cualquier otro destino se rechaza antes de abrir una conexion.
//  - La URI bunker:// y las claves efimeras viven SOLO en memoria; nunca en disco, URL, registros ni respuestas. Se olvidan al cerrar la sesion o por inactividad.
//  - Escucha en 0.0.0.0 DENTRO del contenedor; Docker la publica solo en 127.0.0.1. Valida Host y Origin y exige un token por sesion (cabecera) y una cabecera propia.
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { randomBytes, createHash, timingSafeEqual } from 'node:crypto';
import NDK, { NDKNip46Signer } from '@nostr-dev-kit/ndk';
import { eventId, sha256hex, verifySignedResponse } from './verify.mjs';

const PORT = Number(process.env.LAB_PORT ?? 18080);
const PUBLIC_PORT = String(process.env.LAB_PUBLIC_PORT ?? PORT);
const ORIGIN = process.env.LAB_ORIGIN ?? 'https://sn.manual.invalid';
const OP_TIMEOUT_MS = Number(process.env.OP_TIMEOUT_MS ?? 150000);
const SESSION_TTL_MS = Number(process.env.SESSION_TTL_MS ?? 15 * 60 * 1000);
const MAX_SESSIONS = 4;
const MAX_OPS = 60;
const MAX_BODY = 4096;
const LOCAL_RELAY_HOSTS = new Set(['relay', 'localhost', '127.0.0.1', '[::1]']);
const ALLOWED_HOSTS = new Set([`127.0.0.1:${PUBLIC_PORT}`, `localhost:${PUBLIC_PORT}`, `127.0.0.1:${PORT}`, `localhost:${PORT}`]);
const HEX64 = /^[0-9a-f]{64}$/;
const NDK_VERSION = (() => { try { return JSON.parse(readFileSync(new URL('../node_modules/@nostr-dev-kit/ndk/package.json', import.meta.url), 'utf8')).version; } catch { return 'desconocida'; } })();
const STATIC = new Map([['/', ['index.html', 'text/html; charset=utf-8']], ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']], ['/app.css', ['app.css', 'text/css; charset=utf-8']]]);
const FILES = new Map([...new Set([...STATIC.values()].map((v) => v[0]))].map((name) => [name, readFileSync(new URL(name, import.meta.url))]));
const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

// Variantes de firma INVALIDA (cada una incumple UNA regla de la politica del firmante).
const VARIANTS = {
  origen: 'origen de la etiqueta u ajeno', kind: 'kind distinto de 27235', metodo: 'método POST en lugar de GET', contenido: 'contenido distinto',
  edad: 'plantilla de hace 10 minutos', reto: 'reto con formato inválido', repeticion: 'reutiliza el reto de una firma ya hecha',
};

// ---------------------------------------------------------------------------------------------------- registro (sin secretos)
const clean = (s) => String(s ?? '').replace(/bunker:\/\/\S+/gi, '[uri]').replace(/secret=[^&\s]+/gi, 'secret=[x]').replace(/[0-9a-f]{64}/gi, '[hex64]').slice(0, 140);
const log = (ev, fields = {}) => console.log(JSON.stringify({ ts: new Date().toISOString(), actor: 'client-web', ev, ...Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, typeof v === 'string' ? clean(v) : v])) }));
process.on('unhandledRejection', (e) => log('unhandled_rejection', { error: e?.message ?? e }));

class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }

// ---------------------------------------------------------------------------------------------------- URI y relays locales
function parseUri(uri) {
  if (typeof uri !== 'string' || uri.length > 2048 || !uri.startsWith('bunker://')) throw new HttpError(400, 'La URI no es válida.');
  let u;
  try { u = new URL(uri.replace('bunker://', 'http://')); } catch { throw new HttpError(400, 'La URI no es válida.'); }
  const bunkerPubkey = u.hostname;
  const relays = u.searchParams.getAll('relay');
  const secret = u.searchParams.get('secret');
  if (!HEX64.test(bunkerPubkey) || relays.length === 0 || !secret) throw new HttpError(400, 'La URI no es válida.');
  for (const key of u.searchParams.keys()) if (key !== 'relay' && key !== 'secret') throw new HttpError(400, 'La URI no es válida.');
  for (const r of relays) {
    let ru;
    try { ru = new URL(r); } catch { throw new HttpError(400, 'La URI no es válida.'); }
    if (ru.protocol !== 'ws:' || !LOCAL_RELAY_HOSTS.has(ru.hostname) || ru.username || ru.password || ru.search || ru.hash) {
      throw new HttpError(400, 'Rechazada: este cliente solo se conecta a relays locales (ws://relay, ws://localhost o ws://127.0.0.1).');
    }
  }
  return { bunkerPubkey, relayHosts: [...new Set(relays.map((r) => new URL(r).host))] };
}

// NDK REAL, con el mismo parche de URL que Stacker News (lib/nostr.js): bunker:// -> http:// para que `new URL()` lea los parametros.
class NDKNip46SignerURLPatch extends NDKNip46Signer {
  connectionTokenInit(connectionToken) { return super.connectionTokenInit(connectionToken.replace('bunker://', 'http://')); }
}

// ---------------------------------------------------------------------------------------------------- sesiones (solo memoria)
const sessions = new Map(); // id -> sesion

async function createSession(uri) {
  if (sessions.size >= MAX_SESSIONS) {
    const oldest = [...sessions.values()].sort((a, b) => a.last - b.last)[0];
    destroySession(oldest, 'reemplazada');
  }
  const meta = parseUri(uri);
  const ndk = new NDK({ autoConnectUserRelays: false, autoFetchUserMutelist: false, clientName: 'nip46-lab-web' });
  const signer = new NDKNip46SignerURLPatch(ndk, uri);
  const token = randomBytes(24).toString('hex');
  const session = {
    id: randomBytes(6).toString('hex'), tokenHash: createHash('sha256').update(token).digest(), ndk, signer, bunker: signer.bunkerPubkey, relayHosts: meta.relayHosts,
    identity: null, connecting: false, ops: [], opSeq: 0, created: Date.now(), last: Date.now(), lastSignedChallenge: null, clientPub8: '', listening: false,
  };
  session.clientPub8 = (await signer.localSigner.user()).pubkey.slice(0, 8);
  // Correlacion: se anota el id de cada solicitud NIP-46 al ENVIARLA (el cuerpo cifrado pasa por el firmante local de NDK).
  const local = signer.localSigner;
  const origEncrypt = local.encrypt.bind(local);
  local.encrypt = async (recipient, value, scheme) => {
    try { noteRequest(session, JSON.parse(value)); } catch { /* no era una solicitud */ }
    return origEncrypt(recipient, value, scheme);
  };
  sessions.set(session.id, session);
  log('session_created', { session: session.id, relay: meta.relayHosts.join(','), ndk: NDK_VERSION });
  return { session, token };
}

function destroySession(session, reason) {
  if (!session || !sessions.has(session.id)) return;
  sessions.delete(session.id);
  try { for (const relay of session.ndk.pool.relays.values()) relay.disconnect(); } catch { /* ya cerrado */ }
  Object.assign(session, { ndk: null, signer: null, identity: null, ops: [], tokenHash: null, lastSignedChallenge: null });
  log('session_closed', { session: session.id, reason });
}

function sessionFromToken(req) {
  const token = String(req.headers['x-lab-token'] ?? '');
  if (!/^[0-9a-f]{48}$/.test(token)) return null;
  const hash = createHash('sha256').update(token).digest();
  for (const s of sessions.values()) if (s.tokenHash && timingSafeEqual(s.tokenHash, hash)) { s.last = Date.now(); return s; }
  return null;
}

setInterval(() => { for (const s of [...sessions.values()]) if (Date.now() - s.last > SESSION_TTL_MS) destroySession(s, 'inactividad'); }, 30000).unref();

// ---------------------------------------------------------------------------------------------------- operaciones
function newOp(session, type, label, method, extra = {}) {
  if (session.ops.length >= MAX_OPS) session.ops.shift();
  const op = { id: `op${++session.opSeq}`, type, label, method, state: 'pending', message: 'Enviada. Esperando respuesta del firmante…', startedAt: Date.now(), endedAt: null,
               requestId: null, checks: null, detail: {}, late: null, templateJson: null, ...extra };
  session.ops.push(op);
  return op;
}

function noteRequest(session, request) {
  if (!request || typeof request.id !== 'string' || typeof request.method !== 'string') return;
  const params = Array.isArray(request.params) ? request.params : [];
  const op = session.ops.find((o) => o.state === 'pending' && !o.requestId && o.method === request.method && (request.method !== 'sign_event' || o.templateJson === params[0]));
  if (op) op.requestId = request.id;
}

const finish = (op, state, message, extra = {}) => { Object.assign(op, { state, message, endedAt: Date.now(), ...extra }); log('op_result', { op: op.id, type: op.type, state }); };

/** Envia UNA solicitud NIP-46 por la capa real de NDK. `sendRequest` solo resuelve por callback (su promesa interna no se usa). */
function rpcRequest(session, op, method, params) {
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => { if (!settled) { settled = true; resolve({ timeout: true }); } }, OP_TIMEOUT_MS);
    session.signer.startListening().then(() => session.signer.rpc.sendRequest(session.bunker, method, params, 24133, (res) => {
      if (!settled) { settled = true; clearTimeout(timer); resolve({ res }); } else { op.late = { ok: !res.error }; }  // respuesta tras expirar: NUNCA cuenta como exito
    })).catch((err) => { if (!settled) { settled = true; clearTimeout(timer); resolve({ failure: clean(err?.message ?? err) }); } });
  });
}

const REJECT_TEXT = {
  unauthorized: 'El firmante rechazó la solicitud (no autorizada): la política no se cumple, el operador la rechazó, la aprobación caducó o ya no podía firmarse. El motivo exacto se ve en el panel del firmante.',
  'invalid params': 'El firmante rechazó la solicitud por parámetros inválidos.',
  'internal error': 'El firmante informó de un error interno.',
  'unsupported method': 'El firmante no soporta ese método.',
};
const rejectText = (error) => REJECT_TEXT[String(error)] ?? `El firmante respondió con un error (${clean(error)}).`;
const timeoutText = () => `Sin respuesta en ${Math.round(OP_TIMEOUT_MS / 1000)} s: el cliente dejó de esperar (expirada). Si el firmante la aprueba ahora, la respuesta se marcará como tardía y NO se tratará como firma.`;

async function runConnect(session, op) {
  session.connecting = true;
  try {
    const user = await Promise.race([
      session.signer.blockUntilReady(),  // exactamente el camino de Stacker News: connect (con el secreto) y despues get_public_key
      new Promise((_, reject) => setTimeout(() => reject(new Error('__timeout__')), OP_TIMEOUT_MS)),
    ]);
    const identity = user.pubkey;
    if (!HEX64.test(identity) || identity === session.bunker) { finish(op, 'invalid', 'La identidad recibida no es válida (vacía o igual a la clave de transporte).'); return; }
    session.identity = identity;
    finish(op, 'ok', 'Conectado: el operador aprobó la conexión y el firmante entregó su identidad.', { detail: { identidad8: identity.slice(0, 8) } });
  } catch (e) {
    if (e?.message === '__timeout__') finish(op, 'expired', timeoutText());
    else finish(op, 'rejected', rejectText(e?.message ?? e));
  } finally { session.connecting = false; }
}

async function runSimple(session, op, method, params, interpret) {
  const out = await rpcRequest(session, op, method, params);
  if (out.timeout) return finish(op, 'expired', timeoutText());
  if (out.failure) return finish(op, 'invalid', `No se pudo enviar la solicitud: ${out.failure}`);
  if (out.res.error) return finish(op, 'rejected', rejectText(out.res.error));
  return interpret(out.res.result);
}

function buildTemplate(session, variant) {
  const now = Math.floor(Date.now() / 1000);
  const challenge = variant === 'reto' ? 'XYZ' : variant === 'repeticion' ? session.lastSignedChallenge : randomBytes(32).toString('hex');
  const t = {
    pubkey: session.identity, created_at: now + (variant === 'edad' ? -600 : 0), kind: variant === 'kind' ? 1 : 27235,
    tags: [['challenge', challenge], ['u', variant === 'origen' ? 'https://evil.invalid' : ORIGIN], ['method', variant === 'metodo' ? 'POST' : 'GET']],
    content: variant === 'contenido' ? 'otro texto' : 'Stacker News Authentication',
  };
  return { ...t, id: eventId(t) };
}

async function runSign(session, op, template, expectValid) {
  const params = [JSON.stringify(template)];
  op.templateJson = params[0];
  op.detail = { reto_sha16: sha256hex(template.tags[0][1]).slice(0, 16), kind: template.kind, edad_s: Math.floor(Date.now() / 1000) - template.created_at };
  const out = await rpcRequest(session, op, 'sign_event', params);
  if (out.timeout) return finish(op, 'expired', timeoutText());
  if (out.failure) return finish(op, 'invalid', `No se pudo enviar la solicitud: ${out.failure}`);
  if (out.res.error) {
    return finish(op, 'rejected', (expectValid ? '' : 'Rechazo esperado. ') + rejectText(out.res.error), { detail: { ...op.detail, esperado: !expectValid } });
  }
  const v = verifySignedResponse(out.res.result, template, session.identity);
  if (v.ok && expectValid) {
    session.lastSignedChallenge = template.tags[0][1];
    return finish(op, 'signed', 'Firma recibida y VERIFICADA criptográficamente (id, firma BIP-340, identidad y contenido).', { checks: v.checks, detail: { ...op.detail, evento_id16: v.event.id16, pubkey8: v.event.pubkey8 } });
  }
  if (v.ok && !expectValid) return finish(op, 'invalid', '¡FALLA! El firmante firmó una solicitud que debía rechazar.', { checks: v.checks, detail: { ...op.detail, esperado: false } });
  return finish(op, 'invalid', 'La respuesta NO se acepta como firma: falló la verificación criptográfica.', { checks: v.checks, detail: op.detail });
}

function startOp(session, body) {
  const type = body?.type;
  if (type === 'connect') {
    if (session.connecting) throw new HttpError(409, 'Ya hay una conexión en curso en esta sesión.');
    const op = newOp(session, type, 'Conectar (connect)', 'connect');
    runConnect(session, op);
    return op;
  }
  if (type === 'get_public_key') {
    const op = newOp(session, type, 'get_public_key', 'get_public_key');
    runSimple(session, op, 'get_public_key', [], (result) => {
      if (!HEX64.test(String(result)) || result === session.bunker) return finish(op, 'invalid', 'La clave recibida no es válida (o es la de transporte).');
      if (session.identity && result !== session.identity) return finish(op, 'invalid', 'La identidad recibida CAMBIÓ respecto a la de la conexión.');
      session.identity ??= result;
      return finish(op, 'ok', 'El firmante entregó su identidad (distinta de su clave de transporte).', { detail: { identidad8: result.slice(0, 8) } });
    });
    return op;
  }
  if (type === 'ping') {
    const op = newOp(session, type, 'ping', 'ping');
    runSimple(session, op, 'ping', [], (result) => (result === 'pong' ? finish(op, 'ok', 'El firmante respondió pong.') : finish(op, 'invalid', 'Respuesta inesperada al ping.')));
    return op;
  }
  if (type === 'sign_valid' || type === 'sign_invalid') {
    const variant = type === 'sign_valid' ? 'valida' : String(body?.variant ?? '');
    if (type === 'sign_invalid' && !Object.hasOwn(VARIANTS, variant)) throw new HttpError(400, 'Variante de firma inválida desconocida.');
    const label = type === 'sign_valid' ? 'Firma válida (sign_event)' : `Firma inválida: ${VARIANTS[variant]}`;
    const op = newOp(session, type, label, 'sign_event');
    if (!session.identity) { finish(op, 'rejected', 'Conéctese primero (connect): hace falta conocer la identidad del firmante.'); return op; }
    if (variant === 'repeticion' && !session.lastSignedChallenge) { finish(op, 'rejected', 'Para reutilizar un reto, primero obtenga una firma válida.'); return op; }
    runSign(session, op, buildTemplate(session, variant), type === 'sign_valid');
    return op;
  }
  throw new HttpError(400, 'Operación desconocida.');
}

const publicOp = (op, now = Date.now()) => ({
  id: op.id, type: op.type, label: op.label, state: op.state, message: op.message, request_id: op.requestId, checks: op.checks, detail: op.detail, late: op.late,
  elapsed_s: Math.round(((op.endedAt ?? now) - op.startedAt) / 100) / 10,
});
const publicSession = (s) => ({
  client_pub8: s.clientPub8, bunker_pub8: s.bunker.slice(0, 8), relay_hosts: s.relayHosts, connected: Boolean(s.identity), identity8: s.identity ? s.identity.slice(0, 8) : null,
  ndk_version: NDK_VERSION, origin: ORIGIN, op_timeout_s: Math.round(OP_TIMEOUT_MS / 1000), variants: VARIANTS,
});

// ---------------------------------------------------------------------------------------------------- HTTP
function send(res, status, body, type = 'application/json; charset=utf-8', extra = {}) {
  res.writeHead(status, {
    'Content-Type': type, 'Cache-Control': 'no-store', 'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer', 'Cross-Origin-Resource-Policy': 'same-origin', 'Cross-Origin-Opener-Policy': 'same-origin', ...extra,
  });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    if (!/^application\/json(;|$)/i.test(String(req.headers['content-type'] ?? ''))) return reject(new HttpError(415, 'Se requiere application/json.'));
    let size = 0; const chunks = [];
    let tooBig = false;
    req.on('data', (c) => { size += c.length; if (size > MAX_BODY) { if (!tooBig) { tooBig = true; reject(new HttpError(413, 'Cuerpo demasiado grande.')); } } else chunks.push(c); });  // se descarta el resto sin cortar el socket (la respuesta debe llegar)
    req.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); } catch { reject(new HttpError(400, 'JSON inválido.')); } });
    req.on('error', () => reject(new HttpError(400, 'Solicitud inválida.')));
  });
}

async function route(req, res) {
  if (!ALLOWED_HOSTS.has(String(req.headers.host ?? ''))) throw new HttpError(400, 'Host no permitido.');
  const path = new URL(req.url, 'http://local').pathname;
  if (req.method === 'GET' && STATIC.has(path)) { const [name, type] = STATIC.get(path); return send(res, 200, FILES.get(name), type); }
  if (req.method === 'GET' && path === '/healthz') return send(res, 200, { status: 'ok' });
  if (!path.startsWith('/api/')) throw new HttpError(404, 'No encontrado.');

  // Defensa frente a paginas ajenas: Origin (si lo hay) debe ser el propio origen, y toda llamada exige una cabecera propia (fuerza preflight, que NO se atiende: sin CORS).
  const origin = req.headers.origin;
  if (origin !== undefined && origin !== `http://${req.headers.host}`) throw new HttpError(403, 'Origen no permitido.');
  if (req.method !== 'GET' && req.headers['x-lab-client'] !== '1') throw new HttpError(403, 'Solicitud no permitida.');
  if (req.method === 'OPTIONS') throw new HttpError(405, 'Método no permitido.');

  if (req.method === 'POST' && path === '/api/session') {
    const body = await readJson(req);
    const { session, token } = await createSession(body?.uri);
    return send(res, 201, { token, session: publicSession(session) });
  }
  const session = sessionFromToken(req);
  if (!session) throw new HttpError(401, 'Sesión no válida o cerrada.');
  if (req.method === 'GET' && path === '/api/state') return send(res, 200, { session: publicSession(session), ops: session.ops.map((o) => publicOp(o)) });
  if (req.method === 'POST' && path === '/api/op') { const op = startOp(session, await readJson(req)); return send(res, 202, { op: publicOp(op) }); }
  if (req.method === 'DELETE' && path === '/api/session') { destroySession(session, 'cerrada por el usuario'); return send(res, 204, ''); }
  throw new HttpError(404, 'No encontrado.');
}

const server = http.createServer((req, res) => {
  route(req, res).catch((e) => {
    if (res.headersSent) return;
    if (e instanceof HttpError) return send(res, e.status, { error: e.message });
    log('error', { error: e?.message ?? e });
    return send(res, 500, { error: 'Error interno.' });
  });
});
server.headersTimeout = 10000;
server.requestTimeout = 15000;
server.listen(PORT, '0.0.0.0', () => log('listening', { port: PORT, public_port: PUBLIC_PORT, ndk: NDK_VERSION, origin: ORIGIN }));
for (const sig of ['SIGTERM', 'SIGINT']) process.on(sig, () => { for (const s of [...sessions.values()]) destroySession(s, 'apagado'); server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 2000).unref(); });
