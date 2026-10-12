"""Explicit project copies between distinct editing and dubbing workflows."""
from copy import deepcopy
from pathlib import Path
import shutil
from uuid import uuid4

from . import storage, media, timeline, editor


def checkpoint(event):
    if event.is_set():raise InterruptedError('Đã dừng chuyển dự án; bản gốc được giữ nguyên.')


def attach(project, source):
    key=uuid4().hex
    folder=storage.project_path(project['id'])/'assets'
    folder.mkdir(parents=True,exist_ok=True)
    destination=folder/(key+source.suffix)
    shutil.copy2(source,destination)
    project.setdefault('local_assets',{})[key]={'id':key,'name':source.name,'file':destination.name}
    project['video']=key
    storage.save_project(project)
    return key


def captions(project, cfg):
    tracks=[]
    for cue in sorted(project['cues'],key=lambda c:c['start_ms']):
        text=editor.caption(cue,cfg)
        if not text.strip():continue
        track=next((t for t in tracks if t.clips[-1].start_ms+t.clips[-1].duration_ms<=cue['start_ms']),None)
        if track is None:
            track=timeline.Track(id=uuid4().hex,name='Phụ đề',kind='text');tracks.append(track)
        track.clips.append(timeline.Clip(id=uuid4().hex,start_ms=cue['start_ms'],duration_ms=cue['end_ms']-cue['start_ms'],
            text=text,font=cfg['subtitle_font'],font_size=cfg['subtitle_size'],color=cfg['subtitle_color'],
            x=cfg['subtitle_x'],y=cfg['subtitle_y'],box=cfg['subtitle_style']=='box',
            box_color=cfg['subtitle_box_color'],box_opacity=cfg['subtitle_box_opacity']))
    return tracks


def run(flow, payload, job_id, progress, event):
    target=payload.get('target')
    if target not in {'dub','edit'} or payload.get('confirmed') is not True:
        raise ValueError('Xác nhận chuyển dự án sang Lồng tiếng / Biên tập.')
    original=storage.project(payload['project_id'])
    if storage.project_kind(original)==target:raise ValueError('Dự án đã thuộc tab này.')
    doc=timeline.load(original['id']) if target=='dub' else None
    expected=doc['revision'] if doc else original['revision']
    if payload.get('revision')!=expected:raise ValueError('Dự án đã thay đổi; lưu rồi chuyển lại.')
    checkpoint(event)
    created=None
    try:
        if target=='dub':
            output=storage.output_folder('edit',job_id)/'transfer.mp4'
            timeline.render(original,doc,output,event,progress)
            checkpoint(event)
            if timeline.load(original['id'])['revision']!=expected:raise ValueError('Timeline đã đổi trong lúc chuyển; bản gốc vẫn giữ nguyên.')
            created=storage.new_project(original['name'][:75]+' · Lồng tiếng',kind='dub',transfer_pending=True)
            attach(created,output)
            message='Đã tạo bản lồng tiếng từ video render đầy đủ. Nhập SRT hoặc nhận dạng để tạo lời đọc.'
        else:
            if not original.get('video'):raise ValueError('Chọn video nguồn trước khi chuyển sang Biên tập.')
            source,_=storage.project_asset(original,original['video'])
            cfg=editor.config(original.get('edit'))
            text_tracks=captions(original,cfg)  # Validate timing before copying anything.
            from .workflows import cue_key
            ready=bool(original['cues']) and all(c.get('status') in {'complete','review'} and
                c.get('fingerprint')==cue_key(c,original,storage.settings()['precision'],storage.reading_settings()) and
                (storage.project_path(original['id'])/'cues'/c.get('audio','')).is_file() for c in original['cues'])
            created=storage.new_project(original['name'][:75]+' · Biên tập',kind='edit',transfer_pending=True)
            if ready:
                # Render an isolated copy: export must not rewrite the source project.
                clone={**deepcopy(original),'id':created['id'],'kind':'edit','revision':created['revision'],'exports':[],'transfer_pending':True}
                for name in ('assets','cues'):
                    folder=storage.project_path(original['id'])/name
                    if folder.is_dir():shutil.copytree(folder,storage.project_path(created['id'])/name,dirs_exist_ok=True)
                storage.save_project(clone)
                flow.job_export({'project_id':created['id'],'mode':'video'},job_id,progress,event)
                source=Path(storage.read_json(storage.DATA/'output-index.json',{})[job_id])/'video.mp4'
                created=storage.project(created['id'])
            checkpoint(event)
            if storage.project(original['id'])['revision']!=expected:raise ValueError('Dự án đã đổi trong lúc chuyển; bản gốc vẫn giữ nguyên.')
            key=attach(created,source)
            info=media.probe(source);stream=next(s for s in info['streams'] if s.get('codec_type')=='video')
            duration=round(float(info['format']['duration'])*1000)
            tracks=[timeline.Track(id=uuid4().hex,name='Video',kind='video',clips=[timeline.Clip(id=uuid4().hex,
                asset=key,start_ms=0,duration_ms=duration)])]+text_tracks
            if cfg['title'].strip() and not ready:
                tracks.append(timeline.Track(id=uuid4().hex,name='Tiêu đề',kind='text',clips=[timeline.Clip(id=uuid4().hex,
                    start_ms=0,duration_ms=duration,text=cfg['title'],font_size=cfg['title_size'],color=cfg['title_color'],
                    x=cfg['title_x'],y=cfg['title_y'],box=cfg['title_box'],box_color=cfg['title_box_color'],box_opacity=cfg['title_box_opacity'])]))
            doc=timeline.Timeline(width=stream['width'],height=stream['height'],assets=[key],tracks=tracks)
            timeline.save(created['id'],doc.model_dump())
            message='Đã tạo bản biên tập với phụ đề chỉnh sửa được.'+(' Audio và hiệu ứng lồng tiếng được giữ trong video.' if ready else ' Chưa có audio đúng phiên bản: chỉ chuyển video nguồn, phụ đề và tiêu đề; chưa áp dụng hiệu ứng lồng tiếng.')
        checkpoint(event)
        created=storage.project(created['id']);created.pop('transfer_pending',None)
        created['transferred_from']=original['id'];storage.save_project(created)
        return {'project_id':created['id'],'tab':target,'message':message}
    except BaseException:
        # Keep an incomplete copy recoverable, never recursively remove user data.
        if created:storage.delete_project(created['id'])
        raise
