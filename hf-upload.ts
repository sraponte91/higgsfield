import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';

export const API = 'https://api.higgsfield.ai';

export const authHeaders = (creds: string) => ({ Authorization: `Key ${creds}`, 'Content-Type': 'application/json' });

// Uploads a local image to Higgsfield storage and returns a public URL usable as a model input.
export async function uploadImage(path: string, creds: string): Promise<string> {
  const contentType = extname(path).toLowerCase() === '.png' ? 'image/png' : 'image/jpeg';
  const res = await fetch(`${API}/files/generate-upload-url`, {
    method: 'POST',
    headers: authHeaders(creds),
    body: JSON.stringify({ content_type: contentType }),
  });
  if (!res.ok) throw new Error(`Upload URL request failed (HTTP ${res.status})`);
  const slot = (await res.json()) as { public_url: string; upload_url: string; upload_headers: Record<string, string> };

  // The signed PUT gets only the headers Higgsfield returned, never the API credentials.
  const put = await fetch(slot.upload_url, { method: 'PUT', headers: slot.upload_headers, body: await readFile(path) });
  if (!put.ok) throw new Error(`Image upload failed (HTTP ${put.status})`);
  return slot.public_url;
}
