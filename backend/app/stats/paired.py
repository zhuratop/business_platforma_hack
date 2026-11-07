import numpy as np
from scipy.stats import binomtest
from backend.app.storage.mart import records


def interval(deltas,params,statistic='mean'):
    x = np.asarray(deltas,dtype=float)
    n = len(x)
    if not n:
        return None
    rng = np.random.default_rng(params.get('seed',20260827))
    B = int(params.get('bootstrap',5000))
    if not 100 <= B <= 20000:
        raise ValueError('bootstrap must be between 100 and 20000')
    samples = []
    for start in range(0,B,100):
        sample = x[rng.integers(0,n,size=(min(100,B-start),n))]
        samples.extend((np.median(sample,axis=1) if statistic=='median' else sample.mean(axis=1)).tolist())
    alpha = float(params.get('alpha',0.05))
    if not 0 < alpha < 1:
        raise ValueError('alpha must be between 0 and 1')
    return [float(q) for q in np.quantile(samples,[alpha/2,1-alpha/2])]


def paired_binary(before,after,params):
    b,a = np.asarray(before,dtype=int),np.asarray(after,dtype=int)
    n = len(b)
    lost,gained = int(((b==1)&(a==0)).sum()),int(((b==0)&(a==1)).sum())
    return dict(n=n,before=int(b.sum()),after=int(a.sum()),lost=lost,gained=gained,
                delta=float((a-b).mean()) if n else None,ci=interval(a-b,params),
                p=float(binomtest(lost,lost+gained,0.5).pvalue) if lost+gained else 1.,
                information='insufficient' if n<30 or lost+gained==0 else 'available')


def holm(items):
    ordered = sorted(items,key=lambda r:r['p'])
    previous = 0.
    for index,row in enumerate(ordered):
        previous = min(1.,max(previous,row['p']*(len(ordered)-index)))
        row['p_adjusted'] = previous


def calculate(con,params):
    seg = records(con,'SELECT * FROM app_segments ORDER BY APP_ID')
    binary = lambda rows:paired_binary([r['DECISION_BEFORE']=='APPROVE' for r in rows],[r['DECISION_AFTER']=='APPROVE' for r in rows],params)
    app = binary(seg)
    counts = records(con,"""SELECT s.APP_ID,
          count(*) FILTER(WHERE t.SOURCE='BEFORE' AND t.decision='APPROVE') AS b,
          count(*) FILTER(WHERE t.SOURCE='AFTER' AND t.decision='APPROVE') AS a
          FROM app_segments s LEFT JOIN product_trials t USING(APP_ID) GROUP BY s.APP_ID ORDER BY s.APP_ID""")
    deltas = [r['a']-r['b'] for r in counts]
    products = dict(n=len(counts),before=sum(r['b'] for r in counts),after=sum(r['a'] for r in counts),
                    delta=float(np.mean(deltas)),median_delta=float(np.median(deltas)),ci=interval(deltas,params),median_ci=interval(deltas,params,'median'),unit='products per application')
    families = {}
    for col,field in [('product_id','products'),('partner_id','partners')]:
        family = []
        for value in params.get(field,[]):
            if col == 'product_id':
                pairs = records(con,"""SELECT b.APP_ID,b.decision AS b,a.decision AS a FROM product_trials b JOIN product_trials a
                    ON b.APP_ID=a.APP_ID AND b.product_id=a.product_id WHERE b.SOURCE='BEFORE' AND a.SOURCE='AFTER' AND b.product_id=?""",[value])
            else:
                pairs = records(con,"""SELECT b.APP_ID,bool_or(b.decision='APPROVE') AS b,bool_or(a.decision='APPROVE') AS a
                    FROM product_trials b JOIN product_trials a ON b.APP_ID=a.APP_ID AND b.product_id=a.product_id AND b.partner_id=a.partner_id
                    WHERE b.SOURCE='BEFORE' AND a.SOURCE='AFTER' AND b.partner_id=? GROUP BY b.APP_ID""",[value])
            result = paired_binary([r['b']=='APPROVE' if col=='product_id' else r['b'] for r in pairs], [r['a']=='APPROVE' if col=='product_id' else r['a'] for r in pairs],params)
            presence = records(con,f'SELECT SOURCE,count(DISTINCT APP_ID) AS n FROM product_trials WHERE "{col}"=? GROUP BY SOURCE',[value])
            result.update(group=str(value),coverage={r['SOURCE']:r['n'] for r in presence},family=field)
            if col=='product_id':
                membership = records(con,"SELECT APP_ID,bool_or(SOURCE='BEFORE') AS b,bool_or(SOURCE='AFTER') AS a FROM product_trials WHERE product_id=? GROUP BY APP_ID",[value])
                result.update(appeared=sum(not r['b'] and r['a'] for r in membership),disappeared=sum(r['b'] and not r['a'] for r in membership))
            family.append(result)
        holm(family)
        families[field] = family
    score = records(con,"""SELECT b.APP_ID,avg(a.target_score-b.target_score) AS delta FROM product_trials b JOIN product_trials a
        ON b.APP_ID=a.APP_ID AND b.product_id=a.product_id AND b.pd_model=a.pd_model AND b.target_score_type=a.target_score_type
        WHERE b.SOURCE='BEFORE' AND a.SOURCE='AFTER' AND b.target_score IS NOT NULL AND a.target_score IS NOT NULL
        AND b.target_score_type='APPROVAL_PROBABILITY' GROUP BY b.APP_ID""")
    pd = dict(n=len(score),delta=float(np.mean([r['delta'] for r in score])) if score else None,ci=interval([r['delta'] for r in score],params),
              median_delta=float(np.median([r['delta'] for r in score])) if score else None,median_ci=interval([r['delta'] for r in score],params,'median'),
              type='APPROVAL_PROBABILITY',unit='mean per-app score delta, same model and scale')
    external = [r for r in seg if r['SCORE_OKB_BEFORE'] == r['SCORE_OKB_AFTER']]
    same_model = [r for r in seg if r['PD_MODEL_BEFORE'] == r['PD_MODEL_AFTER']]
    return dict(app_approval_rate=app,approved_products=products,target_score=pd,families=families,
                strata={'external_unchanged':binary(external),'target_model_unchanged':binary(same_model)},
                alpha=params.get('alpha',0.05),bootstrap=params.get('bootstrap',5000),seed=params.get('seed',20260827),
                method='Paired APP_ID percentile bootstrap; exact McNemar; Holm within configured families',
                interpretation='Исторический парный набор, не рандомизированный A/B-тест. Интервалы применимы к будущему потоку при репрезентативности и независимости заявок. Смена внешних данных смешивает факторы; причинность не установлена.')


def decision(stats,checks,thresholds):
    conditions = []
    for key,metric,scale in [('allowed_approval_drop_pp','app_approval_rate',100),('allowed_products_drop','approved_products',1)]:
        limit = thresholds.get(key)
        ci = stats[metric]['ci']
        state = 'unknown' if limit is None or ci is None else 'passed' if ci[0]*scale >= -limit else 'violated' if ci[1]*scale < -limit else 'uncertain'
        conditions.append(dict(metric_id=metric,status=state,threshold=limit,ci=ci))
    conditions.append(dict(metric_id='mandatory_checks',status='uncertain' if any(r['RESULT']=='FAIL' for r in checks) else 'passed'))
    conditions.extend(dict(metric_id=m,status='unknown') for m in ['pd_default','offered_limit'])
    states = {c['status'] for c in conditions}
    status = 'hold_current' if 'violated' in states else 'investigate' if 'uncertain' in states else 'needs_data' if 'unknown' in states else 'pilot_candidate'
    return dict(status=status,preferred_strategy='BEFORE' if status=='hold_current' else 'AFTER' if status=='pilot_candidate' else 'undetermined',
                working_action='Пока оставить BEFORE; проверить пороги, сигналы и недостающие данные',conditions=conditions)
