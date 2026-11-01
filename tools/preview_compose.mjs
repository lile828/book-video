/**
 * preview_compose.mjs —— 把背景图与若干透明层叠加，输出一张预览图（仅用于验收，不进草稿）
 *
 * 用法：
 *   node preview_compose.mjs --base 背景图.png --layers a.png,b.png --out 预览.png [--w 1080] [--h 1920]
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

function loadChromium() {
  for (const c of [
    process.env.PLAYWRIGHT_CORE_PATH,
    'C:/Users/scott/.workbuddy/binaries/node/workspace/node_modules/playwright-core',
    'playwright-core',
  ].filter(Boolean)) {
    try { const m = require(c); return m.chromium || (m.default && m.default.chromium); } catch (e) {}
  }
  console.error('[X] 找不到 playwright-core'); process.exit(1);
}

function findChrome() {
  for (const base of [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'ms-playwright'),
    process.env.USERPROFILE && path.join(process.env.USERPROFILE, 'AppData', 'Local', 'ms-playwright'),
    path.join(process.env.HOME || '', 'AppData', 'Local', 'ms-playwright'),
  ].filter(Boolean)) {
    if (!fs.existsSync(base)) continue;
    const dirs = fs.readdirSync(base).filter((d) => d.startsWith('chromium-')).sort().reverse();
    for (const d of dirs) for (const sub of ['chrome-win64', 'chrome-win']) {
      const exe = path.join(base, d, sub, 'chrome.exe');
      if (fs.existsSync(exe)) return exe;
    }
  }
}

const arg = (n, d = null) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : d; };
const base = arg('base');
const layers = (arg('layers', '') || '').split(',').map((s) => s.trim()).filter(Boolean);
const out = arg('out', 'preview.png');
const W = parseInt(arg('w', '1080'), 10);
const H = parseInt(arg('h', '1920'), 10);
const caption = arg('caption', '');           // 示例字幕文本
const captionY = parseInt(arg('caption-y', '1580'), 10); // 字幕中心 Y（像素）
const captionSize = parseInt(arg('caption-size', '80'), 10); // 字幕字号（像素）

if (!base || !fs.existsSync(base)) { console.error('[X] 背景图不存在'); process.exit(1); }

const toUrl = (p) => pathToFileURL(path.resolve(p)).href;

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:${W}px;height:${H}px;overflow:hidden;background:#000}
  .stage{position:relative;width:${W}px;height:${H}px}
  .stage img.base{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
  .stage img.layer{position:absolute;inset:0;width:100%;height:100%}
  .cap{position:absolute;left:0;right:0;top:${captionY}px;transform:translateY(-50%);
    text-align:center;font-family:"Source Han Sans SC","Noto Sans SC","Microsoft YaHei",sans-serif;
    font-size:${captionSize}px;font-weight:700;line-height:1.18;color:#fff;
    -webkit-text-stroke:${Math.round(captionSize * 0.08)}px #000;
    paint-order:stroke fill;
    text-shadow:0 ${Math.round(captionSize*0.05)}px ${Math.round(captionSize*0.12)}px rgba(0,0,0,.75);}
</style></head><body><div class="stage">
  <img class="base" src="${toUrl(base)}">
  ${layers.map((l) => `<img class="layer" src="${toUrl(l)}">`).join('\n  ')}
  ${caption ? `<div class="cap">${caption}</div>` : ''}
</div></body></html>`;

const tmp = path.join(path.dirname(path.resolve(out)), '.preview_tmp.html');
fs.writeFileSync(tmp, html, 'utf-8');

const chromium = loadChromium();
const exe = findChrome();
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.goto(toUrl(tmp));
await page.waitForTimeout(400);
await page.screenshot({ path: out, type: 'png' });
await browser.close();
fs.unlinkSync(tmp);
console.log('[OK] 预览已生成: ' + out);
