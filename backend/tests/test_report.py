import duckdb

from backend.app.core.report import render,tree_data
from backend.app.core.normalize import flatten,compare_rows
from backend.app.storage.mart import initialize,write


def test_report_full_tree_unique_counts_typed_values_checks_and_escaping():
    with duckdb.connect() as con:
        initialize(con)
        response={'offers':[{'product_id':1,'type':'a'},{'product_id':1,'type':'b'}],
                  'null':None,'empty':'','flag':False,'text':'<script>alert(1)</script>'}
        params={'arrays':{'offers':{'mode':'fields','keys':['product_id','type']}}}
        for source in ['BEFORE','AFTER']:
            write(con,'normalized_union',flatten({**response,'flag':source=='AFTER'},'A',source,params))
            write(con,'normalized_union',flatten({'null':'NULL'},'B',source,{}))
        write(con,'comparison_mart',compare_rows(list(flatten(response,'A','BEFORE',params)),list(flatten({**response,'flag':True},'A','AFTER',params)),{}))
        write(con,'comparison_mart',compare_rows(list(flatten({'null':'NULL'},'B','BEFORE',{})),list(flatten({'null':'NULL'},'B','AFTER',{})),{}))
        roots,totals=tree_data(con)
        assert totals==(2,2,2,2,1,2,1)
        offers=next(n for n in roots if n['path']=='offers')
        assert offers['counts']==[1,1,1,1,0,1,0]
        product=next(n for n in offers['children'] if n['path']=='offers.product_id')
        assert len(product['children'])==2  # composite keys remain separate
        null=next(n for n in roots if n['path']=='null')
        assert {(n['label'],n['value_kind']) for n in null['children']}=={('null','null'),('"NULL"','string')}
        checks=[dict(LABEL='<img src=x onerror=alert(1)>',ARGUMENT='product',SOURCE='AFTER',CNT=5,TOTAL=10,
                     METRIC=.2347,APP_IDS=['<app>'],RESULT='FAIL',CONFIDENCE='LOW',
                     threshold={'value':.1,'parameter':'max_drop_rel','operator':'>'})]
        content=render({'id':'test','created':'now'},{'total_apps':2,'changed_apps':1},{},checks,con)
    assert '<script>alert' not in content and '&lt;script&gt;' in content
    assert '<img src=x' not in content and '&lt;img' in content and '&lt;app&gt;' in content
    assert '23.5%' in content and '10.0%' in content
    assert 'FAIL' in content and 'LOW' in content and 'список неполный' in content
    assert 'id="pivot"' in content and 'id="checks"' in content
    assert 'id="statistics"' not in content and 'id="comparability"' not in content
    assert 'strategy-table' not in content and 'attribute-table' in content
    header=content.split('<thead>',1)[1].split('</thead>',1)[0]
    assert header.count('DIFF_FLAG = 0')==2 and header.count('DIFF_FLAG = 1')==2
    assert '<link' not in content and 'fetch(' not in content


def test_report_handles_empty_tables_and_no_checks():
    with duckdb.connect() as con:
        initialize(con)
        content=render({'id':'empty','created':'now'},{'total_apps':0,'changed_apps':0},{},[],con)
    assert 'Нет атрибутов для отображения' in content
    assert 'Для этого прогона нет результатов проверок' in content
