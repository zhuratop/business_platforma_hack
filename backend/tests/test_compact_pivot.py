import duckdb

from backend.app.core import pivot
from backend.app.domain.contracts import PivotRequest
from backend.app.storage import meta


def test_compact_cells_totals_and_drilldown_union_app_ids(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    with duckdb.connect() as con:
        con.execute('CREATE TABLE pivot_facts(fact_id INTEGER,PATH VARCHAR,VALUE_ADJUSTED VARCHAR,DIFF_FLAG INTEGER,SOURCE VARCHAR)')
        con.execute('CREATE TABLE fact_memberships(fact_id INTEGER,APP_ID VARCHAR)')
        for id,flag,source in [(1,0,'BEFORE'),(2,0,'AFTER'),(3,1,'BEFORE'),(4,1,'AFTER')]:
            con.execute("INSERT INTO pivot_facts VALUES (?,'score','one bucket',?,?)",[id,flag,source])
            con.execute("INSERT INTO fact_memberships VALUES (?,'a')",[id])
        con.execute("INSERT INTO pivot_facts VALUES (5,'other','value',1,'AFTER')")
        con.execute("INSERT INTO fact_memberships VALUES (5,'b')")
        request=PivotRequest(rows=['PATH','VALUE_ADJUSTED'],columns=['DIFF_FLAG','SOURCE'],include_totals=True,collapse_unchanged=True,page_size=10)
        data=pivot.cells(con,'test',request)
        total=next(c for c in data['row_totals'] if c['dimensions']['PATH']=='score')
        stable=next(c for c in data['unchanged_cells'] if c['dimensions']['PATH']=='score')
        assert total['count']==stable['count']==1  # Not a sum of four source/flag cells.
        assert data['unchanged_total']['count']==1 and data['grand_total']['count']==2
        for cell in [total,stable,data['grand_total'],data['unchanged_total']]:
            assert pivot.apps(con,pivot.decode(cell['cell_token'],'test'))['total']==cell['count']
        request.page_size=1
        page=pivot.cells(con,'test',request)
        assert len(page['row_totals'])==len(page['unchanged_cells'])==1
        assert page['pagination']['total_rows']==2 and page['grand_total']['count']==2
