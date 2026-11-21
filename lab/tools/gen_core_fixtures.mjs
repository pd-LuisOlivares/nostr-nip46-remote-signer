// Generador de fixtures de interoperabilidad para las pruebas del nucleo Nostr (Fase 1.0B, Bloque B1).
// Usa Node 22 y nostr-tools 2.16.2 (la implementacion que usa el cliente NDK de Stacker News), SIN red.
// Claves de JUGUETE (0x...01, 0x...02, 0x...03): nunca claves reales. Genera JSON por la salida estandar:
//   docker run --rm -i --network none nip46-lab-node:1.0a node --input-type=module < lab/tools/gen_core_fixtures.mjs > tests/nostr/fixtures/nostr_tools_fixtures.json
// Los textos de prueba y las claves estan fijos; los IV/nonces los elige la biblioteca, de modo que el archivo generado es una
// FOTOGRAFIA (no se regenera en las pruebas). Proveniencia: ver tests/nostr/fixtures/README.md.
import { nip04, nip44, nip19, getPublicKey } from 'nostr-tools';
const bytesToHex = (b) => Buffer.from(b).toString('hex');
const hexToBytes = (h) => Uint8Array.from(Buffer.from(h, 'hex'));

const sk = (n) => hexToBytes(n.toString(16).padStart(64, '0'));
const SK1 = sk(1), SK2 = sk(2), SK3 = sk(3);
const PK1 = getPublicKey(SK1), PK2 = getPublicKey(SK2), PK3 = getPublicKey(SK3);

// --- 1. Serializacion NIP-01: JSON.stringify de [0, pubkey, created_at, kind, tags, content] ---
const ctrl = Array.from({ length: 32 }, (_, i) => String.fromCharCode(i));
const contents = [
  'hola', '', 'comillas " y barra \\ y barra / ', 'linea1\nlinea2\r\n\ttab', '\b\f', 'nulo \u0000 fin', ctrl.join(''), 'del \u007f',
  '   separadores', 'ñandú 漢字 😀 é', 'sol 🌞', '</script> <b>&amp;</b>', 'Stacker News Authentication',
  ...ctrl.map((c, i) => `ctl${i}:${c}:fin`),
];
const tagSets = [
  [], [['challenge', 'ab'.repeat(32)], ['u', 'https://stacker.news'], ['method', 'GET']], [['t', 'comillas " \\ \n'], ['e']], [['p', 'ñ漢😀', '\u0001']],
];
const serialization = [];
for (const content of contents) {
  for (const tags of tagSets.slice(0, content.length > 40 ? 1 : 4)) {
    serialization.push({ pubkey: PK1, created_at: 1800000000, kind: 27235, tags, content, expected: JSON.stringify([0, PK1, 1800000000, 27235, tags, content]) });
  }
}

// --- 2. NIP-04 (nostr-tools): SK1 -> PK2, la prueba descifra con SK2 y PK1 ---
const plain04 = ['hola', 'ñandú 漢字 😀', 'x'.repeat(300), '{"id":"1","method":"connect","params":["","secreto"]}'];
const nip04Cases = [];
for (const text of plain04) {
  const payload = await nip04.encrypt(SK1, PK2, text);
  nip04Cases.push({ sender_sk: bytesToHex(SK1), recipient_sk: bytesToHex(SK2), sender_pub: PK1, recipient_pub: PK2, plaintext: text, payload });
}

// --- 3. NIP-44 v2 (nostr-tools): SK1 <-> PK2; la prueba descifra con SK2 y PK1 ---
const ck12 = nip44.v2.utils.getConversationKey(SK1, PK2);
const nip44Cases = [];
for (const text of ['hola', 'ñandú 漢字 😀', 'y'.repeat(1000)]) {
  nip44Cases.push({ sender_sk: bytesToHex(SK1), recipient_sk: bytesToHex(SK2), sender_pub: PK1, recipient_pub: PK2, plaintext: text,
                    payload: nip44.v2.encrypt(text, ck12) });
}

// --- 4. NIP-19 ---
const nip19Cases = [SK1, SK2, SK3].map((s) => ({ secret_hex: bytesToHex(s), nsec: nip19.nsecEncode(s), pubkey_hex: getPublicKey(s), npub: nip19.npubEncode(getPublicKey(s)) }));

console.log(JSON.stringify({
  generator: 'lab/tools/gen_core_fixtures.mjs', nostr_tools: '2.16.2', node: process.version,
  serialization, nip04: nip04Cases, nip44: nip44Cases, nip19: nip19Cases,
}, null, 1));
