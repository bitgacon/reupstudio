"""Curated offline creative library; numeric filters and original particle art."""
import math
from pathlib import Path
from uuid import uuid4
from PIL import Image,ImageDraw
from . import storage,media,timeline

FILTERS={
 'none':('Gốc',[1,0,0,0,1,0,0,0,1]),
 'mono':('Đen trắng',[.2126,.7152,.0722]*3),
 'sepia':('Hoài cổ',[.393,.769,.189,.349,.686,.168,.272,.534,.131]),
 'warm':('Nắng ấm',[1.12,.02,0,0,1,0,0,0,.82]),
 'cool':('Xanh lạnh',[.82,0,0,0,1,0,.04,0,1.12]),
 'cinema':('Điện ảnh',[.9,0,0,0,.94,.02,0,.03,1.04]),
 'neon':('Neon tím',[1.2,0,0,0,.85,0,0,0,1.25]),
 'dream':('Mơ màng',[.92,.08,.04,.04,.94,.04,.06,.04,.96]),
}
STICKERS={'heart':'Trái tim','fire':'Ngọn lửa','sparkles':'Lấp lánh','star':'Ngôi sao','rocket':'Tên lửa','party':'Ăn mừng','laugh':'Cười vui','wow':'Ngạc nhiên','clap':'Vỗ tay','like':'Thích','lightning':'Tia chớp','flower':'Bông hoa'}
FLUENT_REV='1ffb34c752ecf5d402f04cfb4b392c77f57c54bc'
FLUENT_NAMES={'heart':('Red heart','Trái tim'),'fire':('Fire','Ngọn lửa'),'sparkles':('Sparkles','Lấp lánh'),'party':('Party popper','Ăn mừng'),'love':('Smiling face with heart-eyes','Mắt trái tim'),'laugh':('Face with tears of joy','Cười vui'),'rocket':('Rocket','Tên lửa'),'eyes':('Eyes','Đôi mắt'),'hundred':('Hundred points','100 điểm'),'crown':('Crown','Vương miện'),'alien':('Alien','Người ngoài hành tinh'),'money':('Money bag','Túi tiền')}
FLUENT={f'fluent-{style}-{key}':f'{name} · Fluent {style}' for key,(_,name) in FLUENT_NAMES.items() for style in ('3D','Flat')}
MAGIC={'magic-ring':'Vòng phép thuật','magic-sparkles':'Bụi sao','magic-confetti':'Mưa màu',
 'magic-hologram':'Hologram · khung quét','magic-aurora':'Cực quang mềm','magic-doodle':'Nét vẽ tay · vòng vui',
 'magic-speed':'Manga · đường tốc độ','magic-bokeh':'Bokeh · ánh sáng trôi','magic-rain':'Mưa · lớp kính',
 'magic-snow':'Tuyết nhẹ','magic-orbit':'Quỹ đạo neon'}

def sticker_credit(key):
    if key in FLUENT:
        license_text=(storage.ROOT/'web'/'creative'/'FLUENT-LICENSE.txt').read_text(encoding='utf-8')
        return f'Microsoft Fluent Emoji, commit {FLUENT_REV}; https://github.com/microsoft/fluentui-emoji. Flat SVG rasterized to PNG; 3D PNG retained.\n'+license_text
    return 'Twemoji graphics © Twitter, Inc and contributors, CC BY 4.0; https://github.com/twitter/twemoji; https://creativecommons.org/licenses/by/4.0/. SVG rasterized to PNG.'

def matrix(name,strength=1):
    original=FILTERS['none'][1];target=FILTERS[name][1]
    return [a+(b-a)*strength for a,b in zip(original,target)]

def ffmpeg_filter(clip):
    name=clip.get('color_filter','none')
    if name=='none' or not clip.get('filter_strength',1):return ''
    values=matrix(name,clip.get('filter_strength',1));keys=['rr','rg','rb','gr','gg','gb','br','bg','bb']
    return ',colorchannelmixer='+':'.join(f'{k}={v:.9g}' for k,v in zip(keys,values))

def magic_frame(kind,t,size=512):
    if kind not in MAGIC:raise ValueError('Hiệu ứng không hỗ trợ.')
    image=Image.new('RGBA',(size,size));draw=ImageDraw.Draw(image);S=size/512
    colors=[(255,210,60),(60,235,255),(240,90,255),(100,255,120)]
    def line(points,color,width=2):
        draw.line([(x*S,y*S) for x,y in points],fill=color,width=max(1,round(width*S)))
    if kind=='magic-hologram':
        for j in range(9):
            y=40+j*54;line([(40,y),(472,y)],(50,240,255,45))
        y=40+(t/3%1)*432
        line([(40,y),(472,y)],(80,255,235,200),4)
        for x,y,dx,dy in [(40,40,1,1),(472,40,-1,1),(40,472,1,-1),(472,472,-1,-1)]:
            line([(x,y+dy*45),(x,y),(x+dx*45,y)],(100,255,245,220),4)
    elif kind=='magic-aurora':
        for j in range(16):
            points=[(x,230+j*4+55*math.sin(x/105+t*1.5+j*.12)) for x in range(0,513,8)]
            line(points,(60+j*9,245-j*7,220,40+j%4*12),12)
    elif kind=='magic-doodle':
        for j in range(3):
            points=[]
            for n in range(100):
                a=n/99*math.tau;r=135+j*5+5*math.sin(n*.7+t*4+j)
                points.append((256+r*math.cos(a),256+r*math.sin(a)))
            line(points,(*colors[j],200),3)
    elif kind=='magic-speed':
        for j in range(28):
            a=j*math.tau/28;r=155+20*math.sin(t*6+j);end=360
            line([(256+r*math.cos(a),256+r*math.sin(a)),(256+end*math.cos(a),256+end*math.sin(a))],(235,245,255,140+j%4*20),1+j%3)
    elif kind=='magic-orbit':
        for j in range(4):
            a=t*2+j*math.pi/2;points=[(256+180*math.cos(a+n*.014),256+65*math.sin(a+n*.014+j)) for n in range(130)]
            line(points,(*colors[j],170),3)
            x,y=points[-1];r=8*S;draw.ellipse((x*S-r,y*S-r,x*S+r,y*S+r),fill=(*colors[j],240))
    elif kind in ('magic-bokeh','magic-rain','magic-snow'):
        for j in range(48):
            phase=(t/3+j*.137)%1;x=((j*73)%480+16)+8*math.sin(t+j);y=phase*560-24
            if kind=='magic-rain':line([(x,y),(x-8,y+28)],(160,210,255,100),1)
            else:
                r=(10+j%14 if kind=='magic-bokeh' else 2+j%3)*S
                color=colors[j%4] if kind=='magic-bokeh' else (255,255,255)
                alpha=round((40 if kind=='magic-bokeh' else 190)*math.sin(math.pi*phase))
                draw.ellipse((x*S-r,y*S-r,x*S+r,y*S+r),fill=(*color,alpha))
    elif kind=='magic-ring':
        for j in range(3):
            r=(110+12*math.sin(t*math.tau+j))*S;c=colors[j];a=t*(1+j*.3)*180+j*120
            draw.arc((256*S-r,256*S-r,256*S+r,256*S+r),a,a+240,fill=(*c,200-j*40),width=max(1,round((7-j*2)*S)))
        for j in range(12):
            a=j*math.tau/12+t*2;r=130*S;x=256*S+math.cos(a)*r;y=256*S+math.sin(a)*r
            draw.ellipse((x-3*S,y-3*S,x+3*S,y+3*S),fill=(*colors[j%4],230))
    else:
        for j in range(45):
            phase=(t/3+j*.137)%1;x=((j*73)%480+16)*S;y=(512*(1-phase) if kind=='magic-sparkles' else 512*phase)*S
            a=int(220*math.sin(math.pi*phase));r=(3+j%4)*S;color=(*colors[j%4],a)
            if kind=='magic-sparkles':
                draw.polygon([(x,y-r*2),(x+r*.6,y),(x,y+r*2),(x-r*.6,y)],fill=color)
                draw.polygon([(x-r*2,y),(x,y+r*.6),(x+r*2,y),(x,y-r*.6)],fill=color)
            else:draw.rectangle((x-r,y-r/2,x+r,y+r/2),fill=color)
    return image

def catalog():
    return {'filters':[{'id':key,'name':name,'matrix':values,'thumb':f'/static/creative/{key}.png','kind':'filter'} for key,(name,values) in FILTERS.items()],
      'media':[{'id':key,'name':name,'kind':'sticker','pack':pack,'thumb':f'/static/creative/{key}.png','license':license_name} for items,pack,license_name in [(STICKERS,'Twemoji','Twemoji · CC BY 4.0'),(FLUENT,'Fluent','Microsoft Fluent Emoji · MIT')] for key,name in items.items() if (storage.ROOT/'web'/'creative'/f'{key}.png').is_file()]+[{'id':key,'name':name,'kind':'magic','pack':'Reup','thumb':f'/static/creative/{key}.png','license':'Reup · original procedural artwork'} for key,name in MAGIC.items()]}

def make_media(project,key,folder,event,progress):
    if key not in STICKERS and key not in FLUENT and key not in MAGIC:raise ValueError('Tài nguyên không hỗ trợ.')
    folder.mkdir(parents=True,exist_ok=True)
    if key in STICKERS or key in FLUENT:
        import shutil
        original=storage.ROOT/'web'/'creative'/f'{key}.png'
        if not original.is_file():raise ValueError('Thiếu nhãn dán. Chạy PREPARE_CREATIVE.py.')
        output=folder/'sticker.png';shutil.copy2(original,output)
        attribution=sticker_credit(key)
    else:
        # Short raw stream keeps CPU/memory bounded; cancellation kills owned FFmpeg.
        import subprocess
        output=folder/'magic.webm';attribution='Original procedural artwork generated by Reup Voice Studio.'
        with (folder/'creative.log').open('w') as log:
            proc=subprocess.Popen([media.binary(),'-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','512x512','-r','24','-i','pipe:0','-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-auto-alt-ref','0','-deadline','realtime','-cpu-used','8','-threads','2',str(output)],stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for i in range(72):
                    if event.is_set():raise InterruptedError('Đã dừng tạo hiệu ứng.')
                    proc.stdin.write(magic_frame(key,i/24).tobytes());progress(5+80*i/72,'Đang tạo lớp phép thuật trong suốt…')
                proc.stdin.close()
                if proc.wait(timeout=120):raise RuntimeError('Không tạo được hiệu ứng; xem creative.log.')
            finally:media.stop_owned_process(proc)
    if event.is_set():raise InterruptedError('Đã dừng nhập tài nguyên.')
    import shutil
    asset_id=uuid4().hex;dest=storage.DATA/'uploads'/asset_id;dest.mkdir(parents=True);source=dest/('source'+output.suffix);shutil.copy2(output,source)
    storage.atomic_json(dest/'asset.json',{'id':asset_id,'name':STICKERS.get(key) or FLUENT.get(key) or MAGIC[key],'file':source.name,'attribution':attribution,'creative_id':key})
    (folder/'ATTRIBUTION.txt').write_text(attribution,encoding='utf-8')
    return timeline.prepare(project,asset_id,event)
