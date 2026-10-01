import { readFile, writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Relights one still with Grok Imagine 2.0 (image edit). Used to design lighting on a key frame,
// which tools/ai_light_composite.py then extracts and tracks onto the real footage.
// Usage: npx tsx relight-still.ts <frame.png> <prompt.txt> <out.png>
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'xai/grok-imagine-image-2.0';

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [frame, promptFile, out] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!frame || !promptFile || !out) { console.error('Usage: npx tsx relight-still.ts <frame.png> <prompt.txt> <out.png>'); return 1; }

  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 10 * 60 * 1000, pollInterval: 4000 });
  const result = await client.subscribe(MODEL, {
    input: {
      prompt: (await readFile(promptFile, 'utf8')).trim(),
      image_urls: [await uploadImage(frame, creds)],
      aspect_ratio: '9:16',
      resolution: '2k',
    },
    withPolling: true,
  });
  const url = result.images?.[0]?.url;
  if (result.status !== 'completed' || !url) {
    const detail = (result as { error?: string }).error;
    console.error(`Relight did not succeed: ${result.status}${detail ? `: ${detail}` : ''}.`);
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
