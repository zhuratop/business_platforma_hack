import pytest
from scipy.stats import ttest_ind, ttest_rel

from backend.app.stats.overlap_t import overlapping_ttest


def test_published_partially_overlapping_example():
    # TQMP 2017 13(2) p120, Table 1 and equations 4-6 (unequal variances).
    before={f'b{i}':x for i,x in enumerate([20,21,16,18,14,12,14,17])}
    after={f'a{i}':x for i,x in enumerate([10,16,18,16,15,14,13,10])}
    before.update({f'p{i}':x for i,x in enumerate([14,15,18,20,11,19,14,15])})
    after.update({f'p{i}':x for i,x in enumerate([15,10,15,17,13,19,12,13])})
    test=overlapping_ttest(before,after)
    assert test['method']=='overlap_welch_t' and test['n_common']==8
    assert abs(test['statistic'])==pytest.approx(2.419,abs=.001)
    assert test['df']==pytest.approx(18.422,abs=.001)
    assert test['p']==pytest.approx(.026,abs=.001)


def test_limits_match_scipy_and_degenerate_data_stay_unavailable():
    b,a=[10,20,30,45],[13,22,35,50]
    paired=overlapping_ttest(dict(enumerate(b)),dict(enumerate(a)))
    assert paired['p']==pytest.approx(ttest_rel(a,b).pvalue)
    independent=overlapping_ttest(dict(enumerate(b)),{i+10:x for i,x in enumerate(a)})
    assert independent['p']==pytest.approx(ttest_ind(a,b,equal_var=False).pvalue)
    assert overlapping_ttest({}, {})['p'] is None
    assert overlapping_ttest({1:5,2:5},{1:5,2:5})['p'] is None
