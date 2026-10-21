# -*- coding: utf-8 -*-
"""应用图标生成器：把 assets/Image.png（用户提供的水晶插画，白底）
处理成透明底图标（连通域去背、边缘去白、裁切居中、多尺寸 ico + 预览）。

用法：python assets/make_icon.py
产物：icon-full.png / icon-1024.png / workbench.ico / preview-icon.png
"""
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ASSETS = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ASSETS, "新.png")
if not os.path.exists(SRC):
    SRC = os.path.join(ASSETS, "Image.png")

img = Image.open(SRC).convert("RGB")
w, h = img.size
print("src:", img.size)

# 1) 擦掉右下角水印区域（纯背景区，宝石不在此）
d = ImageDraw.Draw(img)
d.rectangle([int(w * 0.55), int(h * 0.86), w, h], fill=(255, 255, 255))

arr = np.array(img).astype(np.int16)

# 2) 背景 = 与图像边缘连通的近白区域（宝石内部高光不与边缘连通，保留）
near_white = (arr[:, :, 0] > 232) & (arr[:, :, 1] > 232) & (arr[:, :, 2] > 232)
lab, n = ndimage.label(near_white)
edge_labels = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])))
edge_labels.discard(0)
bg = np.isin(lab, list(edge_labels))
print("bg px:", int(bg.sum()), "edge labels:", len(edge_labels))

alpha_bin = ~bg
alpha_bin = ndimage.binary_erosion(alpha_bin, iterations=1)
alpha_f = ndimage.gaussian_filter(alpha_bin.astype(float), 1.1)

# 3) 边缘去白（unpremultiply，背景为白色）
a = alpha_f[..., None]
rgb = np.array(img).astype(float)
rgb = np.where(a > 0.02, (rgb - (1 - a) * 255.0) / np.maximum(a, 1e-6), rgb)
rgb = np.clip(rgb, 0, 255)

out = np.dstack([rgb, alpha_f * 255.0]).astype(np.uint8)
im = Image.fromarray(out, "RGBA")

# 4) 裁切到内容 bbox + 12% padding，正方形居中
#    SCALE：图案在画布中的放大倍率（1.0 = 原始 12% 留白；1.2 = 图案再放大 1.2 倍，尖端轻微裁剪）
SCALE = 1.2
bbox = im.getchannel("A").getbbox()
print("bbox:", bbox)
x0, y0, x1, y1 = bbox
side = int(max(x1 - x0, y1 - y0) * 1.12 / SCALE)
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
left, top = int(cx - side / 2), int(cy - side / 2)
crop = im.crop((left, top, left + side, top + side))
print("crop:", crop.size)
crop.save(os.path.join(ASSETS, "icon-full.png"))

base = crop.resize((1024, 1024), Image.LANCZOS)
base.save(os.path.join(ASSETS, "icon-1024.png"))
ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
base.save(os.path.join(ASSETS, "workbench.ico"), sizes=ico_sizes)
print("saved icon-full.png / icon-1024.png / workbench.ico")

# 5) 预览：浅底/深底大图 + 小尺寸 + 任务栏模拟
def paste_c(canvas, im2, cx, cy):
    canvas.paste(im2, (int(cx - im2.width / 2), int(cy - im2.height / 2)), im2)

PW, PH = 1560, 820
canvas = Image.new("RGB", (PW, PH), (255, 255, 255))
d = ImageDraw.Draw(canvas)
d.rectangle([0, 0, PW, 360], fill=(245, 243, 238))
d.rectangle([0, 372, PW, 732], fill=(20, 19, 28))
d.rectangle([0, 744, PW, PH], fill=(34, 34, 38))
big = base.resize((256, 256), Image.LANCZOS)
paste_c(canvas, big, 170, 180)
paste_c(canvas, big, 170, 552)
x = 380
for s in [128, 96, 64, 48, 32, 24, 16]:
    im2 = base.resize((s, s), Image.LANCZOS)
    paste_c(canvas, im2, x + s / 2, 180)
    paste_c(canvas, im2, x + s / 2, 552)
    x += s + 40
x = 460
for s in [64, 48, 32, 24, 16]:
    im2 = base.resize((s, s), Image.LANCZOS)
    paste_c(canvas, im2, x + s / 2, 786)
    x += s + 60
canvas.save(os.path.join(ASSETS, "preview-icon.png"))
print("saved preview-icon.png")
