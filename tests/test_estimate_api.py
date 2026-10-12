from fastapi.testclient import TestClient
from reup import storage
from reup.server import make_app

def test_local_estimate_and_reference_routes_validate_and_do_not_save(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    with TestClient(make_app()) as c:
        c.get('/');headers={'X-Reup-Token':c.get('/api/state').json()['csrf']}
        cue={'id':1,'text':'Xin chào mọi người đây là câu đọc dài quá','start_ms':0,'end_ms':1000,'rate':1}
        assert c.post('/api/cue-estimate',json=cue).status_code==403
        r=c.post('/api/cue-estimate',json=cue,headers=headers)
        assert r.status_code==200 and r.json()['speed']>1.3 and r.json()['warning']
        assert c.post('/api/cue-estimate',json={**cue,'rate':99},headers=headers).status_code==422
        assert not list((tmp_path/'projects').glob('*/project.json'))
        words=[{'word':'Xin','start':0,'end':200},{'word':'chào','start':200,'end':500}]
        assert c.post('/api/align-reference',json={'reference':'Xin chào!','words':words},headers=headers).json()['can_apply']
        bad=[words[0],{**words[1],'start':100}]
        assert c.post('/api/align-reference',json={'reference':'Xin chào','words':bad},headers=headers).status_code==400
