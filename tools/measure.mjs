// 用 Chromium canvas 精确测量截图中元素的像素位置
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const _pw = require('C:/Users/scott/.workbuddy/binaries/node/workspace/node_modules/playwright-core');
const chromium = _pw.chromium || (_pw.default && _pw.default.chromium);

function findChrome() {
  const base = 'C:/Users/scott/AppData/Local/ms-playwright';
  if (!fs.existsSync(base)) return undefined;
  const dirs = fs.readdirSync(base).filter((d) => d.startsWith('chromium-')).sort().reverse();
  for (const d of dirs) {
    for (const sub of ['chrome-win64', 'chrome-win']) {
      const exe = path.join(base, d, sub, 'chrome.exe');
      if (fs.existsSync(exe)) return exe;
    }
  }
  return undefined;
}

const arg = (n, d = null) => {
  const i = process.argv.indexOf('--' + n);
  return i > -1 ? process.argv[i + 1] : d;
};

const img = arg('img');
if (!img || !fs.existsSync(img)) {
  console.error('[X] 图片不存在:', img);
  process.exit(1);
}

const browser = await chromium.launch({ executablePath: findChrome() });
const page = await browser.newPage();
await page.setContent('<!doctype html><html><body></body></html>');

const ext = path.extname(img).toLowerCase();
const mime = ext === '.png' ? 'image/png' : ext === '.webp' ? 'image/webp' : 'image/jpeg';
const dataUrl = 'data:' + mime + ';base64,' + fs.readFileSync(img).toString('base64');

const result = await page.evaluate(async (url) => {
  const im = new Image();
  im.src = url;
  await im.decode();
  const W = im.naturalWidth, H = im.naturalHeight;
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d');
  ctx.drawImage(im, 0, 0);
  const data = ctx.getImageData(0, 0, W, H).data;

  // 找"接近纯白"的像素（字幕是白字黑描边），逐行统计
  const rows = new Array(H).fill(0);
  const colsBright = [];
  for (let y = 0; y < H; y++) {
    let c = 0;
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const r = data[i], g = data[i + 1], b = data[i + 2];
      if (r > 235 && g > 235 && b > 235) c++;
    }
    rows[y] = c;
  }
  // 找"画面内容"外框：以四角颜色为背景基准，差异明显的才算内容
  const bgr = data[0], bgg = data[1], bgb = data[2];
  const diff = (i) => Math.abs(data[i] - bgr) + Math.abs(data[i + 1] - bgg) + Math.abs(data[i + 2] - bgb);
  let bx0 = W, bx1 = -1, by0 = H, by1 = -1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (diff((y * W + x) * 4) > 60) {
        if (x < bx0) bx0 = x;
        if (x > bx1) bx1 = x;
        if (y < by0) by0 = y;
        if (y > by1) by1 = y;
      }
    }
  }

  return { W, H, rows, box: { x0: bx0, x1: bx1, y0: by0, y1: by1, w: bx1 - bx0 + 1, h: by1 - by0 + 1 } };
}, dataUrl);

const { W, H, rows, box } = result;
console.log('图片尺寸: ' + W + ' x ' + H);
console.log('画面内容框: x ' + box.x0 + '-' + box.x1 + ' (' + box.w + 'px)  y ' + box.y0 + '-' + box.y1 + ' (' + box.h + 'px)');
console.log('画面宽高比: ' + (box.w / box.h).toFixed(4) + '  (9:16 = 0.5625)');
console.log('');
console.log('白色文字行段:');
const thr = Math.max(6, Math.round(W * 0.02));
const bands = [];
let start = -1;
for (let y = 0; y < H; y++) {
  if (rows[y] >= thr) {
    if (start < 0) start = y;
  } else if (start >= 0) {
    if (y - start >= 8) bands.push({ y0: start, y1: y - 1, peak: Math.max(...rows.slice(start, y)) });
    start = -1;
  }
}
if (start >= 0) bands.push({ y0: start, y1: H - 1, peak: Math.max(...rows.slice(start, H)) });

for (const b of bands) {
  const center = (b.y0 + b.y1) / 2;
  const rel = (center - box.y0) / box.h;
  const canvasY = rel * 1920;
  const offset = canvasY - 960; // 相对画面中心
  console.log('  y ' + b.y0 + '-' + b.y1 + ' 高 ' + (b.y1 - b.y0 + 1) +
    ' | 画面内 ' + (rel * 100).toFixed(1) + '%' +
    ' | 对应 1920 画布 y=' + canvasY.toFixed(0) +
    ' | 相对中心 ' + (offset >= 0 ? '+' : '') + offset.toFixed(0) + 'px');
}
await browser.close();
