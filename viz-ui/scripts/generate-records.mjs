import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const generated = JSON.parse(execFileSync('cargo', ['run', '--quiet', '--manifest-path',
  resolve(root, 'kernel/Cargo.toml'), '--example', 'record_descriptions', '--', 'bundle'],
{ encoding: 'utf8', cwd: root }));
const outputs = [
  ['viz-ui/packages/components/src/generated/record.ts', generated.typescript],
  ['kernel/generated/record.schema.json', `${JSON.stringify(generated.schema, null, 2)}\n`],
];
for (const [relative, content] of outputs) {
  const path = resolve(root, relative);
  if (process.argv.includes('--check')) {
    if (readFileSync(path, 'utf8') !== content) throw new Error(`Regenerate ${relative}`);
  } else {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
}
