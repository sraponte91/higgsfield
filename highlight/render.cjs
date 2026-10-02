// Renders volatility-now.html frame by frame at 2160 x 3840 (30 fps, set in the HTML), with transparency, and encodes:
//   volatility-now-4k-alpha.mov    PNG in QuickTime with alpha: the phone with the highlight, transparent around it
//   volatility-now-1080-alpha.mov  ProRes 4444 with alpha at 1080 x 1920 (the source frame's native resolution, ~70 MB)
//   volatility-now-preview.mp4   1080 x 1920 preview over grey, to check the motion
// Usage: node highlight/render.cjs [output-dir] [frame,frame,...]   (frame list = render only those as PNG stills)
// OVERLAY=1 renders the graphics only (no phone, no push-in) to volatility-now-overlay-4k.mov, to stack on the
// phone image in the editor (place the 1121 x 2000 frame with "scale to fit" on a 2160 x 3840 timeline).
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
  const overlay = !!process.env.OVERLAY;
  await page.goto('file://' + path.join(__dirname, 'volatility-now.html') + '?render' + (overlay ? '&overlay' : ''));
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
  if (overlay) {
    execFileSync(ffmpeg, [...input, '-c:v', 'png', '-pred', 'mixed', '-compression_level', '9', '-pix_fmt', 'rgba',
      path.join(outDir, 'volatility-now-overlay-4k.mov')]);
    console.log(`Rendered ${FRAMES} overlay frames to ${outDir}`);
    return;
  }
  execFileSync(ffmpeg, [...input, '-c:v', 'png', '-pred', 'mixed', '-compression_level', '9', '-pix_fmt', 'rgba',
    path.join(outDir, 'volatility-now-4k-alpha.mov')]);
  execFileSync(ffmpeg, [...input, '-vf', 'scale=1080:1920:flags=lanczos', '-c:v', 'prores_ks', '-profile:v', '4444',
    '-qscale:v', '6', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '8', '-vendor', 'apl0',
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', path.join(outDir, 'volatility-now-1080-alpha.mov')]);
  execFileSync(ffmpeg, [...input, '-f', 'lavfi', '-i', `color=c=0x8a9099:s=2160x3840:r=${FPS}`,
    '-filter_complex', '[1][0]overlay=shortest=1,scale=1080:1920,format=yuv420p', '-c:v', 'libx264', '-crf', '18',
    '-movflags', '+faststart', path.join(outDir, 'volatility-now-preview.mp4')]);
  console.log(`Rendered ${FRAMES} frames to ${outDir}`);
})().catch(e => { console.error(e); process.exit(1); });
