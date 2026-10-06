import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

// Reviewed presentation assets belong to these exact prepared examples. They
// are not migrations: a later owner edit/upload always keeps its own design.
// Hashes describe source and image bytes, never visitor state or revision IDs.
const definitions = {
  mira: {
    sources: ['e8e9013b80e37e6249f6afc88d39db3c08e6b2cd48b3116fb1a9bf572a3fee0f'],
    icon: '44bc59763951041d04098e7aef098ad2d467ea4865bff42585a033faebc01d04',
  },
  james: {
    sources: ['66c3ec7cccef57f338a78c7b57ebf21e7b7a11028bcaada8c84da80837a1e98c'],
    icon: '66b3ab46e61d01ebb9e55287f5436c6db8cd9c036bb6229944374b3ed78c1fcd',
  },
  jake: {
    sources: ['fb933f33056715589467d0b10823ddaa29513c4b1178f9ca77e73980b1207532'],
    icon: '36ea192212fe13bf9522322eac159e73da8b3a477ce511b297aff19302b70f1f',
  },
  erica: {
    sources: ['5c45b2317e455275daa87067e1ae04c8e153c2479e78ee432a147a31bf488043'],
    icon: '6d8895dd88edd74f90e24202ea99e01fcc9a0ed98501daf905daf7ca3cc7a779',
  },
  iris: {
    sources: ['1be66d5a3e887a6569f71c18056e0819aae4c06fc3d12d9a87a03976242a53ef',
      '769e1753533500e7b086f36066b7a2d1ac9bda1d5ac3609141d50b6dfa2adc4d',
      '81aeea2fee12eef9e170f331d33ce31d137eeb3c6bd461917a4fd93bfc8f3250',
      '82f68aa15b8c2437a9ac8a0f3c6caed1994ef979bb632fcabfd1716d122b79e8'],
    icon: 'c663825d25b601b05bd233da19aa1b9f8a160458e13b100f2725276325b73f68',
  },
  luca: {
    sources: ['341eeb3da0fc7e9cdb2e128405d20bb1d1d36dc2c65c4fcba385d6d86ab75578'],
    icon: '3ab7e034b0887e166e2e7fa60302b37272f34f952b74dd3cc4badfa08e3d868c',
  },
  karen: {
    sources: ['454a062d0ca3099796e9b90b17500a13673070d84ca027a998dddefc6c7bf7aa',
      '630a6b9d84bd8e15b6f69d1d0db1223351d247bbcfafd97dbbd36f148b8f4d78'],
    icon: 'bd220bbeaaf31817eaf9a7a956d25b6a8261390a405094231d5b2d7b7af243d1',
  },
  nora: {
    sources: [
      'a230a2ea29be438efa70e5faf69dc90863fe51223967e5da00453dcf1b6fc88d',
      '8979a482a503e618837c5c9e591df3577a33376ded81e3e6ed32c4e1d47aa286',
      'e5158893340862256289c0da1d53d2b2670a014e83bd90d686080ef0abde5280',
    ],
    icon: '6e0c196d14fc11a7a96f0e89749d9ad2c39d510fb2a77008aa54727598327cf6',
  },
};
const hash = value => createHash('sha256').update(value).digest('hex');
const styles = new Map(await Promise.all(Object.keys(definitions).map(async id => [
  id, await readFile(new URL(`./demo-appearance/${id}.css`, import.meta.url), 'utf8'),
])));
const presentationCss = (await Promise.all(['shared', 'nature-finance', 'creative'].map(name =>
  readFile(new URL(`./demo-presentation/${name}.css`, import.meta.url), 'utf8'),
))).join('\n');

export function demoAppearanceFor(ownerId, source) {
  const definition = Object.hasOwn(definitions, ownerId) ? definitions[ownerId] : undefined;
  if (!definition || typeof source !== 'string') return undefined;
  // A resolution-only edit should not discard the prepared light theme or TV
  // typography. All other source bytes must still match the reviewed canvas.
  let appearanceSource = source;
  if (ownerId === 'iris') {
    appearanceSource = source.replace(/^const (COLUMNS|ROWS) = (\d+);$/gm, (line, name, value) =>
      Number(value) >= 1 && Number(value) <= 256 ? `const ${name} = ${name === 'COLUMNS' ? 48 : 32};` : line);
  }
  if (!definition.sources.includes(hash(appearanceSource))) return undefined;
  return { lightCss: styles.get(ownerId), presentationCss };
}

export function withDemoIconAppearance(ownerId, icon) {
  const definition = Object.hasOwn(definitions, ownerId) ? definitions[ownerId] : undefined;
  const prefix = 'data:image/webp;base64,';
  if (!definition || typeof icon?.dataUrl !== 'string' || !icon.dataUrl.startsWith(prefix)) return icon;
  if (hash(Buffer.from(icon.dataUrl.slice(prefix.length), 'base64')) !== definition.icon) return icon;
  return { ...icon, lightDataUrl: `/space-icons/light/${ownerId}.webp` };
}
