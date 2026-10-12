from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import time
import json
import math,re
from uuid import uuid4

from . import storage

RETRY_KINDS={'tts','podcast','document','translate','dub','export','editor_export','download','download_scan','subtitle_remove','subtitle_prepare','preview','editor_preview','editor_proxy','removal_preview','removal_effect_preview','separate','editor_separate'}
RETRY_STATUSES={'error','cancelled','interrupted'}

def clean_request(value):
    """Keep job inputs private, but never persist inline credentials for replay."""
    if isinstance(value,dict):
        result={};complete=True
        for key,item in value.items():
            lowered=key.lower()
            if lowered in {'key','password','authorization','access_token','secret','api_key','translation_key','elevenlabs_key'} or lowered.endswith('_api_key'):
                complete=False;continue
            result[key],safe=clean_request(item);complete=complete and safe
        return result,complete
    if isinstance(value,list):
        results=[clean_request(item) for item in value]
        return [r[0] for r in results],all(r[1] for r in results)
    return value,True


class JobQueue:
    def __init__(self, handler):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reup")
        self.lock = threading.RLock()
        self.events = {}
        self.rows = {}
        self.handler = handler
        self.accepting = True
        self.load_issues=[]
        for path in (storage.DATA / "jobs").glob("*.json"):
            try:
                row = storage.read_json(path)
                if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',row['id']) or row.get('status') not in {'queued','running','complete','error','cancelled','interrupted'} or not isinstance(row.get('created'),(int,float)) or not math.isfinite(row['created']) or not isinstance(row.get('result',{}),dict):
                    raise ValueError('Metadata tác vụ không hợp lệ.')
                json.dumps(row,allow_nan=False)
                files=row.get('result',{}).get('files',[])
                if not isinstance(files,list) or any(not isinstance(f,dict) for f in files):raise ValueError('Kết quả tác vụ không hợp lệ.')
            except (ValueError,OSError,TypeError):
                self.load_issues.append({'file':path.name,'message':'Không đọc được tác vụ; giữ nguyên file để khôi phục.'});continue
            if row["status"] in {"queued", "running"}:
                row.update(status="interrupted", message="Phiên trước đã đóng. Có thể tiếp tục cue đã lưu.")
                try:storage.atomic_json(path, row)
                except OSError:self.load_issues.append({'file':path.name,'message':'Không ghi được trạng thái khôi phục; kiểm tra ổ đĩa/quyền ghi.'})
            row.setdefault('finished',row.get('created',time.time()))
            self.rows[row["id"]] = row
        # Repair the parent link if shutdown happened after saving a retry child.
        for child in sorted(self.rows.values(),key=lambda r:r['created']):
            parent=self.rows.get(child.get('retry_of'))
            if parent and not parent.get('retry_child'):parent['retry_child']=child['id']

    def all(self):
        with self.lock:
            rows=deepcopy(sorted(self.rows.values(), key=lambda v: v["created"], reverse=True)[:100])
            for row in rows:row['retryable']=bool(row.get('request_saved') and row.get('kind') in RETRY_KINDS and row['status'] in RETRY_STATUSES and not row.get('retry_child'))
            return rows

    def busy(self, project_id=None):
        with self.lock:
            return any(r["status"] in {"queued", "running"} and
                       (project_id is None or r.get("project_id") == project_id) for r in self.rows.values())

    def submit(self, kind: str, payload: dict, retry_of=None):
        with self.lock:
            if getattr(self,'maintenance',False):
                raise ValueError('Đang sao lưu/khôi phục; chờ hoàn tất trước khi tạo tác vụ.')
            if not self.accepting:
                raise ValueError('Đang đóng ứng dụng để cập nhật; không nhận tác vụ mới.')
            if sum(r["status"] in {"queued", "running"} for r in self.rows.values()) >= 20:
                raise ValueError("Hàng đợi đã có 20 tác vụ; chờ hoặc dừng bớt.")
            project_id = payload.get("project_id")
            if project_id and self.busy(project_id):
                raise ValueError("Dự án đang có tác vụ. Chờ xong hoặc dừng trước khi tạo thêm.")
            row = {"id": uuid4().hex, "kind": kind, "project_id": project_id, "status": "queued",
                   "ui_tab": payload.get("ui_tab", "dub" if project_id else "clone" if kind == "clone" else "podcast" if kind == "podcast" else "documents" if kind == "document" else "tts"),
                   "progress": 0, "message": "Đang chờ…", "created": time.time(), "result": {}}
            saved,complete=clean_request(payload)
            if len(json.dumps(saved,ensure_ascii=False,allow_nan=False))>600_000:raise ValueError('Nội dung quá dài.')
            row['request_saved']=complete and kind in RETRY_KINDS
            if retry_of:row['retry_of']=retry_of
            if row['request_saved']:storage.atomic_json(storage.DATA/'jobs'/'requests'/(row['id']+'.json'),{'kind':kind,'payload':saved})
            self.rows[row["id"]] = row
            self.events[row["id"]] = threading.Event()
            try:
                self.update(row["id"])
                self.executor.submit(self.run, row["id"], deepcopy(payload))
            except BaseException:
                # A failed disk write/schedule must not leave an un-runnable busy row.
                self.rows.pop(row['id'],None);self.events.pop(row['id'],None);raise
            return deepcopy(row)

    def retry_plan(self, job_id):
        storage.identifier(job_id)
        with self.lock:
            row=self.rows.get(job_id)
            if not row:raise ValueError('Không tìm thấy tác vụ.')
            if row['status'] not in RETRY_STATUSES:raise ValueError('Chỉ chạy lại tác vụ lỗi, đã dừng hoặc gián đoạn.')
            if row.get('retry_child'):raise ValueError('Đã tạo lượt chạy lại; xem tác vụ mới trong Lịch sử.')
            if not row.get('request_saved') or row.get('kind') not in RETRY_KINDS:raise ValueError('Tác vụ cũ chưa lưu yêu cầu hoặc không hỗ trợ chạy lại; mở tab gốc để tiếp tục.')
            request=storage.read_json(storage.DATA/'jobs'/'requests'/(job_id+'.json'))
            if not isinstance(request,dict) or request.get('kind')!=row['kind'] or not isinstance(request.get('payload'),dict):raise ValueError('Yêu cầu chạy lại không còn hợp lệ; dữ liệu cũ giữ nguyên.')
            payload=deepcopy(request['payload']);project=storage.project(payload['project_id']) if payload.get('project_id') else None
            if project and payload.get('selected') is not None and row['kind'] in {'dub','translate'}:
                if not set(payload['selected'])<={c['id'] for c in project['cues']}:raise ValueError('Danh sách cue đã đổi; mở dự án để chọn lại.')
            def check_assets(value):
                if isinstance(value,dict):
                    for key,item in value.items():
                        if key in {'asset','asset_id','video','subtitle_asset','reference_asset','logo_asset','cookie'} and isinstance(item,str) and item:
                            storage.project_asset(project,item) if project else storage.asset(item)
                        else:check_assets(item)
                elif isinstance(value,list):
                    for item in value:check_assets(item)
            check_assets(payload)
            skipped=0
            if row['kind']=='download':
                from . import downloads
                ancestors={job_id};parent=row.get('retry_of')
                while parent and parent not in ancestors:
                    ancestors.add(parent);parent=self.rows.get(parent,{}).get('retry_of')
                done=set()
                for item in storage.read_json(storage.DATA/'download-index.json',[]):
                    if item.get('job_id') in ancestors:
                        try:storage.asset(item['asset']);done.add(item['source_url'])
                        except (ValueError,OSError,KeyError):pass
                urls=list(dict.fromkeys(downloads.normalize(str(u)) for u in payload.get('urls',[])))
                payload['urls']=[u for u in urls if u not in done];skipped=len(urls)-len(payload['urls'])
                if not payload['urls']:raise ValueError('Các URL của tác vụ này đã có kết quả; không tải lại.')
            force_removed=bool(payload.pop('force',False));payload['skip_existing']=True if row['kind']=='subtitle_remove' else payload.get('skip_existing',False)
            def cloud(value):
                if isinstance(value,dict):return value.get('provider')=='elevenlabs' or any(cloud(v) for v in value.values())
                return isinstance(value,list) and any(cloud(v) for v in value)
            network=row['kind'] in {'translate','download','download_scan'} or cloud(payload) or bool(project and cloud(project))
            return {'kind':row['kind'],'payload':payload,'network':network,'uses_current_project':bool(project),'force_removed':force_removed,'skipped_downloads':skipped}

    def retry(self,job_id,confirmed=False,network_confirmed=False):
        with self.lock:
            plan=self.retry_plan(job_id)
            if confirmed is not True:raise ValueError('Cần xác nhận trước khi chạy lại.')
            if plan['network'] and network_confirmed is not True:raise ValueError('Cần xác nhận dịch vụ Internet có thể phát sinh phí/quota.')
            child=self.submit(plan['kind'],plan['payload'],retry_of=job_id)
            self.update(job_id,retry_child=child['id'])
            return child

    def update(self, job_id, **values):
        with self.lock:
            self.rows[job_id].update(values)
            storage.atomic_json(storage.DATA / "jobs" / (job_id + ".json"), self.rows[job_id])

    def cancel(self, job_id):
        with self.lock:
            if job_id in self.events:
                self.events[job_id].set()
                if self.rows[job_id]["status"] in {"queued", "running"}:
                    self.update(job_id, message="Sẽ dừng sau câu/bước hiện tại…")

    def run(self, job_id, payload):
        event = self.events[job_id]
        try:
            if event.is_set():
                raise InterruptedError("Đã dừng trước khi chạy.")
            self.update(job_id, status="running")
            result = self.handler(self.rows[job_id]["kind"], payload, job_id,
                                  lambda percent, message: self.update(job_id, progress=percent, message=message), event)
            state = "cancelled" if event.is_set() else "complete"
            self.update(job_id, status=state, progress=100 if state == "complete" else self.rows[job_id]["progress"], result=result,
                        message="Đã dừng; phần đã tạo được giữ lại." if event.is_set() else result.get("message", "Hoàn tất"))
        except InterruptedError as exc:
            self.update(job_id, status="cancelled", message=str(exc))
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            key = storage.settings().get("translation_key")
            if key:
                detail = detail.replace(key, "[đã ẩn khóa]")
            self.update(job_id, status="error", message=detail[-2000:])
        finally:
            self.update(job_id, finished=time.time())

    def close(self):
        with self.lock:
            self.accepting=False
            for event in self.events.values():event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def forget(self, ids=None):
        with self.lock:
            if ids is not None and any(not isinstance(key,str) for key in ids):raise ValueError('Mã lịch sử không hợp lệ.')
            keys=list(self.rows) if ids is None else list(dict.fromkeys(storage.identifier(key) for key in ids))
            # Never remove an active job; its completion callback still needs it.
            keys=[key for key in keys if key in self.rows and self.rows[key]['status'] not in {'queued','running'} and 'finished' in self.rows[key]]
            folder=storage.DATA/'jobs'/'forgotten';folder.mkdir(parents=True,exist_ok=True)
            for key in keys:
                path=storage.DATA/'jobs'/(key+'.json')
                if path.exists():path.replace(folder/(key+'.json'))
                request=storage.DATA/'jobs'/'requests'/(key+'.json')
                if request.exists():
                    archived=folder/'requests';archived.mkdir(exist_ok=True);request.replace(archived/request.name)
                self.rows.pop(key,None);self.events.pop(key,None)
            return {'removed':len(keys),'message':'Đã xóa lịch sử đã kết thúc; giữ tác vụ đang chạy và mọi file kết quả.'}
