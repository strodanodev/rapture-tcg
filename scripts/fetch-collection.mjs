// Download the Rapture ARC 1 collection snapshot and its card art from the Forge hall into collection/ (gitignored).
// The art is © LitVM Games and is never committed: every build fetches it.
//
//   node scripts/fetch-collection.mjs [--from https://forge.litvm.games]
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const i = process.argv.indexOf('--from');
const BASE = (i > 0 ? process.argv[i + 1] : 'https://forge.litvm.games').replace(/\/+$/, '');
const OUT = join(ROOT, 'collection');

const get = async (url) => {
  for (let attempt = 0; ; attempt++) {
    const r = await fetch(url);
    if (r.ok) return r;
    if (attempt >= 3) throw new Error(`${url}: HTTP ${r.status}`);
    await new Promise((res) => setTimeout(res, 1000 * 2 ** attempt));
  }
};

const snapshot = await (await get(`${BASE}/assets/rapture/cards.json`)).json();
const save = (rel, data) => {
  const path = normalize(join(OUT, rel));
  if (!path.startsWith(OUT + sep)) throw new Error(`refusing to write outside collection/: ${rel}`);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, data);
};
save('assets/rapture/cards.json', JSON.stringify(snapshot, null, 2));
let n = 0;
for (const card of snapshot.cards) {
  // Art paths are relative to the site root, like ./assets/rapture/art/<name>.webp; only those are fetched.
  const rel = String(card.art ?? '').replace(/^\.\//, '');
  if (!/^assets\/rapture\/art\/[a-z0-9._-]+\.(webp|png|jpg)$/i.test(rel)) continue;
  save(rel, Buffer.from(await (await get(`${BASE}/${rel}`)).arrayBuffer()));
  n++;
}
console.log(`collection/: ${snapshot.cards.length} cards, ${n} art files from ${BASE}`);
