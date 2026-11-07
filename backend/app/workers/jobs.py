import contextlib
import itertools
import json
import os
import time
import traceback
from pathlib import Path
import duckdb
from backend.app.storage import meta
from backend.app.storage.mart import MartAPI,initialize,write,indexes,records
from backend.app.core import importer
from backend.app.core.execution import compile_script,run_checks,LimitedOutput
from backend.app.core.report import render
from backend.app.stats.paired import calculate,decision

def summary(con):
    n = con.execute('SELECT count(*) FROM app_segments').fetchone()[0]
    overview = records(con,"""SELECT count(DISTINCT c.APP_ID) FILTER(WHERE DIFF_FLAG=1) AS changed_apps,
          count(DISTINCT c.APP_ID) FILTER(WHERE DIFF_FLAG=1 AND s.DECISION_CHANGED=0) AS changed_without_decision,
          count(DISTINCT c.APP_ID) FILTER(WHERE s.DECISION_CHANGED=1) AS decision_changed,
          count(*) AS attributes FROM comparison_mart c JOIN app_segments s USING(APP_ID)""")[0]
    return dict(total_apps=n,**overview,
        approvals=[
            {'SOURCE':s,'approved':con.execute(f"SELECT count(*) FROM app_segments WHERE DECISION_{s}='APPROVE'").fetchone()[0]} for s in ['BEFORE','AFTER']],
        transitions=records(con,'SELECT DECISION_BEFORE,DECISION_AFTER,count(*) AS CNT FROM app_segments GROUP BY ALL ORDER BY ALL'),
        products=records(con,"SELECT SOURCE,product_id,partner_id,count(*) AS attempts,count(*) FILTER(WHERE decision='APPROVE') AS approved,count(*) FILTER(WHERE decision='APPROVE')::DOUBLE/count(*) AS approval_rate FROM product_trials GROUP BY ALL ORDER BY ALL"),
        approved_products=records(con,"SELECT SOURCE,count(*) FILTER(WHERE decision='APPROVE') AS approved,count(*) AS attempts FROM product_trials GROUP BY SOURCE ORDER BY SOURCE"),
        offers=records(con,'SELECT SOURCE,type,count(*) AS CNT,count(DISTINCT product_id) AS unique_products FROM offers GROUP BY ALL ORDER BY ALL'),
        top_offer_changed=con.execute('SELECT count(*) FROM app_segments WHERE TOP_OFFER_BEFORE!=TOP_OFFER_AFTER').fetchone()[0],
        external_score_changed=con.execute('SELECT count(*) FROM app_segments WHERE SCORE_OKB_BEFORE!=SCORE_OKB_AFTER').fetchone()[0],
        model_changed=con.execute('SELECT count(*) FROM app_segments WHERE PD_MODEL_BEFORE!=PD_MODEL_AFTER').fetchone()[0],
        availability={k:{'status':'unavailable','reason':v} for k,v in {'pd_default':'Нужны pd_default, pd_horizon, pd_model_version, pd_calibrated','limits':'Нужны offered_limit, currency','money':'Нужны PD_default, EAD, LGD, take_up_probability, денежные потоки и затраты'}.items()},
        top_changes=records(con,'SELECT PATH,count(DISTINCT APP_ID) AS CNT FROM comparison_mart WHERE DIFF_FLAG=1 GROUP BY PATH ORDER BY CNT DESC,PATH LIMIT 15'))

def full_run(id):
    run = meta.get('runs',id)
    config,snaps = run['config'],run['snapshots']
    dataset = meta.get('datasets',run['dataset_id'],run['owner_id'])
    folder = meta.RUNTIME/'runs'/id
    folder.mkdir(parents=True,exist_ok=True)
    temp = folder/'mart.tmp.duckdb'
    started = time.perf_counter()
    timings = {}
    phase_start = started
    def phase(stage,kind=None):
        nonlocal phase_start
        t = time.perf_counter()
        timings[run.get('_phase','startup')] = round(t-phase_start,4)
        run['_phase'] = stage
        phase_start = t
        sid = config['stages'].get(kind)
        meta.update('runs',id,status=stage,progress=0,total=dataset['count'],heartbeat=meta.now())
        meta.event(id,stage,stage,0,dataset['count'],sid,snaps[sid]['hash'] if sid else None)
    params = config.get('params',{})
    con = duckdb.connect(str(temp))
    con.execute('SET threads=4')
    try:
        initialize(con)
        phase('NORMALIZING','normalize')
        norm_id = config['stages']['normalize']
        norm = compile_script(snaps[norm_id])['normalize']
        def normalized():
            for i,(app_id,b,a) in enumerate(importer.pairs(dataset),1):
                for source,response in [('BEFORE',b),('AFTER',a)]:
                    seen = set()
                    for row in norm(response,app_id,source,{**params.get('normalize',{}),**snaps[norm_id].get('params',{})}):
                        key = row.get('PATH'),row.get('ARRAY_KEY')
                        if row.get('APP_ID')!=app_id or row.get('SOURCE')!=source or key in seen or row.get('VALUE_KIND') not in ['null','boolean','number','string']:
                            raise ValueError(f'Invalid normalization contract: {app_id} {key}')
                        seen.add(key)
                        yield row
                if i%50==0 or i==dataset['count']:
                    meta.update('runs',id,progress=i,heartbeat=meta.now())
                    meta.event(id,'NORMALIZING',f'Приведено пар: {i}',i,dataset['count'],norm_id,snaps[norm_id]['hash'])
        write(con,'normalized_union',normalized())
        phase('COMPARING','compare')
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
        phase('FACTS','facts')
        facts = compile_script(snaps[config['stages']['facts']])['build_facts'](MartAPI(con),lambda:importer.pairs(dataset),{**params.get('facts',{}),**snaps[config['stages']['facts']].get('params',{})})
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
        phase('CHECKS')
    finally:
        con.close()
    with duckdb.connect(str(temp),read_only=True) as con:
        rows = run_checks(MartAPI(con),snaps,config.get('checks',[]),params.get('checks',{}),
                          lambda sid,n:meta.event(id,'CHECKS',f'Результатов: {n}',snapshot_id=sid,code_hash=snaps[sid]['hash']))
        phase('STATS')
        stats = calculate(con,params.get('stats',{}))
        overview = summary(con)
    overview['decision'] = decision(stats,rows,params.get('thresholds',{}))
    phase('REPORTING')
    timings['REPORTING'] = round(time.perf_counter()-phase_start,4)
    overview['timings'] = timings
    overview['processing_seconds'] = round(time.perf_counter()-started,4)
    with duckdb.connect(str(temp),read_only=True) as con:
        html = render(run,overview,stats,rows,con)
    version = meta.uid()
    (folder/f'report-{version}.html').write_text(html,encoding='utf-8')
    os.replace(temp,folder/'mart.duckdb')
    meta.update('runs',id,status='READY',progress=dataset['count'],summary=overview,stats=stats,checks=rows,
                report_version=version,mart_path=str(folder/'mart.duckdb'),heartbeat=meta.now())
    meta.event(id,'READY',f"Готово за {overview['processing_seconds']:.2f} с",dataset['count'],dataset['count'])

def checks_only(id):
    execution = meta.get('check_executions',id)
    run = meta.get('runs',execution['run_id'],execution['owner_id'])
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        rows = run_checks(MartAPI(con),execution['snapshots'],execution['checks'],execution.get('params',{}),
                          lambda sid,n:meta.event(run['id'],'CHECKS',f'Повторная проверка: {n} строк',snapshot_id=id+':'+sid,code_hash=execution['snapshots'][sid]['hash']))
    overview = {**run['summary'],'decision':decision(run['stats'],rows,run['config'].get('params',{}).get('thresholds',{}))}
    html = render(run,overview,run['stats'],rows)
    folder = Path(run['mart_path']).parent
    (folder/f'report-{id}.html').write_text(html,encoding='utf-8')
    meta.update('runs',run['id'],checks=rows,summary=overview,report_version=id)
    meta.update('check_executions',id,status='READY',rows=rows)

def execute(table,id):
    output = LimitedOutput()
    try:
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
            (full_run if table=='runs' else checks_only)(id)
    except BaseException as e:
        trace = traceback.format_exc()[-16000:]
        obj = meta.get(table,id)
        meta.update(table,id,status='FAILED',error=str(e),traceback=trace)
        meta.event(id if table=='runs' else obj['run_id'],'FAILED',str(e),traceback=trace)
    finally:
        if output.getvalue():
            obj = meta.get(table,id)
            meta.event(id if table=='runs' else obj['run_id'],'OUTPUT',output.getvalue())
