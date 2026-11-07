"""Ordered dependencies and public checkpoint contracts."""
STAGES = ['READING', 'NORMALIZING', 'COMPARING', 'FACTS', 'CHECKS', 'STATS', 'REPORTING']
LABELS = dict(zip(STAGES, ['Чтение данных', 'Нормализация', 'Сравнение', 'Факты и разрезы', 'Автопроверки', 'Статистика', 'HTML-отчёт']))
TABLES = {
    'READING': ['raw_inputs'],
    'NORMALIZING': ['raw_inputs', 'normalized_union'],
    'COMPARING': ['raw_inputs', 'normalized_union', 'comparison_mart'],
    'FACTS': ['raw_inputs', 'normalized_union', 'comparison_mart', 'app_segments', 'product_trials', 'offers', 'pivot_facts'],
}


def stop_stage(value):
    if value not in STAGES:
        raise ValueError('Неизвестный этап остановки')
    return value


def checkpoint_tables(stage):
    tables = list(TABLES.get(stage, TABLES['FACTS']))
    if stage in ['CHECKS','STATS','REPORTING']:
        tables.append('checks')
    if stage in ['STATS','REPORTING']:
        tables.append('stats')
    return tables
