"""No-key Google web translation, using the same mobile page as deep-translator.

This is not the paid Google Cloud API. Requests are bounded and serial; if the
service blocks requests we stop, retaining completed cues, without bypasses.
"""
from html.parser import HTMLParser

import requests
import time
import hashlib
import math
from email.utils import parsedate_to_datetime

from . import media,storage


class TranslationError(RuntimeError):
    pass


class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []
        self.finished = False

    def handle_starttag(self, tag, attrs):
        if self.finished:
            return
        if self.depth:
            if tag not in {"br", "img", "hr", "input", "meta", "link"}:
                self.depth += 1
            if tag == "br":
                self.parts.append("\n")
        elif tag == "div" and set(dict(attrs).get("class", "").split()) & {"result-container", "t0"}:
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth and tag not in {"br", "img", "hr", "input", "meta", "link"}:
            self.depth -= 1
            if not self.depth:
                self.finished = True

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


class GoogleWebTranslator:
    retries = 1
    interval = 2.0
    backoff = 30.0
    def __init__(self, source, target, event):
        self.source = "zh-CN" if source == "zh" else source
        self.target = "zh-CN" if target == "zh" else target
        self.event = event
        self.session = requests.Session()
        self.session.trust_env = False
        self.requested = False
        self.notify=lambda message:None
        self.use_cache=True

    def close(self):
        self.session.close()

    def wait(self, seconds=0):
        if self.event.wait(seconds):
            raise InterruptedError("Đã dừng dịch; các câu hoàn thành đã được lưu.")

    def translate(self, text):
        if not text.strip():
            raise TranslationError("Nguyên văn trống; sửa câu này trước khi dịch.")
        self.wait()
        if self.source == self.target:
            return text.strip()
        result = []
        for part in media.split_script(text, limit=self.max_chars):
            key=hashlib.sha256(repr((type(self).__name__,self.source,self.target,part)).encode()).hexdigest()
            cache_path=storage.DATA/'translation-cache.json'
            cache=storage.read_json(cache_path,{})
            if self.use_cache and key in cache:
                result.append(cache[key]);continue
            if self.requested:
                self.wait(self.interval)
            self.requested = True
            try:
                state_path=storage.DATA/'translation-cooldown.json'
                provider=type(self).__name__;state=storage.read_json(state_path,{})
                remaining=max(0,state.get(provider,0)-time.time())
                if remaining>60:raise TranslationError(f'Google đang giới hạn truy cập; thử lại sau khoảng {int(remaining)+1} giây. Chưa gửi thêm yêu cầu.')
                if remaining:
                    self.notify(f'Google đang giới hạn; chờ {int(remaining)+1}s trước khi thử lại…');self.wait(remaining)
                for attempt in range(self.retries+1):
                    response=self.request(part)
                    if response.status_code!=429:break
                    raw=getattr(response,'headers',{}).get('Retry-After','')
                    try:delay=max(0,float(raw))
                    except (ValueError,TypeError):
                        try:delay=max(0,parsedate_to_datetime(raw).timestamp()-time.time())
                        except (ValueError,TypeError,OverflowError):delay=self.backoff*(2**attempt)
                    if not math.isfinite(delay):delay=self.backoff*(2**attempt)
                    state[provider]=time.time()+delay
                    storage.atomic_json(state_path,state)
                    if attempt==self.retries or delay>60:break
                    self.notify(f'Google HTTP 429; chờ {int(delay)+1}s rồi thử lại {attempt+1}/{self.retries}…')
                    self.wait(delay)
            except requests.RequestException as exc:
                raise TranslationError("Không kết nối được Google Translate. Kiểm tra mạng rồi bấm Dịch / Tiếp tục.") from exc
            self.wait()
            if response.status_code in {403, 429}:
                raise TranslationError(f"Google giới hạn truy cập (HTTP {response.status_code}). Chờ rồi bấm Dịch / Tiếp tục; không cần API key.")
            if not response.ok:
                raise TranslationError(f"Google Translate HTTP {response.status_code}. Các câu trước đã lưu; thử tiếp tục sau.")
            translated = self.parse(response)
            if not translated:
                raise TranslationError("Google không trả bản dịch (trang xác minh hoặc cấu trúc trang đã đổi). Không thay nguyên văn; thử lại sau.")
            result.append(translated)
            if self.use_cache:
                cache[key]=translated
                storage.atomic_json(cache_path,dict(list(cache.items())[-5000:]))
        text = "\n".join(result)
        if len(text) > 5000:
            raise TranslationError("Bản dịch quá 5.000 ký tự; chia nhỏ câu trước khi dịch.")
        return text

    max_chars = 4500

    def request(self, part):
        return self.session.get("https://translate.google.com/m",
            params={"sl": self.source, "tl": self.target, "q": part}, timeout=(10, 35))

    def parse(self, response):
        parser = ResultParser()
        parser.feed(response.text)
        return "".join(parser.parts).strip() if parser.finished else ""


class GoogleV1Translator(GoogleWebTranslator):
    """The no-key V1 endpoint used by Subtitle Edit, not Cloud V2.

    Separately selected provider; never automatically switch endpoints on blocks.
    """
    max_chars = 1500

    def request(self, part):
        return self.session.get("https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": self.source, "tl": self.target, "dt": "t", "q": part}, timeout=(10, 35))

    def parse(self, response):
        try:
            data = response.json()
            if not isinstance(data, list) or not data or not isinstance(data[0], list) or not data[0]:
                raise ValueError()
            parts = []
            for segment in data[0]:
                if not isinstance(segment, list) or not segment or not isinstance(segment[0], str):
                    raise ValueError()
                parts.append(segment[0])
            return "".join(parts).strip()
        except (ValueError, TypeError, IndexError) as exc:
            raise TranslationError("Google V1 trả dữ liệu không hợp lệ. Cue chưa thay đổi; thử tiếp tục sau.") from exc
