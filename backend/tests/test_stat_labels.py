from copy import deepcopy

import duckdb

from scripts.default_spr.stat_labels import named_families


def test_names_follow_array_key_and_snapshot_without_changing_statistics():
    with duckdb.connect() as con:
        con.execute('CREATE TABLE normalized_union(APP_ID VARCHAR,SOURCE VARCHAR,ARRAY_KEY VARCHAR,PATH VARCHAR,VALUE VARCHAR,VALUE_KIND VARCHAR)')
        rows = []
        for source, key, product, name, partner, partner_name in [
            ('BEFORE', 'p1', '1', 'First', '10', 'Partner A'),
            ('AFTER', 'p1', '1', 'First renamed', '10', 'Partner A'),
            ('AFTER', 'p2', '2', 'Second', '20', 'Partner B'),
        ]:
            for field, value in [('product_id', product), ('product_name', name), ('partner_id', partner), ('partner_name', partner_name)]:
                rows.append(('app', source, key, 'decisionResult.product_trials.' + field, value, 'string'))
        con.executemany('INSERT INTO normalized_union VALUES (?,?,?,?,?,?)', rows)
        stats = {'families': {'products': [{'group': '1', 'delta': -.12}, {'group': '2'}, {'group': 'unknown'}], 'partners': [{'group': '10'}, {'group': '20'}]}, 'alpha': .05}
        original = deepcopy(stats)
        result = named_families(con, stats)
    assert stats == original
    products = result['families']['products']
    assert products[0]['group_name'] == 'First / First renamed'
    assert products[0]['delta'] == -.12
    assert products[1]['group_name'] == 'Second'
    assert products[2]['name_available'] is False
    assert 'unknown' in products[2]['group_name']
    assert [r['group_name'] for r in result['families']['partners']] == ['Partner A', 'Partner B']
