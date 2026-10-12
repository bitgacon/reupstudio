import threading
import pytest
from pydantic import ValidationError
from pydub import AudioSegment
from fastapi.testclient import TestClient
from reup import reading, storage, media
from reup.server import make_app
from reup.workflows import Workflows, cue_key


def options(**kwargs):
    return reading.config({"rules":[{"source":"SGK","spoken":"Sách giáo khoa"}],**kwargs})


def test_whole_word_unicode_case_and_no_cascade():
    c=options()
    assert reading.replace("SGK sgk XSGK SGK2 [SGK]",c)=="Sách giáo khoa Sách giáo khoa XSGK SGK2 [SGK]"
    c["rules"]=[{"source":"SGK","spoken":"SG","whole_word":True,"case_sensitive":True,"enabled":True},{"source":"SG","spoken":"Sài Gòn","whole_word":True,"case_sensitive":False,"enabled":True}]
    assert reading.replace("SGK sgk SG",c)=="SG sgk Sài Gòn"
    c=reading.config({"rules":[{"source":"giáo","spoken":"dáo"},{"source":"giáo khoa","spoken":"dáo khoa"}]})
    assert reading.replace("giáo khoa giáo",c)=="dáo khoa dáo"


def test_pauses_tags_decimal_and_source_preservation():
    c=options(pauses={"enabled":True,"comma":.2,"period":.5,"newline":1})
    parts=reading.pieces("SGK, giá 3.14.\n[cười] tiếp [0.8] hết [nghỉ 2s]",c)
    assert [p["silence"] for p in parts if "silence" in p]==[200,500,1000,800,2000]
    assert parts[0]=={"text":"SGK,","spoken":"Sách giáo khoa,"}
    assert any("3.14" in p.get("spoken","") for p in parts)
    assert any("[cười]" in p.get("spoken","") for p in parts)
    assert reading.pieces("Một. Hai, ba!",reading.config())==[{"text":"Một. Hai, ba!","spoken":"Một. Hai, ba!"}]
    with pytest.raises(ValueError): reading.pieces("a [31] b",c)


@pytest.mark.parametrize("value",[{"pauses":{"comma":-1}},{"pauses":{"period":float("nan")}},{"rules":[{"source":" ","spoken":"a"}]},{"rules":[{"source":"x","spoken":"a"}]*501}])
def test_invalid_settings(value):
    with pytest.raises(ValidationError): reading.config(value)


def test_api_persistence_and_preview_does_not_rewrite_source(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DATA",tmp_path)
    with TestClient(make_app()) as client:
        client.get("/");client.headers["X-Reup-Token"]=client.get("/api/state").json()["csrf"]
        assert not client.get("/api/reading").json()["pauses"]["enabled"]
        assert client.post("/api/reading",json=options()).status_code==200
        preview=client.post("/api/reading-preview",json={"text":"SGK","settings":options()}).json()
        assert preview["source"]=="SGK" and preview["pieces"][0]["spoken"]=="Sách giáo khoa"
        assert client.get("/api/reading").json()["rules"][0]["source"]=="SGK"
        assert client.post("/api/reading",json={"rules":[{}]}).status_code==400


def test_actual_silence_and_original_srt_with_mock_engine(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,"DATA",tmp_path)
    storage.reading_settings(options(pauses={"enabled":True,"period":.5}))
    calls=[]
    class FakeEngine:
        precision="fp32"
        def start(self,*args): pass
        def speak(self,text,voice,path,*args):
            calls.append(text);AudioSegment.silent(100,frame_rate=48000).export(path,format="wav")
    flow=Workflows();flow.engine=FakeEngine()
    result=flow.job_tts({"text":"SGK. [0.8] Hết","voice":"demo"},"a"*32,lambda *args:None,threading.Event())
    assert calls==["Sách giáo khoa.","Hết"]
    # FFmpeg atempo can shorten generated speech even at rate=1; inserted pauses
    # must nevertheless add exactly 500+800 ms, independent of spoken duration.
    spoken_ms=sum(len(AudioSegment.from_wav(path)) for path in storage.output_folder('tts','a'*32).glob("part-*-speed.wav"))
    assert abs(result["duration_ms"]-(1300+spoken_ms))<=1  # sample-to-ms rounding
    srt=(storage.output_folder('tts','a'*32)/"subtitle.srt").read_text(encoding="utf-8-sig")
    assert "SGK." in srt and "Sách giáo khoa" not in srt and "[0.8]" not in srt
    cue={"text":"SGK","start_ms":0,"end_ms":1000};project={"voice":"demo"}
    assert cue_key(cue,project,"fp32",options())!=cue_key(cue,project,"fp32",reading.config())
    out=tmp_path/"dub.wav";flow.speak_with_rules("SGK [0.8] Hết","demo",out,options(),threading.Event())
    assert len(AudioSegment.from_wav(out))==1000
