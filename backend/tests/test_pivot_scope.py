"""Product scope is not just an APP_ID filter on every attribute of an app."""
import duckdb
import pytest
from backend.app.core import pivot
from backend.app.core.normalize import flatten,compare_rows
from backend.app.domain.contracts import PivotRequest
from backend.app.storage.mart import initialize,write,MartAPI,SCHEMAS

@pytest.fixture
def con(tmp_path,monkeypatch):
    from backend.app.storage import meta
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    c=duckdb.connect(':memory:')
    initialize(c)
    params={'arrays':{'trials':{'mode':'fields','keys':['id']}},'buckets':{'score':[
        {'min':None,'max':0.3,'label':'low'},{'min':0.3,'max':None,'label':'middle'}]}}
    normalized=[];comparisons=[];segments=[];trials=[]
    for app,old_score,old_products,new_products in [('X',0.42,['A','B'],['A','B']),('Y',0.11,['A'],['B']),('Z',0.11,[],[])]:
        b={'decision':'APPROVE','score':old_score,'trials':[{'id':p,'decision':'APPROVE'} for p in old_products]}
        a={'decision':'REJECT','score':0.58,'trials':[{'id':p,'decision':'REJECT'} for p in new_products]}
        before=list(flatten(b,app,'BEFORE',params));after=list(flatten(a,app,'AFTER',params))
        normalized+=before+after;comparisons+=list(compare_rows(before,after,{}))
        segments.append({**{k:'' for k in SCHEMAS['app_segments']},'APP_ID':app,'DECISION_BEFORE':'APPROVE','DECISION_AFTER':'REJECT','DECISION_CHANGED':1})
        for source,products in [('BEFORE',old_products),('AFTER',new_products)]:
            for p in products:
                trials.append({**{k:None if t=='DOUBLE' else '' for k,t in SCHEMAS['product_trials'].items()},'APP_ID':app,'SOURCE':source,'product_id':p,'partner_id':'P' if p=='A' else 'Q'})
    write(c,'normalized_union',normalized);write(c,'comparison_mart',comparisons)
    write(c,'app_segments',segments);write(c,'product_trials',trials)
    facts=list(MartAPI(c).default_facts(product_paths=['trials.']))
    write(c,'pivot_facts',({**r,'fact_id':i} for i,r in enumerate(facts,1)))
    write(c,'fact_memberships',({'fact_id':i,'APP_ID':a} for i,r in enumerate(facts,1) for a in r['APP_IDS']))
    yield c
    c.close()

def query(con,rows=None,columns=None,**filters):
    return pivot.cells(con,'run',PivotRequest(rows=rows or [],columns=columns or [],filters=filters))['cells']

def test_global_decision_survives_lost_product_and_source_filter(con):
    cells=query(con,columns=['SOURCE'],PATH=['decision'],product_id=['A'])
    assert {r['dimensions']['SOURCE']:r['count'] for r in cells}=={'BEFORE':2,'AFTER':2}
    for cell in cells:
        f=pivot.decode(cell['cell_token'],'run')
        pages=[pivot.apps(con,f,page=i,page_size=1) for i in [1,2]]
        assert pages[0]['total']==cell['count']==2
        assert [p['app_ids'][0] for p in pages]==['X','Y']
        assert pivot.matching_attributes(con,'Y',f)=={('decision','')}

def test_product_attributes_do_not_leak_other_products_or_partners(con):
    cells=query(con,columns=['SOURCE'],PATH=['trials.decision'],product_id=['A'])
    assert {r['dimensions']['SOURCE']:r['count'] for r in cells}=={'BEFORE':2,'AFTER':1}
    empty=query(con,PATH=['decision'],product_id=['A'],partner_id=['Q'])[0]
    assert empty['count']==0
    assert pivot.apps(con,pivot.decode(empty['cell_token'],'run'))['app_ids']==[]
    assert query(con,PATH=['decision'],partner_id=['P'])[0]['count']==2

def test_unique_apps_and_apps_with_no_products(con):
    assert query(con,PATH=['decision'])[0]['count']==3
    assert query(con,product_id=['A','B'])[0]['count']==2
    assert query(con,PATH=['decision'],product_id=[''])[0]['count']==1
    assert {r['dimensions']['product_id']:r['count'] for r in query(con,rows=['product_id'],PATH=['decision'])}=={'A':2,'B':2,'':1}

def test_pair_buckets_are_resolved_per_member_of_shared_fact(con):
    # X/Y/Z share AFTER score bucket; their BEFORE buckets differ.
    cells=query(con,rows=['ADJUSTED_BEFORE'],columns=['ADJUSTED_AFTER'],PATH=['score'],SOURCE=['AFTER'])
    assert {(r['dimensions']['ADJUSTED_BEFORE'],r['dimensions']['ADJUSTED_AFTER']):r['count'] for r in cells}=={('low','middle'):2,('middle','middle'):1}
    cell=next(r for r in cells if r['dimensions']['ADJUSTED_BEFORE']=='middle')
    f=pivot.decode(cell['cell_token'],'run')
    assert pivot.apps(con,f)['app_ids']==['X']
    assert pivot.matching_attributes(con,'X',f)=={('score','')}
    assert query(con,rows=['ADJUSTED_BEFORE'],columns=['ADJUSTED_AFTER'],PATH=['score'],product_id=['A'])[0]['count']==1

def test_report_pages_complete_rows_and_exact_union_totals(con):
    filters={'product_id':['A','B']}
    layout={'rows':['PATH','ARRAY_KEY','VALUE_ADJUSTED'],'columns':['DIFF_FLAG','SOURCE'],'filters':filters}
    full=pivot.cells(con,'run',PivotRequest(**layout))['cells']
    first=pivot.cells(con,'run',PivotRequest(**layout,page_size=1,include_totals=True))
    assert first['grand_total']['count']==2
    assert not first['truncated']
    all_cells=[]
    for page in range(1,first['pagination']['total_rows']+1):
        result=pivot.cells(con,'run',PivotRequest(**layout,page=page,page_size=1,include_totals=True))
        assert len({tuple(r['dimensions'][k] for k in layout['rows']) for r in result['cells']})==1
        all_cells+=result['cells']
        assert result['grand_total']['count']==2
        assert result['column_totals']==first['column_totals']
    identify=lambda r:(tuple(sorted(r['dimensions'].items())),r['count'])
    assert sorted(map(identify,all_cells))==sorted(map(identify,full))
    assert len({identify(r)[0] for r in all_cells})==len(all_cells)
    assert sum(r['count'] for r in full)>first['grand_total']['count']
    direct=pivot.cells(con,'run',PivotRequest(rows=[],columns=layout['columns'],filters=filters))['cells']
    assert sorted(map(identify,direct))==sorted(map(identify,first['column_totals']))
    for total in first['column_totals']+[first['grand_total']]:
        args=pivot.decode(total['cell_token'],'run')
        assert pivot.apps(con,args)['total']==total['count']

def test_report_empty_page_and_filter_have_explicit_totals(con):
    r=pivot.cells(con,'run',PivotRequest(rows=['PATH'],columns=['DIFF_FLAG','SOURCE'],page=999,page_size=10,include_totals=True))
    assert r['cells']==[] and r['grand_total']['count']==3
    r=pivot.cells(con,'run',PivotRequest(rows=['PATH'],columns=['SOURCE'],filters={'product_id':['absent']},page_size=10))
    assert r['cells']==[] and r['grand_total']['count']==0 and r['pagination']['total_rows']==0

def test_report_bucket_pages_do_not_split_pair_groups(con):
    r=pivot.cells(con,'run',PivotRequest(rows=['ADJUSTED_BEFORE'],columns=['ADJUSTED_AFTER'],filters={'PATH':['score']},page_size=1))
    assert r['pagination']['total_rows']==2
    assert r['cells'][0]['count']==2 and r['grand_total']['count']==3
    assert r['column_totals'][0]['count']==3

def test_report_rejects_too_many_columns(con):
    first=dict(zip([r[0] for r in con.execute('SELECT * FROM pivot_facts LIMIT 1').description],con.fetchone()))
    start=con.execute('SELECT max(fact_id) FROM pivot_facts').fetchone()[0]
    write(con,'pivot_facts',({**first,'fact_id':start+i+1,'VALUE_ADJUSTED':f'value-{i}'} for i in range(129)))
    write(con,'fact_memberships',({'fact_id':start+i+1,'APP_ID':'X'} for i in range(129)))
    with pytest.raises(ValueError,match='128'):
        pivot.cells(con,'run',PivotRequest(rows=['PATH'],columns=['VALUE_ADJUSTED'],page_size=10))
