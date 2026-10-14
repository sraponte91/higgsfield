import { readFile, writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Generates one 9:16 still with Grok Imagine 2.0 from a prompt and reference images (identity, set, look).
// Used for storyboard frames of planned shots.
// Usage: npx tsx gen-image.ts <prompt.txt> <out.png> [ref.jpg ...]   (ASPECT=3:4 to change the 9:16 default)
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'xai/grok-imagine-image-2.0';

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [promptFile, out, ...refs] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!promptFile || !out) { console.error('Usage: npx tsx gen-image.ts <prompt.txt> <out.png> [ref.jpg ...]'); return 1; }

  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 10 * 60 * 1000, pollInterval: 4000 });
  const result = await client.subscribe(MODEL, {
    input: {
      prompt: (await readFile(promptFile, 'utf8')).trim(),
      ...(refs.length ? { image_urls: await Promise.all(refs.map((r) => uploadImage(r, creds))) } : {}),
      aspect_ratio: process.env.ASPECT || '9:16',
      resolution: '2k',
    },
    withPolling: true,
  });
  const url = result.images?.[0]?.url;
  if (result.status !== 'completed' || !url) {
    const detail = (result as { error?: string }).error;
    console.error(`Generation did not succeed: ${result.status}${detail ? `: ${detail}` : ''}.`);
    return 1;
  }
  const img = await fetch(url);
  if (!img.ok) { console.error(`Download failed (HTTP ${img.status}).`); return 1; }
  await writeFile(out, Buffer.from(await img.arrayBuffer()));
  console.log(`Saved ${out}`);
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    console.error('Error:', error instanceof Error ? error.message : 'unexpected error');
    process.exit(1);
  });
