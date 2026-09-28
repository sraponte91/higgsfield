import { writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Previz for "Volatility Now" scene 7 (outro), matching the relit intro:
// same presenter, same set, brand-orange LED lighting.
// Usage: npx tsx outro-previz.ts <lit-set-still.jpg> <presenter-closeup.jpg> [output.mp4]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.0/reference-to-video';

const PROMPT = `@set: Reference image 1, the exact location and lighting: the office with the black-and-white line-art mural, orange partitions, white desks, striped grey carpet, the six-monitor bank on the left desk showing green and red charts, the trader in a grey t-shirt and headphones at the right-hand station. Warm orange LED strips glow behind the six monitors and under the front edge of the left desk; overhead fluorescents slightly dimmed.
@presenter: Reference image 2, the same young woman: face, shoulder-length brown hair in a loose ponytail, oversized light-grey sweatshirt. Keep her identity, face and wardrobe exactly; ripped light-wash jeans and white sneakers as in the set image.

Photoreal. 9:16. 8s. Warm brand-orange practical LED look matching the set image in every shot. Fast social-media edit, hard cuts on the beat, slight handheld energy. No on-screen text, no logos.

Shot 1, 0 to 1.5 seconds, medium on the trader at the right-hand station: they lean back from their screens, stretch, then lean in again, orange spill on the desk edge. Her voice-over begins: "With economists watching the markets 24/7,"
Hard cut. Shot 2, 1.5 to 3 seconds, tight on the six monitors: candles ticking up and down, slow push-in, orange glow around the screen edges.
Hard cut. Shot 3, 3 to 6 seconds, medium close-up on her at the six-monitor desk, monitors and orange glow behind her, warm orange rim on her hair and shoulders: she looks straight into the lens with a confident smile and says, lips in sync: "stay on the pulse with Forex Factory."
Hard cut. Shot 4, 6 to 8 seconds, wide from the set image's angle: she gives the camera a quick two-finger salute, spins her chair back toward the monitors; hold the wide for the last second, trader still working.

Face and identity unchanged from the presenter reference in every shot, same wardrobe, same set and lighting as the set reference.

Audio: her line, clear and close to camera, in one continuous read across the cuts: "With economists watching the markets 24/7, stay on the pulse with Forex Factory." The same upbeat electronic beat as the intro with a hit on each cut, resolving on the final wide; soft keyboard clicks.`;

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [setStill, presenter, out = 'outro-previz.mp4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!setStill || !presenter) { console.error('Usage: npx tsx outro-previz.ts <lit-set-still.jpg> <presenter-closeup.jpg> [output.mp4]'); return 1; }

  console.log('Uploading references...');
  const imageUrls = [await uploadImage(setStill, creds), await uploadImage(presenter, creds)];
  const input = { prompt: PROMPT, image_urls: imageUrls, aspect_ratio: '9:16', duration: 8, resolution: '720p', generate_audio: true };

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
