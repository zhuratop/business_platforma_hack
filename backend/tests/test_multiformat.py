import io
import json
import zipfile
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app.api import app
from backend.app.core import importer
from backend.app.core.execution import compile_script
from backend.app.core.validator import reader_preview
from backend.app.storage import meta
from backend.app.workers.jobs import execute
from scripts.default_spr.reader import read_input
from scripts.default_spr.normalize import normalize
from scripts.default_spr.compare import compare
from backend.app.plugins.defaults import default_params


from scripts.make_multiformat_sample import encode


@pytest.mark.parametrize('fmt',['json','xml','csv'])
def test_typed_values_and_arrays(fmt):
    value={'empty':'','null':None,'false':False,'text':'001','n':0.25,'arr':[{'id':'x','n':2}, {'id':'y','n':3}], 'empty_array':[]}
    assert read_input(encode(value,fmt),'x.'+fmt,'x','BEFORE',{})==value


def test_reader_rejects_ambiguous_and_unsafe_inputs():
    for raw in [b'path,value,value_kind\n/x,1,number\n/x,2,number',
                b'path,value,value_kind\n/a/1,x,string',b'path,value,value_kind\n/x,no,boolean']:
        with pytest.raises(ValueError):
            read_input(raw,'x.csv','x','BEFORE',{})
    with pytest.raises(ValueError,match='DTD'):
        read_input(b'<!DOCTYPE a [<!ENTITY x "test">]><a>&x;</a>','x.xml','x','BEFORE',{})


def test_cross_format_composite_keys_presence_and_bucket_change():
    before={'decisionResult':{'available_offers':[{'product_id':'1','type':'A','rank':1},{'product_id':'1','type':'B','rank':2}]},
            'score':0.42,'nullable':None,'lost':'','flag':False}
    after={'decisionResult':{'available_offers':list(reversed(before['decisionResult']['available_offers']))},
           'score':0.58,'nullable':None,'new':'','flag':False}
    before['appData']=after['appData']={'application_id':'x'}
    b=read_input(encode(before,'xml'),'x.xml','x','BEFORE',{})
    a=read_input(encode(after,'csv'),'x.csv','x','AFTER',{})
    params={**default_params()['normalize'],'buckets':{'score':[{'min':0,'max':1,'label':'same bucket'}]}}
    rows=list(compare(list(normalize(b,'x','BEFORE',params)),list(normalize(a,'x','AFTER',params)),{}))
    offers=[r for r in rows if r['PATH'].startswith('decisionResult.available_offers.')]
    assert len({r['ARRAY_KEY'] for r in offers})==2
    assert all(r['DIFF_FLAG']==0 for r in offers)
    by_path={r['PATH']:r for r in rows}
    assert by_path['score']['DIFF_FLAG']==1
    assert by_path['score']['ADJUSTED_BEFORE']==by_path['score']['ADJUSTED_AFTER']
    assert by_path['lost']['CHANGE_TYPE']=='ATTRIBUTE_LOST'
    assert by_path['new']['CHANGE_TYPE']=='ATTRIBUTE_NEW'
    assert by_path['nullable']['KIND_BEFORE']=='null' and by_path['flag']['KIND_AFTER']=='boolean'


def test_semicolon_csv_dialect_is_not_overruled_at_import():
    raw=b'path;value;value_kind\n"/decision";"APPROVE";"string"\n'
    importer.syntax(raw,'.csv')
    assert read_input(raw,'x.csv','x','BEFORE',{'csv_delimiter':';'})=={'decision':'APPROVE'}


def unpack(response):
    assert response.status_code==200,response.text
    return response.json()['data']


def test_mixed_real_pairs_custom_upload_and_durable_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path/'runtime')
    meta.init()
    client=TestClient(app)
    other=TestClient(app)
    unpack(client.post('/api/auth/login',json={'username':'alice','password':'demo'}))
    unpack(other.post('/api/auth/login',json={'username':'bob','password':'demo'}))
    boot=unpack(client.get('/api/bootstrap'))
    root=Path(__file__).parent/'fixtures'/'spr'
    files=sorted((root/'BEFORE').glob('*.json'))
    expected={}
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('manifest.json',json.dumps({'applications':len(files),'srez':{s:{'dir':s} for s in ['BEFORE','AFTER']}}))
        for i,f in enumerate(files):
            for j,source in enumerate(['BEFORE','AFTER']):
                value=json.loads((root/source/f.name).read_bytes())
                expected[source,f.stem]=value
                fmt=['json','xml','csv'][(i+j)%3]
                z.writestr(f'{source}/{f.stem}.{fmt}',encode(value,fmt))
    ds=unpack(client.post('/api/datasets/upload',files={'file':('mixed.zip',archive.getvalue())}))
    assert ds['formats']==['csv','json','xml'] and ds['count']==len(files)
    for app_id,b,a in importer.pairs(ds):
        assert b==expected['BEFORE',app_id] and a==expected['AFTER',app_id]
    reader_code=(meta.ROOT/'scripts/default_spr/reader.py').read_text(encoding='utf-8')
    # A side effect catches accidental repeated reader execution in facts.
    reader_code+='\n_original=read_input\n_calls=set()\ndef read_input(raw,filename,app_id,source,params):\n key=(app_id,source)\n if key in _calls: raise ValueError("reader called twice")\n _calls.add(key)\n return _original(raw,filename,app_id,source,params)\n'
    reader=unpack(client.post('/api/scripts/upload?kind=reader',files={'file':('custom_reader.py',reader_code.encode())}))
    preview=reader_preview({'dataset':ds,'params':{}},compile_script(reader))
    assert preview[1][0]['response']==expected['BEFORE',preview[0]]
    assert other.post('/api/scripts/validate',json={'script_id':reader['id'],'dataset_id':ds['id']}).status_code==404
    cfg=boot['configs'][0]
    cfg['stages']['reader']=reader['id']
    cfg['params']['stats']['bootstrap']=100
    cfg['params']['processing']={'batch_pairs':1}
    cfg=unpack(client.post('/api/configs',json=cfg))
    run=unpack(client.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    execute('runs',run['id'])
    ready=meta.get('runs',run['id'])
    assert ready['status']=='READY',ready.get('traceback')
    assert ready['saved_pairs']==len(files)
    assert 'custom_reader.py'==ready['snapshots'][reader['id']]['name']
    with duckdb.connect(ready['mart_path'],read_only=True) as con:
        assert con.execute('SELECT count(*) FROM raw_inputs').fetchone()[0]==len(files)
        assert con.execute('SELECT count(DISTINCT APP_ID),count(*) FROM app_segments').fetchone()==(len(files),len(files))
        for app_id,b,a in con.execute('SELECT * FROM raw_inputs').fetchall():
            assert json.loads(b)==expected['BEFORE',app_id] and json.loads(a)==expected['AFTER',app_id]
        assert con.execute('SELECT count(*) FROM normalized_union').fetchone()[0]==ready['normalized_rows']
    assert client.get(f"/api/runs/{run['id']}/report.html").status_code==200
    assert other.get(f"/api/runs/{run['id']}").status_code==404
    # Fail halfway through pair 2: only pair 1 may remain committed.
    norm=next(s for s in boot['scripts'] if s['id']==cfg['stages']['normalize'])
    bad_code=norm['code']+f'\n_original=normalize\ndef normalize(response,app_id,source,params):\n yield from _original(response,app_id,source,params)\n if app_id=={files[1].stem!r}: raise ValueError("deliberate pair failure")\n'
    bad=unpack(client.post('/api/scripts',json={'name':'bad.py','kind':'normalize','source':'editor','code':bad_code,'params':{}}))
    cfg['stages']['normalize']=bad['id']
    cfg=unpack(client.post('/api/configs',json=cfg))
    run=unpack(client.post('/api/runs',json={'dataset_id':ds['id'],'config_id':cfg['id']}))
    execute('runs',run['id'])
    failed=meta.get('runs',run['id'])
    assert failed['status']=='FAILED' and failed['saved_pairs']==1
    partial=meta.RUNTIME/'runs'/run['id']/'mart.tmp.duckdb'
    with duckdb.connect(str(partial),read_only=True) as con:
        # Reading is now a separately durable stage; all raw pairs survive a
        # later normalization failure, while only complete normalized pairs commit.
        assert con.execute('SELECT count(*) FROM raw_inputs').fetchone()[0]==len(files)
        assert con.execute('SELECT DISTINCT APP_ID FROM normalized_union').fetchall()==[(files[0].stem,)]
    assert client.get(f"/api/runs/{run['id']}/report.html").status_code==409


def test_duplicate_id_across_formats_is_rejected(tmp_path):
    (tmp_path/'b').mkdir();(tmp_path/'a').mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'applications':1,'srez':{'BEFORE':{'dir':'b'},'AFTER':{'dir':'a'}}}))
    for name in ['b/x.json','b/x.xml','a/x.json']:
        (tmp_path/name).write_text('{}')
    with pytest.raises(ValueError,match='Duplicate APP_ID'):
        importer.validate(tmp_path)
