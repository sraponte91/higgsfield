import { readFile, writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Video-to-video with Seedance 2.0 (reference-to-video): the source clip is the base, the images are
// lighting/look references. 4K keeps faces and fine detail stable.
// Usage: npx tsx footage-relight.ts <source.mp4> <prompt.txt> <out.mp4> <seconds> <480p|720p|1080p|4k> [ref.jpg ...]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.0/reference-to-video';

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [source, promptFile, out, seconds, resolution, ...refs] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!source || !promptFile || !out || !seconds || !resolution) {
    console.error('Usage: npx tsx footage-relight.ts <source.mp4> <prompt.txt> <out.mp4> <seconds> <480p|720p|1080p|4k> [ref.jpg ...]');
    return 1;
  }

  console.log(`Uploading source clip and ${refs.length} reference image(s)...`);
  const input = {
    prompt: (await readFile(promptFile, 'utf8')).trim(),
    video_urls: [await uploadImage(source, creds)],
    image_urls: await Promise.all(refs.map((r) => uploadImage(r, creds))),
    aspect_ratio: '9:16',
    duration: Number(seconds),
    resolution,
    generate_audio: false,
  };

  console.log(`Submitting ${MODEL} (9:16, ${input.duration}s, ${input.resolution})...`);
  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 30 * 60 * 1000, pollInterval: 8000 });
  const result = await client.subscribe(MODEL, { input, withPolling: true });
  const status: string = result.status;
  console.log(`Request ${result.request_id} finished with status: ${status}`);

  if (status !== 'completed' || !result.video?.url) {
    const detail = (result as { error?: string }).error;
    const reason = status === 'nsfw' ? 'blocked by content moderation' : status === 'completed' ? 'no video URL returned' : detail ? `${status}: ${detail}` : status;
    console.error(`Generation did not succeed: ${reason}.`);
    return 1;
  }
  console.log(`Video URL: ${result.video.url}`);
  const video = await fetch(result.video.url);
  if (!video.ok) { console.error(`Download failed (HTTP ${video.status}).`); return 1; }
  await writeFile(out, Buffer.from(await video.arrayBuffer()));
  console.log(`Saved to ${out}`);
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    console.error('Error:', error instanceof Error ? error.message : 'unexpected error');
    process.exit(1);
  });
