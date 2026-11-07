import pytest
from backend.app.stats.paired import paired_binary,interval,holm,decision

P = {'bootstrap':5000,'seed':20260827,'alpha':0.05}

def test_exact_mcnemar_known_cases():
    r = paired_binary([1]*10,[0]*10,P)
    assert r['p']==pytest.approx(2/1024)
    assert r['delta']==-1 and r['ci']==[-1.,-1.]
    equal = paired_binary([0,1,1],[0,1,1],P)
    assert equal['p']==1 and equal['ci']==[0.,0.] and equal['information']=='insufficient'
    open_set = paired_binary([1]*273+[0]*112+[1]*384+[0]*1233,[0]*273+[1]*112+[1]*384+[0]*1233,P)
    assert open_set['n']==2002
    assert open_set['p']==pytest.approx(1.254165079861648e-16)

def test_bootstrap_is_paired_reproducible():
    assert interval([3]*50,P)==[3.,3.]
    assert interval([-1,0,1]*30,P)==interval([-1,0,1]*30,P)
    assert interval([],P) is None

def test_holm_monotonic_known_example():
    rows = [{'p':0.01},{'p':0.03},{'p':0.04}]
    holm(rows)
    assert [r['p_adjusted'] for r in rows]==[0.03,0.06,0.06]

def test_decision_thresholds_no_default_zero():
    stats={'app_approval_rate':{'ci':[-0.1,-0.06]},'approved_products':{'ci':[-0.3,-0.1]}}
    assert decision(stats,[],{})['status']=='needs_data'
    d = decision(stats,[],{'allowed_approval_drop_pp':5,'allowed_products_drop':1})
    assert d['status']=='hold_current' and d['preferred_strategy']=='BEFORE'
    assert decision(stats,[{'RESULT':'FAIL'}],{})['status']=='investigate'
