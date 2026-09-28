import { config as loadEnv } from 'dotenv';
import {
  createHiggsfieldClient,
  APIError,
  AuthenticationError,
  BadInputError,
  NotEnoughCreditsError,
  ValidationError,
} from '@higgsfield/client/v2';

// Load HF_CREDENTIALS (key-id:key-secret) from .env.local at runtime. Server-side only.
loadEnv({ path: '.env.local', quiet: true });

const MODEL = 'bytedance/seedance-2.5/text-to-video';

async function main(): Promise<number> {
  if (!process.env.HF_CREDENTIALS) {
    console.error('HF_CREDENTIALS is not set. Add it to .env.local (see .env.example).');
    return 1;
  }

  const client = createHiggsfieldClient({
    credentials: process.env.HF_CREDENTIALS,
    // Video generation can take several minutes; the SDK default is 5 minutes.
    maxPollTime: 15 * 60 * 1000,
    pollInterval: 5000,
  });

  console.log(`Submitting ${MODEL} request...`);
  const result = await client.subscribe(MODEL, {
    input: {
      prompt: 'A cinematic scene at sunset',
      duration: 5,
      resolution: '720p',
      aspect_ratio: '16:9',
    },
    withPolling: true,
  });

  // The SDK types list queued/in_progress/completed/failed/nsfw; "canceled" is handled defensively.
  const status: string = result.status;
  console.log(`Request ${result.request_id} finished with status: ${status}`);

  switch (status) {
    case 'completed': {
      const url = result.video?.url;
      if (!url) {
        console.error('Request completed but no video URL was returned.');
        return 1;
      }
      console.log(`Video URL: ${url}`);
      return 0;
    }
    case 'nsfw':
      console.error('Generation was blocked by content moderation (credits refunded).');
      return 1;
    case 'failed':
      console.error('Generation failed (credits refunded).');
      return 1;
    case 'canceled':
    case 'cancelled':
      console.error('Generation was canceled.');
      return 1;
    default:
      console.error(`Generation did not complete (status: ${status}).`);
      return 1;
  }
}

main()
  .then((code) => process.exit(code))
  .catch((error: unknown) => {
    if (error instanceof AuthenticationError) {
      console.error('Authentication failed - check HF_CREDENTIALS.');
    } else if (error instanceof NotEnoughCreditsError) {
      // The SDK maps every HTTP 403 to this error, including a proxy/firewall refusing the connection.
      console.error('HTTP 403: not enough credits, or the connection was refused by a proxy/firewall.');
    } else if (error instanceof BadInputError || error instanceof ValidationError) {
      console.error('Invalid input:', error.message);
    } else if (error instanceof APIError) {
      console.error(`API error (${error.statusCode}):`, error.message);
    } else if (error instanceof Error) {
      console.error('Unexpected error:', error.message);
    } else {
      console.error('Unexpected error.');
    }
    process.exit(1);
  });
