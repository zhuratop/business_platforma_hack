import duckdb
import pytest

from scripts.default_spr.stat_charts import chart_data


def test_charts_keep_one_application_and_match_product_model_and_type():
    with duckdb.connect() as con:
        con.execute('CREATE TABLE app_segments(APP_ID VARCHAR,DECISION_BEFORE VARCHAR,DECISION_AFTER VARCHAR)')
        con.executemany('INSERT INTO app_segments VALUES (?,?,?)', [('a','APPROVE','REJECT'),('a','APPROVE','REJECT'),('b','REJECT','APPROVE'),('c','REJECT','REJECT'),('d',None,None)])
        con.execute('CREATE TABLE product_trials(APP_ID VARCHAR,SOURCE VARCHAR,product_id VARCHAR,pd_model VARCHAR,target_score_type VARCHAR,target_score DOUBLE)')
        for app, product, before, after, bm, am, bt, at in [
            ('a','p1',0,.2,'m','m','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
            ('a','p2',1,.4,'m','m','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
            ('b','p1',.1,1,'m','m','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
            ('a','mismatch-model',.9,.8,'old','new','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
            ('a','mismatch-type',.9,.8,'m','m','APPROVAL_PROBABILITY','OTHER'),
            ('c','bad',1.2,.5,'m','m','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
            ('c','good',0,0,'m','m','APPROVAL_PROBABILITY','APPROVAL_PROBABILITY'),
        ]:
            con.executemany('INSERT INTO product_trials VALUES (?,?,?,?,?,?)', [(app,'BEFORE',product,bm,bt,before),(app,'AFTER',product,am,at,after)])
        result = chart_data(con)
    assert result['total_apps'] == 4
    assert sum(r['count'] for r in result['transitions']) == 4
    assert sum(r['share'] for r in result['transitions']) == 1
    assert result['approvals'] == {'lost':1,'gained':1,'net':0}
    score = result['probability']
    assert score['n'] == 2 and score['invalid_score'] == 1 and score['no_matched_score'] == 1
    assert score['mean_before'] == pytest.approx(.3)
    assert score['mean_after'] == pytest.approx(.65)
    assert sum(b['before'] for b in score['bins']) == sum(b['after'] for b in score['bins']) == 2
    assert sum(b['before_share'] for b in score['bins']) == sum(b['after_share'] for b in score['bins']) == 1
    assert score['bins'][5]['before'] == 1  # First application's two products averaged.
    assert score['bins'][9]['after'] == 1  # Upper endpoint 1 belongs to the last bin.


def test_empty_chart_data_has_no_fake_zero_percentages():
    with duckdb.connect() as con:
        con.execute('CREATE TABLE app_segments(APP_ID VARCHAR,DECISION_BEFORE VARCHAR,DECISION_AFTER VARCHAR)')
        con.execute('CREATE TABLE product_trials(APP_ID VARCHAR,SOURCE VARCHAR,product_id VARCHAR,pd_model VARCHAR,target_score_type VARCHAR,target_score DOUBLE)')
        result = chart_data(con)
    assert result['total_apps'] == 0 and result['transitions'] == []
    assert result['probability']['n'] == 0
    assert result['probability']['mean_before'] is None
    assert all(b['before_share'] is None and b['after_share'] is None for b in result['probability']['bins'])
