// Pruebas del verificador (ejecutor integrado de Node, SIN red): `node --test web/verify.test.mjs` dentro de la imagen del laboratorio.
import test from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { schnorr } from '@noble/curves/secp256k1';
import { eventId, verifySignedResponse } from './verify.mjs';

const toHex = (u8) => Buffer.from(u8).toString('hex');
const sk = schnorr.utils.randomPrivateKey();
const pubkey = toHex(schnorr.getPublicKey(sk));
const challenge = randomBytes(32).toString('hex');
const base = { pubkey, created_at: 1_800_000_000, kind: 27235, tags: [['challenge', challenge], ['u', 'https://sn.manual.invalid'], ['method', 'GET']], content: 'Stacker News Authentication' };
const template = { ...base, id: eventId(base) };
const sign = (e) => toHex(schnorr.sign(e.id, sk));
const good = { ...template, sig: sign(template) };
const verify = (result, tpl = template, identity = pubkey) => verifySignedResponse(typeof result === 'string' ? result : JSON.stringify(result), tpl, identity);
const flip = (hex) => (hex[0] === 'a' ? 'b' : 'a') + hex.slice(1);

test('una firma correcta, de la identidad y sobre lo solicitado se acepta con TODAS las comprobaciones', () => {
  const r = verify(good);
  assert.equal(r.ok, true);
  assert.ok(Object.values(r.checks).every((v) => v === true), JSON.stringify(r.checks));
  assert.deepEqual(r.event, { id16: template.id.slice(0, 16), pubkey8: pubkey.slice(0, 8), kind: 27235 });
});

test('una firma alterada NO se acepta', () => {
  const r = verify({ ...good, sig: flip(good.sig) });
  assert.equal(r.ok, false);
  assert.equal(r.checks.sig_ok, false);
});

test('un id que no corresponde al contenido NO se acepta (aunque la firma sea del id falso)', () => {
  const fakeId = flip(good.id);
  const r = verify({ ...good, id: fakeId, sig: toHex(schnorr.sign(fakeId, sk)) });
  assert.equal(r.checks.id_ok, false);
  assert.equal(r.ok, false);
});

test('firmado por OTRA clave: la firma es valida pero no es la identidad del firmante', () => {
  const other = schnorr.utils.randomPrivateKey();
  const otherPub = toHex(schnorr.getPublicKey(other));
  const e = { ...base, pubkey: otherPub };
  e.id = eventId(e);
  const r = verify({ ...e, sig: toHex(schnorr.sign(e.id, other)) });
  assert.equal(r.checks.sig_ok, true);
  assert.equal(r.checks.pubkey_es_la_identidad, false);
  assert.equal(r.ok, false);
});

test('un evento valido pero DISTINTO de lo solicitado (contenido, tags, kind o fecha) NO se acepta', () => {
  for (const change of [{ content: 'otro texto' }, { kind: 1 }, { created_at: base.created_at + 1 }, { tags: [['challenge', challenge], ['u', 'https://evil.invalid'], ['method', 'GET']] }]) {
    const e = { ...base, ...change };
    e.id = eventId(e);
    const r = verify({ ...e, sig: sign(e) });
    assert.equal(r.checks.sig_ok, true, JSON.stringify(change));
    assert.equal(r.checks.plantilla_coincide, false, JSON.stringify(change));
    assert.equal(r.ok, false, JSON.stringify(change));
  }
});

test('la respuesta de OTRA solicitud (otro reto) no se acepta como respuesta a esta', () => {
  const otherBase = { ...base, tags: [['challenge', randomBytes(32).toString('hex')], ...base.tags.slice(1)] };
  const other = { ...otherBase, id: eventId(otherBase) };
  const r = verify({ ...other, sig: sign(other) });  // firma valida, de la identidad, pero de OTRA plantilla
  assert.equal(r.ok, false);
  assert.equal(r.checks.plantilla_coincide, false);
  assert.equal(r.checks.reto_coincide, false);
});

test('entradas basura nunca se aceptan ni lanzan excepciones', () => {
  for (const junk of ['', 'texto', 'null', '[]', '42', '{}', '{"id":1}', JSON.stringify({ ...good, sig: 'zz' }), JSON.stringify({ ...good, tags: 'x' }), JSON.stringify({ ...good, kind: '27235' })]) {
    const r = verifySignedResponse(junk, template, pubkey);
    assert.equal(r.ok, false, junk.slice(0, 30));
  }
  assert.equal(verifySignedResponse(JSON.stringify(good), template, 'no-es-hex').ok, false);
  assert.equal(verifySignedResponse(JSON.stringify(good), template, undefined).ok, false);
});
