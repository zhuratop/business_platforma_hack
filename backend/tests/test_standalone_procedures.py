import ast
import builtins
import json
from pathlib import Path

import duckdb

from backend.app.core.normalize import flatten,compare_rows
from backend.app.plugins.defaults import default_params
from backend.app.storage.mart import initialize,write,MartAPI,SCHEMAS


ROOT=Path(__file__).resolve().parents[2]


def load_procedure(name):
    code=(ROOT/'scripts'/'default_spr'/f'{name}.py').read_text(encoding='utf-8')
    imports=[n for n in ast.walk(ast.parse(code)) if isinstance(n,ast.ImportFrom)]
    assert all(not (n.module or '').startswith(('backend','scripts')) for n in imports)
    normal_import=builtins.__import__
    def isolated_import(module,*args,**kwargs):
        assert not module.startswith(('backend','scripts')),module
        return normal_import(module,*args,**kwargs)
    namespace={'__name__':'standalone_procedure','__builtins__':{**vars(builtins),'__import__':isolated_import}}
    exec(compile(code,name+'.py','exec'),namespace)
    return namespace


def test_standalone_normalize_compare_and_facts_match_core_on_real_pairs():
    normalize=load_procedure('normalize')['normalize']
    compare=load_procedure('compare')['compare']
    build_facts=load_procedure('facts')['build_facts']
    folder=Path(__file__).parent/'fixtures'/'spr'
    pairs=[];normalized=[];compared=[]
    params=default_params()['normalize']
    for path in sorted((folder/'BEFORE').glob('*.json')):
        b=json.loads(path.read_bytes());a=json.loads((folder/'AFTER'/path.name).read_bytes())
        pairs.append((path.stem,b,a))
        before=list(normalize(b,path.stem,'BEFORE',params));after=list(normalize(a,path.stem,'AFTER',params))
        assert before==list(flatten(b,path.stem,'BEFORE',params))
        assert after==list(flatten(a,path.stem,'AFTER',params))
        delta=list(compare(before,after,{}))
        assert delta==list(compare_rows(before,after,{}))
        normalized+=before+after;compared+=delta
    with duckdb.connect() as con:
        initialize(con)
        write(con,'normalized_union',normalized);write(con,'comparison_mart',compared)
        mart=MartAPI(con);facts=build_facts(mart,lambda:iter(pairs),{})
        for name,table in [('segments','app_segments'),('product_trials','product_trials'),('offers','offers')]:
            write(con,table,list(facts[name]))
        actual=list(facts['pivot_facts'])
        expected=list(mart.default_facts(product_paths=['decisionResult.product_trials.','decisionResult.available_offers.']))
        canonical=lambda rows:sorted(json.dumps(row,sort_keys=True) for row in rows)
        assert canonical(actual)==canonical(expected)
        assert all(r['CNT']==len(set(r['APP_IDS'])) for r in actual)
        assert set(actual[0])==set(SCHEMAS['pivot_facts'])-{'fact_id'}|{'APP_IDS'}


def test_standalone_compare_preserves_types_presence_and_in_bucket_change():
    normalize=load_procedure('normalize')['normalize'];compare=load_procedure('compare')['compare']
    params={'buckets':{'score':[{'min':0,'max':1,'label':'one bucket'}]}}
    b={'appData':{'application_id':'app'},'null':None,'false':False,'empty':'','lost':1,'score':.42}
    a={'appData':{'application_id':'app'},'null':False,'false':None,'new':'','score':.58}
    rows={r['PATH']:r for r in compare(list(normalize(b,'app','BEFORE',params)),list(normalize(a,'app','AFTER',params)),{})}
    assert rows['null']['KIND_BEFORE']=='null' and rows['null']['KIND_AFTER']=='boolean'
    assert rows['false']['KIND_BEFORE']=='boolean' and rows['false']['KIND_AFTER']=='null'
    assert rows['empty']['CHANGE_TYPE']=='ATTRIBUTE_LOST' and rows['new']['CHANGE_TYPE']=='ATTRIBUTE_NEW'
    assert rows['score']['ADJUSTED_BEFORE']==rows['score']['ADJUSTED_AFTER']
    assert rows['score']['DIFF_FLAG']==1
