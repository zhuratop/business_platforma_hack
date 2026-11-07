import html
import json
from backend.app.storage import meta

def render(run,summary,stats,checks):
    esc = lambda v:html.escape(str(v))
    columns = ['LABEL','SOURCE','ARGUMENT','CNT','TOTAL','METRIC','RESULT','CONFIDENCE','APP_IDS']
    rows = ''.join('<tr class="'+('low' if r['CONFIDENCE']=='LOW' else r['RESULT'].lower())+'">'+''.join('<td>'+esc(r.get(k,''))+'</td>' for k in columns)+'</tr>' for r in checks)
    back_url = esc(meta.PUBLIC_BASE_URL+'/?run='+run['id']+'&tab=pivot')
    return f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>СПР · {esc(run['id'])}</title>
    <style>body{{font:15px system-ui;max-width:1200px;margin:40px auto;color:#173037;padding:20px}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{border:1px solid #ccd6d6;padding:8px;text-align:left;word-break:break-word}}.fail{{background:#ffe7df}}.low{{background:#faf2e7;color:#7a776f}}pre{{white-space:pre-wrap;background:#f1f6f5;padding:20px}}a{{color:#087d77}}</style>
    <h1>Система анализа изменений СПР</h1><p>Прогон {esc(run['id'])} · {esc(run['created'])}</p>
    <p><a href="{back_url}">Открыть интерактивную сводную</a> (нужен вход владельца)</p>
    <h2>Обзор</h2><pre>{esc(json.dumps(summary,ensure_ascii=False,indent=2))}</pre>
    <h2>Единый отчёт проверок</h2><table><thead><tr>{''.join('<th>'+k+'</th>' for k in columns)}</tr></thead><tbody>{rows}</tbody></table>
    <h2>Парная статистика</h2><pre>{esc(json.dumps(stats,ensure_ascii=False,indent=2))}</pre>
    <p>scoring.pd — APPROVAL_PROBABILITY. PD дефолта, лимиты и деньги недоступны без дополнительных данных.
    Совпадение изменений не доказывает причинность. Срабатывания проверок приведены в исходной формулировке их авторов.
    У APP_IDS проверок может быть показана только первая часть списка; полный переход доступен из сводной.</p></html>'''
