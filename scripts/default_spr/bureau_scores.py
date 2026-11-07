"""Approved-population means and fixed-cohort paired bureau-score diagnostics."""
import math

from backend.app.stats.paired import interval
from backend.app.stats.overlap_t import overlapping_ttest


FIELDS = ['score_equ', 'score_okb']


def approved_bureau_scores(con, params):
    segments = {app: (before, after) for app, before, after in con.execute(
        'SELECT APP_ID,DECISION_BEFORE,DECISION_AFTER FROM app_segments').fetchall()}
    values = {}
    for app, source, path, raw, kind in con.execute('''SELECT APP_ID,SOURCE,PATH,VALUE,VALUE_KIND
            FROM normalized_union WHERE PATH IN ('characteristics.score_equ','characteristics.score_okb')
            AND ARRAY_KEY='' ''').fetchall():
        if kind != 'number':
            continue
        try:
            value = float(raw)
        except (ValueError, TypeError):
            continue
        if math.isfinite(value):
            values[(app, source, path.rsplit('.', 1)[-1])] = value
    result = {}
    for field in FIELDS:
        slices = {}
        score_maps = {}
        for index, source in enumerate(['BEFORE', 'AFTER']):
            approved = [app for app, decisions in segments.items() if decisions[index] == 'APPROVE']
            score_maps[source] = {app:values[(app,source,field)] for app in approved if (app,source,field) in values}
            scores = list(score_maps[source].values())
            slices[source] = dict(mean=sum(scores) / len(scores) if scores else None,
                                  n=len(scores), approved_total=len(approved), missing=len(approved) - len(scores))
        both = [app for app, decisions in segments.items() if decisions == ('APPROVE', 'APPROVE')]
        pairs = [(values[(app, 'BEFORE', field)], values[(app, 'AFTER', field)]) for app in sorted(both)
                 if (app, 'BEFORE', field) in values and (app, 'AFTER', field) in values]
        deltas = [after - before for before, after in pairs]
        before, after = slices['BEFORE']['mean'], slices['AFTER']['mean']
        result[field] = dict(before=slices['BEFORE'], after=slices['AFTER'],
            t_test=overlapping_ttest(score_maps['BEFORE'],score_maps['AFTER'],params.get('alpha',.05)),
            delta=after - before if before is not None and after is not None else None,
            paired=dict(n=len(pairs), approved_both_total=len(both), missing=len(both) - len(pairs),
                before=sum(b for b, _ in pairs) / len(pairs) if pairs else None,
                after=sum(a for _, a in pairs) / len(pairs) if pairs else None,
                delta=sum(deltas) / len(deltas) if deltas else None, ci=interval(deltas, params),
                information='insufficient' if len(pairs) < 30 else 'available'), unit='bureau_score_points')
    tests = sorted([r['t_test'] for r in result.values() if r['t_test']['p'] is not None],key=lambda r:r['p'])
    previous = 0.
    for index,test in enumerate(tests):
        # The predeclared family is both bureau scores, even if one is unavailable.
        previous = min(1.,max(previous,test['p']*(len(FIELDS)-index)))
        test.update(p_adjusted=previous,significant=previous < test['alpha'])
    return result
