/**
 * gen_bookcover.mjs —— 用 Playwright 把书名叠到书封底图上，输出书籍封面 PNG
 *
 * 用法：
 *   node gen_bookcover.mjs --cover <底图路径> --title "假如给我三天光明" --author "海伦凯勒" --out <输出路径> [--w 1024] [--h 1476]
 *
 * 说明：
 *   - Chromium 支持 omitBackground，输出带透明通道的 PNG
 *   - 底图向上偏移 CROP_BOTTOM 像素，用来裁掉 AI 生成器打在右下角的水印
 *   - 书名横排铺满宽度，作者名放在插画下方，均为衬线体
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

// ---- 定位 playwright-core（不依赖项目本地安装）----
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
    } catch (e) { /* 试下一个 */ }
  }
  console.error('[X] 找不到 playwright-core，请设置环境变量 PLAYWRIGHT_CORE_PATH');
  process.exit(1);
}

// ---- 定位本机已下载的 Chromium ----
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

const chromium = loadChromium();
const CHROME_EXE = findChrome();

const CROP_BOTTOM = 90; // 裁掉底图底部像素（去水印）

function arg(name, def = null) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const coverPath = arg('cover');
const title = arg('title');
const author = arg('author', '');
const outPath = arg('out');
const W = parseInt(arg('w', '1024'), 10);

if (!coverPath || !title || !outPath) {
  console.error('用法: node gen_bookcover.mjs --cover 底图.png --title 书名 --author 作者 --out 输出.png');
  process.exit(1);
}
if (!fs.existsSync(coverPath)) {
  console.error('[X] 底图不存在: ' + coverPath);
  process.exit(1);
}

// 底图原始高度 -> 容器高度 = 原高 - 裁切
const imgH = await new Promise((resolve) => {
  // PNG 头 24 字节处是宽高
  const fd = fs.openSync(coverPath, 'r');
  const buf = Buffer.alloc(24);
  fs.readSync(fd, buf, 0, 24, 0);
  fs.closeSync(fd);
  resolve(buf.readUInt32BE(20));
});
const H = imgH - CROP_BOTTOM;

const imgUrl = pathToFileURL(path.resolve(coverPath)).href;
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// 字号按容器宽高自适应：书名铺到 ~85% 宽
const titleSize = Math.round((W * 0.85) / (title.length * 1.12));
const authorSize = Math.round(titleSize * 0.5);

const html = `<!doctype html>
<html><head><meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:${W}px; height:${H}px; background:transparent; overflow:hidden; }
  .stage { position:relative; width:${W}px; height:${H}px; }
  .bg { position:absolute; left:0; top:0; width:${W}px; height:${imgH}px; }
  /* 底图四边压一圈极淡暗角，让书封边缘更实 */
  .vignette { position:absolute; inset:0;
    box-shadow: inset 0 0 ${Math.round(W * 0.09)}px rgba(0,0,0,.55); }
  .title { position:absolute; left:0; right:0; top:${Math.round(H * 0.052)}px;
    text-align:center; text-indent:${Math.round(titleSize * 0.06)}px;
    font-family:"STZhongsong","Source Han Serif SC","Noto Serif CJK SC","SimSun",serif;
    font-size:${titleSize}px; font-weight:700; line-height:1.0;
    color:#f4efe3; letter-spacing:${Math.round(titleSize * 0.06)}px;
    text-shadow: 0 2px 8px rgba(0,0,0,.75), 0 0 2px rgba(0,0,0,.5); }
  .author { position:absolute; left:0; right:0; bottom:${Math.round(H * 0.085)}px;
    text-align:center; text-indent:${Math.round(authorSize * 0.18)}px;
    font-family:"STZhongsong","Source Han Serif SC","SimSun",serif;
    font-size:${authorSize}px; font-weight:400; line-height:1.0;
    color:#c2a04e; letter-spacing:${Math.round(authorSize * 0.18)}px;
    text-shadow: 0 2px 6px rgba(0,0,0,.8); }
  .rule { position:absolute; left:50%; transform:translateX(-50%);
    bottom:${Math.round(H * 0.062)}px; width:${Math.round(W * 0.22)}px; height:1px;
    background:linear-gradient(90deg,transparent,#b08d3f,transparent); }
</style></head>
<body>
  <div class="stage">
    <img class="bg" src="${imgUrl}">
    <div class="vignette"></div>
    <div class="title">${esc(title)}</div>
    ${author ? `<div class="author">${esc(author)}</div><div class="rule"></div>` : ''}
  </div>
</body></html>`;

const tmpHtml = path.join(path.dirname(outPath), '.bookcover_tmp.html');
fs.writeFileSync(tmpHtml, html, 'utf-8');

const browser = await chromium.launch(CHROME_EXE ? { executablePath: CHROME_EXE } : {});
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(tmpHtml).href);
await page.waitForTimeout(300);
await page.screenshot({ path: outPath, omitBackground: true, type: 'png' });
await browser.close();
fs.unlinkSync(tmpHtml);

console.log(`[OK] 书封已生成: ${outPath}`);
console.log(`     尺寸 ${W}×${H} | 书名 ${title.length}字 字号${titleSize}px | 作者 字号${authorSize}px`);
