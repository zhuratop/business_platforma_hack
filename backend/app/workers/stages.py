"""Individually executable pipeline stages, preserving complete-pair commits."""
import itertools
import json

from backend.app.storage import meta
from backend.app.storage.mart import MartAPI, write, indexes
from backend.app.core import importer
from backend.app.core.execution import compile_script
from backend.app.plugins.defaults import DEFAULT_BATCH_PAIRS


def saved_pairs(con, batch_pairs=DEFAULT_BATCH_PAIRS):
    cursor = con.cursor()
    try:
        cursor.execute('SELECT APP_ID,BEFORE_JSON,AFTER_JSON FROM raw_inputs ORDER BY APP_ID')
        while batch := cursor.fetchmany(batch_pairs):
            for app, before, after in batch:
                yield app, json.loads(before), json.loads(after)
    finally:
        cursor.close()


def reading(con, run, dataset, batch_pairs):
    config, snaps = run['config'], run['snapshots']
    reader_id = config['stages'].get('reader')
    reader = compile_script(snaps[reader_id])['read_input'] if reader_id else None
    params = {**config.get('params', {}).get('reader', {}), **(snaps[reader_id].get('params', {}) if reader_id else {})}
    source = iter(importer.pairs(dataset, reader, params))
    saved = 0
    while batch := list(itertools.islice(source, batch_pairs)):
        con.execute('BEGIN TRANSACTION')
        try:
            con.executemany('INSERT INTO raw_inputs VALUES (?,?,?)', [
                (app, json.dumps(b, ensure_ascii=False, allow_nan=False), json.dumps(a, ensure_ascii=False, allow_nan=False)) for app, b, a in batch])
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
        con.execute('CHECKPOINT')
        saved += len(batch)
        meta.update('runs', run['id'], progress=saved, raw_saved_pairs=saved, saved_at=meta.now())
    if saved != dataset['count']:
        raise ValueError('Число прочитанных пар не совпало с датасетом')


def normalizing(con, run, dataset, batch_pairs):
    config, snaps = run['config'], run['snapshots']
    norm_id = config['stages']['normalize']
    norm = compile_script(snaps[norm_id])['normalize']
    params = {**config.get('params', {}).get('normalize', {}), **snaps[norm_id].get('params', {})}
    def normalized(batch):
        for app_id, before, after in batch:
            for source, response in [('BEFORE', before), ('AFTER', after)]:
                seen = set()
                for row in norm(response, app_id, source, params):
                    key = row.get('PATH'), row.get('ARRAY_KEY')
                    if row.get('APP_ID') != app_id or row.get('SOURCE') != source or key in seen or row.get('VALUE_KIND') not in ['null', 'boolean', 'number', 'string']:
                        raise ValueError(f'Invalid normalization contract: {app_id} {key}')
                    seen.add(key)
                    yield row
    source = iter(saved_pairs(con, batch_pairs))
    saved, normalized_rows = 0, 0
    meta.update('runs', run['id'], saved_pairs=0, normalized_rows=0)
    while batch := list(itertools.islice(source, batch_pairs)):
        con.execute('BEGIN TRANSACTION')
        try:
            count = write(con, 'normalized_union', normalized(batch))
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
        con.execute('CHECKPOINT')
        saved += len(batch)
        normalized_rows += count
        meta.update('runs', run['id'], progress=saved, saved_pairs=saved, normalized_rows=normalized_rows, saved_at=meta.now())
        meta.event(run['id'], 'NORMALIZING', f'Сохранено пар: {saved}; атрибутов: {normalized_rows}', saved, dataset['count'], norm_id, snaps[norm_id]['hash'])


def comparing(con, run, dataset, batch_pairs):
    config, snaps = run['config'], run['snapshots']
    params = config.get('params', {})

    compare = compile_script(snaps[config['stages']['compare']])['compare']
    cursor = con.cursor()
    cursor.execute('SELECT * FROM normalized_union ORDER BY APP_ID,SOURCE,PATH,ARRAY_KEY')
    columns = [r[0] for r in cursor.description]
    def stream():
        while batch:=cursor.fetchmany(10000):
            for row in batch:
                yield dict(zip(columns,row))
    def comparisons():
        for app_id,group in itertools.groupby(stream(),lambda r:r['APP_ID']):
            rows = list(group)
            by_source = {s:{(r['PATH'],r['ARRAY_KEY']):r for r in rows if r['SOURCE']==s} for s in ['BEFORE','AFTER']}
            seen = set()
            for r in compare([r for r in rows if r['SOURCE']=='BEFORE'],[r for r in rows if r['SOURCE']=='AFTER'],{**params.get('compare',{}),**snaps[config['stages']['compare']].get('params',{})}):
                if r.get('APP_ID')!=app_id or r.get('CHANGE_TYPE') not in ['SAME','VALUE_CHANGED','ATTRIBUTE_NEW','ATTRIBUTE_LOST'] or r.get('DIFF_FLAG')!=int(r.get('CHANGE_TYPE')!='SAME'):
                    raise ValueError('Invalid comparison contract')
                key = r['PATH'],r['ARRAY_KEY']
                if key in seen or key not in (by_source['BEFORE'].keys()|by_source['AFTER'].keys()):
                    raise ValueError(f'Invalid or duplicate comparison key: {key}')
                seen.add(key)
                b,a = by_source['BEFORE'].get(key),by_source['AFTER'].get(key)
                expected = 'ATTRIBUTE_NEW' if b is None else 'ATTRIBUTE_LOST' if a is None else 'VALUE_CHANGED' if (b['VALUE_KIND'],b['VALUE'])!=(a['VALUE_KIND'],a['VALUE']) else 'SAME'
                if r['CHANGE_TYPE'] != expected:
                    raise ValueError(f'Comparison must use typed original values: {app_id} {key}')
                for source in ['BEFORE','AFTER']:
                    original = by_source[source].get(key)
                    if r['VALUE_'+source] != (original['VALUE'] if original else ''):
                        raise ValueError(f'Comparison changed original VALUE: {app_id} {key}')
                    r.setdefault('PRESENT_'+source,original is not None)
                    r.setdefault('KIND_'+source,original['VALUE_KIND'] if original else 'missing')
                yield r
            if seen != by_source['BEFORE'].keys()|by_source['AFTER'].keys():
                raise ValueError(f'Comparison omitted attributes for {app_id}')
    write(con,'comparison_mart',comparisons())
    cursor.close()

def facts_stage(con, run, dataset, batch_pairs):
    config, snaps = run['config'], run['snapshots']
    params = config.get('params', {})
    def raw_pairs():
        yield from saved_pairs(con, batch_pairs)
    facts = compile_script(snaps[config['stages']['facts']])['build_facts'](MartAPI(con),raw_pairs,{**params.get('facts',{}),**snaps[config['stages']['facts']].get('params',{})})
    for key,table in [('segments','app_segments'),('product_trials','product_trials'),('offers','offers')]:
        write(con,table,facts[key])
    if con.execute('SELECT count(*) FROM app_segments').fetchone()[0] != dataset['count']:
        raise ValueError('Segment count must match paired dataset')
    if con.execute('SELECT 1 FROM comparison_mart c LEFT JOIN app_segments s USING(APP_ID) WHERE s.APP_ID IS NULL LIMIT 1').fetchone():
        raise ValueError('Missing segment for comparison APP_ID')
    memberships = []
    segment_lookup = {r['APP_ID']:r for r in MartAPI(con).segments()}
    segment_dimensions = ['DECISION_BEFORE','DECISION_AFTER','DECISION_CHANGED','PARTNER_TYPE','ROUTING_METHOD']
    def fact_rows():
        index = 0
        for row in facts['pivot_facts']:
            ids = row['APP_IDS']
            if not isinstance(ids,list) or row['CNT'] != len(set(ids)) or len(ids)!=len(set(ids)):
                raise ValueError('Fact CNT must equal full unique APP_IDS')
            grouped = {}
            for app in ids:
                if app not in segment_lookup:
                    raise ValueError(f'Unknown fact APP_ID: {app}')
                # Segment columns are enriched by the core; plugin Fact only
                # has to provide the contract's base dimensions and full ids.
                values = tuple(segment_lookup[app][d] for d in segment_dimensions)
                grouped.setdefault(values,[]).append(app)
            for values,group_ids in grouped.items():
                index += 1
                memberships.extend(dict(fact_id=index,APP_ID=a) for a in group_ids)
                yield {**row,**dict(zip(segment_dimensions,values)),'fact_id':index,'CNT':len(group_ids)}
    write(con,'pivot_facts',fact_rows())
    write(con,'fact_memberships',memberships)
    indexes(con)
    dims = ','.join('"'+d+'"' for d in __import__('backend.app.domain.contracts',fromlist=['FACT_DIMENSIONS']).FACT_DIMENSIONS)
    if con.execute(f'SELECT 1 FROM pivot_facts GROUP BY {dims} HAVING count(*)>1 LIMIT 1').fetchone():
        raise ValueError('Duplicate fact dimensions')
    if con.execute('SELECT 1 FROM fact_memberships m LEFT JOIN app_segments s USING(APP_ID) WHERE s.APP_ID IS NULL LIMIT 1').fetchone():
        raise ValueError('Unknown fact APP_ID')
