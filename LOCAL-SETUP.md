# Run the Seedance 4K scripts on your own computer

For computers where you can't install Node 22 (no admin rights, or an old Node such as 16). Node 22 goes inside the project folder, so nothing on the computer changes. You only need the old Node and npm that are already there.

## 1. Get the project (once)

Download the branch as a zip (log in to GitHub in the browser first):
<https://github.com/sraponte91/higgsfield/archive/refs/heads/claude/higgsfield-seedance-setup-q7pj7p.zip>

Unzip it and open a terminal in the folder.

## 2. Install, with Node 22 inside the project (once)

```bash
npm install
npm install node@22
npx node -v
```

The last line must print `v22.x`. `npx` runs everything with that Node 22. Ignore the "EBADENGINE" warnings from the first `npm install`, which runs on the old Node.

## 3. Add your Higgsfield API key (once)

Create a file called `.env.local` in the folder with one line:

```
HF_CREDENTIALS=your-key-id:your-key-secret
```

Type it in yourself. Never paste it into a chat. Git ignores this file.

## 4. Run a relight (billable)

```bash
npx tsx footage-relight.ts "C:\path\to\clip.mp4" prompt.txt out.mp4 7 4k
```

- `prompt.txt`: the Seedance prompt. Write it with Claude (seedance-footage-vfx skill) or reuse `prompts-intro-seedance-4k-v2.txt` or `prompts-timeline1-seedance-4k.txt`.
- `7`: the output length in seconds (4 to 15). Match your clip.
- `4k`: the resolution (480p, 720p, 1080p or 4k).
- Optional: add look reference images at the end, for example `look_wide.jpg`.

Cost at 4K with a video input: (input seconds + output seconds) × width × height × 24 / 1024 tokens × $0.0048 per 1,000 tokens. For a 7 s vertical 4K clip (2160 × 3840) that is about $13. Run one job at a time.

## 5. Use it from Claude on this computer

Open Claude Code (or the desktop app) in this folder and ask, for example: "relight `C:\path\to\clip.mp4` at 4K with prompts-timeline1-seedance-4k.txt, 7 seconds". Claude runs the same `npx tsx …` command. The clip is read from your disk, so nothing needs uploading.
