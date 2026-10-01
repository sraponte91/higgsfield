import { readFile, writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Regenerates a shot between two real frames of existing footage (Seedance 2.5 image-to-video),
// e.g. to replace a section where the motion stalls. The prompt is read from a text file.
// Usage: npx tsx bridge-shot.ts <first-frame> <last-frame> <prompt.txt> [output.mp4] [seconds]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.5/image-to-video';

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [first, last, promptFile, out = 'bridge-shot.mp4', seconds = '4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!first || !last || !promptFile) {
    console.error('Usage: npx tsx bridge-shot.ts <first-frame> <last-frame> <prompt.txt> [output.mp4] [seconds]');
    return 1;
  }

  console.log('Uploading first and last frames...');
  const input = {
    prompt: (await readFile(promptFile, 'utf8')).trim(),
    image_url: await uploadImage(first, creds),
    end_image_url: await uploadImage(last, creds),
    duration: Number(seconds),
    resolution: '1080p',
    bitrate_mode: 'high',
    generate_audio: false,
  };

  console.log(`Submitting ${MODEL} (${input.duration}s, ${input.resolution}, high bitrate)...`);
  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 15 * 60 * 1000, pollInterval: 5000 });
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
  if (video.ok) {
    await writeFile(out, Buffer.from(await video.arrayBuffer()));
    console.log(`Saved to ${out}`);
  }
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    console.error('Error:', error instanceof Error ? error.message : 'unexpected error');
    process.exit(1);
  });
