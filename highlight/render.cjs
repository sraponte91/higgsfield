// Renders volatility-now.html frame by frame at 2160 x 3840, 60 fps, and encodes:
//   volatility-now-4k.mov       H.264, the full frame with the highlight (phone and background untouched)
//   volatility-now-preview.mp4  1080 x 1920 preview
// Usage: node highlight/render.cjs [output-dir] [frame,frame,...]   (frame list = render only those as PNG stills)
// Uses the project's Playwright Chromium and the bundled ffmpeg-static binary.
// Override with CHROMIUM=/path/to/chromium or FFMPEG=/path/to/ffmpeg.
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const outDir = path.resolve(process.argv[2] || 'highlight/out');
  const stills = process.argv[3] ? process.argv[3].split(',').map(Number) : null;
  const framesDir = path.join(outDir, stills ? 'stills' : 'frames');
  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.mkdirSync(framesDir, { recursive: true });
  const ffmpeg = process.env.FFMPEG || require('ffmpeg-static');

  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width: 2160, height: 3840 } });
  await page.goto('file://' + path.join(__dirname, 'volatility-now.html') + '?render');
  // The frame is passed in as a data URL so the canvas stays exportable from a file:// page.
  const frame = fs.readFileSync(path.join(__dirname, 'volatility-now-frame.webp')).toString('base64');
  await page.evaluate(src => window.VN.load(src), 'data:image/webp;base64,' + frame);
  const { FPS, FRAMES } = await page.evaluate(() => ({ FPS: window.VN.FPS, FRAMES: window.VN.FRAMES }));

  for (const f of stills || [...Array(FRAMES).keys()]) {
    const data = await page.evaluate(i => { window.VN.renderFrame(i); return window.VN.canvas.toDataURL('image/png'); }, f);
    fs.writeFileSync(path.join(framesDir, `f${String(f).padStart(4, '0')}.png`), Buffer.from(data.split(',')[1], 'base64'));
  }
  await browser.close();
  if (stills) { console.log(`Rendered stills ${stills.join(', ')} to ${framesDir}`); return; }

  const input = ['-y', '-v', 'error', '-framerate', String(FPS), '-i', path.join(framesDir, 'f%04d.png')];
  execFileSync(ffmpeg, [...input, '-c:v', 'libx264', '-crf', '12', '-preset', 'slow', '-pix_fmt', 'yuv420p',
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-movflags', '+faststart',
    path.join(outDir, 'volatility-now-4k.mov')]);
  execFileSync(ffmpeg, [...input, '-vf', 'scale=1080:1920,format=yuv420p', '-c:v', 'libx264', '-crf', '18',
    '-movflags', '+faststart', path.join(outDir, 'volatility-now-preview.mp4')]);
  console.log(`Rendered ${FRAMES} frames to ${outDir}`);
})().catch(e => { console.error(e); process.exit(1); });
