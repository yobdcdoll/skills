#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preprocess.py — 试卷照片预处理：纠偏 + 纸张定位 + 左右分页

用法:
  python3 preprocess.py <input.jpg> --outdir hw_restore [--split] [--debug]

输出:
  <outdir>/01_deskewed_full.jpg   回正后的整张纸
  <outdir>/angle.txt              估计的纠偏角(度)
  <outdir>/L_full.jpg, R_full.jpg 左右分页(需 --split)
  <outdir>/_debug_*.jpg           中间图(需 --debug)

依赖: opencv-python, numpy
"""
import argparse, os, sys
import numpy as np
import cv2


def estimate_angle_projection(gray, rng=3.0):
    """投影法：找使水平投影方差最大的角（文字行最水平）。返回 (角度, 是否可信)。
    若最优角落在搜索范围边界，说明是噪声，判为不可信。"""
    best_a, best_score = 0.0, -1.0
    inv = 255 - gray
    h, w = gray.shape
    for a in np.arange(-rng, rng + 1e-9, 0.1):
        M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
        rot = cv2.warpAffine(inv, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=255)
        score = rot.sum(axis=1).astype(np.float64).var()
        if score > best_score:
            best_score, best_a = score, a
    trust = abs(abs(best_a) - rng) > 0.15   # 不贴边界才可信
    return float(best_a), trust


def estimate_angle_hough(gray):
    """Hough 变换：取检测到的长线角度中位数。返回 (角度, 线数)。"""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=150,
                            minLineLength=gray.shape[1] // 4, maxLineGap=20)
    if lines is None:
        return None, 0
    angs = []
    for l in lines[:, 0]:
        x1, y1, x2, y2 = l
        ang = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -30 < ang < 30:
            angs.append(ang)
    return (float(np.median(angs)), len(angs)) if angs else (None, 0)


def decide_angle(gray):
    """综合投影法与 Hough 决定纠偏角。
    经验：两者一致时最可信；矛盾时优先取「有足够线支撑的 Hough」；
    都没有则退回投影（哪怕它不可信），绝不靠肉眼估。"""
    a_proj, proj_trust = estimate_angle_projection(gray)
    a_hough, n_lines = estimate_angle_hough(gray)
    print(f"[angle] 投影法={a_proj:.2f}(可信={proj_trust})  "
          f"Hough={('None' if a_hough is None else format(a_hough, '.2f'))}(线数={n_lines})")
    if a_hough is not None and n_lines >= 8:
        if proj_trust and abs(a_proj - a_hough) <= 1.0:
            return (a_proj + a_hough) / 2
        return a_hough
    if proj_trust:
        return a_proj
    if a_hough is not None:
        return a_hough
    return a_proj


def rotate(gray, angle):
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def paper_bbox(gray):
    """返回纸张 bbox (x0,y0,x1,y1)。"""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thr = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    cnts, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return (0, 0, gray.shape[1], gray.shape[0])
    c = max(cnts, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    return (x, y, x + w, y + h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--split", action="store_true", help="按中缝切左右两页")
    ap.add_argument("--seam", type=float, default=0.5, help="中缝位置(宽度占比)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    img = cv2.imread(args.image)
    if img is None:
        sys.exit(f"读不到图: {args.image}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- 纠偏（投影法 + Hough 交叉验证） ---
    angle = decide_angle(gray)
    print(f"[angle] 采用 ≈ {angle:.2f}°")
    desk = rotate(gray, angle)

    # --- 纸张定位 ---
    x0, y0, x1, y1 = paper_bbox(desk)
    print(f"[paper] bbox = {x0} {y0} {x1} {y1}")
    desk = desk[y0:y1, x0:x1]

    cv2.imwrite(os.path.join(args.outdir, "01_deskewed_full.jpg"), desk,
                [cv2.IMWRITE_JPEG_QUALITY, 92])
    with open(os.path.join(args.outdir, "angle.txt"), "w") as f:
        f.write(str(-angle))  # 记录「需要旋转的量」，供参考

    if args.split:
        h, w = desk.shape
        seam = int(w * args.seam)
        L = desk[:, :seam]
        R = desk[:, seam:]
        cv2.imwrite(os.path.join(args.outdir, "L_full.jpg"), L, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(os.path.join(args.outdir, "R_full.jpg"), R, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"[split] L={L.shape[1]}x{L.shape[0]}  R={R.shape[1]}x{R.shape[0]}  seam={seam}")

    if args.debug:
        cv2.imwrite(os.path.join(args.outdir, "_debug_edges.jpg"),
                    cv2.Canny(desk, 50, 150))

    print("done.")


if __name__ == "__main__":
    main()
