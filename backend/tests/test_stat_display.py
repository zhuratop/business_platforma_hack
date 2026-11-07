from copy import deepcopy

import duckdb
import pytest

from scripts.default_spr.stat_display import binary_baseline, display_stats


def test_baseline_percent_and_absolute_difference_preserve_paired_statistics():
    binary = dict(n=100, before=50, after=40, delta=-.1, ci=[-.15, -.05])
    assert binary_baseline(binary) == {'before': .5, 'after': .4}
    assert binary_baseline(dict(n=1, before=0, after=1)) == {'before': 0, 'after': 1}
    assert binary_baseline(dict(n=0, before=0, after=0)) == {'before': None, 'after': None}
    stats = dict(app_approval_rate=binary, target_score=dict(n=2, delta=0, ci=[-.1, .1]), families={}, strata={'external_unchanged': binary, 'target_model_unchanged': binary})
    original = deepcopy(stats)
    with duckdb.connect() as con:
        con.execute('CREATE TABLE normalized_union(APP_ID VARCHAR,SOURCE VARCHAR,ARRAY_KEY VARCHAR,PATH VARCHAR,VALUE VARCHAR,VALUE_KIND VARCHAR)')
        con.execute('CREATE TABLE product_trials(APP_ID VARCHAR,SOURCE VARCHAR,product_id VARCHAR,pd_model VARCHAR,target_score_type VARCHAR,target_score DOUBLE)')
        for app, product, before, after in [('app1', 'p1', .2, .3), ('app1', 'p2', .4, .5), ('app2', 'p1', .8, .7)]:
            for source, value in [('BEFORE', before), ('AFTER', after)]:
                con.execute("INSERT INTO product_trials VALUES (?,?,?,'model','APPROVAL_PROBABILITY',?)", [app, source, product, value])
        result = display_stats(con, stats)
    assert stats == original
    assert result['app_approval_rate']['delta'] == -.1
    assert result['app_approval_rate']['ci'] == [-.15, -.05]
    assert result['target_score']['baseline'] == pytest.approx({'before': .55, 'after': .55})
    assert result['strata']['external_unchanged']['baseline'] == {'before': .5, 'after': .4}
    assert 'target_model_unchanged' not in result['strata']
    assert 'relative' not in result['app_approval_rate']
