"""Offline model inference; models install only in the explicit install task."""
import json,sys,wave
from pathlib import Path


def main(request):
    import numpy as np
    import torch
    from transformers import AutoModelForCTC,AutoTokenizer,AutoFeatureExtractor
    from CTC_ALIGNMENT import align,word_rows
    home=request['model'];local=request.get('install') is not True
    kwargs={'local_files_only':local,'trust_remote_code':False}
    tokenizer=AutoTokenizer.from_pretrained(home,**kwargs)
    extractor=AutoFeatureExtractor.from_pretrained(home,**kwargs)
    model=AutoModelForCTC.from_pretrained(home,**kwargs).eval()
    if request.get('check'):
        print('ALIGNMENT_RUNTIME_OK',flush=True);return
    if not local:
        destination=request['destination']
        tokenizer.save_pretrained(destination);extractor.save_pretrained(destination);model.save_pretrained(destination,safe_serialization=True)
        print('ALIGNMENT_RUNTIME_OK',flush=True);return
    torch.set_num_threads(2)
    with wave.open(request['audio'],'rb') as f:
        if f.getnchannels()!=1 or f.getframerate()!=16000 or f.getsampwidth()!=2:raise ValueError('Cần PCM mono 16 kHz.')
        audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32)/32768
    words=request['reference'].split();tokens=[];ranges=[]
    import re,unicodedata
    romanizer=None
    if request['romanize']:
        from uroman import Uroman
        romanizer=Uroman()
    vocab=tokenizer.get_vocab();separator=getattr(tokenizer,'word_delimiter_token','|')
    for word in words:
        text=unicodedata.normalize('NFC',word).lower()
        if romanizer:text=romanizer.romanize_string(text,lcode=request['language'])
        text=re.sub(r'[^\w\s]','',text).strip()
        # Do not silently drop unsupported letters or words.
        text=re.sub(r'\s+',separator,text)
        if not text or any(ch not in vocab for ch in text):raise ValueError('Model không hỗ trợ ký tự trong từ: '+word)
        if tokens and separator in vocab:tokens.append(vocab[separator])
        a=len(tokens);tokens.extend(vocab[ch] for ch in text);ranges.append((a,len(tokens)))
    blank=model.config.pad_token_id
    with torch.inference_mode():
        inputs=extractor(audio,sampling_rate=16000,return_tensors='pt')
        emission=model(**inputs).logits[0].log_softmax(-1).cpu().numpy()
    rows=align(emission,tokens,blank)
    value={'words':word_rows(words,ranges,rows,request['duration_ms'],len(emission)),
           'language':request['language'],'method':'ctc-viterbi','message':'CTC căn toàn bộ văn bản vào audio. Độ tin cậy thấp cần nghe/duyệt; không xác minh audio có đúng lời.'}
    Path(request['result']).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':main(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
