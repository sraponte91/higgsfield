import { readFile, writeFile } from 'node:fs/promises';
import { extname } from 'node:path';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';

// Previz for "Volatility Now" scene 1: the location photo as the set reference,
// a presenter seated at the six-monitor desk, monitors switched on.
// Usage: npx tsx intro-previz.ts <location-photo> [output.mp4]
loadEnv({ path: '.env.local', quiet: true });

const API = 'https://api.higgsfield.ai';
const MODEL = 'bytedance/seedance-2.0/reference-to-video';

const PROMPT = `Use the reference image as the exact location: same office, same black-and-white line-art mural with orange accents, same striped grey carpet, same white desks and orange partitions, same trader in a grey t-shirt and headphones working at the multi-monitor station on the right. Vertical 9:16, wide locked-off shot from the same angle as the reference.

A 24-year-old American woman sits in an office chair at the left desk, directly in front of the bank of six monitors, facing the camera. Shoulder-length brown hair, navy blazer over a white top, natural makeup, relaxed and confident. All six monitors behind her are switched on, showing live forex candlestick charts and price tickers in green and red, one chart spiking sharply upward. Behind her to the right, the trader keeps working, typing and glancing between their screens.

She looks straight into the lens, leans in slightly and says with a curious half-smile: "Wondering what just rocked the market?"

Photoreal, natural light from the overhead fluorescent panels. No on-screen text, no logos.

Audio: her line, clear and close to camera; soft office ambience and keyboard clicks.`;

const INPUT = {
  prompt: PROMPT,
  aspect_ratio: '9:16',
  duration: 5,
  resolution: '720p',
  generate_audio: true,
};

const creds = process.env.HF_CREDENTIALS;
const authHeaders = () => ({ Authorization: `Key ${creds}`, 'Content-Type': 'application/json' });

async function uploadImage(path: string): Promise<string> {
  const contentType = extname(path).toLowerCase() === '.png' ? 'image/png' : 'image/jpeg';
  const res = await fetch(`${API}/files/generate-upload-url`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ content_type: contentType }),
  });
  if (!res.ok) throw new Error(`Upload URL request failed (HTTP ${res.status})`);
  const slot = (await res.json()) as { public_url: string; upload_url: string; upload_headers: Record<string, string> };

  // The signed PUT gets only the headers Higgsfield returned, never the API credentials.
  const put = await fetch(slot.upload_url, { method: 'PUT', headers: slot.upload_headers, body: await readFile(path) });
  if (!put.ok) throw new Error(`Image upload failed (HTTP ${put.status})`);
  return slot.public_url;
}

async function estimate(body: object): Promise<string> {
  const res = await fetch(`${API}/estimate/${MODEL}`, { method: 'POST', headers: authHeaders(), body: JSON.stringify(body) });
  if (!res.ok) return `unavailable (HTTP ${res.status})`;
  const e = (await res.json()) as { credits?: string; usd?: string };
  return e.credits !== undefined ? `${e.credits} credits (~$${e.usd})` : JSON.stringify(e);
}

async function main(): Promise<number> {
  const [photo, out = 'intro-previz.mp4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!photo) { console.error('Usage: npx tsx intro-previz.ts <location-photo> [output.mp4]'); return 1; }

  console.log('Uploading location photo...');
  const imageUrl = await uploadImage(photo);
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
