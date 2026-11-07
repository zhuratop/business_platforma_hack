"""Small real-data integration: checkpoints, resumption, isolation, parallel workers."""
import io
import hashlib
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app.api import app
from backend.app.storage import meta
from backend.app.workers.jobs import execute
from backend.app.workers.main import recover
from backend.app.workers.processes import JobProcess


def data(response):
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(meta, 'RUNTIME', tmp_path)
    monkeypatch.setenv('SPR_RUNTIME', str(tmp_path))
    meta.init()
    clients = [TestClient(app), TestClient(app)]
    archive = io.BytesIO()
    root = Path(__file__).parent / 'fixtures' / 'spr'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('manifest.json', json.dumps({'applications': 4, 'srez': {s: {'dir': s} for s in ['BEFORE', 'AFTER']}}))
        for file in root.rglob('*.json'):
            z.write(file, file.relative_to(root))
    objects = []
    for client, name in zip(clients, ['alice', 'bob']):
        data(client.post('/api/auth/login', json={'username': name, 'password': 'demo'}))
        boot = data(client.get('/api/bootstrap'))
        ds = data(client.post('/api/datasets/upload', files={'file': ('small.zip', archive.getvalue(), 'application/zip')}))
        cfg = boot['configs'][0]
        cfg['params']['stats']['bootstrap'] = 100
        cfg = data(client.post('/api/configs', json=cfg))
        objects.append((client, ds, cfg))
    yield objects
    for client in clients:
        client.close()


def test_checkpoints_resume_use_saved_input_and_frozen_config(setup, monkeypatch):
    alice, ds, cfg = setup[0]
    bob = setup[1][0]
    run = data(alice.post('/api/runs', json={'dataset_id': ds['id'], 'config_id': cfg['id'], 'stop_after': 'READING'}))
    id = run['id']
    execute('runs', id)
    run = data(alice.get('/api/runs/' + id))
    assert run['status'] == 'PAUSED' and run['completed_stage'] == 'READING'
    assert 'path' not in run['checkpoints'][0]
    assert data(alice.get(f'/api/runs/{id}/preview'))['total'] == 4
    assert alice.get(f'/api/runs/{id}/preview?table=comparison_mart').status_code == 400
    assert alice.get(f'/api/runs/{id}/report.html').status_code == 409
    assert bob.get(f'/api/runs/{id}/preview').status_code == 404
    assert bob.post(f'/api/runs/{id}/resume', json={}).status_code == 404
    assert alice.post(f'/api/runs/{id}/resume', json={'stop_after': 'READING'}).status_code == 409
    meta.update('runs', id, status='NORMALIZING')
    recover()
    assert meta.get('runs', id)['status'] == 'FAILED'
    assert meta.get('runs', id)['completed_stage'] == 'READING'
    # The input files are no longer needed after the reading checkpoint.
    for file in Path(ds['path']).rglob('I*.json'):
        file.unlink()
    cfg['params']['normalize']['exclude'] = ['decisionResult']
    data(alice.post('/api/configs', json=cfg))
    data(alice.post(f'/api/runs/{id}/resume', json={'stop_after': 'NORMALIZING'}))
    assert alice.post(f'/api/runs/{id}/resume', json={}).status_code == 409
    execute('runs', id)
    preview = data(alice.get(f'/api/runs/{id}/preview?table=normalized_union'))
    assert preview['total'] > 0
    saved = meta.get('runs', id)
    with duckdb.connect(saved['checkpoints'][-1]['path'], read_only=True) as con:
        assert con.execute("SELECT count(*) FROM normalized_union WHERE PATH='decisionResult.decision'").fetchone()[0] == 8
    first_times = [p['completed_at'] for p in saved['checkpoints']]
    digest = hashlib.sha256(Path(saved['checkpoints'][-1]['path']).read_bytes()).hexdigest()
    # A failed next stage must not damage the completed normalization artifact.
    data(alice.post(f'/api/runs/{id}/resume', json={'stop_after': 'COMPARING'}))
    from backend.app.workers.pipeline import DB_STAGES
    def fail(*args):
        raise ValueError('temporary comparison failure')
    with monkeypatch.context() as patch:
        patch.setitem(DB_STAGES, 'COMPARING', fail)
        execute('runs', id)
    assert meta.get('runs', id)['status'] == 'FAILED'
    assert meta.get('runs', id)['completed_stage'] == 'NORMALIZING'
    assert hashlib.sha256(Path(saved['checkpoints'][-1]['path']).read_bytes()).hexdigest() == digest
    data(alice.post(f'/api/runs/{id}/resume', json={'stop_after': 'STATS'}))
    execute('runs', id)
    assert meta.get('runs', id)['status'] == 'PAUSED'
    assert data(alice.get(f'/api/runs/{id}/preview?table=checks'))['total'] > 0
    assert data(alice.get(f'/api/runs/{id}/preview?table=stats'))['total'] > 0
    data(alice.post(f'/api/runs/{id}/resume', json={}))
    execute('runs', id)
    result = meta.get('runs', id)
    assert result['status'] == 'READY', result.get('traceback')
    assert len(result['checkpoints']) == 7
    assert [p['completed_at'] for p in result['checkpoints'][:2]] == first_times
    assert alice.get(f'/api/runs/{id}/report.html').status_code == 200
    assert 'http://lan-machine:8000/' in alice.get(f'/api/runs/{id}/report.html', headers={'host': 'lan-machine:8000'}).text


def test_parallel_users_and_atomic_resume_with_real_supervisor(setup):
    ids = []
    for client, ds, cfg in setup:
        # Deliberate short read delay makes overlap observable on fast machines.
        boot = data(client.get('/api/bootstrap'))
        reader = next(s for s in boot['scripts'] if s['id'] == cfg['stages']['reader'])
        code = reader['code'] + '\n_original=read_input\ndef read_input(*args,**kwargs):\n import time\n time.sleep(.15)\n return _original(*args,**kwargs)\n'
        script = data(client.post('/api/scripts', json={'name': 'slow reader', 'kind': 'reader', 'source': 'editor', 'code': code, 'params': {}}))
        cfg['stages']['reader'] = script['id']
        cfg = data(client.post('/api/configs', json=cfg))
        ids.append(data(client.post('/api/runs', json={'dataset_id': ds['id'], 'config_id': cfg['id'], 'stop_after': 'READING'}))['id'])
    child = JobProcess([sys.executable, '-m', 'backend.app.workers.main', '--workers', '2'], meta.ROOT)
    overlapped = False
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            runs = [meta.get('runs', id) for id in ids]
            if all(r['status'] not in ['QUEUED', 'PAUSED', 'FAILED'] and r.get('process_id') for r in runs):
                assert runs[0]['process_id'] != runs[1]['process_id']
                overlapped = True
            if all(r['status'] in ['PAUSED', 'FAILED'] for r in runs):
                break
            time.sleep(.1)
        assert overlapped, runs
        assert [r['status'] for r in runs] == ['PAUSED', 'PAUSED'], runs
    finally:
        child.close()
    assert len(data(setup[0][0].get('/api/runs'))) == 1
    assert len(data(setup[1][0].get('/api/runs'))) == 1
    assert setup[1][0].get('/api/runs/' + ids[0]).status_code == 404
    recover()
    assert meta.get('runs', ids[0])['status'] == 'PAUSED'
    owner = meta.get('runs', ids[0])['owner_id']
    def resume():
        try:
            return meta.resume_run(ids[0], owner, 'NORMALIZING')['status']
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: resume(), range(2))) == ['QUEUED', 'conflict']


def test_additional_account_can_log_in_without_access_to_other_users(setup):
    meta.create_user('analyst', 'test-password-123')
    with TestClient(app) as client:
        data(client.post('/api/auth/login', json={'username': 'analyst', 'password': 'test-password-123'}))
        assert data(client.get('/api/runs')) == []
        assert data(client.get('/api/datasets')) == []
    with pytest.raises(ValueError):
        meta.create_user('analyst', 'other-password')
