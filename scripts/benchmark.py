"""HTTP timings, environment and full-run counters. API must be running."""
import ctypes
import json
import os
import platform
import statistics
import time
from pathlib import Path
import duckdb
import httpx
from backend.app.storage import meta
from backend.app.storage.mart import records

def main():
    client=httpx.Client(base_url=meta.PUBLIC_BASE_URL,timeout=60)
    client.post('/api/auth/login',json={'username':'alice','password':os.environ.get('SPR_DEMO_PASSWORD','demo')}).raise_for_status()
    runs=client.get('/api/runs').json()['data']
    run=next(r for r in runs if r['status']=='READY')
    id=run['id']
    results={}
    def measure(name,fn,n=10):
        times=[]
        for _ in range(n):
            start=time.perf_counter();response=fn();response.raise_for_status();times.append(1000*(time.perf_counter()-start))
        results[name]={'first_ms':round(times[0],3),'median_ms':round(statistics.median(times),3),'max_ms':round(max(times),3),'n':n}
        return response
    summary=measure('ready_report',lambda:client.get(f'/api/runs/{id}/summary')).json()['data']
    cell=measure('first_pivot',lambda:client.post(f'/api/runs/{id}/pivot',json={'rows':['PATH'],'columns':['CHANGE_TYPE'],'filters':{'DIFF_FLAG':[1]}})).json()['data']['cells'][0]
    measure('change_layout',lambda:client.post(f'/api/runs/{id}/pivot',json={'rows':['product_id','partner_id'],'columns':['SOURCE'],'filters':{'DIFF_FLAG':[1]}}))
    measure('filter',lambda:client.post(f'/api/runs/{id}/pivot',json={'rows':['PATH'],'columns':['SOURCE'],'filters':{'DIFF_FLAG':[1],'product_id':['15210']}}))
    apps=measure('cell_apps',lambda:client.post(f'/api/runs/{id}/pivot/apps',json={'cell_token':cell['cell_token']})).json()['data']
    app_id=apps['app_ids'][0]
    measure('application',lambda:client.get(f'/api/runs/{id}/apps/{app_id}',params={'cell_token':cell['cell_token']}))
    measure('html',lambda:client.get(f'/api/runs/{id}/report.html'))
    raw=meta.get('runs',id)
    with duckdb.connect(raw['mart_path'],read_only=True) as con:
        table_counts={t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ['normalized_union','comparison_mart','app_segments','product_trials','offers','pivot_facts','fact_memberships']}
        partners=records(con,'SELECT DISTINCT partner_id FROM product_trials ORDER BY partner_id')
        # Validate a coarse cell with many repeated attributes: never SUM(CNT).
        distinct=con.execute('SELECT count(DISTINCT m.APP_ID) FROM pivot_facts f JOIN fact_memberships m USING(fact_id) WHERE DIFF_FLAG=1').fetchone()[0]
        assert distinct==summary['changed_apps']
        assert not con.execute('SELECT f.fact_id FROM pivot_facts f JOIN fact_memberships m USING(fact_id) GROUP BY f.fact_id,f.CNT HAVING f.CNT!=count(DISTINCT m.APP_ID) LIMIT 1').fetchone()
    ram=None
    if os.name=='nt':
        value=ctypes.c_ulonglong()
        ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(value));ram=value.value//1024
    result=dict(run_id=id,date=meta.now(),machine={'os':platform.platform(),'cpu':os.environ.get('PROCESSOR_IDENTIFIER',platform.processor()),'logical_cpus':os.cpu_count(),'ram_mib':ram,'python':platform.python_version()},
                table_counts=table_counts,partners=partners,processing_seconds=summary['processing_seconds'],stages=summary['timings'],http=results)
    (meta.RUNTIME/'benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
