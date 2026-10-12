"""Editor text animation using reviewed ASR timings or estimated fallback."""
import re
from . import editor

def words(text,duration):
    tokens=re.findall(r'\S+',text);total=sum(len(w) for w in tokens);at=0;out=[]
    for w in tokens:
        end=at+len(w)*duration/max(1,total);out.append((w,round(at),round(end)));at=end
    return out

def animate_ass(body,clip):
    mode=clip['text_animation']
    if mode=='none':return body
    lines=body.splitlines(keepends=True);out=[]
    for line in lines:
        if not line.startswith('Dialogue:'):out.append(line);continue
        parts=line.rstrip('\n').split(',',9);text=parts[9];match=re.match(r'^(\{[^}]*\})(.*)$',text)
        prefix=match[1] if match else '';safe=match[2] if match else text
        if mode=='pop':
            size=clip['scale']*100;tags=f'\\fscx{size*.75}\\fscy{size*.75}\\t(0,180,\\fscx{size}\\fscy{size})'
            parts[9]=prefix+'{'+tags+'}'+safe;out.append(','.join(parts)+'\n')
        else:
            tokens=[(w['word'],w['start'],w['end']) for w in clip.get('word_cues',[])] or words(clip['text'],clip['duration_ms'])
            # ASS has centisecond precision. Discrete events preserve leading/inter-word
            # silence and match the realtime word-onset highlight, including seeks.
            boundaries=sorted(set([0,clip['duration_ms'],clip.get('fade_in_ms',0),clip['duration_ms']-clip.get('fade_out_ms',0)]+[a for _,a,_ in tokens]))
            color=clip['color'].lstrip('#');spoken='&H'+color[4:6]+color[2:4]+color[0:2]+'&'
            for a,b in zip(boundaries,boundaries[1:]):
                current=max((i for i,(_,start,_) in enumerate(tokens) if start<=a),default=-1)
                if mode=='typewriter' and current<0:continue
                row=parts.copy();row[1]=editor.ass_time(clip['start_ms']+a);row[2]=editor.ass_time(clip['start_ms']+b)
                if row[1]==row[2]:continue
                # Do not restart the whole clip fade at each word event.
                event_prefix=re.sub(r'\\fad\([^)]*\)|\\alpha&H[0-9A-Fa-f]+&','',prefix)
                def alpha(ms):
                    envelope=max(0,min(1,ms/clip['fade_in_ms'] if clip.get('fade_in_ms') else 1,(clip['duration_ms']-ms)/clip['fade_out_ms'] if clip.get('fade_out_ms') else 1))
                    return round(255*(1-clip.get('opacity',1)*envelope))
                event_prefix+='{\\alpha&H'+f'{alpha(a):02X}'+'&\\t(0,'+str(b-a)+',\\alpha&H'+f'{alpha(b):02X}'+'&)}'
                if mode=='karaoke':
                    row[9]=event_prefix+' '.join('{\\c'+(spoken if i<=current else '&H00FFFF&')+'}'+editor.ass_text(w) for i,(w,_,_) in enumerate(tokens))
                else:row[9]=event_prefix+editor.ass_text(' '.join(w for w,_,_ in tokens[:current+1]))
                out.append(','.join(row)+'\n')
    return ''.join(out)
