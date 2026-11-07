"""Repeatable A1 real-dataset acceptance; no hardcoded production metrics."""
import json
from backend.app.storage import meta
from backend.app.core.importer import snapshot,pairs
from backend.app.core.execution import seed,snapshots
from backend.app.workers.jobs import execute

def main():
    meta.init()
    with meta.db() as c:
        owner = c.execute("SELECT id FROM users WHERE name='alice'").fetchone()[0]
    seed(owner)
    ds = snapshot(owner,meta.DATA_ROOT/'data'/'RUN-20260827-0001')
    duplicate_offer_products = 0
    null_hits = 0
    for _,b,a in pairs(ds):
        for response in [b,a]:
            offers = response['decisionResult']['available_offers']
            duplicate_offer_products += int(len({o['product_id'] for o in offers})<len(offers))
            null_hits += sum(rule['hit'] is None for trial in response['decisionResult']['product_trials'] for rule in trial['rules'])
    assert duplicate_offer_products==25
    assert null_hits>0
    print('responses with repeated offer product_id:',duplicate_offer_products,'null rule hits:',null_hits,flush=True)
    config = meta.listing('configs',owner)[-1]
    run = meta.put('runs',owner,dict(dataset_id=ds['id'],config_id=config['id'],config=config,snapshots=snapshots(owner,config),progress=0,total=ds['count']),'QUEUED')
    print('RUN',run['id'],flush=True)
    execute('runs',run['id'])
    result = meta.get('runs',run['id'])
    if result['status']!='READY':
        raise RuntimeError(result.get('traceback',result))
    print(json.dumps({'id':run['id'],'summary':result['summary'],'stats':result['stats']['app_approval_rate'],'checks':len(result['checks'])},ensure_ascii=False,indent=2))
    summary = result['summary']
    assert summary['total_apps']==2002
    assert {r['SOURCE']:r['approved'] for r in summary['approvals']}=={'BEFORE':657,'AFTER':496}
    assert {r['SOURCE']:r['approved'] for r in summary['approved_products']}=={'BEFORE':1544,'AFTER':1163}
    assert result['stats']['app_approval_rate']['lost']==273
    assert result['stats']['app_approval_rate']['gained']==112
    assert sum(r['CNT'] for r in summary['offers'] if r['SOURCE']=='BEFORE')==1559
    assert sum(r['CNT'] for r in summary['offers'] if r['SOURCE']=='AFTER')==1173
    print('REAL DATA ACCEPTANCE PASSED')

if __name__=='__main__':
    main()
