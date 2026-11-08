/**
 * gen_overlay2.mjs —— 支持多行书名的 1080×1920 叠加层生成器
 *
 * 与技能包 gen_overlay.mjs 的差别只有一处：
 *   gen_overlay 只支持单行书名，长书名会被字号自适应压到 60px（10 字时），
 *   在 1080 宽画布上明显弱于底部字幕。本项目书名 10 字，
 *   按《分镜方案》§五「主标题 96-120px，行距 1.2，最多两行」的要求拆成两行、每行 108px。
 *
 * 用法：
 *   node gen_overlay2.mjs --title "蛤蟆先生|去看心理医生" --author "罗伯特·戴博德" \
 *        --cover 00_原始素材/封面/书封_蛤蟆先生_暖调.png --outdir 00_原始素材/叠加层
 *
 * 用 "|" 分隔多行；不带 "|" 时行为与原脚本一致（单行自适应）。
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

const titleRaw = arg('title');
const author = arg('author', '');
const coverPath = arg('cover');
const outDir = arg('outdir', '00_原始素材/叠加层');
const W = parseInt(arg('w', '1080'), 10);
const H = parseInt(arg('h', '1920'), 10);

if (!titleRaw) {
  console.error('用法: node gen_overlay2.mjs --title "第一行|第二行" [--author 作者] [--cover 书封.png] [--outdir 目录]');
  process.exit(1);
}

const lines = titleRaw.split('|').map((s) => s.trim()).filter(Boolean);

// 单行时沿用原脚本的自适应区间；多行时按「行数越少字越大」给固定档位，落在方案要求的 96-120px
const maxLen = Math.max(...lines.map((s) => s.length));
let titleSize;
if (lines.length === 1) {
  const raw = Math.round((W * 0.62) / (maxLen * 1.12));
  titleSize = Math.max(Math.round(W * 0.055), Math.min(raw, Math.round(W * 0.10)));
} else {
  const raw = Math.round((W * 0.80) / (maxLen * 1.10));
  titleSize = Math.max(Math.round(W * 0.088), Math.min(raw, Math.round(W * 0.112)));
}
const lineH = Math.round(titleSize * 1.2);
const authorSize = Math.round(titleSize * 0.38);
const titleTop = Math.round(H * 0.062);
const authorTop = titleTop + lineH * lines.length + 14;
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const titleCss = `
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:${W}px; height:${H}px; background:transparent; overflow:hidden; }
  .wrap { position:relative; width:${W}px; height:${H}px; }
  .band { position:absolute; left:0; top:0; width:${W}px; height:${Math.round(H * 0.265)}px;
    background:linear-gradient(180deg, rgba(8,10,14,.58) 0%, rgba(8,10,14,.32) 48%, rgba(8,10,14,0) 100%); }
  .title { position:absolute; left:0; right:0; top:${titleTop}px;
    text-align:center;
    font-family:"STZhongsong","Source Han Serif SC","Songti SC","SimSun",serif;
    font-size:${titleSize}px; font-weight:700; line-height:${lineH}px;
    color:#fdfaf2; letter-spacing:${Math.round(titleSize * 0.06)}px;
    text-indent:${Math.round(titleSize * 0.06)}px;
    -webkit-text-stroke:${Math.round(titleSize * 0.07)}px rgba(18,16,14,.92);
    paint-order:stroke fill;
    text-shadow:0 ${Math.round(titleSize * 0.05)}px ${Math.round(titleSize * 0.16)}px rgba(0,0,0,.78); }
  .author { position:absolute; left:0; right:0; top:${authorTop}px;
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
<div class="title">${lines.map(esc).join('<br>')}</div>
${author ? `<div class="author">${esc(author)}</div>` : ''}
</div></body></html>`;

fs.mkdirSync(outDir, { recursive: true });
const chromium = loadChromium();
const CHROME_EXE = findChrome();
const browser = await chromium.launch(CHROME_EXE ? { executablePath: CHROME_EXE } : {});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });

const tmp1 = path.join(outDir, '.title_tmp.html');
fs.writeFileSync(tmp1, titleHtml, 'utf-8');
await page.goto(pathToFileURL(tmp1).href);
await page.waitForTimeout(250);
const titleOut = path.join(outDir, '标题层_1080x1920.png');
await page.screenshot({ path: titleOut, omitBackground: true, type: 'png' });
fs.unlinkSync(tmp1);
console.log(`[OK] ${titleOut}  ${lines.length}行 / 每行${titleSize}px / 作者${authorSize}px`);

if (coverPath && fs.existsSync(coverPath)) {
  const coverUrl = pathToFileURL(path.resolve(coverPath)).href;
  // 用真实书封宽高比，避免 object-fit 裁掉封面文字
  const ratio = (() => {
    try {
      const buf = fs.readFileSync(coverPath);
      if (buf.slice(1, 4).toString() === 'PNG') {
        return buf.readUInt32BE(16) / buf.readUInt32BE(20);
      }
    } catch (e) { /* fallthrough */ }
    return 1 / 1.412;
  })();
  const coverW = Math.round(W * 0.26);
  const coverH = Math.round(coverW / ratio);
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
    .spine { position:absolute; left:0; top:0; width:${Math.round(coverW * 0.055)}px; height:100%;
      background:linear-gradient(90deg, rgba(255,255,255,.14), rgba(0,0,0,.36)); }
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
  console.log(`[OK] ${coverOut}  ${coverW}×${coverH} @ (${left},${top}) ratio=${ratio.toFixed(3)}`);
}

await browser.close();
