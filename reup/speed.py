"""Piecewise-linear output-time speed; exact integral and inverse for video PTS."""
from functools import lru_cache
from . import media

@lru_cache(maxsize=4)
def has_rubberband(binary):
    return 'rubberband' in media.command([binary,'-hide_banner','-filters'])

def segments(clip):
    points=clip.get('speed_curve') or [{'ms':0,'speed':clip['speed']},{'ms':clip['duration_ms'],'speed':clip['speed']}]
    source=0.
    for a,b in zip(points,points[1:]):
        length=(b['ms']-a['ms'])/1000;rate=a['speed'];slope=(b['speed']-rate)/length
        span=length*(rate+b['speed'])/2
        yield a['ms']/1000,length,source,span,rate,slope
        source+=span

def source_ms(clip,ms):
    total=0.
    for start,length,source,span,rate,slope in segments(clip):
        local=max(0,min(length,ms/1000-start));total+=rate*local+slope*local*local/2
    return total*1000

def rate(clip,ms):
    for start,length,source,span,value,slope in segments(clip):
        if ms/1000<=start+length:return value+slope*max(0,ms/1000-start)
    return value+slope*length

def pts(clip):
    expr=f"{clip['duration_ms']/1000}"
    # Stable quadratic inverse, including deceleration and near-constant rates.
    for start,length,source,span,value,slope in reversed(list(segments(clip))):
        delta=f'max(0,((PTS-STARTPTS)*TB-{source:.12g}))'
        local=f'({delta})/{value:.12g}' if abs(slope)<1e-10 else f'2*({delta})/({value:.12g}+sqrt(max(0,{value*value:.12g}+2*{slope:.12g}*({delta}))))'
        expr=f'if(lt((PTS-STARTPTS)*TB,{source+span:.12g}),{start:.12g}+({local}),{expr})'
    return f"setpts='({expr})/TB'"

def audio(clip,index,folder):
    if not clip.get('speed_curve'):return None
    # Commands every 20ms of output, timestamped on source input. One atempo
    # stage avoids cascaded command-clock drift; wider rates use rubberband.
    commands=[]
    single=all(.5<=p['speed']<=2 for p in clip['speed_curve'])
    rubber=not single
    if rubber and not has_rubberband(media.binary()):raise ValueError('Curve audio ngoài 0,5–2× cần FFmpeg có rubberband; dùng tốc độ trong khoảng này hoặc tắt audio track.')
    for ms in range(0,clip['duration_ms'],20):
        source=source_ms(clip,ms)/1000;value=rate(clip,ms)
        commands.append(f'{source:.8f} '+(f'rubberband@r{index}' if rubber else f'atempo@a{index}')+f' tempo {value:.8f};')
    path=folder/f'speed-audio-{index}.txt';path.write_text('\n'.join(commands),encoding='utf-8')
    initial=rate(clip,0)
    tempo=f'rubberband@r{index}=tempo={initial}:pitch=1:window=short' if rubber else f'atempo@a{index}={initial}'
    return f"asendcmd=f='{path.name}',{tempo},apad,atrim=duration={clip['duration_ms']/1000}"
