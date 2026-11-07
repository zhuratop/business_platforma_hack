"""Read-only aggregates for charts; applications, never product attempts, are counted."""
import math


def chart_data(con):
    total = con.execute('SELECT count(DISTINCT APP_ID) FROM app_segments').fetchone()[0]
    transitions = [dict(before=b, after=a, count=n, share=n / total if total else None)
                   for b, a, n in con.execute('''SELECT DECISION_BEFORE,DECISION_AFTER,
                       count(DISTINCT APP_ID) FROM app_segments GROUP BY ALL ORDER BY ALL''').fetchall()]
    lost = sum(r['count'] for r in transitions if r['before'] == 'APPROVE' and r['after'] != 'APPROVE')
    gained = sum(r['count'] for r in transitions if r['before'] != 'APPROVE' and r['after'] == 'APPROVE')
    # Exactly one observation per APP_ID, averaging only its matched products.
    pairs = con.execute('''SELECT b.APP_ID,avg(b.target_score),avg(a.target_score),
        bool_and(isfinite(b.target_score) AND isfinite(a.target_score)
            AND b.target_score BETWEEN 0 AND 1 AND a.target_score BETWEEN 0 AND 1)
        FROM product_trials b JOIN product_trials a
        ON b.APP_ID=a.APP_ID AND b.product_id=a.product_id AND b.pd_model=a.pd_model
        AND b.target_score_type=a.target_score_type
        WHERE b.SOURCE='BEFORE' AND a.SOURCE='AFTER'
        AND b.pd_model IS NOT NULL AND b.pd_model<>''
        AND b.target_score IS NOT NULL AND a.target_score IS NOT NULL
        AND b.target_score_type='APPROVAL_PROBABILITY'
        GROUP BY b.APP_ID ORDER BY b.APP_ID''').fetchall()
    valid = [(b, a) for _, b, a, ok in pairs if ok and math.isfinite(b) and math.isfinite(a)]
    n = len(valid)
    bins = [dict(lower=i / 10, upper=(i + 1) / 10, before=0, after=0) for i in range(10)]
    for before, after in valid:
        for source, value in [('before', before), ('after', after)]:
            bins[min(9, int(value * 10))][source] += 1
    for bin in bins:
        bin.update(before_share=bin['before'] / n if n else None, after_share=bin['after'] / n if n else None)
    return dict(total_apps=total, transitions=transitions,
                approvals=dict(lost=lost, gained=gained, net=gained - lost),
                probability=dict(n=n, total_apps=total, no_matched_score=total - len(pairs),
                    invalid_score=len(pairs) - n, bins=bins,
                    mean_before=sum(b for b, _ in valid) / n if n else None,
                    mean_after=sum(a for _, a in valid) / n if n else None,
                    unit='one APP_ID: mean of matched product APPROVAL_PROBABILITY scores'))
