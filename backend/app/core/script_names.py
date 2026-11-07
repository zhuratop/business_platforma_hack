"""Readable procedure labels; inspect CHECK metadata without executing user code."""
import ast
from collections import defaultdict
import hashlib
import re
from backend.app.core.check_display import static_definition


CHECK_NAMES = {
    'ar_drop_by_product': ('Падение одобрения заявок по продуктам', 'Сравнивает итоговое одобрение заявок с данным продуктом с допустимым снижением.'),
    'attribute_new_loss': ('Появление и исчезновение атрибутов', 'Находит поля, которые появились или исчезли между BEFORE и AFTER.'),
    'external_score_drift': ('Изменение внешнего скора и входных данных', 'Сопоставляет изменение внешнего скора, входных признаков и итогового решения.'),
    'stop_factor_disappeared': ('Исчезновение или отключение стоп-факторов', 'Показывает исчезнувшие правила и переход сработавшего стоп-фактора в несработавший.'),
    'target_model_changed': ('Смена целевой модели и порога', 'Показывает смену целевой модели и сопутствующее изменение порога.'),
    'my_changes': ('Доля изменений в пределах порога', 'Сравнивает долю изменённых заявок с параметром max_share.'),
}


def check_metadata(code):
    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError):
        return {}
    result = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(isinstance(t, ast.Name) and t.id == 'CHECK' for t in node.targets) or not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value in ['id','label'] and isinstance(value, ast.Constant) and isinstance(value.value,str):
                result[key.value] = value.value
    return result


def named_scripts(scripts):
    result = []
    duplicates = defaultdict(list)
    for script in scripts:
        row = dict(script)
        if row.get('kind') == 'check':
            metadata = check_metadata(row.get('code',''))
            row['check_id'] = metadata.get('id')
            generic = bool(re.match(r'^Моя проверка(?:\b|\.)',row.get('name',''),re.I))
            known = CHECK_NAMES.get(metadata.get('id'))
            share_variant = bool(re.fullmatch(r'my_changes(?:_[a-zA-Z0-9_]+)?',metadata.get('id') or ''))
            if share_variant:
                defaults=static_definition(row.get('code','')).get('params',{})
                limit=row.get('params',{}).get('max_share',defaults.get('max_share',.3))
                percentage=f'{limit*100:g}' if type(limit) in (int,float) and 0<=limit<=1 else '—'
                label=f'Доля изменений в пределах порога · {percentage}%'
                if not generic and not row.get('name','').startswith(('Доля изменений','check_')):
                    label=row.get('name') or label
                description=f'Сравнивает долю изменённых заявок с параметром max_share. {percentage}% — предел.'
            elif known and (generic or row.get('name','').startswith('check_')):
                label, description = known
            else:
                label = metadata.get('label') if generic else row.get('name')
                label = label or row.get('name') or 'Пользовательская проверка'
                description = 'Пользовательская проверка. Откройте код, чтобы посмотреть условие и параметры.'
            row.update(display_name=label,description=description)
            if generic and not share_variant:
                duplicates[(label,hashlib.sha256(row.get('code','').encode()).hexdigest())].append(row)
        result.append(row)
    for group in duplicates.values():
        if len(group)>1:
            for index,row in enumerate(sorted(group,key=lambda r:(r.get('created',''),r['id'])),1):
                row['display_name'] += f' · копия {index}'
                row['description'] += f' Одинаковая логика: копия {index} из {len(group)}.'
    return result
