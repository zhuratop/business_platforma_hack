"""Self-contained full attribute pivot and saved check results."""
import html
import json
import math
import re
from pathlib import Path

import duckdb

from backend.app.core.attribute_tree import TREE_COUNTS
from backend.app.core.check_display import with_thresholds
from backend.app.storage import meta


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return '—'
    return f'{value:.4f}'.rstrip('0').rstrip('.') if value else '0'


def percent(value):
    return f'{value * 100:.1f}%' if type(value) in (int, float) and math.isfinite(value) else '—'


def short_text(value,limit=90):
    text=' '.join(str(value).split())
    return text[:limit-1].rstrip()+'…' if len(text)>limit else text


def short_argument(text):
    sides=re.split(r'\s+(?:->|→)\s+',text)
    if len(sides)==2:
        groups=[[item.strip() for item in side.split(';')] for side in sides]
        if all(all(re.fullmatch(r'\d+:.+',item) for item in group) for group in groups):
            models=[set(item.split(':',1)[1] for item in group) for group in groups]
            if all(len(group)==1 for group in models):
                n=len({item.split(':',1)[0] for group in groups for item in group})
                word='продукт' if n%10==1 and n%100!=11 else 'продукта' if 2<=n%10<=4 and not 12<=n%100<=14 else 'продуктов'
                return f'{short_text(next(iter(models[0])),36)} → {short_text(next(iter(models[1])),36)} · {n} {word}'
        return ' → '.join(short_text(side,42) for side in sides)
    return short_text(text)


def tree_data(con):
    """Same distinct application counts and typed buckets as the unfiltered UI.

    Compute parent counts from applications, never by summing child counts.
    All levels and values are exported without API pagination.
    """
    prefix='WITH scoped AS (SELECT n.*,c.DIFF_FLAG FROM normalized_union n JOIN comparison_mart c USING(APP_ID,PATH,ARRAY_KEY)) '
    paths = con.execute(prefix+''', expanded AS (
        SELECT APP_ID,SOURCE,DIFF_FLAG,array_to_string(list_slice(string_split(PATH,'.'),1,depth),'.') AS NODE_PATH
        FROM scoped CROSS JOIN UNNEST(range(1,len(string_split(PATH,'.'))+1)) AS parts(depth))
        SELECT NODE_PATH,''' + TREE_COUNTS + ' FROM expanded GROUP BY NODE_PATH ORDER BY NODE_PATH').fetchall()
    roots, nodes = [], {}
    for path, *counts in paths:
        node = dict(label=path.rsplit('.', 1)[-1],path=path,kind='path',counts=counts,children=[])
        nodes[path] = node
        parent = path.rsplit('.', 1)[0] if '.' in path else None
        (nodes[parent]['children'] if parent else roots).append(node)
    key_counts = con.execute(prefix+'SELECT PATH,ARRAY_KEY,' + TREE_COUNTS +
        ' FROM scoped GROUP BY PATH,ARRAY_KEY ORDER BY PATH,ARRAY_KEY').fetchall()
    keyed_paths = {path for path, key, *_ in key_counts if key}
    keys = {}
    for path, key, *counts in key_counts:
        if path in keyed_paths:
            node = dict(label=key or 'Без ключа массива',path=path,kind='array',counts=counts,children=[])
            keys[path,key] = node
            nodes[path]['children'].append(node)
    values = con.execute(prefix+'SELECT PATH,ARRAY_KEY,VALUE_KIND,ADJUSTED_VALUE,' + TREE_COUNTS +
        ' FROM scoped GROUP BY PATH,ARRAY_KEY,VALUE_KIND,ADJUSTED_VALUE ORDER BY PATH,ARRAY_KEY,VALUE_KIND,ADJUSTED_VALUE').fetchall()
    for path, key, kind, value, *counts in values:
        label = 'null' if kind == 'null' else json.dumps(value,ensure_ascii=False) if kind == 'string' else str(value)
        parent = keys[path,key] if path in keyed_paths else nodes[path]
        parent['children'].append(dict(label=label,path=path,kind='value',value_kind=kind,counts=counts,children=[]))
    totals = con.execute(prefix+'SELECT ' + TREE_COUNTS + ' FROM scoped').fetchone()
    return roots, totals


def pivot_table(con):
    roots, totals = tree_data(con)
    rows = []
    def walk(node, parent='', depth=0):
        identifier = str(len(rows)+1)
        branch = bool(node['children'])
        label = esc(node['label'])
        name = (f'<button class="tree-toggle" aria-expanded="false" aria-label="Раскрыть {label}">'
                f'<span class="arrow" aria-hidden="true">▸</span>{label}</button>' if branch else
                f'<span class="tree-leaf">{label}</span>')
        kind = 'ключ массива' if node['kind']=='array' else node.get('value_kind','')
        cells = ''.join(f'<td class="num {"changed" if i in [4,6] else ""}">{number(node["counts"][i])}</td>' for i in [3,4,5,6,2])
        rows.append(f'<tr data-id="{identifier}" data-parent="{parent}" data-kind="{node["kind"]}" '
            f'data-path="{esc(node["path"])}"{ " hidden" if parent else ""}>'
            f'<th scope="row"><div class="node-name" style="padding-left:{depth*18}px" title="{esc(node["path"])}">'
            f'{name}<small>{esc(kind)}</small></div></th>{cells}</tr>')
        for child in node['children']:
            walk(child, identifier, depth+1)
    for root in roots:
        walk(root)
    foot = ''.join(f'<td class="num {"changed" if i in [4,6] else ""}">{number(totals[i])}</td>' for i in [3,4,5,6,2])
    return f'''<div class="section-title"><div><h2>Сводная таблица · все атрибуты</h2><p>Полный прогон: оба среза, все значения DIFF_FLAG.</p></div>
        <div class="tree-actions"><button id="expand-all">Раскрыть всё</button><button id="collapse-all">Свернуть всё</button></div></div>
        <p class="note">Числа — уникальные APP_ID. Итог родителя и общий итог считаются отдельно: складывать дочерние строки или BEFORE и AFTER нельзя. В каждом срезе выделены DIFF_FLAG = 0 (без изменений) и DIFF_FLAG = 1 (есть изменения). У родительского узла заявка может входить в обе группы по разным атрибутам; их сумма не является общим итогом.
        Порядок массива сопоставляется по настроенным ключам; null, false, пустая строка и отсутствие поля различаются. В значениях показаны те же бакеты, что в приложении.</p>
        <div class="table-scroll"><table class="attribute-table"><thead><tr><th rowspan="2">Атрибут / ключ массива / значение</th><th colspan="2">BEFORE (MASTER)</th><th colspan="2">AFTER (BETA)</th><th rowspan="2">Уникальных заявок</th></tr><tr><th>DIFF_FLAG = 0</th><th class="changed">DIFF_FLAG = 1</th><th>DIFF_FLAG = 0</th><th class="changed">DIFF_FLAG = 1</th></tr></thead>
        <tbody>{''.join(rows) if rows else '<tr><td colspan="6">Нет атрибутов для отображения.</td></tr>'}</tbody>
        <tfoot><tr><th>Итого уникальных заявок</th>{foot}</tr></tfoot></table></div>
        <p class="note">В файл включены все уровни дерева и значения, без ограничения страниц. Стрелки раскрывают узлы; сворачивание родителя закрывает всё поддерево. При печати выводятся все строки. Локальные фильтры страницы в этот полный отчёт не переносятся.</p>'''


def check_rows(run, checks):
    snapshots = run.get('snapshots',{})
    overrides = run.get('config',{}).get('params',{}).get('checks',{})
    if run.get('report_version') and run.get('owner_id'):
        try:
            execution = meta.get('check_executions',run['report_version'],run['owner_id'])
            if execution['run_id']==run['id']:
                snapshots,overrides = execution['snapshots'],execution.get('params',{})
        except KeyError:
            pass
    return with_thresholds(checks,snapshots,overrides)


def checks_table(checks):
    body = []
    for row in checks:
        ids = list(dict.fromkeys(row.get('APP_IDS',[])))
        total = row.get('CNT',0)
        limited = len(ids)<total
        apps = (f'<details><summary>Показать {len(ids)} APP_ID</summary><ul>' +
                ''.join(f'<li><code>{esc(app)}</code></li>' for app in ids) + '</ul></details>') if ids else 'Нет APP_ID'
        if limited:
            apps += f'<small>Первые {len(ids)} из {number(total)}. Проверка ограничивает APP_IDS; список неполный.</small>'
        elif not total:
            apps += '<small>Нет затронутых заявок.</small>'
        threshold = row.get('threshold') or {}
        result = row.get('RESULT','')
        confidence = row.get('CONFIDENCE','')
        style = 'pass' if result=='PASS' else 'fail' if result=='FAIL' else ''
        body.append(f'''<tr class="{'low' if confidence=='LOW' else ''}"><td><b title="{esc(row.get('LABEL',''))}">{esc(short_text(row.get('LABEL',''),72))}</b><small title="{esc(row.get('ARGUMENT',''))}">{esc(short_argument(row.get('ARGUMENT','')))}</small></td>
            <td>{esc(row.get('SOURCE',''))}</td><td class="num">{number(total)} / {number(row.get('TOTAL'))}</td>
            <td class="num" title="{esc(threshold.get('parameter') or '')} {esc(threshold.get('operator',''))}">{percent(threshold.get('value'))}</td>
            <td class="num">{percent(row.get('METRIC'))}</td><td><span class="badge {style}">{esc(result)}</span></td>
            <td>{esc(confidence)}</td><td>{apps}</td></tr>''')
    return f'''<div class="section-title"><h2>Результаты автопроверок</h2><span class="badge">{len(checks)} строк · PASS {sum(r.get('RESULT')=='PASS' for r in checks)} · FAIL {sum(r.get('RESULT')=='FAIL' for r in checks)}</span></div>
        <p>Сохранённые результаты этого прогона, включая последнее успешное повторное применение проверок. Все строки включены без фильтров.</p>
        <div class="table-scroll"><table class="checks-table"><thead><tr><th>Проверка / аргумент</th><th>Срез</th><th>CNT / TOTAL</th><th>Порог, %</th><th>Разница в %</th><th>Результат</th><th>Уверенность</th><th>Заявки</th></tr></thead><tbody>
        {''.join(body) if body else '<tr><td colspan="8">Для этого прогона нет результатов проверок.</td></tr>'}</tbody></table></div>
        <p class="note">Числа в процентных столбцах — исходные METRIC и пороги × 100, с одним знаком после запятой. Для Approval Rate это относительное падение, для остальных выданных проверок — доля затронутых заявок. Прочерк означает отсутствие численного порога. LOW — низкая уверенность; PASS/FAIL сохраняют смысл исходной проверки.</p>'''


TREE_SCRIPT = '''
const table=document.querySelector('.attribute-table');
const rows=Array.from(table.querySelectorAll('tbody tr[data-id]'));
const children=new Map();
for(const row of rows){const parent=row.dataset.parent;if(!children.has(parent))children.set(parent,[]);children.get(parent).push(row);}
function expanded(row,value){const button=row.querySelector('.tree-toggle');if(button){button.setAttribute('aria-expanded',String(value));button.querySelector('.arrow').textContent=value?'▾':'▸';}}
function collapse(row){for(const child of children.get(row.dataset.id)||[]){child.hidden=true;expanded(child,false);collapse(child);}}
table.addEventListener('click',event=>{const button=event.target.closest('.tree-toggle');if(!button)return;const row=button.closest('tr');const open=button.getAttribute('aria-expanded')!=='true';expanded(row,open);if(open){for(const child of children.get(row.dataset.id)||[])child.hidden=false;}else collapse(row);});
document.getElementById('expand-all').addEventListener('click',()=>{for(const row of rows){row.hidden=false;expanded(row,true);}});
document.getElementById('collapse-all').addEventListener('click',()=>{for(const row of rows){row.hidden=!!row.dataset.parent;expanded(row,false);}});
'''


def render(run, summary, stats, checks, con=None, public_base_url=None):
    if con is None:
        with duckdb.connect(run['mart_path'],read_only=True) as connection:
            return render(run,summary,stats,checks,connection,public_base_url)
    css = Path(__file__).with_name('report.css').read_text(encoding='utf-8')
    base = (public_base_url or meta.PUBLIC_BASE_URL).rstrip('/')+'/?run='+run['id']
    checks = check_rows(run,checks)
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>СПР · сводная и проверки · {esc(run['id'])}</title><style>{css}</style></head><body><main>
        <header><div class="eyebrow">Система анализа изменений СПР</div><h1>BEFORE (MASTER) → AFTER (BETA)</h1><p>Сводная таблица и результаты автопроверок</p>
        <div>Прогон {esc(run['id'])} · {esc(run['created'])}</div>
        <div class="run-numbers">Пар заявок: <b>{number(summary.get('total_apps'))}</b> · С различиями, включая смену решения: <b>{number(summary.get('changed_apps'))}</b></div>
        <nav><a href="#pivot">Сводная таблица</a><a href="#checks">Автопроверки</a><a href="{esc(base+'&tab=pivot')}">Открыть сводную в приложении</a><a href="{esc(base+'&tab=checks')}">Открыть проверки в приложении</a></nav></header>
        <section id="pivot">{pivot_table(con)}</section><section id="checks">{checks_table(checks)}</section>
        <footer>Данные и оформление включены в файл; дерево и списки APP_ID работают без сервера. Для перехода в приложение нужен вход владельца прогона.</footer>
        </main><script>{TREE_SCRIPT}</script></body></html>'''
