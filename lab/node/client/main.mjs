// Arnes cliente del laboratorio: NDK 2.12.2 REAL (NDKNip46Signer) replicando el camino de Stacker News.
//  - parche de URL identico a stacker.news lib/nostr.js:196-202 (bunker:// -> http://)
//  - evento de login identico a components/nostr-auth.js:148-157
//  - comprobaciones de servidor identicas a pages/api/auth/[...nextauth].js:241-270 (mismo @noble/curves)
// Instrumentacion: se ENVUELVEN metodos de la instancia (encrypt/decrypt/parseEvent/sendRequest) para
// registrar esquemas y transiciones SIN modificar el codigo de NDK y SIN registrar texto plano
// (solo SHA-256 del texto plano, para compararlo con el que descifra el firmante).
import NDK, { NDKEvent, NDKNip46Signer } from '@nostr-dev-kit/ndk';
import { schnorr } from '@noble/curves/secp256k1';
import { createHash, randomBytes } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const SCENARIO = process.env.SCENARIO ?? 'e1';
const TIMEOUT_MS = Number(process.env.TIMEOUT_MS ?? 15000);
const N_SIGN = Number(process.env.N_SIGN ?? 20);
const emit = (o) => console.log(JSON.stringify({ ts: new Date().toISOString(), actor: 'client', ...o }));
const sha = (s) => createHash('sha256').update(s, 'utf8').digest('hex');
const pkgVersion = (name) => JSON.parse(readFileSync(`/lab/node/node_modules/${name}/package.json`, 'utf8')).version;

process.on('unhandledRejection', (e) => emit({ ev: 'unhandled_rejection', error: String(e?.message ?? e).slice(0, 120) }));

// Ensayo interactivo (Compuerta B local): BUNKER_FROM_STDIN=1 -> la URI llega por la ENTRADA ESTANDAR (nunca por archivo) y la identidad
// se toma del propio firmante tras connect/get_public_key. Por defecto, igual que antes: /ctl/bunker.txt e /ctl/identity.txt.
const FROM_STDIN = process.env.BUNKER_FROM_STDIN === '1';
let token; let identity;
if (FROM_STDIN) {
  token = await new Promise((resolve) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (d) => { buf += d; if (buf.includes(String.fromCharCode(10))) resolve(buf.split(String.fromCharCode(10))[0].trim()); });
    process.stdin.on('end', () => resolve(buf.trim()));
  });
  identity = '';
} else {
  for (let i = 0; i < 300 && !existsSync('/ctl/bunker.txt'); i++) await sleep(100);
  if (!existsSync('/ctl/bunker.txt')) { emit({ ev: 'fatal', error: 'no aparecio /ctl/bunker.txt (el firmante no esta listo)' }); process.exit(2); }
  token = readFileSync('/ctl/bunker.txt', 'utf8').trim();
  identity = readFileSync('/ctl/identity.txt', 'utf8').trim();
}

// === igual que stacker.news lib/nostr.js:196-202 ===
class NDKNip46SignerURLPatch extends NDKNip46Signer {
  connectionTokenInit(connectionToken) {
    connectionToken = connectionToken.replace('bunker://', 'http://');
    return super.connectionTokenInit(connectionToken);
  }
}

const ndk = new NDK({ autoConnectUserRelays: false, autoFetchUserMutelist: false, clientName: 'nip46-lab' });
const signer = new NDKNip46SignerURLPatch(ndk, token);
const rpc = signer.rpc;
const local = signer.localSigner;
const clientPub = (await local.user()).pubkey;

// --- instrumentacion ---
const origEnc = local.encrypt.bind(local);
local.encrypt = async (recipient, value, scheme) => {
  const out = await origEnc(recipient, value, scheme);
  emit({ ev: 'ndk_encrypt', scheme: scheme ?? 'undefined', plaintext_sha256: sha(value), plaintext_len: value.length });
  return out;
};
const origDec = local.decrypt.bind(local);
local.decrypt = async (sender, value, scheme) => {
  try {
    const out = await origDec(sender, value, scheme);
    emit({ ev: 'ndk_decrypt', scheme: scheme ?? 'undefined', ok: true, plaintext_sha256: sha(out), sender8: sender.pubkey.slice(0, 8) });
    return out;
  } catch (e) {
    emit({ ev: 'ndk_decrypt', scheme: scheme ?? 'undefined', ok: false, error: String(e?.message ?? e).slice(0, 80) });
    throw e;
  }
};
const origParse = rpc.parseEvent.bind(rpc);
rpc.parseEvent = async (ev) => {
  const before = rpc.encryptionType;
  const contentScheme = ev.content.includes('?iv=') ? 'nip04' : 'nip44-like';
  try {
    const r = await origParse(ev);
    emit({ ev: 'ndk_parse', before, after: rpc.encryptionType, content_scheme: contentScheme, author8: ev.pubkey.slice(0, 8), ok: true, req_id: r.id });
    return r;
  } catch (e) {
    emit({ ev: 'ndk_parse', before, after: rpc.encryptionType, content_scheme: contentScheme, author8: ev.pubkey.slice(0, 8), ok: false, error: String(e?.message ?? e).slice(0, 80) });
    throw e;
  }
};
const origSend = rpc.sendRequest.bind(rpc);
rpc.sendRequest = (remote, method, params, kind, cb) => {
  emit({ ev: 'ndk_request', method, encryption_type: rpc.encryptionType, nparams: params.length });
  return origSend(remote, method, params, kind, cb);
};
signer.on('authUrl', (url) => emit({ ev: 'authUrl', url: String(url).slice(0, 80) }));

emit({
  ev: 'start', scenario: SCENARIO, client_pub8: clientPub.slice(0, 8), client_pub: clientPub,
  initial_encryption_type: rpc.encryptionType, bunker_relays: signer.relayUrls, uses_secret: token.includes('secret='),
  versions: { node: process.version, ndk: pkgVersion('@nostr-dev-kit/ndk'), nostr_tools: pkgVersion('nostr-tools'), noble_curves: pkgVersion('@noble/curves') },
});

// === igual que stacker.news nostr-auth.js:148-157 + comprobaciones de [...nextauth].js:241-270 ===
async function signLogin(label) {
  const k1 = randomBytes(32).toString('hex');
  const event = new NDKEvent(ndk, {
    kind: 27235,
    created_at: Math.floor(Date.now() / 1000),
    tags: [['challenge', k1], ['u', 'https://sn.lab.invalid'], ['method', 'GET']],
    content: 'Stacker News Authentication',
  });
  await event.sign(signer);
  const e = event.rawEvent();
  const id = createHash('sha256').update(JSON.stringify([0, e.pubkey, e.created_at, e.kind, e.tags, e.content])).digest('hex');
  const sig_ok = await schnorr.verify(e.sig, e.id, e.pubkey);
  const r = {
    label, event_id: e.id.slice(0, 16), pubkey8: e.pubkey.slice(0, 8), pubkey_is_identity: e.pubkey === identity,
    id_ok: id === e.id, sig_ok, tags0_ok: e.tags[0].length === 2 && e.tags[0][0] === 'challenge' && e.tags[0][1] === k1,
    kind: e.kind, content_ok: e.content === 'Stacker News Authentication',
  };
  r.all_ok = r.pubkey_is_identity && r.id_ok && r.sig_ok && r.tags0_ok;
  return r;
}

// === Fase 1.0A.2 (e8/e9): variantes del evento de login contra el firmante REAL minimo ===
const SIGN_TIMEOUT_MS = Number(process.env.SIGN_TIMEOUT_MS ?? 6000);
const ORIGIN = 'https://sn.lab.invalid';
async function signVariant(label, over = {}) {
  const k1 = over.k1 ?? randomBytes(32).toString('hex');
  const now = Math.floor(Date.now() / 1000);
  const base = [['challenge', over.challenge ?? k1], ['u', over.u ?? ORIGIN], ['method', over.method ?? 'GET']];
  const tags = over.tags === 'extra' ? [...base, ['t', 'extra']] : over.tags === 'swapped' ? [base[1], base[0], base[2]] : base;
  const event = new NDKEvent(ndk, { kind: over.kind ?? 27235, created_at: now + (over.age ?? 0), tags, content: over.content ?? 'Stacker News Authentication' });
  const t = Date.now();
  try {
    await withTimeout(event.sign(signer), SIGN_TIMEOUT_MS);
    const e = event.rawEvent();
    const id = createHash('sha256').update(JSON.stringify([0, e.pubkey, e.created_at, e.kind, e.tags, e.content])).digest('hex');
    const sig_ok = await schnorr.verify(e.sig, e.id, e.pubkey);
    return { label, k1, signed: true, ms: Date.now() - t, id_ok: id === e.id, sig_ok, pubkey_is_identity: e.pubkey === identity,
             tags_n: e.tags.length, tags_unchanged: JSON.stringify(e.tags) === JSON.stringify(tags) };
  } catch (err) {
    return { label, k1, signed: false, ms: Date.now() - t, error: String(err?.message ?? err).slice(0, 60) };
  }
}
const E8_VARIANTS = [
  ['wrong_origin', { u: 'https://evil.invalid' }], ['wrong_content', { content: 'otro texto' }], ['wrong_method', { method: 'POST' }],
  ['extra_tag', { tags: 'extra' }], ['wrong_kind', { kind: 1 }], ['stale', { age: -600 }], ['future', { age: 60 }],
  ['bad_challenge', { challenge: 'XYZ' }], ['tag_order', { tags: 'swapped' }],
];

const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('TIMEOUT')), ms))]);

// NDKUser.pubkey es un getter que LANZA ("npub not set") si la clave es indefinida: se lee de forma segura.
function readPubkey(u) {
  try { return { value: u.pubkey, type: typeof u.pubkey, threw: null }; }
  catch (e) { return { value: undefined, type: 'threw', threw: String(e?.message ?? e).slice(0, 60) }; }
}

const t0 = Date.now();
let user; let error;
try { user = await withTimeout(signer.blockUntilReady(), TIMEOUT_MS); } catch (e) { error = e; }
const pk = user === undefined ? { value: undefined, type: 'no_user', threw: null } : readPubkey(user);
if (FROM_STDIN && typeof pk.value === 'string' && pk.value) identity = pk.value;
emit({
  ev: 'ready_result', ok: user !== undefined, user_pub8: typeof pk.value === 'string' && pk.value ? pk.value.slice(0, 8) : null,
  user_pub_type: pk.type, pubkey_getter_error: pk.threw, matches_identity: pk.value === identity,
  error: error === undefined ? null : String(error?.message ?? error).slice(0, 80), error_type: error === undefined ? null : typeof error,
  ms: Date.now() - t0, encryption_type: rpc.encryptionType,
});

if (user !== undefined && pk.value === identity) {
  if (SCENARIO === 'e2' || SCENARIO === 'e4' || SCENARIO === 'e3') {
    try { emit({ ev: 'login_event', ...(await withTimeout(signLogin('single'), TIMEOUT_MS)), encryption_type: rpc.encryptionType }); }
    catch (e) { emit({ ev: 'login_event', error: String(e?.message ?? e).slice(0, 80), encryption_type: rpc.encryptionType }); }
  } else if (SCENARIO === 'e8') {
    // Politica: 9 variantes invalidas (deben rechazarse sin pregunta), una valida (se firma) y la REPETICION del reto firmado.
    for (const [label, over] of E8_VARIANTS) emit({ ev: 'variant', ...(await signVariant(label, over)) });
    const ok = await signVariant('valid');
    emit({ ev: 'variant', ...ok });
    emit({ ev: 'variant', ...(await signVariant('replay_same_challenge', { k1: ok.k1 })) });
  } else if (SCENARIO === 'e9') {
    // Aprobacion humana: 5 solicitudes validas con distinto reto (el guion del firmante decide: n, timeout, s, s, tope).
    for (const label of ['a', 'b', 'c', 'd', 'e']) emit({ ev: 'variant', ...(await signVariant(`valid_${label}`)) });
  } else if (SCENARIO === 'e6') {
    const res = await Promise.allSettled(Array.from({ length: N_SIGN }, (_, i) => withTimeout(signLogin(`c${i}`), TIMEOUT_MS)));
    const ok = res.filter((r) => r.status === 'fulfilled' && r.value.all_ok).length;
    emit({ ev: 'burst_result', requested: N_SIGN, fulfilled: res.filter((r) => r.status === 'fulfilled').length, all_ok: ok,
           rejected: res.filter((r) => r.status === 'rejected').map((r) => String(r.reason?.message ?? r.reason).slice(0, 60)), encryption_type: rpc.encryptionType });
  }
}
await sleep(800);  // deja llegar respuestas tardias (duplicados, etc.)
emit({ ev: 'end', encryption_type: rpc.encryptionType });
process.exit(0);
