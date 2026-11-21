// Firmante de REFERENCIA del laboratorio (Node + nostr-tools 2.16.2). NO es el firmante productivo.
// Aisla el comportamiento de NDK usando la misma biblioteca criptografica que el navegador de Stacker News.
// Claves desechables en memoria; nunca se registran. Mismos fallos inyectables que el simulador Python.
import { createHash, randomBytes } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import { generateSecretKey, getPublicKey, finalizeEvent, verifyEvent, nip04, nip44 } from 'nostr-tools';

const RELAY_URL = process.env.RELAY_URL ?? 'ws://relay:7777';
const REPLY_MODE = process.env.REPLY_MODE ?? 'nip44';
const FAULT = process.env.FAULT ?? 'none';
const JITTER_MS = Number(process.env.JITTER_MS ?? 0);
const USE_SECRET = (process.env.USE_SECRET ?? '1') === '1';
const KIND_AUTH = 27235;

const emit = (o) => console.log(JSON.stringify({ ts: new Date().toISOString(), actor: 'signer-ref', ...o }));
const sha = (s) => createHash('sha256').update(s, 'utf8').digest('hex');

const transportSk = generateSecretKey();   // clave de transporte (remote-signer-pubkey)
const identitySk = generateSecretKey();    // clave de identidad (user-pubkey), DISTINTA
const transportPk = getPublicKey(transportSk);
const identityPk = getPublicKey(identitySk);
const secret = USE_SECRET ? randomBytes(16).toString('base64url') : null;
let secretUsed = false;
let mixed = 0;
const authorized = new Set();
const seen = new Set();

const ws = new WebSocket(RELAY_URL);
await new Promise((resolve, reject) => { ws.addEventListener('open', resolve); ws.addEventListener('error', () => reject(new Error('no se pudo conectar al relay'))); });

async function encryptFor(authorSk, clientPk, plaintext, scheme) {
  if (scheme === 'nip04') return await nip04.encrypt(authorSk, clientPk, plaintext);
  return nip44.v2.encrypt(plaintext, nip44.v2.utils.getConversationKey(authorSk, clientPk));
}

async function buildResponse(authorSk, clientPk, reqId, res, scheme, { mutate, rawContent } = {}) {
  const body = { id: reqId, result: res.result ?? '' };
  if (res.error) body.error = res.error;
  let content = rawContent ?? await encryptFor(authorSk, clientPk, JSON.stringify(body), scheme);
  if (mutate) content = mutate(content);
  return finalizeEvent({ kind: 24133, created_at: Math.floor(Date.now() / 1000), tags: [['p', clientPk]], content }, authorSk);
}

async function publish(ev, label, info) {
  if (JITTER_MS) await sleep(Math.random() * JITTER_MS);
  ws.send(JSON.stringify(['EVENT', ev]));
  emit({ ev: 'response_published', label, id: ev.id.slice(0, 16), author: ev.pubkey.slice(0, 8), ...info });
}

function schemeFor(requestScheme) {
  if (FAULT === 'mixed') { mixed += 1; return mixed % 2 === 1 ? 'nip44' : 'nip04'; }
  return REPLY_MODE === 'mirror' ? requestScheme : REPLY_MODE;
}

function runMethod(method, params, clientPk) {
  const err = (m) => ({ result: 'error', error: m });
  if (method === 'connect') {
    if (secret !== null) {
      if (secretUsed || params.length < 2 || params[1] !== secret) return err('unauthorized');
      secretUsed = true;
    }
    authorized.add(clientPk);
    return { result: 'ack' };
  }
  if (!authorized.has(clientPk)) return err('unauthorized');
  if (method === 'get_public_key') return { result: identityPk };
  if (method === 'ping') return { result: 'pong' };
  if (method === 'sign_event') {
    try {
      const tpl = JSON.parse(params[0]);
      if (tpl.kind !== KIND_AUTH) return err('unauthorized kind');
      if ('pubkey' in tpl && tpl.pubkey !== identityPk) return err('pubkey mismatch');
      const signed = finalizeEvent({ kind: tpl.kind, created_at: tpl.created_at, tags: tpl.tags, content: tpl.content }, identitySk);
      if (tpl.id !== undefined && tpl.id !== signed.id) {
        emit({ ev: 'client_id_mismatch', client_id: String(tpl.id).slice(0, 16), own_id: signed.id.slice(0, 16) });
        return err('id mismatch');
      }
      emit({ ev: 'sign_event_ok', kind: signed.kind, id: signed.id.slice(0, 16), tags0: signed.tags[0]?.[0] ?? null });
      return { result: JSON.stringify(signed) };
    } catch { return err('invalid params'); }
  }
  return err('unsupported method');
}

async function respond(clientPk, reqId, method, res, requestScheme) {
  const scheme = schemeFor(requestScheme);
  const info = { method, scheme, fault: FAULT, req_id: reqId };
  const ack = res.result === 'ack' && method === 'connect';
  const normal = async (label = 'normal', rid = reqId) =>
    publish(await buildResponse(transportSk, clientPk, rid, res, scheme), label, info);

  if (method === 'get_public_key' && FAULT === 'get_pubkey_error') {
    return publish(await buildResponse(transportSk, clientPk, reqId, { result: '', error: 'lab-error' }, scheme), 'get_pubkey_error', info);
  }
  if (!(ack && !['none', 'mixed', 'get_pubkey_error'].includes(FAULT))) return normal();
  switch (FAULT) {
    case 'wrong_id': await normal('wrong_id', 'wrong-' + randomBytes(4).toString('hex')); await sleep(1500); return normal('correct_after_wrong_id');
    case 'error_field': return publish(await buildResponse(transportSk, clientPk, reqId, { result: 'error', error: 'lab-denied' }, scheme), 'error_field', info);
    case 'malformed_json':
      await publish(await buildResponse(transportSk, clientPk, reqId, res, scheme, { rawContent: await encryptFor(transportSk, clientPk, 'not-json{', scheme) }), 'malformed_json', info);
      await sleep(1500); return normal('correct_after_malformed');
    case 'garbage':
      await publish(await buildResponse(transportSk, clientPk, reqId, res, scheme, { rawContent: randomBytes(120).toString('base64') }), 'garbage', info);
      await sleep(1500); return normal('correct_after_garbage');
    case 'bad_mac': {
      const flip = (c) => { const b = Buffer.from(c, 'base64'); b[b.length - 1] ^= 1; return b.toString('base64'); };
      await publish(await buildResponse(transportSk, clientPk, reqId, res, 'nip44', { mutate: flip }), 'bad_mac', info);
      await sleep(1500); return normal('correct_after_bad_mac');
    }
    case 'spoof': return publish(await buildResponse(generateSecretKey(), clientPk, reqId, res, scheme), 'spoofed_by_other_key', info);
    case 'duplicate': await normal('duplicate_1'); return normal('duplicate_2');
    case 'unknown_id_first': await normal('unknown_id', 'unknown-' + randomBytes(4).toString('hex')); return normal('correct_after_unknown_id');
    case 'auth_url':
      await publish(await buildResponse(transportSk, clientPk, reqId, { result: 'auth_url', error: 'https://lab.invalid/approve' }, scheme), 'auth_url', info);
      await sleep(1000); return normal('final_after_auth_url');
    default: return normal();
  }
}

async function handleEvent(e) {
  if (!verifyEvent(e) || e.kind !== 24133 || !e.tags.some((t) => t[0] === 'p' && t[1] === transportPk)) { emit({ ev: 'drop', reason: 'evento invalido o etiqueta p incorrecta' }); return; }
  if (seen.has(e.id)) { emit({ ev: 'drop', reason: 'duplicado' }); return; }
  seen.add(e.id);
  const clientPk = e.pubkey;
  const scheme = e.content.includes('?iv=') ? 'nip04' : 'nip44';
  let plaintext;
  try {
    plaintext = scheme === 'nip04'
      ? await nip04.decrypt(transportSk, clientPk, e.content)
      : nip44.v2.decrypt(e.content, nip44.v2.utils.getConversationKey(transportSk, clientPk));
  } catch (exc) { emit({ ev: 'decrypt_error', scheme, error: String(exc.message).slice(0, 60), client: clientPk.slice(0, 8) }); return; }
  let req;
  try { req = JSON.parse(plaintext); if (typeof req.id !== 'string' || typeof req.method !== 'string') throw new Error('forma'); }
  catch { emit({ ev: 'request_malformed', scheme, plaintext_sha256: sha(plaintext) }); return; }
  const params = req.params ?? [];
  emit({ ev: 'request', method: req.method, scheme, req_id: req.id, client: clientPk.slice(0, 8), plaintext_sha256: sha(plaintext), nparams: params.length });
  await respond(clientPk, req.id, req.method, runMethod(req.method, params, clientPk), scheme);
}

ws.addEventListener('message', (m) => {
  const msg = JSON.parse(m.data);
  if (msg[0] === 'EOSE' && msg[1] === 's1') {
    const uri = `bunker://${transportPk}?relay=${encodeURIComponent(RELAY_URL)}` + (secret ? `&secret=${secret}` : '');
    writeFileSync('/ctl/identity.txt', identityPk);
    writeFileSync('/ctl/bunker.txt', uri);
    emit({ ev: 'ready', transport_pub8: transportPk.slice(0, 8), identity_pub8: identityPk.slice(0, 8), transport_pub: transportPk, identity_pub: identityPk, reply_mode: REPLY_MODE, fault: FAULT, jitter_ms: JITTER_MS, uses_secret: USE_SECRET });
  } else if (msg[0] === 'EVENT') {
    handleEvent(msg[2]).catch((exc) => emit({ ev: 'handler_error', error: String(exc.message).slice(0, 80) }));
  } else if (msg[0] === 'OK') {
    emit({ ev: 'relay_ok', id: String(msg[1]).slice(0, 16), accepted: msg[2], message: String(msg[3]).slice(0, 60) });
  } else if (msg[0] === 'CLOSED' || msg[0] === 'NOTICE') {
    emit({ ev: 'relay_notice', tipo: msg[0], message: String(msg[msg.length - 1]).slice(0, 80) });
  }
});
ws.send(JSON.stringify(['REQ', 's1', { kinds: [24133], '#p': [transportPk] }]));
process.on('SIGTERM', () => process.exit(0));
