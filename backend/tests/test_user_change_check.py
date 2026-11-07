from pathlib import Path

import pytest

from backend.app.core.execution import compile_script,run_checks


CODE=(Path(__file__).resolve().parents[2]/'scripts/templates/check_changed_share.py').read_text(encoding='utf-8')


class Mart:
    def __init__(self,changed,total=100):self.changed,self.total=changed,total
    def total_apps(self):return self.total
    def app_ids(self,**kwargs):return [str(i) for i in range(self.changed)]


def test_real_threshold_controls_pass_fail_and_remains_in_result():
    snapshot={'name':'user.py','code':CODE,'params':{}}
    check=compile_script(snapshot)['CHECK']
    assert check['entrypoint'](Mart(25),{})[0]['RESULT']=='PASS'
    assert check['entrypoint'](Mart(30),{})[0]['RESULT']=='PASS'
    assert check['entrypoint'](Mart(31),{})[0]['RESULT']=='FAIL'
    assert check['entrypoint'](Mart(25),{'max_share':.1})[0]['RESULT']=='FAIL'
    assert check['entrypoint'](Mart(0,0),{})[0]['RESULT']=='FAIL'
    with pytest.raises(ValueError):check['entrypoint'](Mart(0),{'max_share':1.5})
    row=run_checks(Mart(25),{'script':snapshot},['script'],{})[0]
    assert row['threshold']=={'value':.3,'parameter':'max_share','operator':'>'}
    assert row['METRIC']==.25 and row['CNT']==25 and len(row['APP_IDS'])==20
