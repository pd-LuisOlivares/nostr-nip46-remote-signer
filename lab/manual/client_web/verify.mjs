// B6.1D-R3: verificacion CRIPTOGRAFICA de la respuesta `sign_event` de un firmante NIP-46. Modulo puro (sin red, sin estado, sin NDK).
// Una firma se muestra como exitosa SOLO si TODAS las comprobaciones pasan; nunca por el mero hecho de haber recibido una respuesta.
import { schnorr } from '@noble/curves/secp256k1';
import { createHash } from 'node:crypto';

const HEX64 = /^[0-9a-f]{64}$/;
const HEX128 = /^[0-9a-f]{128}$/;

export const sha256hex = (text) => createHash('sha256').update(text, 'utf8').digest('hex');

/** Identificador de un evento Nostr (NIP-01): SHA-256 de la serializacion canonica. */
export const eventId = (e) => sha256hex(JSON.stringify([0, e.pubkey, e.created_at, e.kind, e.tags, e.content]));

const sameTags = (a, b) => Array.isArray(a) && Array.isArray(b) && JSON.stringify(a) === JSON.stringify(b);

/**
 * @param {string} resultText  campo `result` de la respuesta NIP-46 (el evento firmado, serializado)
 * @param {{id:string,pubkey:string,created_at:number,kind:number,tags:string[][],content:string}} template  lo que SE SOLICITO firmar
 * @param {string} identity  clave publica que el firmante declaro en `get_public_key` (NO la que venga en la respuesta)
 * @returns {{ok:boolean, checks:Record<string,boolean>, event:null|{id16:string,pubkey8:string,kind:number}}}
 */
export function verifySignedResponse(resultText, template, identity) {
  const checks = {
    json_valido: false, campos_validos: false, id_ok: false, sig_ok: false, pubkey_es_la_identidad: false, plantilla_coincide: false, reto_coincide: false,
  };
  let e;
  try { e = JSON.parse(resultText); checks.json_valido = e !== null && typeof e === 'object' && !Array.isArray(e); } catch { return { ok: false, checks, event: null }; }
  if (!checks.json_valido) return { ok: false, checks, event: null };
  checks.campos_validos = HEX64.test(String(e.id)) && HEX64.test(String(e.pubkey)) && HEX128.test(String(e.sig)) && Number.isInteger(e.kind)
    && Number.isInteger(e.created_at) && typeof e.content === 'string' && Array.isArray(e.tags) && e.tags.every((t) => Array.isArray(t) && t.every((x) => typeof x === 'string'));
  if (checks.campos_validos) {
    checks.id_ok = eventId(e) === e.id;
    try { checks.sig_ok = schnorr.verify(e.sig, e.id, e.pubkey) === true; } catch { checks.sig_ok = false; }
    checks.pubkey_es_la_identidad = HEX64.test(String(identity)) && e.pubkey === identity;
    checks.plantilla_coincide = e.id === template.id && e.kind === template.kind && e.created_at === template.created_at && e.content === template.content
      && e.pubkey === template.pubkey && sameTags(e.tags, template.tags);
    checks.reto_coincide = Array.isArray(e.tags[0]) && e.tags[0].length === 2 && e.tags[0][0] === 'challenge' && e.tags[0][1] === (template.tags[0] ?? [])[1];
  }
  const ok = Object.values(checks).every(Boolean);
  return { ok, checks, event: checks.campos_validos ? { id16: e.id.slice(0, 16), pubkey8: e.pubkey.slice(0, 8), kind: e.kind } : null };
}
