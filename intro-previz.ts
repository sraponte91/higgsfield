import { writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { API, authHeaders, uploadImage } from './hf-upload.js';

// Previz for "Volatility Now" scene 1: the location photo as the set reference,
// a presenter seated at the six-monitor desk, monitors switched on.
// Usage: npx tsx intro-previz.ts <location-photo> [output.mp4]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.0/reference-to-video';

const PROMPT = `Location: use the reference image as the exact set. Same office, same black-and-white line-art mural with orange accents, same striped grey carpet, same white desks and orange partitions. The trader in a grey t-shirt and headphones works at the multi-monitor station on the right. All six monitors on the left desk are switched on, showing live forex candlestick charts and price tickers in green and red.

Presenter: a 24-year-old American woman, shoulder-length brown hair in a loose ponytail, casual outfit: oversized light-grey crewneck sweatshirt, light-wash jeans, white sneakers. Natural makeup, bright and high-energy, expressive face, quick smile.

Vertical 9:16 social-media edit, fast pace, hard cuts on the beat, slight handheld energy. Five shots:

Shot 1, wide from the reference angle, 0 to 1.5 seconds: she spins her office chair around from the six monitors to face the camera, grinning.
Hard cut. Shot 2, medium close-up on her face and shoulders, monitors glowing behind her, 1.5 to 4 seconds: she leans toward the lens, eyebrows up, and says with punchy energy: "Wondering what just rocked the market?"
Hard cut. Shot 3, tight on the monitors, 4 to 5.5 seconds: a candlestick chart spikes sharply upward, quick push-in on the screen.
Hard cut. Shot 4, medium on the trader at the right-hand station, 5.5 to 7 seconds: they lean in fast toward their screens and hammer the keyboard.
Hard cut. Shot 5, back to the medium close-up on her, 7 to 8 seconds: she raises an eyebrow at the camera with a knowing smirk.

Photoreal, natural light from the overhead fluorescent panels, same people and wardrobe in every shot. No on-screen text, no logos.

Audio: her line, clear and close to camera; upbeat electronic beat with a hit on each cut; keyboard clatter on shot 4.`;

const INPUT = {
  prompt: PROMPT,
  aspect_ratio: '9:16',
  duration: 8,
  resolution: '720p',
  generate_audio: true,
};

const creds = process.env.HF_CREDENTIALS;

async function estimate(body: object): Promise<string> {
  const res = await fetch(`${API}/estimate/${MODEL}`, { method: 'POST', headers: authHeaders(creds!), body: JSON.stringify(body) });
  if (!res.ok) return `unavailable (HTTP ${res.status})`;
  const e = (await res.json()) as { credits?: string; usd?: string };
  return e.credits !== undefined ? `${e.credits} credits (~$${e.usd})` : JSON.stringify(e);
}

async function main(): Promise<number> {
  const [photo, out = 'intro-previz.mp4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!photo) { console.error('Usage: npx tsx intro-previz.ts <location-photo> [output.mp4]'); return 1; }

  console.log('Uploading location photo...');
  const imageUrl = await uploadImage(photo, creds);
  const input = { ...INPUT, image_urls: [imageUrl] };

  console.log(`Estimated cost: ${await estimate(input)}`);
  console.log(`Submitting ${MODEL} (9:16, ${INPUT.duration}s, ${INPUT.resolution})...`);

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
