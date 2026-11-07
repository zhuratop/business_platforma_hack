"""Integration tests exercise a real worker-built four-pair immutable mart."""
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
import duckdb
import pytest
from fastapi.testclient import TestClient
from backend.app.storage import meta
from backend.app.api import app
from backend.app.workers.jobs import execute
from backend.app.storage.mart import MartAPI
from backend.app.core.pivot import decode,where

CUSTOM='''def run(mart,params):
    ids=mart.app_ids(diff_flag=1)
    return [dict(LABEL='Custom',SOURCE='AFTER',ARGUMENT='all',CNT=len(ids),TOTAL=mart.total_apps(),METRIC=len(ids)/mart.total_apps(),APP_IDS=ids[:20],RESULT='PASS',CONFIDENCE='HIGH')]
CHECK=dict(id='custom',label='Custom',params={'app_ids_limit':20},entrypoint=run)
'''

def data(response):
    assert response.status_code==200,response.text
    return response.json()['data']

@pytest.fixture(scope='module')
def env(tmp_path_factory):
    previous=meta.RUNTIME
    meta.RUNTIME=tmp_path_factory.mktemp('spr-api')
    meta.init()
    folder=meta.RUNTIME/'input'
    (folder/'BEFORE').mkdir(parents=True);(folder/'AFTER').mkdir()
    sample_root=Path(__file__).parent/'fixtures'/'spr'
    files=sorted((sample_root/'BEFORE').glob('*.json'))
    for f in files:
        shutil.copy2(f,folder/'BEFORE'/f.name)
        shutil.copy2(sample_root/'AFTER'/f.name,folder/'AFTER'/f.name)
    (folder/'manifest.json').write_text(json.dumps({'applications':len(files),'srez':{'BEFORE':{'dir':'BEFORE'},'AFTER':{'dir':'AFTER'}}}))
    alice,bob=TestClient(app),TestClient(app)
    data(alice.post('/api/auth/login',json={'username':'alice','password':'demo'}))
    data(bob.post('/api/auth/login',json={'username':'bob','password':'demo'}))
    boot=data(alice.get('/api/bootstrap'))
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        for f in folder.rglob('*.json'):
            z.write(f,f.relative_to(folder))
    ds=data(alice.post('/api/datasets/upload',files={'file':('test.zip',archive.getvalue(),'application/zip')}))
    cfg=boot['configs'][0]
    cfg['params']['stats']['bootstrap']=100
    cfg=data(alice.post('/api/configs',json=cfg))
    run=data(alice.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    execute('runs',run['id'])
    ready=data(alice.get('/api/runs/'+run['id']))
    assert ready['status']=='READY',ready
    yield alice,bob,ds,cfg,run['id']
    alice.close();bob.close()
    meta.RUNTIME=previous

def test_user_isolation_every_object(env):
    alice,bob,ds,cfg,rid=env
    assert data(bob.get('/api/runs'))==[]
    assert data(bob.get('/api/datasets'))==[]
    own=data(alice.get('/api/bootstrap'))
    for path in ['/datasets/'+ds['id'],'/runs/'+rid,'/runs/'+rid+'/events','/runs/'+rid+'/summary','/runs/'+rid+'/stats','/runs/'+rid+'/checks','/runs/'+rid+'/report.html','/runs/'+rid+'/apps/I32554354','/runs/'+rid+'/scripts/'+cfg['stages']['normalize']]:
        assert bob.get('/api'+path).status_code==404,path
    for path,payload in [('/runs',{'dataset_id':ds['id'],'config_id':cfg['id']}),('/configs',cfg),('/scripts',own['scripts'][0]),('/runs/'+rid+'/checks',{}),('/runs/'+rid+'/pivot',{'rows':['PATH']}),('/scripts/validate',{'script_id':own['scripts'][0]['id']})]:
        assert bob.post('/api'+path,json=payload).status_code==404,path
    assert TestClient(app).get('/api/runs').status_code==401

def test_unique_pivot_memberships_and_attribute_highlight(env):
    alice,_,_,_,rid=env
    req={'rows':[],'columns':[],'filters':{'DIFF_FLAG':[1]}}
    result=data(alice.post(f'/api/runs/{rid}/pivot',json=req))
    cell=result['cells'][0]
    page=data(alice.post(f'/api/runs/{rid}/pivot/apps',json={'cell_token':cell['cell_token'],'page':1,'page_size':2}))
    ids=page['app_ids']
    if page['total']>2:
        ids+=data(alice.post(f'/api/runs/{rid}/pivot/apps',json={'cell_token':cell['cell_token'],'page':2,'page_size':2}))['app_ids']
    assert cell['count']==page['total']==len(set(ids))
    details=data(alice.get(f'/api/runs/{rid}/apps/{ids[0]}',params={'cell_token':cell['cell_token']}))
    assert all(r['highlight']==bool(r['DIFF_FLAG']) for r in details['rows'])
    assert len(details['rows'])>cell['count']
    assert alice.post(f'/api/runs/{rid}/pivot',json={'rows':['PATH;DROP TABLE x']}).status_code==400
    assert alice.post(f'/api/runs/{rid}/pivot/apps',json={'cell_token':cell['cell_token']+'tampered'}).status_code==400

def test_mart_filters_exact_and_combined(env):
    alice,_,_,_,rid=env
    run=meta.get('runs',rid)
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        mart=MartAPI(con)
        for f in [dict(path=['characteristics.score_okb']),dict(path_prefix='decisionResult.product_trials.rules.',key='hit',diff_flag=1),dict(change_type=['ATTRIBUTE_NEW','ATTRIBUTE_LOST']),dict(array_key='15210',value_after='APPROVE'),dict(app_ids=[]),dict(value_before='NULL')]:
            rows=mart.rows(**f)
            assert mart.count(**f)==len(rows)
            assert mart.app_ids(**f)==sorted({r['APP_ID'] for r in rows})
        assert mart.total_apps()==4

def test_new_editor_check_and_atomic_recheck_file_upload(env):
    alice,_,_,cfg,rid=env
    original=meta.get('runs',rid)
    checksum=hashlib.sha256(Path(original['mart_path']).read_bytes()).hexdigest()
    editor=data(alice.post('/api/scripts',json=dict(name='custom.py',kind='check',source='editor',code=CUSTOM,params={})))
    preview=data(alice.post('/api/scripts/validate',json={'script_id':editor['id']}))
    assert preview['valid'],preview
    cfg={**cfg,'id':None,'name':'Custom checks','checks':cfg['checks']+[editor['id']]}
    cfg=data(alice.post('/api/configs',json=cfg))
    execution=data(alice.post(f'/api/runs/{rid}/checks',json={'config_id':cfg['id']}))
    assert meta.get('runs',rid)['report_version']==original['report_version']
    execute('check_executions',execution['id'])
    result=data(alice.get(f'/api/runs/{rid}/checks'))
    assert any(r['LABEL']=='Custom' for r in result['rows'])
    assert result['version']==execution['id']
    assert hashlib.sha256(Path(original['mart_path']).read_bytes()).hexdigest()==checksum
    py=data(alice.post('/api/scripts/upload?kind=check',files={'file':('file.py',CUSTOM.replace("id='custom'","id='file_check'").encode(),'text/x-python')}))
    assert py['source']=='file'
    assert data(alice.post('/api/scripts/validate',json={'script_id':py['id']}))['valid']
    Path(py['path']).write_text(py['code']+'\n# updated on disk\n',encoding='utf-8')
    current=next(s for s in data(alice.get('/api/scripts')) if s['id']==py['id'])
    assert current['code'].endswith('# updated on disk\n')
    cfg['checks']=[py['id']]
    cfg=data(alice.post('/api/configs',json=cfg))
    execution=data(alice.post(f'/api/runs/{rid}/checks',json={'config_id':cfg['id']}))
    execute('check_executions',execution['id'])
    assert meta.get('check_executions',execution['id'])['status']=='READY'
    snapshot=data(alice.get(f'/api/runs/{rid}/scripts/{execution["id"]}:{py["id"]}'))
    assert snapshot['code']==current['code']
    bad=data(alice.post('/api/scripts',json=dict(name='bad.py',kind='check',source='editor',code='raise RuntimeError("broken")',params={})))
    cfg['checks']=[bad['id']];cfg=data(alice.post('/api/configs',json=cfg))
    previous=meta.get('runs',rid)['report_version']
    execution=data(alice.post(f'/api/runs/{rid}/checks',json={'config_id':cfg['id']}))
    execute('check_executions',execution['id'])
    assert meta.get('check_executions',execution['id'])['status']=='FAILED'
    assert meta.get('runs',rid)['report_version']==previous

def test_check_files_unchanged_and_report_link(env):
    alice,_,_,_,rid=env
    for file in (meta.ROOT/'scripts'/'checks').glob('check_*.py'):
        assert file.read_bytes()==(meta.DATA_ROOT/'checks'/file.name).read_bytes()
    response=alice.get(f'/api/runs/{rid}/report.html?download=true')
    assert response.status_code==200
    assert 'attachment' in response.headers['content-disposition']
    assert meta.PUBLIC_BASE_URL+'/?run='+rid+'&amp;tab=pivot' in response.text
    assert 'APPROVAL_PROBABILITY' in response.text

def test_snapshot_codes_immutable_and_no_partial_summary(env):
    alice,_,ds,cfg,_=env
    run=data(alice.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    response=alice.get(f'/api/runs/{run["id"]}/summary').json()
    assert response['status']=='QUEUED' and response['data'] is None
    assert alice.get(f'/api/runs/{run["id"]}/stats').status_code==409
    sid=cfg['stages']['normalize']
    before=data(alice.get(f'/api/runs/{run["id"]}/scripts/{sid}'))
    s={**before,'source':'editor','code':before['code']+'\n# updated\n'}
    data(alice.post('/api/scripts',json=s))
    assert data(alice.get(f'/api/runs/{run["id"]}/scripts/{sid}'))['hash']==before['hash']

def test_replace_all_procedures_without_core_changes(env):
    alice,_,ds,cfg,_=env
    compare_code='''from backend.app.core.normalize import compare_rows
def compare(before_rows,after_rows,params):
    for row in compare_rows(before_rows,after_rows,params):
        for k in ['PRESENT_BEFORE','PRESENT_AFTER','KIND_BEFORE','KIND_AFTER']:
            row.pop(k)
        yield row
'''
    facts_code='''from scripts.default_spr.facts import build_facts as base
def build_facts(mart,raw_pairs,params):
    facts=base(mart,raw_pairs,params)
    original=facts['pivot_facts']
    def minimal():
        for r in original:
            yield {k:v for k,v in r.items() if k not in ['DECISION_BEFORE','DECISION_AFTER','DECISION_CHANGED','PARTNER_TYPE','ROUTING_METHOD']}
    return {**facts,'pivot_facts':minimal()}
'''
    normalize_code='''from scripts.default_spr.normalize import normalize as base
def normalize(response,app_id,source,params):
    yield from base(response,app_id,source,params)
'''
    ids={}
    for kind,code in [('normalize',normalize_code),('compare',compare_code),('facts',facts_code)]:
        s=data(alice.post('/api/scripts',json=dict(name=f'custom-{kind}.py',kind=kind,source='editor',code=code,params={})))
        ids[kind]=s['id']
    cfg=data(alice.post('/api/configs',json={**cfg,'id':None,'name':'All custom procedures','stages':ids}))
    r=data(alice.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    execute('runs',r['id'])
    assert meta.get('runs',r['id'])['status']=='READY',meta.get('runs',r['id']).get('traceback')

def test_second_user_has_own_successful_run(env):
    alice,bob,_,_,_=env
    archive=io.BytesIO()
    samples=Path(__file__).parent/'fixtures'/'spr'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('manifest.json',json.dumps({'applications':4,'srez':{'BEFORE':{'dir':'BEFORE'},'AFTER':{'dir':'AFTER'}}}))
        for f in samples.rglob('*.json'):
            z.write(f,f.relative_to(samples))
    ds=data(bob.post('/api/datasets/upload',files={'file':('bob.zip',archive.getvalue(),'application/zip')}))
    cfg=data(bob.get('/api/configs'))[0]
    cfg['params']['stats']['bootstrap']=100
    cfg=data(bob.post('/api/configs',json=cfg))
    r=data(bob.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    assert alice.get('/api/runs/'+r['id']).status_code==404
    execute('runs',r['id'])
    assert data(bob.get('/api/runs/'+r['id']))['status']=='READY'
    assert data(bob.get('/api/runs/'+r['id']+'/summary'))['total_apps']==4
