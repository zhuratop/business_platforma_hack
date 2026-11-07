import json
from pathlib import Path

from backend.app.core.execution import seed
from backend.app.plugins.defaults import default_params,DEFAULT_EXCLUSIONS
from backend.app.storage import meta
from scripts.default_spr.normalize import normalize


def test_default_exclusions_keep_decisions_scores_and_application_identity():
    source=Path(__file__).parent/'fixtures'/'spr'
    for file in (source/'BEFORE').glob('*.json'):
        response=json.loads(file.read_bytes())
        rows=list(normalize(response,file.stem,'BEFORE',default_params()['normalize']))
        assert {r['PATH'].split('.')[0] for r in rows}=={'decisionResult','characteristics'}
        assert all(r['APP_ID']==file.stem for r in rows)
        paths={r['PATH'] for r in rows}
        assert {'decisionResult.decision','characteristics.score_okb','characteristics.score_equ'}<=paths
        assert any(p.startswith('decisionResult.product_trials.rules.') for p in paths)
        assert 'appData' in response and 'product_catalog' in response


def test_old_default_config_is_updated_but_custom_exclusions_and_runs_are_preserved(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    meta.init()
    owner='test-owner'
    seed(owner)
    config=meta.listing('configs',owner)[0]
    params=config['params']
    params['normalize']['exclude']=['appData.request_id','appData.createDateTime']
    params['checks']={'my_changes':{'max_share':0.3}}
    meta.update('configs',config['id'],params=params)
    old_run=meta.put('runs',owner,{'config':config},'READY')
    custom=meta.put('configs',owner,{**config,'name':'Custom','params':{**params,'normalize':{**params['normalize'],'exclude':['custom']}}})
    seed(owner)
    updated=meta.get('configs',config['id'],owner)
    assert updated['params']['normalize']['exclude']==DEFAULT_EXCLUSIONS
    assert updated['params']['checks']==params['checks']
    assert meta.get('configs',custom['id'],owner)['params']['normalize']['exclude']==['custom']
    assert meta.get('runs',old_run['id'],owner)['config']['params']['normalize']['exclude']==['appData.request_id','appData.createDateTime']
