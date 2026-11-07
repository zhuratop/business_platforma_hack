from pathlib import Path
from backend.app.core.check_display import with_thresholds,threshold
from backend.app.core.execution import run_checks
from backend.app.storage.meta import ROOT

def test_original_snapshots_show_correct_percent_thresholds():
    files={'ar_drop_by_product':'check_ar_drop_by_product.py','attribute_new_loss':'check_attribute_new_loss.py'}
    snaps={key:{'code':(ROOT/'scripts'/'checks'/file).read_text(encoding='utf-8'),'params':{}} for key,file in files.items()}
    rows=[{'check_id':key,'snapshot_id':key,'METRIC':0.2347} for key in files]
    enriched=with_thresholds(rows,snaps,{})
    assert [r['threshold']['value'] for r in enriched]==[0.1,0.001]
    assert [r['METRIC'] for r in enriched]==[0.2347,0.2347]
    assert all('threshold' not in r for r in rows)

def test_legacy_metadata_is_read_without_executing_python():
    code="raise RuntimeError('never execute this in API')\nDEFAULTS={'max_drop_rel':0.12}\nCHECK={'params':DEFAULTS}"
    rows=[{'check_id':'ar_drop_by_product','snapshot_id':'s'}]
    script={'s':{'code':code,'params':{'max_drop_rel':0.15}}}
    assert with_thresholds(rows,script,{'ar_drop_by_product':{'max_drop_rel':0.2}})[0]['threshold']['value']==0.2

def test_recorded_threshold_survives_configuration_changes():
    rows=[{'check_id':'ar_drop_by_product','threshold':{'value':0.17}}]
    assert with_thresholds(rows,{}, {'ar_drop_by_product':{'max_drop_rel':0.9}})[0]['threshold']['value']==0.17
    assert threshold('stop_factor_disappeared',{'low_confidence_cnt':5})['value'] is None

def test_execution_records_effective_parameters_without_changing_metric():
    code='''def run(mart,p):
    return [dict(LABEL='test',SOURCE='AFTER',ARGUMENT='x',CNT=1,TOTAL=2,METRIC=0.2347,APP_IDS=['x'],RESULT='FAIL',CONFIDENCE='LOW')]
CHECK=dict(id='ar_drop_by_product',label='test',params={'max_drop_rel':0.1},entrypoint=run)
'''
    rows=run_checks(None,{'s':{'code':code,'name':'test.py','params':{'max_drop_rel':0.15}}},['s'],{'ar_drop_by_product':{'max_drop_rel':0.25}})
    assert rows[0]['METRIC']==0.2347 and rows[0]['threshold']['value']==0.25

def test_custom_declared_threshold_and_unknown_dynamic_defaults():
    rows=[{'check_id':'custom','snapshot_id':'s'}]
    script={'s':{'code':"CHECK=dict(params={'max_share':0.03},threshold={'parameter':'max_share','operator':'>'})",'params':{}}}
    assert with_thresholds(rows,script,{})[0]['threshold']=={'value':0.03,'parameter':'max_share','operator':'>'}
    assert with_thresholds([{'check_id':'ar_drop_by_product','snapshot_id':'s'}],{'s':{'code':'CHECK=dynamic()'}},{})[0]['threshold']['value'] is None
