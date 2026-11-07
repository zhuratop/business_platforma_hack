import duckdb
import pytest

from scripts.default_spr.bureau_scores import approved_bureau_scores


def tables(con):
    con.execute('CREATE TABLE app_segments(APP_ID VARCHAR,DECISION_BEFORE VARCHAR,DECISION_AFTER VARCHAR)')
    con.execute('CREATE TABLE normalized_union(APP_ID VARCHAR,SOURCE VARCHAR,ARRAY_KEY VARCHAR,PATH VARCHAR,VALUE VARCHAR,VALUE_KIND VARCHAR)')


def test_approved_means_differ_from_fixed_paired_cohort_and_zero_is_valid():
    with duckdb.connect() as con:
        tables(con)
        con.executemany('INSERT INTO app_segments VALUES (?,?,?)', [('a','APPROVE','APPROVE'),('b','APPROVE','REJECT'),('c','REJECT','APPROVE'),('d','APPROVE','APPROVE')])
        for app,before,after in [('a',100,130),('b',200,500),('c',900,300),('d',0,10)]:
            con.executemany("INSERT INTO normalized_union VALUES (?,?,'','characteristics.score_equ',?,'number')", [(app,'BEFORE',str(before)),(app,'AFTER',str(after))])
        con.execute("INSERT INTO normalized_union VALUES ('a','BEFORE','product','characteristics.score_equ','10000','number')")
        result=approved_bureau_scores(con,{'bootstrap':100})
    score=result['score_equ']
    assert score['before']=={'mean':100.,'n':3,'approved_total':3,'missing':0}
    assert score['after']['mean']==pytest.approx(440/3)
    assert score['delta']==pytest.approx(440/3-100)
    assert score['paired']['n']==2 and score['paired']['delta']==20
    assert score['paired']['before']==50 and score['paired']['after']==70
    assert score['paired']['ci']==pytest.approx([10,30])
    assert result['score_okb']['before']['mean'] is None
    assert result['score_okb']['paired']['ci'] is None


def test_null_boolean_string_missing_and_nonfinite_are_not_scores():
    with duckdb.connect() as con:
        tables(con)
        for i,(value,kind) in enumerate([('null','null'),('false','boolean'),('500','string'),('NaN','number'),('Infinity','number')]):
            con.execute("INSERT INTO app_segments VALUES (?,'APPROVE','APPROVE')",[str(i)])
            con.execute("INSERT INTO normalized_union VALUES (?,'BEFORE','','characteristics.score_okb',?,?)",[str(i),value,kind])
        score=approved_bureau_scores(con,{'bootstrap':100})['score_okb']
    assert score['before']['n']==0 and score['before']['missing']==5
    assert score['after']['n']==0 and score['after']['missing']==5
    assert score['delta'] is None and score['paired']['n']==0
    assert score['paired']['missing']==5 and score['paired']['ci'] is None
