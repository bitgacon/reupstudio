from TRACKING_POLICY import TrackingPolicy

def test_short_occlusion_holds_and_reacquires():
    p=TrackingPolicy();p.update(0,[.2,.3],1);p.update(200,[.9,.9],.3);p.update(800,[.4,.3],.9)
    r=p.result(1000)
    assert r['rows'][1]['center']==[.2,.3] and r['rows'][1]['state']=='held'
    assert r['rows'][2]['center']==[.4,.3] and r['stopped'] is None

def test_long_occlusion_truncates_to_first_lost_sample():
    p=TrackingPolicy();p.update(0,[.2,.3],1);p.update(400,[.9,.9],.1);p.update(1200,[.9,.9],.1)
    assert not p.update(1400,[.9,.9],.1)
    r=p.result(2000);assert r['duration_ms']==400 and r['stopped']['reason']=='lost_too_long'
    assert r['rows'][-1]['ms']==400

def test_scene_cut_stops_before_new_subject_even_if_confident():
    p=TrackingPolicy();p.update(0,[.2,.3],1);p.update(200,[.3,.3],.9)
    assert not p.update(600,[.9,.9],.99,scene_change=True)
    r=p.result(2000);assert r['duration_ms']==600 and r['rows'][-1]['center']==[.3,.3]
    assert r['stopped']['reason']=='scene_cut'

def test_invalid_match_is_not_followed():
    p=TrackingPolicy();p.update(0,[.2,.3],1);p.update(200,[float('nan'),.8],float('nan'))
    r=p.result(400);assert r['rows'][1]['center']==[.2,.3]
