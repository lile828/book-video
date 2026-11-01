// 把 ImageGen 原图规格化成 1080x1920，并裁掉底部水印带
// 用法: node prep_images.mjs
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  const cands = [
    process.env.PLAYWRIGHT_CORE_PATH,
    'C:/Users/scott/.workbuddy/binaries/node/workspace/node_modules/playwright-core',
    'playwright-core',
    'playwright',
  ].filter(Boolean);
  for (const c of cands) {
    try {
      const m = require(c);
      return m.chromium || (m.default && m.default.chromium);
    } catch { /* next */ }
  }
  throw new Error('找不到 playwright-core');
}
function findChrome() {
  const bases = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'ms-playwright'),
    process.env.USERPROFILE && path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright'),
    path.join(process.env.HOME || '', 'AppData', 'Local', 'ms-playwright'),
  ].filter(Boolean);
  for (const base of bases) {
    if (!fs.existsSync(base)) continue;
    const dirs = fs.readdirSync(base).filter((d) => d.startsWith('chromium-')).sort().reverse();
    for (const d of dirs) {
      for (const sub of ['chrome-win64', 'chrome-win']) {
        const exe = path.join(base, d, sub, 'chrome.exe');
        if (fs.existsSync(exe)) return exe;
      }
    }
  }
  return undefined;
}

const ROOT = 'C:/Users/scott/WorkBuddy/书单视频/自在独行';
const W = 1080, H = 1920;
const CROP_BOTTOM = 0.06; // 底部 6% 是 AI 水印带

// 源目录 -> 目标文件
const JOBS = [
  ['00_原始素材/_raw/cover', '00_原始素材/封面/封面.png'],
  ['00_原始素材/_raw/bg1', '00_原始素材/背景图/背景图1.png'],
  ['00_原始素材/_raw/bg2', '00_原始素材/背景图/背景图2.png'],
  ['00_原始素材/_raw/bg3', '00_原始素材/背景图/背景图3.png'],
  ['00_原始素材/_raw/bg4', '00_原始素材/背景图/背景图4.png'],
  ['00_原始素材/_raw/bg5', '00_原始素材/背景图/背景图5.png'],
  ['00_原始素材/_raw/bg6', '00_原始素材/背景图/背景图6.png'],
  ['00_原始素材/_raw/bg7', '00_原始素材/背景图/背景图7.png'],
];

const chromium = loadPlaywright();
const browser = await chromium.launch({ executablePath: findChrome() });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });

for (const [srcDir, dstRel] of JOBS) {
  const dir = path.join(ROOT, srcDir);
  const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => f.toLowerCase().endsWith('.png')) : [];
  if (!files.length) { console.log('[X] 源图缺失:', srcDir); continue; }
  const src = path.join(dir, files[0]);
  const dst = path.join(ROOT, dstRel);
  fs.mkdirSync(path.dirname(dst), { recursive: true });

  const dataUrl = 'data:image/png;base64,' + fs.readFileSync(src).toString('base64');
  const buf = await page.evaluate(async ({ url, W, H, cut }) => {
    const im = new Image();
    im.src = url;
    await im.decode();
    const usableH = im.naturalHeight * (1 - cut);
    const s = H / usableH;                 // 让可用高度正好铺满 1920
    const dw = im.naturalWidth * s, dh = usableH * s;
    const dx = (W - dw) / 2, dy = 0;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const g = cv.getContext('2d');
    g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
    g.imageSmoothingQuality = 'high';
    g.drawImage(im, 0, 0, im.naturalWidth, usableH, dx, dy, dw, dh);
    const b64 = cv.toDataURL('image/png').split(',')[1];
    return { b64, src: [im.naturalWidth, im.naturalHeight], scale: s };
  }, { url: dataUrl, W, H, cut: CROP_BOTTOM });

  fs.writeFileSync(dst, Buffer.from(buf.b64, 'base64'));
  const kb = (fs.statSync(dst).size / 1024).toFixed(0);
  console.log('OK  %-34s <- %sx%s  %s KB' % (dstRel, buf.src[0], buf.src[1], kb));
}

await browser.close();
console.log('\n完成。全部 1080x1920，底部水印带已裁掉。');
