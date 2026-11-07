import csv
import json
from pathlib import Path
import pytest
from backend.app.core.normalize import flatten,compare_rows
from backend.app.storage.meta import DATA_ROOT
from scripts.educational import normalize as educational
from scripts.default_spr.normalize import normalize
from backend.app.plugins.defaults import default_params

FIXTURES = Path(__file__).parent/'fixtures'

def csv_rows(file):
    with file.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))

def test_educational_exact_contract():
    folder = FIXTURES/'example'
    b = list(educational(json.loads((folder/'01_response_BEFORE.json').read_bytes()),'1001','BEFORE'))
    a = list(educational(json.loads((folder/'02_response_AFTER.json').read_bytes()),'1001','AFTER'))
    assert (len(b),len(a),len(b+a)) == (12,14,26)
    for rows,file in [(b,'03_normalized_BEFORE.csv'),(a,'04_normalized_AFTER.csv')]:
        expected = csv_rows(folder/file)
        sort_key = lambda r:(r['PREFIX'],r['CLASS'],r['SUFFIX'],r['ARRAY_KEY'],r['KEY'])
        assert sorted([{k:r[k] for k in expected[0]} for r in rows],key=sort_key) == sorted(expected,key=sort_key)
    comparison = list(compare_rows(b,a,{}))
    assert len(comparison)==14 and sum(r['DIFF_FLAG'] for r in comparison)==6
    expected = csv_rows(folder/'06_comparison.csv')
    key = lambda r:(r['PATH'],r['ARRAY_KEY'])
    assert sorted([{k:str(r[k]) for k in expected[0]} for r in comparison],key=key)==sorted(expected,key=key)

def test_null_missing_empty_false_and_bucket():
    p = {'buckets':{'score':[{'min':0.3,'max':0.6,'label':'same'}]}}
    b = list(flatten({'null':None,'false':False,'string':'NULL','empty':'','lost':1,'score':0.42},'x','BEFORE',p))
    a = list(flatten({'null':False,'false':None,'string':None,'new':'','score':0.58},'x','AFTER',p))
    rows = {r['PATH']:r for r in compare_rows(b,a,{})}
    assert rows['null']['CHANGE_TYPE']=='VALUE_CHANGED'
    assert rows['false']['CHANGE_TYPE']=='VALUE_CHANGED'
    assert rows['string']['VALUE_BEFORE']==rows['string']['VALUE_AFTER']=='NULL'
    assert rows['string']['DIFF_FLAG']==1
    assert rows['empty']['CHANGE_TYPE']=='ATTRIBUTE_LOST'
    assert rows['new']['CHANGE_TYPE']=='ATTRIBUTE_NEW'
    assert rows['score']['ADJUSTED_BEFORE']==rows['score']['ADJUSTED_AFTER'] and rows['score']['DIFF_FLAG']==1

def test_real_composite_reordering_and_null():
    folder = FIXTURES/'spr'
    for file in sorted((folder/'AFTER').glob('*.json')):
        response = json.loads(file.read_bytes())
        p = default_params()['normalize']
        b = list(normalize(response,file.stem,'BEFORE',p))
        for value in response['decisionResult'].values():
            if isinstance(value,list):
                value.reverse()
        for trial in response['decisionResult']['product_trials']:
            trial['rules'].reverse()
            trial['scoring']['scoreModels'].reverse()
        response['ext_data'].reverse()
        response['product_catalog'].reverse()
        a = list(normalize(response,file.stem,'AFTER',p))
        assert sum(r['DIFF_FLAG'] for r in compare_rows(b,a,{}))==0
        assert len({(r['PATH'],r['ARRAY_KEY']) for r in a})==len(a)
    response = {'appData':{'application_id':'X'},'decisionResult':{'available_offers':[{'product_id':1,'type':'standard'},{'product_id':1,'type':'manual'}]}}
    rows = list(normalize(response,'X','BEFORE',default_params()['normalize']))
    assert len([r for r in rows if r['KEY']=='type'])==2
    response['decisionResult']['available_offers'].append({'product_id':1,'type':'manual'})
    with pytest.raises(ValueError,match='Duplicate'):
        list(normalize(response,'X','BEFORE',default_params()['normalize']))

def test_vector_index_and_nested_models():
    p = default_params()['normalize']
    response = {'appData':{'application_id':'x'},'decisionResult':{'scoring':[
        {'modelName':'one','features':{'age':1},'value':[0.1,0.2]}, {'modelName':'two','features':{'age':1},'value':[0.2]}]}}
    before = list(normalize(response,'x','BEFORE',p))
    assert {r['ARRAY_KEY'] for r in before if r['KEY']=='age'}=={'one','two'}
    response['decisionResult']['scoring'][0]['value'].reverse()
    rows = list(compare_rows(before,list(normalize(response,'x','AFTER',p)),{}))
    assert sum(r['DIFF_FLAG'] for r in rows)==2

def test_scalar_array_value_mode_preserves_types():
    p={'arrays':{'values':{'mode':'value'}}}
    b=list(flatten({'values':[None,'NULL',False,'false',0,'0']},'x','BEFORE',p))
    a=list(flatten({'values':['0',0,'false',False,'NULL',None]},'x','AFTER',p))
    assert len(b)==6 and len({r['ARRAY_KEY'] for r in b})==6
    assert all(r['DIFF_FLAG']==0 for r in compare_rows(b,a,{}))
