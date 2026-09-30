# Volatility Now: Higgsfield previz and chart transition

Scripts for the Forex Factory "Volatility Now" short:

- Seedance and image generations on the Higgsfield API (billable).
- The chart transition, rendered locally in JavaScript (free, no API).

## 1. Install (once per computer)

1. Install **Node.js 22 LTS** from <https://nodejs.org>.
2. Unzip this project, then open a terminal in its folder:
   - Windows: open the folder, click the address bar, type `cmd`, press Enter.
   - Mac: right-click the folder, then choose "New Terminal at Folder".
3. Install the dependencies:

   ```bash
   npm install
   npx playwright install chromium
   ```

   The second line downloads the headless browser that draws the transition frames. You only need it for `npm run transition`.

## 2. Add your Higgsfield key (once per computer)

Create a file named `.env.local` in the project folder with one line:

```
HF_CREDENTIALS=your-key-id:your-key-secret
```

On Windows you can run `copy .env.example .env.local`, then `notepad .env.local`, and replace the placeholder.

- Git ignores this file, and no script prints it.
- Never commit it or paste it anywhere.
- The key needs credits on your Higgsfield account.

## 3. Commands

| Command | What it does | Cost |
|---|---|---|
| `npm start` | Seedance 2.5 text-to-video test ("A cinematic scene at sunset", 5 s, 720p) and prints the video URL | billable |
| `npm run intro -- <location.jpg> [out.mp4]` | Intro previz: Seedance 2.0 reference-to-video, 9:16, 8 s, from your location photo | billable (~$2.40) |
| `npm run relight -- <video-url> <lighting-still.jpg> [out.mp4]` | Relights an existing clip to match a lighting still | billable (~$2.90) |
| `npm run outro -- <lit-set-still.jpg> <presenter-closeup.jpg> [out.mp4]` | Outro previz with the same presenter and lighting | billable (~$2.40) |
| `npm run lighting -- <frame.jpg> [output-dir]` | Four LED lighting looks on one frame (Grok Imagine 2.0) | billable (~$0.16) |
| `npm run transition -- [output-dir]` | Renders the chart transition at 2160 × 3840, 60 fps | free |
| `npm run typecheck` | Checks the TypeScript | free |

Costs are estimates from Higgsfield's published pricing. The prompts live at the top of each `.ts` file, so edit them there.

### Transition outputs

`npm run transition` writes to `transition/out/` by default:

- `transition-4k-greenscreen.mp4`: use with Chroma key in CapCut or Canva.
- `transition-4k-alpha.mov`: real transparency, for editors that accept it.
- `transition-preview.mp4`: 1080p preview over dark grey.

To tweak the animation, open `transition/transition.html` in a browser; it has a live preview with a scrubber. Timings and speeds are named constants at the top of its script. The chart geometry comes from the Figma frame "transition" and lives in `transition/chart-data.js`.

## Troubleshooting

- **"HF_CREDENTIALS is not set"**: `.env.local` is missing or in the wrong folder.
- **HTTP 403 / "not enough credits"**: either your account has no credits, or a firewall or proxy blocked `api.higgsfield.ai`. Work and office networks often block it.
- **Generation "nsfw"**: the prompt or image was blocked by moderation. Credits are refunded.
- **Transition: "Executable doesn't exist"**: run `npx playwright install chromium`.
