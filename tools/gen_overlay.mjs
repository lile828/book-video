/**
 * gen_overlay.mjs —— 生成两张 1080×1920 透明叠加层
 *
 *   1) title_layer.png  顶部书名 + 作者（全片常驻）
 *   2) cover_layer.png  左下角书籍封面（可选，只在前几秒出现）
 *
 * 用法：
 *   node gen_overlay.mjs --title "假如给我三天光明" --author "海伦凯勒" \
 *        --cover 00_原始素材/封面/书封_假如给我三天光明.png \
 *        --outdir 00_原始素材/叠加层 [--w 1080] [--h 1920]
 *
 * 为什么用图片层而不是剪映文字轨：
 *   add_captions 的颜色/位置是接口级参数，一次调用只能一种样式，
 *   书名（白色大字）+ 作者（金色小字）无法在同一次调用里做出来。
 *   渲染成透明 PNG 后，add_images 一次调用即可，位置和字重完全可控。
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

function loadChromium() {
  const cands = [
    process.env.PLAYWRIGHT_CORE_PATH,
    'C:/Users/scott/.workbuddy/binaries/node/workspace/node_modules/playwright-core',
    'playwright',
    'playwright-core',
  ].filter(Boolean);
  for (const c of cands) {
    try {
      const m = require(c);
      return m.chromium || (m.default && m.default.chromium);
    } catch (e) { /* next */ }
  }
  console.error('[X] 找不到 playwright-core');
  process.exit(1);
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

function arg(name, def = null) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const title = arg('title');
const author = arg('author', '');
const coverPath = arg('cover');
const outDir = arg('outdir', '00_原始素材/叠加层');
const W = parseInt(arg('w', '1080'), 10);
const H = parseInt(arg('h', '1920'), 10);

if (!title) {
  console.error('用法: node gen_overlay.mjs --title 书名 [--author 作者] [--cover 书封.png] [--outdir 目录]');
  process.exit(1);
}

fs.mkdirSync(outDir, { recursive: true });
const chromium = loadChromium();
const CHROME_EXE = findChrome();
const browser = await chromium.launch(CHROME_EXE ? { executablePath: CHROME_EXE } : {});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });

// ---------------- 1. 顶部标题层 ----------------
const titleSize = Math.round((W * 0.80) / (title.length * 1.10));
const authorSize = Math.round(titleSize * 0.46);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const titleCss = `
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:${W}px; height:${H}px; background:transparent; overflow:hidden; }
  .wrap { position:relative; width:${W}px; height:${H}px; }
  .band { position:absolute; left:0; top:0; width:${W}px; height:${Math.round(H * 0.235)}px;
    background:linear-gradient(180deg, rgba(8,10,14,.55) 0%, rgba(8,10,14,.30) 45%, rgba(8,10,14,0) 100%); }
  .title { position:absolute; left:0; right:0; top:${Math.round(H * 0.074)}px;
    text-align:center; text-indent:${Math.round(titleSize * 0.09)}px;
    font-family:"STZhongsong","Source Han Serif SC","Songti SC","SimSun",serif;
    font-size:${titleSize}px; font-weight:700; line-height:1.0;
    color:#fdfaf2; letter-spacing:${Math.round(titleSize * 0.09)}px;
    -webkit-text-stroke:${Math.round(titleSize * 0.075)}px rgba(18,16,14,.92);
    paint-order:stroke fill;
    text-shadow:0 ${Math.round(titleSize * 0.05)}px ${Math.round(titleSize * 0.16)}px rgba(0,0,0,.75); }
  .author { position:absolute; left:0; right:0; top:${Math.round(H * 0.160)}px;
    text-align:center; text-indent:${Math.round(authorSize * 0.10)}px;
    font-family:"STZhongsong","Source Han Serif SC","SimSun",serif;
    font-size:${authorSize}px; font-weight:400; line-height:1.0;
    color:#f7d27e; letter-spacing:${Math.round(authorSize * 0.10)}px;
    -webkit-text-stroke:${Math.round(authorSize * 0.085)}px rgba(22,16,6,.92);
    paint-order:stroke fill;
    text-shadow:0 3px 12px rgba(0,0,0,.85), 0 0 3px rgba(0,0,0,.6); }
`;

const titleHtml = `<!doctype html><html><head><meta charset="utf-8"><style>${titleCss}</style></head>
<body><div class="wrap"><div class="band"></div>
<div class="title">${esc(title)}</div>
${author ? `<div class="author">${esc(author)}</div>` : ''}
</div></body></html>`;

const tmp1 = path.join(outDir, '.title_tmp.html');
fs.writeFileSync(tmp1, titleHtml, 'utf-8');
await page.goto(pathToFileURL(tmp1).href);
await page.waitForTimeout(250);
const titleOut = path.join(outDir, '标题层_1080x1920.png');
await page.screenshot({ path: titleOut, omitBackground: true, type: 'png' });
fs.unlinkSync(tmp1);
console.log(`[OK] ${titleOut}  书名${titleSize}px / 作者${authorSize}px`);

// ---------------- 2. 左下角书封层 ----------------
if (coverPath && fs.existsSync(coverPath)) {
  const coverUrl = pathToFileURL(path.resolve(coverPath)).href;
  // 书封显示尺寸：宽度占画布 26%
  const coverW = Math.round(W * 0.26);
  const coverH = Math.round(coverW * 1.412); // 书封 1024×1446 的宽高比
  const left = Math.round(W * 0.052);
  const top = Math.round(H * 0.400);

  const coverCss = `
    * { margin:0; padding:0; box-sizing:border-box; }
    html,body { width:${W}px; height:${H}px; background:transparent; overflow:hidden; }
    .wrap { position:relative; width:${W}px; height:${H}px; }
    .cover { position:absolute; left:${left}px; top:${top}px;
      width:${coverW}px; height:${coverH}px;
      border:2px solid rgba(240,236,226,.55);
      border-radius:2px;
      box-shadow: 0 10px 26px rgba(0,0,0,.62), 0 2px 6px rgba(0,0,0,.5),
                  inset -6px 0 10px rgba(0,0,0,.45);
      overflow:hidden; }
    .cover img { width:100%; height:100%; object-fit:cover; display:block; }
    .spine { position:absolute; left:0; top:0; width:${Math.round(coverW * 0.07)}px; height:100%;
      background:linear-gradient(90deg, rgba(255,255,255,.16), rgba(0,0,0,.42)); }
  `;

  const coverHtml = `<!doctype html><html><head><meta charset="utf-8"><style>${coverCss}</style></head>
<body><div class="wrap"><div class="cover"><img src="${coverUrl}"><div class="spine"></div></div></div></body></html>`;

  const tmp2 = path.join(outDir, '.cover_tmp.html');
  fs.writeFileSync(tmp2, coverHtml, 'utf-8');
  await page.goto(pathToFileURL(tmp2).href);
  await page.waitForTimeout(250);
  const coverOut = path.join(outDir, '书封层_1080x1920.png');
  await page.screenshot({ path: coverOut, omitBackground: true, type: 'png' });
  fs.unlinkSync(tmp2);
  console.log(`[OK] ${coverOut}  尺寸 ${coverW}×${coverH} @ (${left},${top})`);
}

await browser.close();
