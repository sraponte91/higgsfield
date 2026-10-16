"""Seedance 2.0 video-to-video (reference-to-video) on the Higgsfield API, in plain Python 3: no Node, no pip installs.

Same job as footage-relight.ts: the source clip is the base, optional images are look references, the output is
9:16 with no generated audio (lay the original sound back in the edit). Billable on your Higgsfield API credits.

Usage: python footage_relight.py <source.mp4> <prompt.txt> <out.mp4> <seconds> <480p|720p|1080p|4k> [ref.jpg ...]
Key: HF_CREDENTIALS=key-id:key-secret in .env.local next to this file (or in the environment). Never printed.
"""
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = 'https://api.higgsfield.ai'
MODEL = 'bytedance/seedance-2.0/reference-to-video'
POLL_SECONDS, MAX_WAIT = 8, 30 * 60


def credentials():
    env = Path(__file__).with_name('.env.local')
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            if key.strip() in ('HF_CREDENTIALS', 'HF_KEY') and value.strip():
                return value.strip().strip('"\'')
    return os.environ.get('HF_CREDENTIALS') or os.environ.get('HF_KEY')


def call(method, url, creds=None, body=None, headers=None, data=None):
    h = dict(headers or {})
    if creds:
        h['Authorization'] = f'Key {creds}'
    if body is not None:
        data = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as res:
            raw = res.read()
            return json.loads(raw) if raw and 'json' in res.headers.get('Content-Type', '') else raw
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:500]
        raise SystemExit(f'{method} {url.split("?")[0]} failed (HTTP {e.code}): {detail}')


def upload(path, creds):
    """Upload a local file to Higgsfield storage; returns a public URL to use as a model input."""
    ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    slot = call('POST', f'{API}/files/generate-upload-url', creds, {'content_type': ctype})
    size = os.path.getsize(path)
    with open(path, 'rb') as f:   # streamed, so big clips are not held in memory
        # The signed PUT gets only the headers Higgsfield returned, never the API credentials.
        call('PUT', slot['upload_url'], headers={**slot.get('upload_headers', {}), 'Content-Length': str(size)}, data=f)
    return slot['public_url']


def main():
    if len(sys.argv) < 6:
        print(next(l for l in __doc__.splitlines() if l.startswith('Usage'))); return 1
    source, prompt_file, out, seconds, resolution, *refs = sys.argv[1:]
    creds = credentials()
    if not creds or ':' not in creds:
        print('HF_CREDENTIALS is not set. Add HF_CREDENTIALS=key-id:key-secret to .env.local.'); return 1

    print(f'Uploading source clip and {len(refs)} reference image(s)...')
    body = {
        'prompt': Path(prompt_file).read_text(encoding='utf-8').strip(),
        'video_urls': [upload(source, creds)],
        'aspect_ratio': '9:16',
        'duration': int(seconds),
        'resolution': resolution,
        'generate_audio': False,
    }
    if refs:
        body['image_urls'] = [upload(r, creds) for r in refs]

    print(f'Submitting {MODEL} (9:16, {seconds}s, {resolution})...')
    res = call('POST', f'{API}/{MODEL}', creds, body)
    rid, start = res.get('request_id'), time.time()
    while res.get('status') not in ('completed', 'failed', 'nsfw'):
        if time.time() - start > MAX_WAIT:
            print(f'Still running after {MAX_WAIT // 60} min. Request id: {rid}'); return 1
        time.sleep(POLL_SECONDS)
        res = call('GET', f'{API}/requests/{rid}/status', creds)
        print(f'  {res.get("status")}...', flush=True)

    url = (res.get('video') or {}).get('url')
    if res.get('status') != 'completed' or not url:
        reason = 'blocked by content moderation' if res.get('status') == 'nsfw' else res.get('error') or res.get('status')
        print(f'Generation did not succeed: {reason}.'); return 1
    print('Downloading result...')
    with urllib.request.urlopen(url, timeout=600) as r, open(out, 'wb') as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f'Saved to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
