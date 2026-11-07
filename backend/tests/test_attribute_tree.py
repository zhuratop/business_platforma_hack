import duckdb
import pytest

from backend.app.core import attribute_tree as tree,pivot
from backend.app.core.normalize import flatten,compare_rows
from backend.app.storage import meta
from backend.app.storage.mart import initialize,write


@pytest.fixture
def con(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    c=duckdb.connect();initialize(c)
    params={'arrays':{'offers':{'mode':'fields','keys':['product_id','type']}},
            'buckets':{'score':[{'min':0,'max':1,'label':'one bucket'}]}}
    before={'mixed':'scalar','n':None,'empty':'','lost':1,'score':.42,
            'offers':[{'product_id':7,'type':'a'},{'product_id':7,'type':'b'}]}
    after={'mixed':{'child':1},'n':False,'empty':'','score':.58,
           'offers':[{'product_id':7,'type':'b'},{'product_id':7,'type':'a'}]}
    b=list(flatten(before,'A','BEFORE',params));a=list(flatten(after,'A','AFTER',params))
    b2=list(flatten({'n':'NULL'},'B','BEFORE',{}));a2=list(flatten({'n':'NULL'},'B','AFTER',{}))
    write(c,'normalized_union',b+a+b2+a2);write(c,'comparison_mart',list(compare_rows(b,a,{}))+list(compare_rows(b2,a2,{})))
    yield c
    c.close()


def test_nodes_are_unique_app_counts_with_composite_arrays_and_typed_values(con):
    root=tree.children(con,'run',tree.TreeRequest())
    assert root['totals']['TOTAL']['count']==2
    assert root['totals']['BEFORE_0']['count']==2
    assert root['totals']['BEFORE_1']['count']==1
    assert root['totals']['AFTER_1']['count']==1
    changed=pivot.decode(root['totals']['BEFORE_1']['cell_token'],'run')
    assert changed['__tree']['filters']=={'SOURCE':['BEFORE'],'DIFF_FLAG':[1]}
    assert pivot.apps(con,changed)['app_ids']==['A']
    assert ('score','') in pivot.matching_attributes(con,'A',changed)
    assert all(key not in pivot.matching_attributes(con,'A',changed) for key in [('empty','')])
    offers=next(n for n in root['nodes'] if n['label']=='offers')
    assert offers['cells']['TOTAL']['count']==1
    fields=tree.children(con,'run',tree.TreeRequest(**offers['request']))
    kind=next(n for n in fields['nodes'] if n['label']=='type')
    keys=tree.children(con,'run',tree.TreeRequest(**kind['request']))
    assert len(keys['nodes'])==2 and all(n['cells']['TOTAL']['count']==1 for n in keys['nodes'])
    assert keys['nodes'][0]['label']!=keys['nodes'][1]['label']
    values=[]
    for page in [1,2,3]:
        result=tree.children(con,'run',tree.TreeRequest(path='n',stage='values',array_key='',page_size=1,page=page))
        assert result['pagination']['total_nodes']==3
        values+=result['nodes']
    assert {(n['label'],n['value_kind']) for n in values}=={('null','null'),('false','boolean'),('"NULL"','string')}
    mixed=next(n for n in root['nodes'] if n['label']=='mixed')
    child=tree.children(con,'run',tree.TreeRequest(**mixed['request']))
    assert {n['label'] for n in child['nodes']}=={'Значения этого атрибута','child'}
    spec=pivot.decode(mixed['cells']['TOTAL']['cell_token'],'run')
    assert pivot.apps(con,spec)['total']==1
    assert pivot.matching_attributes(con,'A',spec)=={('mixed',''),('mixed.child','')}


def test_filters_bucket_differences_drilldown_and_highlights_match(con):
    result=tree.children(con,'run',tree.TreeRequest(path='score',stage='values',array_key='',filters={'SOURCE':['AFTER'],'DIFF_FLAG':[1]}))
    node=result['nodes'][0]
    assert node['label']=='one bucket' and node['cells']['AFTER']['count']==1 and node['cells']['BEFORE']['count']==0
    spec=pivot.decode(node['cells']['TOTAL']['cell_token'],'run')
    assert pivot.apps(con,spec)['app_ids']==['A']
    assert pivot.matching_attributes(con,'A',spec)=={('score','')}
    lost=tree.children(con,'run',tree.TreeRequest(path='lost',stage='values',array_key='',filters={'SOURCE':['AFTER'],'DIFF_FLAG':[1]}))
    assert lost['nodes']==[] and lost['totals']['TOTAL']['count']==0
    unchanged=tree.children(con,'run',tree.TreeRequest(path='n',stage='values',array_key='',filters={'DIFF_FLAG':[0]}))
    assert len(unchanged['nodes'])==1 and unchanged['nodes'][0]['label']=='"NULL"'
    with pytest.raises(ValueError):tree.children(con,'run',tree.TreeRequest(filters={'SOURCE':['INVALID']}))
