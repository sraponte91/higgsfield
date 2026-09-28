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

Shot 1, 0 to 2 seconds, medium close-up on her at the six-monitor desk, monitors and orange glow behind her, warm orange rim on her hair and shoulders, mirroring the intro: she looks into the lens, energetic, and starts the line, lips in sync: "With economists watching the markets 24/7,"
Hard cut on the word "watching". Shot 2, 2 to 4 seconds, over-the-shoulder from behind the trader at the right-hand station, the back of their head and headphones in the foreground, their screens in focus: one screen shows the economic calendar and a news feed, the main chart shows a candle spiking sharply upward. The trader is fully focused, leans in toward the screen, eyes tracking the spike, and starts typing fast. Orange spill on the desk edge.
Hard cut. Shot 3, 4 to 6.5 seconds, back to the same medium close-up on her: confident smile straight into the lens, she finishes the line, lips in sync: "stay on the pulse with Forex Factory."
Hard cut. Shot 4, 6.5 to 8 seconds, wide from the set image's angle: she sits at the six-monitor desk facing camera with a small nod, the trader still working behind her to the right; hold the wide still for the end card.

Face and identity unchanged from the presenter reference in every shot, same wardrobe, same set and lighting as the set reference.

Audio: her line, clear and close to camera, in one continuous read across the cuts: "With economists watching the markets 24/7, stay on the pulse with Forex Factory." The same upbeat electronic beat as the intro with a hit on each cut, resolving on the final wide; fast keyboard typing under shot 2.`;

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
