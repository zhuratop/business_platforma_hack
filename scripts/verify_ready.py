"""Read-only acceptance of the last browser-built full dataset and its source snapshot."""
import json
import math
from pathlib import Path
from backend.app.storage import meta
from backend.app.core.importer import pairs

run_id=(meta.RUNTIME/'browser-latest-run.txt').read_text().strip()
run=meta.get('runs',run_id)
assert run['status']=='READY'
s=run['summary']
assert s['total_apps']==2002
assert {r['SOURCE']:r['approved'] for r in s['approvals']}=={'BEFORE':657,'AFTER':496}
assert {r['SOURCE']:r['approved'] for r in s['approved_products']}=={'BEFORE':1544,'AFTER':1163}
assert {source:sum(r['CNT'] for r in s['offers'] if r['SOURCE']==source) for source in ['BEFORE','AFTER']}=={'BEFORE':1559,'AFTER':1173}
st=run['stats']['app_approval_rate']
assert (st['lost'],st['gained'])==(273,112)
assert math.isclose(st['p'],1.254165079861648e-16,rel_tol=1e-10)
duplicates=0
null_hits=0
for _,b,a in pairs(meta.get('datasets',run['dataset_id'])):
    for response in [b,a]:
        offers=response['decisionResult']['available_offers']
        duplicates+=int(len({o['product_id'] for o in offers})<len(offers))
        null_hits+=sum(rule['hit'] is None for trial in response['decisionResult']['product_trials'] for rule in trial['rules'])
assert duplicates==25 and null_hits>0
assert {'ar_drop_by_product','attribute_new_loss','external_score_drift','stop_factor_disappeared','target_model_changed'} <= {r['check_id'] for r in run['checks']}
result=dict(passed=True,run_id=run_id,paired_apps=s['total_apps'],changed_apps=s['changed_apps'],comparison_rows=s['attributes'],
            duplicate_offer_product_responses=duplicates,null_rule_hits=null_hits,check_rows=len(run['checks']),p=st['p'])
(meta.RUNTIME/'real-acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
