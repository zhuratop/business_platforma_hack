from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api import app
from backend.app.storage import meta


CODE=(Path(__file__).resolve().parents[2]/'scripts/templates/check_changed_share.py').read_text(encoding='utf-8')


def data(response):
    assert response.status_code==200,response.text
    return response.json()['data']


def test_delete_check_detaches_configs_but_preserves_frozen_runs_and_files(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    meta.init()
    alice,bob=TestClient(app),TestClient(app)
    data(alice.post('/api/auth/login',json={'username':'alice','password':'demo'}))
    data(bob.post('/api/auth/login',json={'username':'bob','password':'demo'}))
    boot=data(alice.get('/api/bootstrap'))
    config=boot['configs'][0]
    check=data(alice.post('/api/scripts',json={'name':'new.py','kind':'check','source':'editor','code':CODE,'params':{}}))
    config['checks'].append(check['id'])
    config=data(alice.post('/api/configs',json=config))
    from backend.app.core.execution import snapshots
    frozen=snapshots(boot['user']['id'],config)
    run=meta.put('runs',boot['user']['id'],{'config':config,'snapshots':frozen},'QUEUED')
    assert bob.delete('/api/scripts/'+check['id']).status_code==404
    assert alice.delete('/api/scripts/'+config['stages']['normalize']).status_code==400
    result=data(alice.delete('/api/scripts/'+check['id']))
    assert result['updated_configs']==1
    assert check['id'] not in {s['id'] for s in data(alice.get('/api/scripts'))}
    assert check['id'] not in next(c for c in data(alice.get('/api/configs')) if c['id']==config['id'])['checks']
    assert check['id'] in meta.get('runs',run['id'])['config']['checks']
    assert data(alice.get(f"/api/runs/{run['id']}/scripts/{check['id']}"))['code']==CODE
    assert alice.post('/api/configs',json=config).status_code==404
    assert alice.post('/api/scripts',json=check).status_code==404
    assert alice.post('/api/scripts/validate',json={'script_id':check['id']}).status_code==404
    data(alice.delete('/api/scripts/'+check['id']))  # safe repeat
    original=next(s for s in boot['scripts'] if s['kind']=='check' and s['source']=='file')
    file=Path(original['path']);raw=file.read_bytes()
    data(alice.delete('/api/scripts/'+original['id']))
    assert file.read_bytes()==raw
    assert original['id'] not in {s['id'] for s in data(alice.get('/api/bootstrap'))['scripts']}


def test_duplicate_check_id_is_rejected_before_queuing(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    meta.init()
    client=TestClient(app)
    data(client.post('/api/auth/login',json={'username':'alice','password':'demo'}))
    config=data(client.get('/api/bootstrap'))['configs'][0]
    first=data(client.post('/api/scripts',json={'name':'first.py','kind':'check','source':'editor','code':CODE,'params':{}}))
    second=data(client.post('/api/scripts/upload?kind=check',files={'file':('second.py',CODE.encode())}))
    config['checks']+=[first['id'],second['id']]
    response=client.post('/api/configs',json=config)
    assert response.status_code==400 and 'CHECK.id=my_changes' in response.text
    config['checks'].remove(first['id'])
    assert data(client.post('/api/configs',json=config))['checks'][-1]==second['id']
