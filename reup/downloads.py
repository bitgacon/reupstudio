"""User-requested public media downloads; no DRM bypass or shared browser cookies."""
from __future__ import annotations
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from . import media, storage, timeline


def normalize(url):
    url=url.strip(); parts=urlsplit(url)
    if parts.scheme not in {'http','https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Nhập URL HTTP/HTTPS công khai, không chứa mật khẩu.')
    host=parts.hostname.lower()
    if host=='localhost' or host.endswith(('.localhost','.local')):
        raise ValueError('Không tải từ địa chỉ nội bộ.')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Không tải từ địa chỉ nội bộ.')
    except ValueError as exc:
        if 'nội bộ' in str(exc):raise
    if host=='douyin.com' or host.endswith('.douyin.com'):
        key=(parse_qs(parts.query).get('modal_id') or [''])[0]
        if re.fullmatch(r'\d+',key):return 'https://www.douyin.com/video/'+key
    return url


def process(args,event,progress=None):
    if event.is_set():raise InterruptedError('Đã dừng trước khi tải.')
    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=queue.Queue(maxsize=100); output=[]; size=0
    def read():
        try:
            for line in proc.stdout:
                while proc.poll() is None:
                    try:lines.put(line,timeout=.2);break
                    except queue.Full:
                        if event.is_set():return
                else:
                    try:lines.put_nowait(line)
                    except queue.Full:return
        finally:
            try:lines.put(None,timeout=1)
            except queue.Full:pass
    reader=threading.Thread(target=read,daemon=True);reader.start()
    try:
        ended=False
        while not ended or proc.poll() is None:
            if event.is_set():raise InterruptedError('Đã dừng tải; các file đã hoàn thành vẫn được giữ.')
            try:line=lines.get(timeout=.2)
            except queue.Empty:
                if not reader.is_alive() and proc.poll() is not None:break
                continue
            if line is None:ended=True;continue
            if line.startswith('REUP_PROGRESS:'):
                if progress:
                    match=re.search(r'([\d.]+)%',line)
                    if match:progress(float(match[1]))
            else:
                size+=len(line)
                if size>20_000_000:raise ValueError('Phản hồi tải quá lớn; chia nhỏ danh sách.')
                output.append(line)
        if proc.returncode:raise RuntimeError('Nguồn tải từ chối hoặc cần cookies mới. '+''.join(output)[-500:])
        return ''.join(output)
    finally:
        if proc.poll() is None:media.stop_owned_process(proc)
        reader.join(timeout=2);proc.stdout.close()


def command(url,cookie=''):
    import importlib.util
    if not importlib.util.find_spec('yt_dlp'):raise ValueError('Thiếu yt-dlp. Chạy INSTALL_DOWNLOADS.bat trước.')
    args=[sys.executable,'-m','yt_dlp','--ignore-config','--no-plugin-dirs','--no-warnings','--socket-timeout','20','--retries','2','--ffmpeg-location',str(Path(media.binary()).parent)]
    host=urlsplit(url).hostname or ''
    for domain in ['douyin.com','weibo.com','weibo.cn','tiktok.com']:
        if host==domain or host.endswith('.'+domain):args+=['--referer','https://'+domain+'/'];break
    if cookie:
        path,_=storage.asset(cookie)
        if path.suffix!='.txt':raise ValueError('Cookies phải là file Netscape .txt đã nhập.')
        args+=['--cookies',str(path)]
    return args


def scan(payload,event):
    url=normalize(str(payload.get('url','')))
    args=command(url,payload.get('cookie',''))+['--flat-playlist','--skip-download','--playlist-end','200','--dump-single-json','--',url]
    info=json.loads(process(args,event))
    rows=info.get('entries') or [info];seen=set();result=[]
    for row in rows:
        if not row:continue
        link=row.get('webpage_url') or row.get('url') or ''
        if not link.startswith(('https://','http://')) and row.get('ie_key')=='Youtube':link='https://www.youtube.com/watch?v='+str(row.get('id',''))
        try:link=normalize(link)
        except ValueError:continue
        if link not in seen:seen.add(link);result.append({'url':link,'title':str(row.get('title') or link)[:300]})
    return {'entries':result,'message':f'Đã lấy {len(result)} link (tối đa 200); chọn tối đa 50 mỗi lượt tải.'}


def publish(source,title,url,job_id,original=None,subtitles=None):
    key=uuid4().hex;folder=storage.DATA/'uploads'/key;folder.mkdir(parents=True)
    target=folder/('source'+source.suffix.lower())
    try:os.link(source,target)
    except OSError:shutil.copy2(source,target)
    meta={'id':key,'name':title[:200]+source.suffix,'file':target.name,'bytes':source.stat().st_size}
    storage.atomic_json(folder/'asset.json',meta)
    info=media.probe(source);stream=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),{})
    row={'id':key,'asset':key,'name':meta['name'],'source_url':url,'job_id':job_id,'kind':'video' if stream else 'audio','width':stream.get('width',0),'height':stream.get('height',0),'original':original or {},'file':{'url':storage.file_url(source),'name':meta['name'],'type':source.suffix.lstrip('.'),'bytes':meta['bytes']}}
    if subtitles:row['subtitles']=subtitles
    with storage.LOCK:
        rows=storage.read_json(storage.DATA/'download-index.json',[]);rows.insert(0,row);storage.atomic_json(storage.DATA/'download-index.json',rows[:500])
    return row


def download(payload,job_id,progress,event):
    urls=list(dict.fromkeys(normalize(str(u)) for u in payload.get('urls',[])))
    if not 1<=len(urls)<=50:raise ValueError('Nhập từ 1 đến 50 URL mỗi lượt.')
    quality=str(payload.get('quality','1080'));audio=payload.get('audio') is True
    if quality not in {'native','720','1080','1440','2160'}:raise ValueError('Chất lượng không hợp lệ.')
    subtitle_language=str(payload.get('subtitle_language','vi'))
    if payload.get('subtitles') is True and not re.fullmatch(r'[A-Za-z0-9-]{1,20}',subtitle_language):raise ValueError('Mã ngôn ngữ phụ đề không hợp lệ (vi, en, zh-Hans…).')
    folder=storage.output_folder('downloads',job_id);entries=[];errors=[]
    for i,url in enumerate(urls):
        if event.is_set():raise InterruptedError('Đã dừng; xem danh sách các file đã tải xong.')
        part=folder/f'{i+1:03}';part.mkdir(exist_ok=True)
        try:
            fmt='bestaudio/best' if audio else 'bv*+ba/b' if quality=='native' else f'bv*[height<={quality}]+ba/b[height<={quality}]/bv*+ba/b'
            args=command(url,payload.get('cookie',''))+['--no-simulate','--no-playlist','--newline','--max-filesize','8G','-f',fmt,'--merge-output-format','mkv','-o',str(part/'source.%(ext)s'),'--progress-template','download:REUP_PROGRESS:%(progress._percent_str)s','--print','before_dl:REUP_TITLE:%(title)s','--',url]
            if payload.get('subtitles') is True:
                args[-2:-2]=['--write-subs','--sub-langs',subtitle_language,'--sub-format','srt/vtt/best','--convert-subs','srt']
                if payload.get('auto_subtitles') is True:args[-2:-2]=['--write-auto-subs']
            result=process(args,event,lambda pct:progress((i+pct/100*.65)/len(urls)*100,f'Tải {i+1}/{len(urls)} · {pct:.0f}%'))
            source=next((p for p in part.glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov','.m4a','.mp3','.ogg','.wav'}),None)
            if not source:raise ValueError('Không có file media sau khi tải.')
            info=media.probe(source);stream=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),{})
            duration=float(info.get('format',{}).get('duration',0))
            if not 0<duration<=14400:raise ValueError('Media trống hoặc dài hơn 4 giờ; chia nhỏ nguồn.')
            output=part/('audio.mp3' if audio else 'video.mp4')
            vf=[]
            if not audio and quality!='native' and stream:
                factor=int(quality)/min(stream['width'],stream['height']);w=round(stream['width']*factor/2)*2;h=round(stream['height']*factor/2)*2
                if max(w,h)>7680:raise ValueError('Tỷ lệ quá dài; chọn chất lượng nhỏ hơn.')
                vf=['-vf',f'scale={w}:{h}:flags=lanczos']
            encode=['-vn','-c:a','libmp3lame','-b:a','192k'] if audio else vf+['-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-movflags','+faststart']
            progress((i+.65)/len(urls)*100,f'Render {i+1}/{len(urls)} · {quality} (nâng kích thước không thêm chi tiết)…')
            timeline.run_cancel([media.binary(),'-y','-v','error','-threads','2','-i',str(source),*encode,'-progress','pipe:1',str(output)],event,lambda pct,msg:progress((i+.65+.35*pct/100)/len(urls)*100,f'Render {i+1}/{len(urls)} · {pct:.0f}%'),duration*1000)
            title=next((line.split(':',1)[1] for line in result.splitlines() if line.startswith('REUP_TITLE:')),f'Media {i+1}')
            subtitles=[]
            if payload.get('subtitles') is True:
                from .subtitle_removal import artifact,store_asset
                for sub in sorted(part.glob('source.*.srt')):
                    if not sub.resolve().is_relative_to(part.resolve()) or sub.stat().st_size>5_000_000:continue
                    cues,issues=media.parse_srt(media.decode_text(sub.read_bytes()))
                    if cues and not any(i.get('level')=='error' for i in issues):subtitles.append({'asset':store_asset(sub,sub.name),'file':artifact(sub)})
            entries.append(publish(output,title,url,job_id,{'width':stream.get('width',0),'height':stream.get('height',0)},subtitles=subtitles))
            # The final artifact and library asset have been verified/published. Only
            # remove our exact intermediate input, never a folder or user's file.
            source.unlink()
            progress((i+1)/len(urls)*100,f'Đã lưu {i+1}/{len(urls)}')
        except InterruptedError:raise
        except Exception as exc:errors.append({'index':i+1,'error':str(exc)[-500:]})
    if not entries:raise ValueError('Không tải được file nào: '+str(errors)[:1000])
    return {'entries':entries,'errors':errors,'files':[e['file'] for e in entries],'message':f'Đã tải/render {len(entries)} file, {len(errors)} lỗi. File hoàn thành nằm trong danh sách tải.'}


def send_many(asset_ids,tab):
    if tab not in {'dub','edit'}:raise ValueError('Chọn tab lồng tiếng hoặc biên tập.')
    keys=list(dict.fromkeys(storage.identifier(key) for key in asset_ids))
    if not 1<=len(keys)<=50:raise ValueError('Chọn từ 1 đến 50 file.')
    with storage.LOCK:
        index={r['id']:r for r in storage.read_json(storage.DATA/'download-index.json',[])};items=[]
        for key in keys:
            row=index.get(key)
            if not row:raise ValueError('Không tìm thấy bản tải; tải lại danh sách.')
            source,_=storage.asset(key);info=media.probe(source);duration=round(float(info['format']['duration'])*1000)
            if duration<100:raise ValueError('Media quá ngắn.')
            if tab=='dub' and row['kind']!='video':raise ValueError('Lồng tiếng chỉ chọn video; MP3 chuyển sang Biên tập.')
            items.append((row,duration))
        if tab=='edit' and sum(d for r,d in items)>3_600_000:raise ValueError('Tổng timeline editor tối đa 60 phút; chọn ít file hơn.')
        projects=[]
        if tab=='dub':
            for row,duration in items:
                project=storage.new_project(row['name'][:100]);project['video']=row['asset'];storage.retain_assets(project);storage.save_project(project);projects.append(project['id'])
        else:
            tracks={};offset=0
            for row,duration in items:
                kind='video' if row['kind']=='video' else 'audio'
                if kind not in tracks:tracks[kind]=timeline.Track(id=uuid4().hex,name='Media tải về · '+kind,kind=kind)
                tracks[kind].clips.append(timeline.Clip(id=uuid4().hex,asset=row['asset'],label=row['name'][:200],start_ms=offset,duration_ms=duration));offset+=duration
            project=storage.new_project(items[0][0]['name'][:80]+(f' + {len(items)-1} file' if len(items)>1 else ''),kind='edit')
            timeline.save(project['id'],timeline.Timeline(assets=keys,tracks=list(tracks.values())).model_dump());projects.append(project['id'])
    return {'project_id':projects[0],'project_ids':projects,'tab':tab,'count':len(keys)}


def send(asset_id,tab):
    return send_many([asset_id],tab)


def managed_files(row):
    """Exact owned paths, resolved before moving. Never trust client file paths."""
    from urllib.parse import unquote
    job=storage.identifier(row['job_id']);url=unquote(row['file']['url'])
    parts=url.split('/')
    if len(parts)<6 or parts[:2]!=['','files'] or parts[2] not in {'outputs','exports'} or any(p in {'.','..'} or '\\' in p or ':' in p for p in parts[3:]) or not re.fullmatch(r'\d{3}',parts[-2]) or parts[-1] not in {'video.mp4','audio.mp3'}:
        raise ValueError('Đường dẫn tải không hợp lệ; không xóa file.')
    registered=storage.read_json(storage.DATA/'output-index.json',{}).get(job)
    if parts[2]=='exports' and not registered:raise ValueError('Không tìm thấy thư mục tải đã đăng ký.')
    root=(Path(registered) if registered else storage.DATA/'outputs'/job).resolve()
    if root.name not in {job,'Reup-downloads-'+job} and not (root.parent.name=='Downloads' and re.fullmatch(r'Downloads\d+',root.name)):raise ValueError('Thư mục tải không đúng; không xóa file.')
    folder=(root/parts[-2]).resolve()
    if not folder.is_relative_to(root) or folder==root:raise ValueError('Đường dẫn tải ra ngoài thư mục.')
    if url!=unquote(storage.file_url(folder/parts[-1])):raise ValueError('Đường dẫn tải không khớp job; không xóa file.')
    paths=[folder/parts[-1]]+[folder/('source'+ext) for ext in ('.mp4','.webm','.mkv','.mov','.m4a','.mp3','.ogg','.wav')]
    paths += [p for p in folder.glob('source.*') if re.fullmatch(r'source\.[A-Za-z0-9-]+\.(srt|vtt)',p.name)]
    for path in paths:
        if not path.resolve().is_relative_to(folder):raise ValueError('File tải liên kết ra ngoài thư mục; không xóa.')
    return [p for p in paths if p.is_file()]


def referenced(asset_id):
    # Keep the library copy if any saved project/preset still depends on it.
    for row in storage.read_json(storage.DATA/'vsr-index.json',[]):
        if asset_id in {row.get('asset'),row.get('source_asset'),row.get('subtitle_asset')}:return True
    for row in storage.read_json(storage.DATA/'vsr-subtitles.json',[]):
        if asset_id in {row.get('asset'),row.get('subtitle_asset')}:return True
    for summary in storage.list_projects():
        value=storage.project(summary['id']);doc=timeline.load(summary['id'])
        if asset_id==value.get('video') or asset_id in value.get('local_assets',{}) or asset_id in doc['assets'] or any(c['asset']==asset_id for t in doc['tracks'] for c in t['clips']):return True
    for preset in storage.read_json(storage.DATA/'track-presets.json',[]):
        doc=preset['timeline']
        if asset_id in doc['assets'] or any(c['asset']==asset_id for t in doc['tracks'] for c in t['clips']):return True
    return False


def remove_many(asset_ids,delete_files=False):
    keys=list(dict.fromkeys(storage.identifier(key) for key in asset_ids))
    if not 1<=len(keys)<=50:raise ValueError('Chọn từ 1 đến 50 file.')
    with storage.LOCK:
        rows=storage.read_json(storage.DATA/'download-index.json',[]);selected=[r for r in rows if r['id'] in keys]
        if len(selected)!=len(keys):raise ValueError('Danh sách đã thay đổi; tải lại rồi chọn.')
        if not delete_files:
            storage.atomic_json(storage.DATA/'download-index.json',[r for r in rows if r['id'] not in keys]);return {'removed':len(keys),'files_moved':0,'retained_assets':0}
        plan=[];retained=0
        for row in selected:
            plan.extend(managed_files(row))
            if referenced(row['asset']):retained+=1;continue
            folder=(storage.DATA/'uploads'/storage.identifier(row['asset'])).resolve()
            if not folder.is_relative_to((storage.DATA/'uploads').resolve()):raise ValueError('Thư viện nằm ngoài kho; không xóa.')
            meta=storage.read_json(folder/'asset.json',{})
            if meta:
                source,_=storage.asset(row['asset']);plan.extend([source,folder/'asset.json'])
        trash=storage.DATA/'trash'/'downloads'/uuid4().hex;trash.mkdir(parents=True)
        moved=[]
        try:
            for i,path in enumerate(dict.fromkeys(plan)):
                if not path.is_file():continue
                target=trash/(f'{i:03}-'+path.name);shutil.move(str(path),str(target));moved.append((path,target))
            storage.atomic_json(trash/'restore.json',{'rows':selected,'moves':[{'original':str(a),'saved':str(b)} for a,b in moved]})
            storage.atomic_json(storage.DATA/'download-index.json',[r for r in rows if r['id'] not in keys])
        except BaseException:
            for original,saved in reversed(moved):shutil.move(str(saved),str(original))
            raise
        return {'removed':len(keys),'files_moved':len(moved),'retained_assets':retained,'trash':str(trash)}
