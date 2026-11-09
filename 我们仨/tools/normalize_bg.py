# -*- coding: utf-8 -*-
"""把背景图规整到 1080×1920：先按 9:16 居中裁切，再缩放。

为什么要这一步：ImageGen 出图是 1072×1920，裁掉底部 90px 水印后变成 1072×1830
（比例 0.586），直接放进 1080×1920 画布会被剪映拉伸 4%，桌面、碗沿这类
直线条会明显歪。先居中裁到 9:16 再缩放，比例严格一致。

用法：python tools/normalize_bg.py --dir 00_原始素材/背景图
"""
import argparse
import glob
import os
import sys

from PIL import Image

W, H = 1080, 1920


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="00_原始素材/背景图")
    args = ap.parse_args()

    for p in sorted(glob.glob(os.path.join(args.dir, "*.png"))):
        im = Image.open(p).convert("RGB")
        w, h = im.size
        target_ratio = W / float(H)
        if w / float(h) > target_ratio:          # 太宽 -> 裁两侧
            nw = int(round(h * target_ratio))
            left = (w - nw) // 2
            im = im.crop((left, 0, left + nw, h))
        else:                                     # 太高 -> 裁底部（保留上部主体）
            nh = int(round(w / target_ratio))
            im = im.crop((0, 0, w, nh))
        im = im.resize((W, H), Image.LANCZOS)
        im.save(p, optimize=True)
        print("[OK] %-14s %dx%d -> %dx%d" % (os.path.basename(p), w, h, W, H))


if __name__ == "__main__":
    sys.exit(main())
