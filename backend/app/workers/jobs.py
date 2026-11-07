import contextlib
import traceback
from pathlib import Path
import duckdb
from backend.app.storage import meta
from backend.app.storage.mart import MartAPI,records
from backend.app.core.execution import run_checks,LimitedOutput
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

from backend.app.workers.pipeline import full_run


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
