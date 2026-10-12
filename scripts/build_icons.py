"""Raster companions to the original SVG mark, for installed-app compatibility."""
from PIL import Image,ImageDraw
from backend.config import ROOT
for size in (192,512):
    image=Image.new('RGB',(size,size),'#123d39');draw=ImageDraw.Draw(image)
    scale=size/192
    def rect(bounds,radius,color):draw.rounded_rectangle(tuple(round(v*scale) for v in bounds),radius=round(radius*scale),fill=color)
    for x in (42,80,118):rect((x,45,x+32,151),6,'#e5f4ec')
    for x in (64,102):rect((x,42,x+23,107),4,'#123d39')
    image.save(ROOT/f'frontend/public/icon-{size}.png')
