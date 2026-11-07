"""Presentation baselines; stored paired differences and intervals stay immutable."""
from scripts.default_spr.stat_labels import named_families


def binary_baseline(stat):
    n = stat.get('n', 0)
    return {key: stat[key] / n if n else None for key in ['before', 'after']}


def display_stats(con, stats):
    result = named_families(con, stats)
    result['app_approval_rate'] = {**stats['app_approval_rate'], 'baseline': binary_baseline(stats['app_approval_rate'])}
    # Average matched products within APP_ID first, so each application has equal weight.
    before, after = con.execute("""SELECT avg(b),avg(a) FROM (
        SELECT avg(b.target_score) AS b,avg(a.target_score) AS a
        FROM product_trials b JOIN product_trials a
        ON b.APP_ID=a.APP_ID AND b.product_id=a.product_id AND b.pd_model=a.pd_model
        AND b.target_score_type=a.target_score_type
        WHERE b.SOURCE='BEFORE' AND a.SOURCE='AFTER'
        AND b.target_score IS NOT NULL AND a.target_score IS NOT NULL
        AND b.target_score_type='APPROVAL_PROBABILITY'
        GROUP BY b.APP_ID)""").fetchone()
    result['target_score'] = {**stats['target_score'], 'baseline': {'before': before, 'after': after}}
    result['strata'] = {}
    if 'external_unchanged' in stats.get('strata', {}):
        row = stats['strata']['external_unchanged']
        result['strata']['external_unchanged'] = {**row, 'baseline': binary_baseline(row)}
    return result
