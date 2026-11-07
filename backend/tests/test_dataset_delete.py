from fastapi.testclient import TestClient

from backend.app.api import app
from backend.app.storage import meta


def test_delete_hides_all_own_duplicates_keeps_runs_and_allows_new_import(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    with TestClient(app) as client:
        client.post('/api/auth/login',json={'username':'alice','password':'demo'})
        owner=client.get('/api/auth/me').json()['data']['id']
        with meta.db() as con:
            bob=con.execute("SELECT id FROM users WHERE name='bob'").fetchone()[0]
        snapshot=tmp_path/'snapshot';snapshot.mkdir();(snapshot/'input.json').write_text('{}')
        payload={'checksum':'same','name':'Test','path':str(snapshot),'count':1,'bytes':2}
        first=meta.put('datasets',owner,payload,'VALIDATED','old')
        meta.put('datasets',owner,payload,'VALIDATED','new')
        meta.put('datasets',bob,payload,'VALIDATED','bob-copy')
        meta.put('runs',owner,{'dataset_id':first['id']},'READY','history')
        assert client.delete('/api/datasets/bob-copy').status_code==404
        assert client.delete('/api/datasets/new').status_code==200
        assert client.get('/api/datasets').json()['data']==[]
        assert client.get('/api/bootstrap').json()['data']['datasets']==[]
        assert meta.get('datasets','old',owner)['status']=='DELETED'
        assert client.get('/api/runs/history').status_code==200
        assert snapshot.exists() and (snapshot/'input.json').exists()
        assert len(meta.dataset_listing(bob))==1
        assert client.post('/api/runs',json={'dataset_id':'old','config_id':'unused'}).status_code==409
        assert client.delete('/api/datasets/new').status_code==200  # Idempotent.
        imported=meta.register_dataset(owner,payload,'fresh')
        assert imported['id']=='fresh' and len(meta.dataset_listing(owner))==1
        client.delete('/api/datasets/new')  # Replaying an old delete cannot remove a fresh import.
        assert meta.dataset_listing(owner)[0]['id']=='fresh'
