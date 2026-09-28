# Higgsfield Seedance 2.5 example

Text-to-video with `bytedance/seedance-2.5/text-to-video` via the official `@higgsfield/client` v2 SDK.

## Setup

```bash
npm install
cp .env.example .env.local   # then set HF_CREDENTIALS=key-id:key-secret
npm start
```

`.env.local` is git-ignored and loaded server-side at runtime with `dotenv`.
The script prints the video URL on success and exits non-zero on failed,
moderated (`nsfw`), or canceled requests. Running it makes a billable request.
