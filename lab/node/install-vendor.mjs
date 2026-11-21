// Instala node_modules desde tarballs YA descargados y verificados (sin npm, sin red, sin scripts).
// Se ejecuta durante `docker build --network=none`. Re-verifica sha512 antes de extraer.
import { readFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const man = JSON.parse(readFileSync('/lab/deps/artifacts.json', 'utf8'));
const dir = '/lab/vendor/npm';
let count = 0;
for (const it of man.npm.installs) {
  const meta = man.npm.tarballs[it.tarball];
  const file = `${dir}/${it.tarball}`;
  const got = 'sha512-' + createHash('sha512').update(readFileSync(file)).digest('base64');
  if (got !== meta.integrity) { console.error(`INTEGRIDAD INVALIDA: ${it.tarball}`); process.exit(1); }
  const entries = execFileSync('tar', ['-tzf', file], { encoding: 'utf8', maxBuffer: 1 << 26 }).split('\n').filter(Boolean);
  if (entries.some((e) => !e.startsWith('package/') || e.split('/').includes('..'))) {
    console.error(`ENTRADA SOSPECHOSA EN ${it.tarball}`); process.exit(1);
  }
  const target = `/lab/node/${it.path}`;
  mkdirSync(target, { recursive: true });
  execFileSync('tar', ['-xzf', file, '-C', target, '--strip-components=1', '--no-same-owner', '--no-same-permissions']);
  const pj = JSON.parse(readFileSync(`${target}/package.json`, 'utf8'));
  if (pj.name !== it.name || pj.version !== it.version) {
    console.error(`NOMBRE/VERSION NO COINCIDE: ${it.path} -> ${pj.name}@${pj.version}`); process.exit(1);
  }
  count++;
}
console.log(`verificados e instalados: ${count} entradas (${Object.keys(man.npm.tarballs).length} tarballs unicos)`);
