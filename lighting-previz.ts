import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Lighting look-dev for the "Volatility Now" set: relights one frame several ways
// so the practical lighting can be chosen before the next video generation.
// Usage: npx tsx lighting-previz.ts <frame.jpg> [output-dir]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'xai/grok-imagine-image-2.0';

const KEEP =
  'Keep everything else in the photo exactly the same: same woman, same face, same pose, same grey sweatshirt and ripped jeans, same trader at the right-hand station, same mural, desks, chairs, carpet, camera angle and framing. Only change the lighting. Photoreal, like a real photo of the set, not CG.';

const LOOKS: Record<string, string> = {
  '1-blue-monitor-glow':
    'Add cool blue LED strips hidden behind the six monitors on the left desk, throwing a soft blue glow onto the orange partition and the mural behind the screens. Dim the overhead fluorescent panels to about half so the glow reads. Subtle blue spill on the edge of her hair and shoulders.',
  '2-brand-orange':
    'Add warm orange LED strips hidden behind the six monitors and a matching orange strip under the front edge of the left desk, glowing onto the floor. The orange matches the mural accents and partitions. Dim the overhead fluorescent panels a little. Warm orange rim light on her hair and shoulders.',
  '3-two-tone-social':
    'Turn the overhead fluorescent panels down low. Add teal LED strips behind the six monitors washing the wall teal, and magenta-purple LED strips under both desks glowing onto the carpet. Moody, energetic creator-studio look with strong color contrast; the monitors are the brightest thing in frame.',
  '4-presenter-key-light':
    'Add a soft LED panel with a softbox just off camera to the left, lighting her face evenly and flatteringly with a gentle catchlight in her eyes. Add a vertical RGB light tube standing behind her chair, glowing orange, giving a thin rim light around her hair and shoulders. Overhead fluorescents at about half. Blue LED glow behind the six monitors.',
};

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [frame, outDir = 'lighting-looks'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!frame) { console.error('Usage: npx tsx lighting-previz.ts <frame.jpg> [output-dir]'); return 1; }

  await mkdir(outDir, { recursive: true });
  console.log('Uploading frame...');
  const imageUrl = await uploadImage(frame, creds);
  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 10 * 60 * 1000, pollInterval: 4000 });

  const results = await Promise.allSettled(
    Object.entries(LOOKS).map(async ([name, look]) => {
      const result = await client.subscribe(MODEL, {
        input: { prompt: `${look} ${KEEP}`, image_urls: [imageUrl], aspect_ratio: '9:16', resolution: '2k' },
        withPolling: true,
      });
      const url = result.images?.[0]?.url;
      if (result.status !== 'completed' || !url) throw new Error(`status ${result.status}`);
      const img = await fetch(url);
      if (!img.ok) throw new Error(`download failed (HTTP ${img.status})`);
      const file = join(outDir, `${name}.png`);
      await writeFile(file, Buffer.from(await img.arrayBuffer()));
      return file;
    }),
  );

  let failed = 0;
  results.forEach((r, i) => {
    const name = Object.keys(LOOKS)[i];
    if (r.status === 'fulfilled') console.log(`${name}: saved ${r.value}`);
    else { failed++; console.error(`${name}: failed (${r.reason instanceof Error ? r.reason.message : r.reason})`); }
  });
  return failed === 0 ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    console.error('Error:', error instanceof Error ? error.message : 'unexpected error');
    process.exit(1);
  });
