// Renders transition.html frame by frame at 2160 × 3840, 60 fps, and encodes:
//   transition-4k-alpha.mov        QuickTime PNG with transparency (for editors that support alpha)
//   transition-4k-greenscreen.mp4  H.264 over pure green, for chroma key (e.g. CapCut "Chroma key")
//   transition-preview.mp4         1080 × 1920 preview over dark grey, so the wipe is visible
// Usage: node transition/render.cjs [output-dir]
// Needs Playwright (Chromium) and ffmpeg; set FFMPEG=/path/to/ffmpeg if it isn't on PATH.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const outDir = path.resolve(process.argv[2] || 'transition/out');
  const framesDir = path.join(outDir, 'frames');
  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.mkdirSync(framesDir, { recursive: true });
  const ffmpeg = process.env.FFMPEG || 'ffmpeg';

  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width: 2160, height: 3840 } });
  await page.goto('file://' + path.join(__dirname, 'transition.html') + '?render');
  const { FPS, FRAMES } = await page.evaluate(() => ({ FPS: window.TRANSITION.FPS, FRAMES: window.TRANSITION.FRAMES }));

  for (let f = 0; f < FRAMES; f++) {
    const data = await page.evaluate(i => {
      window.TRANSITION.renderFrame(i);
      return window.TRANSITION.canvas.toDataURL('image/png');
    }, f);
    fs.writeFileSync(path.join(framesDir, `f${String(f).padStart(4, '0')}.png`), Buffer.from(data.split(',')[1], 'base64'));
  }
  await browser.close();

  const input = ['-y', '-v', 'error', '-framerate', String(FPS), '-i', path.join(framesDir, 'f%04d.png')];
  execFileSync(ffmpeg, [...input, '-c:v', 'png', '-pix_fmt', 'rgba', path.join(outDir, 'transition-4k-alpha.mov')]);
  execFileSync(ffmpeg, [...input, '-f', 'lavfi', '-i', `color=c=0x00ff00:s=2160x3840:r=${FPS}`,
    '-filter_complex', '[1][0]overlay=shortest=1,format=yuv420p', '-c:v', 'libx264', '-crf', '14', '-preset', 'slow',
    '-movflags', '+faststart', path.join(outDir, 'transition-4k-greenscreen.mp4')]);
  execFileSync(ffmpeg, [...input, '-f', 'lavfi', '-i', `color=c=0x2b2f33:s=2160x3840:r=${FPS}`,
    '-filter_complex', '[1][0]overlay=shortest=1,scale=1080:1920,format=yuv420p', '-c:v', 'libx264', '-crf', '20',
    '-movflags', '+faststart', path.join(outDir, 'transition-preview.mp4')]);
  console.log(`Rendered ${FRAMES} frames to ${outDir}`);
})().catch(e => { console.error(e); process.exit(1); });
