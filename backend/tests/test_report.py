import duckdb

from backend.app.core.report import render, strategy_data


def test_report_keeps_distinct_counts_escapes_values_and_displays_statistics():
    with duckdb.connect() as con:
        con.execute('CREATE TABLE pivot_facts(fact_id INTEGER,PREFIX VARCHAR,CLASS VARCHAR,SUFFIX VARCHAR,ARRAY_KEY VARCHAR,KEY VARCHAR,VALUE_ADJUSTED VARCHAR,DIFF_FLAG INTEGER,SOURCE VARCHAR,PATH VARCHAR)')
        con.execute('CREATE TABLE fact_memberships(fact_id INTEGER,APP_ID VARCHAR)')
        con.execute('CREATE TABLE normalized_union(APP_ID VARCHAR,SOURCE VARCHAR,ARRAY_KEY VARCHAR,PATH VARCHAR,VALUE VARCHAR,VALUE_KIND VARCHAR)')
        con.execute('CREATE TABLE app_segments(APP_ID VARCHAR,DECISION_BEFORE VARCHAR,DECISION_AFTER VARCHAR,SCORE_OKB_BEFORE VARCHAR,SCORE_OKB_AFTER VARCHAR)')
        con.execute("INSERT INTO app_segments VALUES ('app1','APPROVE','REJECT','100','100')")
        con.execute('CREATE TABLE product_trials(APP_ID VARCHAR,SOURCE VARCHAR,product_id VARCHAR,pd_model VARCHAR,target_score_type VARCHAR,target_score DOUBLE)')
        for fact_id in [1, 2]:
            con.execute("INSERT INTO pivot_facts VALUES (?, 'decisionResult','','','','decision',?,1,'BEFORE','decisionResult.decision')", [fact_id, '<script>alert(1)</script>'])
            con.execute("INSERT INTO fact_memberships VALUES (?,'app1')", [fact_id])
        dims, cells, totals, n = strategy_data(con)
        assert len(cells) == 1 and cells[0][-1] == 1
        assert totals[(1, 'BEFORE')] == 1 and n == 1
        binary = dict(n=1, before=1, after=0, delta=-1, ci=[-1, -1], p=1.234567e-16)
        stats = dict(app_approval_rate=binary, approved_products={**binary, 'delta': -.123456}, target_score=binary, families={}, strata={}, alpha=.05, bootstrap=100, seed=42)
        content = render({'id': 'test', 'created': 'now'}, {'total_apps': 1}, stats, [], con)
    assert '<script>' not in content
    assert '&lt;script&gt;' in content
    assert '1.235e-16' in content
    assert '-100 п.п.' in content and '-0.1235' in content
    assert 'BEFORE <b>100%</b>' in content and 'AFTER <b>0%</b>' in content
    assert 'Медиана' not in content and 'Оценка готовности' not in content
    assert '<pre>' not in content and 'strategy-table' in content
    assert '<link' not in content  # Styling is embedded; no external dependencies.
