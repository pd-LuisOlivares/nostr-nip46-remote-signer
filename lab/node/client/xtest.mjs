// Prueba cruzada E5 (NIP-44) y E5b (NIP-04): nostr-tools 2.16.2 <-> Python. Claves de JUGUETE fijas y publicas
// (las de los vectores oficiales: 0x...01 y 0x...02). Uso: node client/xtest.mjs encrypt | decrypt  (JSON por stdin/stdout)
import { nip04, nip44, getPublicKey } from 'nostr-tools';
import { readFileSync } from 'node:fs';

const hexToBytes = (h) => Uint8Array.from(Buffer.from(h, 'hex'));  // sin depender de @noble/hashes (solo existe anidado)

const SK_A = hexToBytes('0000000000000000000000000000000000000000000000000000000000000001');
const SK_B = hexToBytes('0000000000000000000000000000000000000000000000000000000000000002');
const PK_A = getPublicKey(SK_A);
const PK_B = getPublicKey(SK_B);
const uni = 'ñandú 漢字 😀 ✓ “comillas” — fin';
const MESSAGES = {
  '1B': 'a', '32B': 'a'.repeat(32), '33B': 'a'.repeat(33), '1000B': 'a'.repeat(1000),
  unicode: uni, 'unicode~1000B': uni.repeat(Math.ceil(1000 / Buffer.byteLength(uni))),
  '65535B': 'x'.repeat(65535),
};

async function enc(scheme, sk, pk, text) {
  return scheme === 'nip04' ? await nip04.encrypt(sk, pk, text) : nip44.v2.encrypt(text, nip44.v2.utils.getConversationKey(sk, pk));
}
async function dec(scheme, sk, pk, payload) {
  return scheme === 'nip04' ? await nip04.decrypt(sk, pk, payload) : nip44.v2.decrypt(payload, nip44.v2.utils.getConversationKey(sk, pk));
}

const mode = process.argv[2];
if (mode === 'encrypt') {          // A cifra hacia B (Python descifra con la clave B)
  const items = [];
  for (const scheme of ['nip44', 'nip04'])
    for (const [name, plaintext] of Object.entries(MESSAGES))
      items.push({ name, scheme, plaintext, payload: await enc(scheme, SK_A, PK_B, plaintext) });
  console.log(JSON.stringify({ origin: 'nostr-tools', items }));
} else if (mode === 'decrypt') {   // Python cifro hacia A; Node descifra con la clave A
  const input = JSON.parse(readFileSync(0, 'utf8'));
  const results = [];
  for (const it of input.items) {
    try { const out = await dec(it.scheme, SK_A, PK_B, it.payload); results.push({ name: it.name, scheme: it.scheme, ok: out === it.plaintext }); }
    catch (e) { results.push({ name: it.name, scheme: it.scheme, ok: false, error: String(e.message).slice(0, 60) }); }
  }
  console.log(JSON.stringify({ origin: 'nostr-tools', decrypted_python_payloads: results }));
} else { console.error('uso: encrypt | decrypt'); process.exit(2); }
