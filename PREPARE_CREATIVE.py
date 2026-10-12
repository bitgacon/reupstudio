"""Prepare pinned CC-BY Twemoji, MIT Fluent Emoji and original thumbnails."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import requests
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from reup.creative import FILTERS,MAGIC,FLUENT_NAMES,FLUENT_REV,matrix,magic_frame

def save_svg(svg,target):
    renderer=QSvgRenderer(svg)
    if not renderer.isValid():raise ValueError('SVG không hợp lệ: '+str(target))
    image=QImage(512,512,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent);painter=QPainter(image);renderer.render(painter);painter.end()
    if not image.save(str(target)):raise RuntimeError('Không lưu được '+str(target))

root=Path(__file__).resolve().parent/'web'/'creative'
codes={'heart':'2764','fire':'1f525','sparkles':'2728','star':'2b50','rocket':'1f680','party':'1f389','laugh':'1f602','wow':'1f62e','clap':'1f44f','like':'1f44d','lightning':'26a1','flower':'1f33c'}
if __name__=='__main__':
    app=QApplication([]);root.mkdir(parents=True,exist_ok=True)
    base='https://raw.githubusercontent.com/twitter/twemoji/v14.0.2/'
    for name,code in codes.items():
        target=root/f'{name}.png'
        if target.exists():continue
        response=requests.get(base+f'assets/svg/{code}.svg',timeout=45);response.raise_for_status();svg=response.content
        save_svg(svg,target)
        print('Sticker:',name,flush=True)
    fluent_base=f'https://raw.githubusercontent.com/microsoft/fluentui-emoji/{FLUENT_REV}/'
    fluent_notice=root/'FLUENT-LICENSE.txt'
    if not fluent_notice.exists():
        response=requests.get(fluent_base+'LICENSE',timeout=45);response.raise_for_status();fluent_notice.write_bytes(response.content)
    from urllib.parse import quote
    from io import BytesIO
    for key,(directory,_) in FLUENT_NAMES.items():
        for style in ('3D','Flat'):
            target=root/f'fluent-{style}-{key}.png'
            if target.exists():continue
            stem=directory.lower().replace(' ','_');suffix='png' if style=='3D' else 'svg'
            path=f'assets/{directory}/{style}/{stem}_{style.lower()}.{suffix}'
            response=requests.get(fluent_base+quote(path,safe='/'),timeout=45);response.raise_for_status()
            if style=='Flat':save_svg(response.content,target)
            else:
                image=Image.open(BytesIO(response.content));image.load();image.convert('RGBA').save(target)
            print('Fluent:',style,key,flush=True)
    for name in FILTERS:
        target=root/f'{name}.png'
        if target.exists():continue
        image=Image.new('RGB',(160,90));values=matrix(name)
        for y in range(90):
            for x in range(160):
                rgb=(x*255/159,y*255/89,180)
                image.putpixel((x,y),tuple(max(0,min(255,round(sum(values[i*3+j]*rgb[j] for j in range(3))))) for i in range(3)))
        image.save(target)
    for name in MAGIC:
        target=root/f'{name}.png'
        if not target.exists():magic_frame(name,.7,160).save(target)
    notice=root/'TWEMOJI-LICENSE.txt'
    if not notice.exists():
        response=requests.get(base+'LICENSE-GRAPHICS',timeout=45);response.raise_for_status();notice.write_bytes(response.content)
    print('Creative library ready. Twemoji graphics CC BY 4.0; see THIRD_PARTY_NOTICES.md.')
