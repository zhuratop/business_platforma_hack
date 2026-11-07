"""Unequal-variance t-test for partially overlapping samples.

Derrick, Toher & White (2017), equations 4-6:
https://www.tqmp.org/RegularArticles/vol13-2/p120/p120.pdf
Input dictionaries preserve the identity of shared observations.
"""
import math

import numpy as np
from scipy.stats import t as student_t


def overlapping_ttest(before, after, alpha=.05):
    if not 0 < alpha < 1:
        raise ValueError('alpha must be between 0 and 1')
    n1, n2 = len(before), len(after)
    common = sorted(before.keys() & after.keys())
    nc = len(common)
    method = 'paired_t' if nc == n1 == n2 else 'overlap_welch_t' if nc else 'welch_t'
    result = dict(method=method, n_before=n1, n_after=n2, n_common=nc, statistic=None,
                  df=None, p=None, alpha=alpha, status='unavailable', reason=None)
    if n1 < 2 or n2 < 2:
        return {**result, 'reason':'too_few_scores'}
    b, a = np.array(list(before.values())), np.array(list(after.values()))
    if not (np.isfinite(b).all() and np.isfinite(a).all()):
        return {**result, 'reason':'invalid_score'}
    v1, v2 = float(b.var(ddof=1)), float(a.var(ddof=1))
    r = 0.
    if nc:
        if nc < 2:
            return {**result, 'reason':'too_few_common_scores'}
        cb, ca = np.array([before[k] for k in common]), np.array([after[k] for k in common])
        if cb.var(ddof=1) == 0 or ca.var(ddof=1) == 0:
            return {**result, 'reason':'constant_common_scores'}
        r = float(np.clip(np.corrcoef(cb, ca)[0,1], -1., 1.))
    if method == 'paired_t':
        delta = ca - cb
        variance = float(delta.var(ddof=1)) / nc
        df = nc - 1
    else:
        variance = v1/n1 + v2/n2 - 2*r*math.sqrt(v1*v2)*nc/(n1*n2)
        denominator = (v1/n1)**2/(n1-1) + (v2/n2)**2/(n2-1)
        if denominator <= 0:
            return {**result, 'reason':'zero_variance'}
        gamma = (v1/n1 + v2/n2)**2 / denominator
        df = (nc-1) + (gamma-nc+1)/(n1+n2)*(n1+n2-2*nc)
    if variance <= 0 or not math.isfinite(variance) or df <= 0:
        return {**result, 'reason':'zero_variance'}
    statistic = float((a.mean()-b.mean()) / math.sqrt(variance))
    p = float(2*student_t.sf(abs(statistic), df))
    return {**result, 'statistic':statistic, 'df':float(df), 'p':p, 'status':'available'}
