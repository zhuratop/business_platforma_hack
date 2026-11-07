"""User check with an explicit change-share tolerance.

30% is a demonstration setting for experiments, not a production release criterion.
The five supplied checks keep their original code and independent verdicts.
"""
DEFAULTS = {'max_share': 0.30, 'app_ids_limit': 20}


def run(mart, params=None):
    p = {**DEFAULTS, **(params or {})}
    limit = p['max_share']
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not 0 <= limit <= 1:
        raise ValueError('max_share must be a number between 0 and 1')
    total = mart.total_apps()
    apps = sorted(set(mart.app_ids(diff_flag=1)))
    share = len(apps) / total if total else 0.0
    return [{
        'LABEL': CHECK['label'], 'SOURCE': 'AFTER',
        'ARGUMENT': 'Доля заявок с любыми изменениями' if total else 'Нет заявок для проверки',
        'CNT': len(apps), 'TOTAL': total, 'METRIC': round(share, 4),
        'APP_IDS': apps[:p['app_ids_limit']],
        'RESULT': 'PASS' if total and share <= limit else 'FAIL',
        'CONFIDENCE': 'HIGH' if total >= 30 else 'LOW',
    }]


CHECK = {'id': 'my_changes', 'label': 'Доля изменений в пределах порога',
         'params': DEFAULTS, 'threshold': {'parameter': 'max_share', 'operator': '>'},
         'entrypoint': run}
