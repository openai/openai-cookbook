import { lstatSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { crc32, deflateRawSync } from 'node:zlib';

const MAX_UINT32 = 0xffff_ffff;

// A deterministic ZIP writer for the Lambda package, using standard DEFLATE,
// UTF-8 names, fixed dates and regular-file permissions. ZIP64 archives are rejected.
export function createZip(directory) {
  const names = [];
  function visit(path, name = '') {
    const entry = lstatSync(path);
    if (entry.isSymbolicLink()) throw new Error(`Symbolic links are not allowed in ZIP: ${name || '.'}`);
    if (entry.isDirectory()) {
      for (const child of readdirSync(path).sort()) {
        if (child.includes('\\') || child.includes(':')) throw new Error(`Invalid ZIP filename: ${child}`);
        visit(join(path, child), name ? `${name}/${child}` : child);
      }
    } else if (entry.isFile() && name) names.push(name);
    else throw new Error(`Not a regular ZIP input: ${name || '.'}`);
  }
  visit(directory);
  if (names.length >= 0xffff) throw new Error('ZIP64 entry count is not supported');

  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const name of names.sort()) {
    const filename = Buffer.from(name, 'utf8');
    if (filename.length > 0xffff) throw new Error('ZIP filename is too long');
    const data = readFileSync(join(directory, ...name.split('/')));
    const compressed = deflateRawSync(data, { level: 9 });
    if (data.length >= MAX_UINT32 || compressed.length >= MAX_UINT32) throw new Error('ZIP64 file size is not supported');
    const checksum = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6); // UTF-8.
    local.writeUInt16LE(8, 8); // DEFLATE.
    local.writeUInt16LE(0x2821, 12); // 2000-01-01, midnight.
    local.writeUInt32LE(checksum, 14);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(filename.length, 26);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE((3 << 8) | 20, 4); // Unix regular-file permissions on all hosts.
    local.copy(central, 6, 4, 30);
    central.writeUInt32LE((0o100644 << 16) >>> 0, 38);
    central.writeUInt32LE(offset, 42);
    localParts.push(local, filename, compressed);
    centralParts.push(central, filename);
    offset += local.length + filename.length + compressed.length;
    if (offset >= MAX_UINT32) throw new Error('ZIP64 archive size is not supported');
  }
  const centralDirectory = Buffer.concat(centralParts);
  if (offset + centralDirectory.length >= MAX_UINT32) throw new Error('ZIP64 archive size is not supported');
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(names.length, 8);
  end.writeUInt16LE(names.length, 10);
  end.writeUInt32LE(centralDirectory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...localParts, centralDirectory, end]);
}
