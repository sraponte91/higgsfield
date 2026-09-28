import { writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Relights an existing intro clip to a chosen lighting look, keeping people, performance and cuts.
// Usage: npx tsx relight-intro.ts <source-video-url> <lighting-still.jpg> [output.mp4]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.0/reference-to-video';

const PROMPT = `@source: Reference video, the original 8-second vertical intro edit in five hard-cut shots. Shot 1, wide: a young woman in an oversized light-grey sweatshirt, ripped light-wash jeans and white sneakers, hair in a loose ponytail, spins her office chair at the six-monitor desk to face camera; a trader in a grey t-shirt and headphones works at the right-hand station. Shot 2, medium close-up: she leans in and says "Wondering what just rocked the market?". Shot 3, tight on the monitors: a candlestick chart spikes, push-in. Shot 4, medium on the trader typing fast. Shot 5, medium close-up: she raises an eyebrow and smirks. Preserve identity, face, hair, wardrobe, performance, lip-sync, framing, camera moves, shot order and cut points exactly; change only the lighting.
@look: Reference image, lighting reference only: warm orange LED strips hidden behind the six monitors glowing onto the orange partition and the mural, a matching orange strip under the front edge of the left desk glowing onto the carpet, overhead fluorescent panels dimmed slightly. Use it only for light and color; do not copy its pose or framing.

Photoreal. 9:16. 8s. Warm brand-orange practical LED look, overheads slightly dimmed. SFX and source dialogue only.

Same five shots, same framing and same cut points as the source. Relight the whole frame under one look: the orange LED glow from behind the monitors, behind her and screen-left, lays a warm orange rim on her hair and shoulders; the under-desk strip throws an orange pool onto the carpet; the monitors stay bright with green and red charts; the overhead fluorescent fill, lower than before, keeps her face evenly lit and readable with soft shadows. In shot 4 the same orange spill reaches the edge of the trader's station. Consistent shadow direction and density in every shot, subtle warm bounce on skin, no halos or cut-out edges. Face and identity unchanged, lips matching the source exactly, wardrobe, performance, camera and edit identical to the source; only the lighting changes.

SFX and source dialogue only: her line "Wondering what just rocked the market?" exactly as in the source, the upbeat electronic beat with a hit on each cut, keyboard clatter on shot 4.`;

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [videoUrl, still, out = 'intro-relit.mp4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!videoUrl || !still) { console.error('Usage: npx tsx relight-intro.ts <source-video-url> <lighting-still.jpg> [output.mp4]'); return 1; }

  console.log('Uploading lighting still...');
  const stillUrl = await uploadImage(still, creds);
  const input = {
    prompt: PROMPT,
    video_urls: [videoUrl],
    image_urls: [stillUrl],
    aspect_ratio: '9:16',
    duration: 8,
    resolution: '720p',
    generate_audio: true,
  };

  console.log(`Submitting ${MODEL} (9:16, ${input.duration}s, ${input.resolution})...`);
  const client = createHiggsfieldClient({ credentials: creds, maxPollTime: 15 * 60 * 1000, pollInterval: 5000 });
  const result = await client.subscribe(MODEL, { input, withPolling: true });
  const status: string = result.status;
  console.log(`Request ${result.request_id} finished with status: ${status}`);

  if (status !== 'completed' || !result.video?.url) {
    const reason = status === 'nsfw' ? 'blocked by content moderation' : status === 'completed' ? 'no video URL returned' : status;
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
