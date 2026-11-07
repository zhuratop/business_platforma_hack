"""Standalone statistics and strategy pivot, using the same facts as the UI."""
import html
import math
from pathlib import Path

import duckdb

from backend.app.core.pivot import relation, where
from backend.app.storage import meta
from scripts.default_spr.pivot_views import VIEWS
from scripts.default_spr.stat_display import display_stats


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return '—'
    return f'{value:.4f}'.rstrip('0').rstrip('.') if value else '0'


def percent(value):
    return number(value * 100) + '%' if isinstance(value, (int, float)) and math.isfinite(value) else '—'


def points(value):
    return number(value * 100) + ' п.п.' if isinstance(value, (int, float)) and math.isfinite(value) else '—'


def pvalue(value):
    return f'{value:.3e}' if isinstance(value, (int, float)) and 0 < value < .0001 else number(value)


def interval(values, percentage=True):
    return ' … '.join((points if percentage else number)(v) for v in values) if values and len(values) == 2 else '—'


def strategy_data(con):
    """Unpaginated strategy preset; count distinct APP_ID, never sum facts."""
    view = next(v for v in VIEWS if v['id'] == 'strategy')
    dimensions = view['rows'] + view['columns']
    columns = ','.join('f."' + d + '"' for d in dimensions)
    clause, args = where(view['filters'])
    prefix = relation(dimensions + list(view['filters']))
    rows = con.execute(prefix + 'SELECT ' + columns + ',count(DISTINCT f.APP_ID) FROM scoped f' + clause + ' GROUP BY ' + columns + ' ORDER BY ' + columns, args).fetchall()
    totals = con.execute(prefix + 'SELECT f.DIFF_FLAG,f.SOURCE,count(DISTINCT f.APP_ID) FROM scoped f' + clause + ' GROUP BY f.DIFF_FLAG,f.SOURCE', args).fetchall()
    unique = con.execute(prefix + 'SELECT count(DISTINCT f.APP_ID) FROM scoped f' + clause, args).fetchone()[0]
    return view['rows'], rows, {(flag, source): count for flag, source, count in totals}, unique


def stat_card(title, stat, confidence, percentage=True):
    fmt = points if percentage else number
    baseline_fmt = percent if percentage else number
    baseline = stat.get('baseline', {}) if percentage else stat
    before_after = ''
    if baseline.get('before') is not None and baseline.get('after') is not None:
        before_after = f'<div class="before-after">BEFORE <b>{baseline_fmt(baseline["before"])}</b><span>→</span>AFTER <b>{baseline_fmt(baseline["after"])}</b></div>'
    details = f'Пар заявок: {number(stat.get("n"))}'
    if 'p' in stat:
        details += ' · p-value: ' + pvalue(stat['p'])
    if 'lost' in stat:
        details += f'<br>Потеряно одобрений: {number(stat["lost"])} · новых: {number(stat["gained"])}'
    if stat.get('information') == 'insufficient':
        details += '<br>Недостаточно информации для вывода'
    return f'<article class="metric"><h3>{esc(title)}</h3><div class="delta">{fmt(stat.get("delta"))}</div><div class="unit">{"Изменение AFTER − BEFORE" if percentage else "продукта / заявку"}</div><p>CI {confidence}% <strong>{interval(stat.get("ci"), percentage)}</strong></p>{before_after}<small>{details}</small></article>'


def bureau_card(field, stat):
    title = 'Средний скор Эквифакс у одобренных' if field == 'score_equ' else 'Средний скор ОКБ у одобренных'
    test = stat['t_test']
    if test['status'] == 'available':
        status = 'различие статистически значимо' if test['significant'] else 'статистическая значимость не выявлена'
        significance = f'<p><strong>T-тест: {status}</strong></p><small>p-value (Холм) = {pvalue(test["p_adjusted"])} · α = {number(test["alpha"])}</small>'
    else:
        significance = '<p><strong>T-тест: недоступно</strong></p><small>Недостаточно наблюдений или разброса для расчёта.</small>'
    return f'''<article class="metric" data-bureau="{field}"><h3>{title}</h3><small>{field} · баллы бюро</small>
        <div class="before-after">BEFORE <b>{number(stat['before']['mean'])}</b><span>→</span>AFTER <b>{number(stat['after']['mean'])}</b></div>
        <p>Разница средних одобренных: <strong>{number(stat['delta'])} балла</strong></p>
        <small>Со скором BEFORE: {number(stat['before']['n'])} / {number(stat['before']['approved_total'])} одобренных; без скора {number(stat['before']['missing'])}.<br>
        Со скором AFTER: {number(stat['after']['n'])} / {number(stat['after']['approved_total'])} одобренных; без скора {number(stat['after']['missing'])}.</small>
        {significance}</article>'''


def family_table(rows, confidence):
    title = 'Продукты (компании)'
    body = []
    for row in rows:
        n = row['n']
        name = esc(row['group_name'])
        if not row['name_available']:
            name += '<small>Название отсутствует в данных</small>'
        coverage = row.get('coverage', {})
        name += f'<small>Присутствует в срезах: {number(coverage.get("BEFORE", 0))} → {number(coverage.get("AFTER", 0))}</small>'
        if row.get('appeared', 0) or row.get('disappeared', 0):
            name += f'<small>Появились: {number(row.get("appeared", 0))} · исчезли: {number(row.get("disappeared", 0))}</small>'
        approval = lambda key: (percent(row[key] / n) if n else '—') + f'<small>{number(row[key])} / {number(n)}</small>'
        values = [name, number(n), approval('before'), approval('after'), points(row.get('delta')), interval(row.get('ci')), pvalue(row.get('p')) if n else '—', pvalue(row.get('p_adjusted')) if n else '—', 'Недостаточно' if row.get('information') == 'insufficient' else 'Достаточно']
        body.append('<tr>' + ''.join('<td>' + v + '</td>' for v in values) + '</tr>')
    headers = ['Продукт (компания)', 'Пар заявок', 'Одобрено BEFORE, %', 'Одобрено AFTER, %', 'Разница, п.п.', f'CI {confidence}%, п.п.', 'p-value', 'p Холма', 'Данные']
    return f'<h3>{title}</h3><div class="table-scroll"><table class="family-table"><thead><tr>{"".join("<th>"+esc(h)+"</th>" for h in headers)}</tr></thead><tbody>{"".join(body)}</tbody></table></div>' if rows else f'<h3>{title}</h3><p>Группы не заданы в конфигурации.</p>'


def pivot_table(con):
    from scripts.default_spr.pivot_views import STRATEGY_FIELDS
    view = next(v for v in VIEWS if v['id'] == 'strategy')
    clause, args = where(view['filters'])
    prefix = relation(view['rows'] + view['columns'] + list(view['filters']))
    measures = """count(DISTINCT f.APP_ID) FILTER(WHERE f.DIFF_FLAG=0),
        count(DISTINCT f.APP_ID) FILTER(WHERE f.DIFF_FLAG=1 AND f.SOURCE='BEFORE'),
        count(DISTINCT f.APP_ID) FILTER(WHERE f.DIFF_FLAG=1 AND f.SOURCE='AFTER'),
        count(DISTINCT f.APP_ID)"""
    rows = con.execute(prefix+'SELECT f.PATH,f.VALUE_ADJUSTED,'+measures+' FROM scoped f'+clause+' GROUP BY f.PATH,f.VALUE_ADJUSTED',args).fetchall()
    totals = con.execute(prefix+'SELECT '+measures+' FROM scoped f'+clause,args).fetchone()
    order = list(STRATEGY_FIELDS)
    rows.sort(key=lambda r:(order.index(r[0]),str(r[1])))
    body = []
    previous = None
    for path,value,*counts in rows:
        labels = ''
        if path != previous:
            field = STRATEGY_FIELDS[path]
            span = sum(r[0] == path for r in rows)
            labels = f'<td rowspan="{span}" title="{esc(path)}"><b>{esc(field["block"])}</b></td><td rowspan="{span}">{esc(field["key"])}</td>'
        previous = path
        numbers = ''.join(f'<td class="num {style}">{number(n) if n else "—"}</td>' for n,style in zip(counts,['stable','changed','changed','total']))
        body.append(f'<tr data-path="{esc(path)}" data-value="{esc(value)}">{labels}<td>{esc(value)}</td>{numbers}</tr>')
    foot = ''.join(f'<td class="num {style}">{number(n)}</td>' for n,style in zip(totals,['stable','changed','changed','total']))
    return f'''<div class="section-title"><div><h2>Стратегия · ключевые атрибуты</h2><p>Решения, причины отказа, вероятность одобрения, модель и порог.</p></div><span class="badge">{number(totals[-1])} уникальных заявок · {number(len(rows))} строк</span></div>
    <div class="table-scroll pivot-scroll"><table class="strategy-table"><thead><tr><th rowspan="2">Показатель</th><th rowspan="2">Поле (KEY)</th><th rowspan="2">Значение / бакет</th><th rowspan="2" class="stable">Без изменений<br>DIFF_FLAG = 0</th><th colspan="2" class="changed">Есть изменения · DIFF_FLAG = 1</th><th rowspan="2">Общий итог</th></tr><tr><th class="changed">BEFORE (MASTER)</th><th class="changed">AFTER (BETA)</th></tr></thead><tbody>{''.join(body)}</tbody><tfoot><tr><th colspan="3">Уникальных заявок в выборке</th>{foot}</tr></tfoot></table></div>
    <p class="note">Без изменений: заявка учтена один раз на оба среза. Общий итог — объединение APP_ID, не сумма колонок или строк. У заявки может быть несколько продуктов и значений. Изменения учтены по исходным значениям, даже внутри бакета. Все строки включены без пагинации. Лимиты и риск дефолта в этих данных недоступны.</p>'''


def render(run, summary, stats, checks, con=None, public_base_url=None):
    if con is None:
        with duckdb.connect(run['mart_path'], read_only=True) as connection:
            return render(run, summary, stats, checks, connection, public_base_url)
    stats = display_stats(con, stats)
    confidence = number((1 - stats.get('alpha', .05)) * 100)
    cards = ''.join(stat_card(title, stats[key], confidence, percentage) for title, key, percentage in [('Одобрение заявок', 'app_approval_rate', True), ('Одобрено продуктов на заявку', 'approved_products', False), ('Вероятность одобрения', 'target_score', True)])
    cards += '<div class="cards two" style="grid-column:1/-1;margin:0">' + ''.join(bureau_card(field, row) for field, row in stats['bureau_scores'].items()) + '</div><p class="note" style="grid-column:1/-1">Скоры Эквифакс и ОКБ и их изменения — в баллах соответствующего бюро. Чем выше скор, тем выше благонадёжность по оценке этого бюро. T-тест сравнивает средние всех одобренных в каждом срезе, учитывая общие APP_ID; p-value скорректированы по Холму для двух скоров. Разница может отражать отбор и изменение входных данных; значимость не доказывает причинность. Нулевой скор учитывается; отсутствие значения не заменяется нулём.</p>'
    families = family_table(stats.get('families', {}).get('products', []), confidence)
    titles = {'external_unchanged': 'Внешний скор не менялся'}
    strata = ''.join(stat_card(titles.get(key, key), value, confidence) for key, value in stats.get('strata', {}).items())
    back = esc((public_base_url or meta.PUBLIC_BASE_URL).rstrip('/') + '/?run=' + run['id'] + '&tab=pivot')
    css = Path(__file__).with_name('report.css').read_text(encoding='utf-8')
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>СПР · отчёт по прогону {esc(run['id'])}</title><style>{css}</style></head><body><main>
    <header><div class="eyebrow">Система анализа изменений СПР</div><h1>BEFORE (MASTER) → AFTER (BETA)</h1><p>Статистика парных наблюдений и ключевые атрибуты стратегии</p><div>Прогон {esc(run['id'])} · {esc(run['created'])} · {number(summary.get('total_apps'))} пар заявок</div><nav><a href="#statistics">Статистика</a><a href="#families">Продукты (компании)</a><a href="#strategy">Ключевые атрибуты</a><a href="{back}">Открыть интерактивную сводную</a></nav></header>
    <section id="statistics"><div class="section-title"><h2>Парное сравнение заявок</h2><span class="badge">Доверительный интервал {confidence}%</span></div><p>{esc(stats.get('interpretation', ''))}</p><div class="cards">{cards}</div><p class="note">Для долей и вероятности: BEFORE и AFTER — в процентах; изменение AFTER − BEFORE и его CI — в процентных пунктах (п.п.). Например: 50% → 40% означает −10 п.п. Уровень доверия CI — в процентах. Вероятность сравнивается на сопоставимых продуктах с одинаковым названием и типом модели. Для количества продуктов сохранена единица «продукта / заявку». Вероятность одобрения не является вероятностью дефолта.</p><p class="method">Парный bootstrap по APP_ID: {number(stats.get('bootstrap'))} повторений · seed {number(stats.get('seed'))} · α = {number(stats.get('alpha'))}. Для бинарных исходов — точный тест Мак-Немара; для семейств — поправка Холма. Отсутствие значимости не доказывает сохранение метрики.</p></section>
    <section id="families"><h2>Сравнение по продуктам (компаниям)</h2><p>Продукт (компания) сравнивается на заявках, где продукт присутствует в обоих срезах. Поправка Холма применяется внутри заранее заданного семейства продуктов.</p>{families}<p class="note">Названия взяты из данных этого прогона. p-value округлены максимум до четырёх знаков, очень малые значения сохранены в научной записи. Подгруппы служат диагностике.</p></section>
    <section id="comparability"><h2>Анализ сопоставимости</h2><div class="cards two">{strata}</div><p>Изменение доли одобрений среди заявок с неизменным внешним скором. Сравнение подгруппы с неизменным входом не доказывает причинный эффект.</p></section>
    <section id="strategy">{pivot_table(con)}</section><footer>Отчёт самодостаточен: таблицы и оформление доступны без подключения к сервису. Для перехода к заявкам через интерактивную сводную нужен вход владельца. Риск дефолта, лимиты и денежный эффект недоступны без дополнительных данных.</footer></main></body></html>'''
