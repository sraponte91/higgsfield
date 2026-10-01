import { writeFile } from 'node:fs/promises';
import { config as loadEnv } from 'dotenv';
import { createHiggsfieldClient } from '@higgsfield/client/v2';
import { uploadImage } from './hf-upload.js';

// Spin transition: Emiliann at the desk with her back to camera spins her chair around and lands
// facing the camera. Seedance 2.5 image-to-video pinned to a first and a last frame.
// Usage: npx tsx spin-transition.ts <first-frame.jpg> <last-frame.jpg> [output.mp4]
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.5/image-to-video';

const PROMPT = `One continuous shot, vertical 9:16, photoreal, real footage feel. Same office and the same woman throughout: long light-brown hair, glasses, green blazer over a dark green patterned blouse, dark trousers.

Start exactly on the first frame: she sits at the multi-monitor trading desk with her back to the camera, working. She pushes off and spins her office chair around toward the camera in one fast, energetic rotation. At the same time the handheld camera arcs around her from behind to the front and pushes in. Mid-spin there is strong natural motion blur, like a whip pan; the colleague in headphones at the right-hand station flashes past in the background.

She lands facing the camera in a medium close-up, monitors behind her, hands up mid-gesture, starting to talk with a confident smile. End exactly on the last frame.

Keep her face, glasses, hair and wardrobe identical to the frames. Same cool office lighting with blue LED accents and the black-and-white mural behind. No text, no logos.`;

async function main(): Promise<number> {
  const creds = process.env.HF_CREDENTIALS;
  const [first, last, out = 'spin-transition.mp4'] = process.argv.slice(2);
  if (!creds) { console.error('HF_CREDENTIALS is not set. Add it to .env.local.'); return 1; }
  if (!first || !last) { console.error('Usage: npx tsx spin-transition.ts <first-frame.jpg> <last-frame.jpg> [output.mp4]'); return 1; }

  console.log('Uploading first and last frames...');
  const [imageUrl, endImageUrl] = [await uploadImage(first, creds), await uploadImage(last, creds)];
  const input = {
    prompt: PROMPT,
    image_url: imageUrl,
    end_image_url: endImageUrl,
    duration: 4,
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
