// 从书封原图里裁出书本正面（去掉四周背景与右下角水印），输出 1024x1536 的 2:3 书封底图
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  for (const c of [process.env.PLAYWRIGHT_CORE_PATH,
    'C:/Users/scott/.workbuddy/binaries/node/workspace/node_modules/playwright-core',
    'playwright-core', 'playwright'].filter(Boolean)) {
    try { const m = require(c); return m.chromium || (m.default && m.default.chromium); } catch { }
  }
  throw new Error('找不到 playwright-core');
}
function findChrome() {
  const bases = [process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'ms-playwright'),
    process.env.USERPROFILE && path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright'),
    path.join(process.env.HOME || '', 'AppData', 'Local', 'ms-playwright')].filter(Boolean);
  for (const b of bases) {
    if (!fs.existsSync(b)) continue;
    for (const d of fs.readdirSync(b).filter((x) => x.startsWith('chromium-')).sort().reverse()) {
      for (const s of ['chrome-win64', 'chrome-win']) {
        const exe = path.join(b, d, s, 'chrome.exe');
        if (fs.existsSync(exe)) return exe;
      }
    }
  }
  return undefined;
}

const arg = (n, d = null) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : d; };
const src = arg('src');
const out = arg('out');
const boxArg = arg('box'); // "x0,y0,x1,y1" 归一化比例，给了就不自动检测
if (!src || !out) { console.error('用法: node crop_bookface.mjs --src 原图.png --out 底图.png [--box 0.065,0.052,0.922,0.905]'); process.exit(1); }
const box = boxArg ? boxArg.split(',').map(Number) : null;

const chromium = loadPlaywright();
const browser = await chromium.launch({ executablePath: findChrome() });
const page = await browser.newPage();

const dataUrl = 'data:image/png;base64,' + fs.readFileSync(src).toString('base64');
const r = await page.evaluate(async ({ url, box }) => {
  const im = new Image(); im.src = url; await im.decode();
  const W = im.naturalWidth, H = im.naturalHeight;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const g = cv.getContext('2d', { willReadFrequently: true });
  g.drawImage(im, 0, 0);

  let x0, y0, x1, y1;
  if (box) {
    x0 = Math.round(box[0] * W); y0 = Math.round(box[1] * H);
    x1 = Math.round(box[2] * W); y1 = Math.round(box[3] * H);
  } else {
    const d = g.getImageData(0, 0, W, H).data;
    const lum = (i) => 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    const rowDark = new Array(H).fill(0), colDark = new Array(W).fill(0);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (lum((y * W + x) * 4) < 100) { rowDark[y]++; colDark[x]++; }
    }
    y0 = 0; y1 = H - 1; x0 = 0; x1 = W - 1;
    while (y0 < H && rowDark[y0] < W * 0.5) y0++;
    while (y1 > y0 && rowDark[y1] < W * 0.5) y1--;
    while (x0 < W && colDark[x0] < H * 0.5) x0++;
    while (x1 > x0 && colDark[x1] < H * 0.5) x1--;
    const pad = 4;
    x0 += pad; y0 += pad; x1 -= pad; y1 -= pad;
  }
  const bw = x1 - x0 + 1, bh = y1 - y0 + 1;

  // 中心裁成 2:3
  let cw = bw, ch = Math.round(bw * 1.5);
  if (ch > bh) { ch = bh; cw = Math.round(bh / 1.5); }
  const cx = x0 + Math.round((bw - cw) / 2);
  const cy = y0 + Math.round((bh - ch) / 2);

  const ow = 1024, oh = 1536;
  const oc = document.createElement('canvas'); oc.width = ow; oc.height = oh;
  const og = oc.getContext('2d'); og.imageSmoothingQuality = 'high';
  og.drawImage(im, cx, cy, cw, ch, 0, 0, ow, oh);
  return { b64: oc.toDataURL('image/png').split(',')[1], src: [W, H], book: [bw, bh], crop: [cx, cy, cw, ch] };
}, { url: dataUrl, box });

fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, Buffer.from(r.b64, 'base64'));
console.log('原图 %dx%d → 书本框 %dx%d → 裁切 %o → 输出 1024x1536', r.src[0], r.src[1], r.book[0], r.book[1], r.crop);
console.log('已写出', out);
await browser.close();
