"""Validated OpenAI-compatible translation, including Gemini AI Studio keys."""
import json
import re
import math
import threading
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

GEMINI_URL='https://generativelanguage.googleapis.com/v1beta/openai'
RETRIES=2


def retry_delay(response,attempt):
    raw=getattr(response,'headers',{}).get('Retry-After','')
    try:delay=float(raw)
    except (ValueError,TypeError):
        try:delay=parsedate_to_datetime(raw).timestamp()-time.time()
        except (ValueError,TypeError,OverflowError):delay=5*(2**attempt)
    return max(0,delay) if math.isfinite(delay) else 5*(2**attempt)


def normalize(url,model):
    url=str(url).strip().rstrip('/')
    model=str(model).strip()
    parsed=urlsplit(url)
    if parsed.hostname=='aistudio.google.com':
        url=GEMINI_URL
    if urlsplit(url).hostname=='generativelanguage.googleapis.com':
        if url in {'https://generativelanguage.googleapis.com','https://generativelanguage.googleapis.com/v1beta'}:
            url=GEMINI_URL
        model=re.sub(r'\s+','-',model).lower()
        if model.startswith('models/'):model=model[7:]
    return url,model


def request_json(url,model,key,messages,event=None,notify=None):
    event=event if event is not None else threading.Event()
    notify=notify or (lambda message:None)
    url,model=normalize(url,model)
    parsed=urlsplit(url)
    if (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1'})) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('API dịch cần Base URL https (không chứa key), hoặc http localhost cho model local.')
    if not model:raise ValueError('Điền tên model API trong Cài đặt, ví dụ gemini-3.8-flash.')
    if parsed.hostname=='generativelanguage.googleapis.com' and not key:
        raise ValueError('Gemini cần API key lấy từ Google AI Studio; nhập trong Cài đặt.')
    with requests.Session() as session:
        session.trust_env=False
        for attempt in range(RETRIES+1):
            if event.is_set():raise InterruptedError('Đã dừng dịch; các batch hoàn thành đã lưu.')
            try:
                response=session.post(url+'/chat/completions',headers={'Authorization':'Bearer '+key} if key else {},json={'model':model,'messages':messages},timeout=(15,60),allow_redirects=False)
            except requests.Timeout:
                if event.is_set():raise InterruptedError('Đã dừng dịch; các batch hoàn thành đã lưu.') from None
                raise RuntimeError('API dịch quá thời gian chờ; dịch vụ/model có thể đang quá tải hoặc mạng gián đoạn. Batch hiện tại chưa thay đổi; thử Dịch / Tiếp tục sau hoặc chọn model khác. Không gửi lặp tự động khi chưa biết yêu cầu cũ đã xử lý hay chưa.') from None
            except requests.RequestException:
                if event.is_set():raise InterruptedError('Đã dừng dịch; các batch hoàn thành đã lưu.') from None
                raise RuntimeError('Không kết nối được API dịch; kiểm tra mạng và Base URL. Các batch trước đã lưu.') from None
            if event.is_set():raise InterruptedError('Đã dừng dịch; các batch hoàn thành đã lưu.')
            if response.status_code not in {500,502,503,504} or attempt==RETRIES:break
            delay=retry_delay(response,attempt)
            if delay>60:break
            notify(f'API HTTP {response.status_code}; chờ {delay:g}s · thử lại {attempt+1}/{RETRIES}, không đổi model…')
            if event.wait(delay):raise InterruptedError('Đã dừng trong lúc chờ API; các batch hoàn thành đã lưu.')
    if not response.ok or 300<=response.status_code<400:
        hints={400:'Yêu cầu/model không hợp lệ; kiểm tra tên model API.',401:'API key không hợp lệ hoặc đã hết hiệu lực.',403:'Key không được phép dùng API/model này; kiểm tra quyền và khu vực hỗ trợ.',404:'Sai Base URL hoặc model không tồn tại/không khả dụng với key.',429:'Đã hết hạn mức hoặc bị giới hạn tốc độ API Gemini/nhà cung cấp; chờ rồi thử lại hoặc kiểm tra quota.',503:'Dịch vụ/model tạm không sẵn sàng; chờ rồi thử lại hoặc chọn model khác. Chưa thể xác nhận key hoạt động chỉ từ lỗi này.'}
        retry_note=''
        if response.status_code in {500,502,503,504}:
            retry_note=(f' Đã thử lại {attempt}/{RETRIES} lần; giữ các batch đã dịch, bấm Dịch / Tiếp tục sau.' if attempt==RETRIES else ' API yêu cầu chờ lâu hơn 60s; thử tiếp tục sau thời gian chờ.')
        raise RuntimeError(f'API dịch HTTP {response.status_code}. '+hints.get(response.status_code,'Kiểm tra Base URL và trạng thái nhà cung cấp.')+retry_note)
    try:
        data=response.json()
    except ValueError:
        raise ValueError('API trả HTML/rỗng thay vì JSON. Không dùng URL trang web AI Studio; Gemini dùng '+GEMINI_URL+'.') from None
    try:
        content=data['choices'][0]['message']['content']
    except (TypeError,KeyError,IndexError):
        raise ValueError('API không trả nội dung dịch theo định dạng chat/completions; kiểm tra endpoint, model hoặc bộ lọc nội dung.') from None
    if not isinstance(content,str) or not content.strip():
        raise ValueError('Model trả nội dung trống; chưa thay đổi batch này. Kiểm tra model hoặc bộ lọc nội dung.')
    content=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip())
    if len(content)>200_000:raise ValueError('Nội dung JSON từ model quá lớn; chưa thay đổi dữ liệu.')
    try:translated=json.loads(content)
    except ValueError:
        raise ValueError('Model chưa trả mảng JSON bản dịch hợp lệ; batch này giữ nguyên, thử lại hoặc chọn model khác.') from None
    return translated


def complete(url,model,key,messages,event=None,notify=None):
    translated=request_json(url,model,key,messages,event,notify)
    if not isinstance(translated,list) or any(not isinstance(item,dict) or type(item.get('id')) is not int or not isinstance(item.get('text'),str) for item in translated):
        raise ValueError('Model phải trả mảng [{"id": số, "text": bản dịch}]; batch lỗi chưa thay đổi.')
    return translated
