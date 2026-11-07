"""Domain-specific dimensions and separate product/offer grains."""
import math
from decimal import Decimal


def canonical(value):
    if value is None:
        return 'NULL', 'null'
    if isinstance(value, bool):
        return str(value).lower(), 'boolean'
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite JSON number')
        return format(Decimal(str(value)).normalize(), 'f'), 'number'
    if isinstance(value, str):
        return value, 'string'
    raise ValueError(f'Unsupported leaf: {type(value)}')


FACT_DIMENSIONS = ['SOURCE', 'PREFIX', 'CLASS', 'SUFFIX', 'ARRAY_KEY', 'KEY', 'PATH', 'VALUE_ADJUSTED', 'DIFF_FLAG', 'CHANGE_TYPE', 'product_id', 'partner_id', 'DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED', 'PARTNER_TYPE', 'ROUTING_METHOD']


def records(con,sql,args=None):
    cursor = con.execute(sql,args or [])
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols,r)) for r in cursor.fetchall()]


def aggregate_facts(mart, product_paths=()):
    # Domain adapter supplies path associations; core only knows table contracts.
    conditions = ' OR '.join('starts_with(n.PATH, ?)' for _ in product_paths) or 'FALSE'
    sql = f'''SELECT n.*, c.DIFF_FLAG,c.CHANGE_TYPE,s.DECISION_BEFORE,s.DECISION_AFTER,s.DECISION_CHANGED,s.PARTNER_TYPE,s.ROUTING_METHOD,
        CASE WHEN ({conditions}) THEN CASE WHEN starts_with(n.ARRAY_KEY,'[') THEN json_extract_string(split_part(n.ARRAY_KEY,'|',1),'$[0]') ELSE split_part(n.ARRAY_KEY,'|',1) END ELSE '' END AS product_id
        FROM normalized_union n JOIN comparison_mart c USING(APP_ID,PATH,ARRAY_KEY) JOIN app_segments s USING(APP_ID)'''
    # Use DuckDB for aggregation; Python sees aggregate memberships, not a browser-sized raw mart.
    mart.con.execute('CREATE TEMP TABLE enriched AS '+sql,list(product_paths))
    mart.con.execute('ALTER TABLE enriched ADD COLUMN partner_id VARCHAR')
    mart.con.execute("UPDATE enriched e SET partner_id=t.partner_id FROM product_trials t WHERE e.APP_ID=t.APP_ID AND e.SOURCE=t.SOURCE AND e.product_id=t.product_id")
    mart.con.execute("UPDATE enriched SET partner_id='' WHERE partner_id IS NULL")
    dims = ','.join('"'+d+'"' for d in FACT_DIMENSIONS)
    group_dims = dims.replace('"VALUE_ADJUSTED"','"ADJUSTED_VALUE" AS "VALUE_ADJUSTED"')
    for r in records(mart.con, f'SELECT {group_dims},count(DISTINCT APP_ID)::INTEGER AS CNT,list_sort(list(DISTINCT APP_ID)) AS APP_IDS FROM enriched GROUP BY ALL'):
        yield r
    mart.con.execute('DROP TABLE enriched')


def build_facts(mart, raw_pairs, params):
    def products(response):
        return response.get('decisionResult', {}).get('product_trials', [])

    def joined(response, accessor):
        return ';'.join(f"{p['product_id']}:{accessor(p) or ''}" for p in sorted(products(response), key=lambda p:str(p['product_id'])))

    def top(response):
        offers = response.get('decisionResult', {}).get('available_offers', [])
        ranked = [o for o in offers if o.get('rank') == 1]
        return str(ranked[0]['product_id']) if ranked else ''

    def segments():
        for app_id, b, a in raw_pairs():
            db, da = b['decisionResult']['decision'], a['decisionResult']['decision']
            combined = products(b) + products(a)
            r = dict(APP_ID=app_id, DECISION_BEFORE=db, DECISION_AFTER=da, DECISION_CHANGED=int(db!=da),
                     PRODUCTS=';'.join(sorted({str(p['product_id']) for p in combined})),
                     TOP_OFFER_BEFORE=top(b), TOP_OFFER_AFTER=top(a),
                     PARTNER_TYPE=';'.join(sorted({str(p.get('partner_type','')) for p in combined})),
                     ROUTING_METHOD=';'.join(sorted({str(p.get('routing_method','')) for p in combined})))
            for suffix, response in [('BEFORE', b), ('AFTER', a)]:
                r['PD_MODEL_'+suffix] = joined(response, lambda p:p.get('scoring',{}).get('pd',{}).get('modelName'))
                r['CUTOFF_'+suffix] = joined(response, lambda p:p.get('cutOff',{}).get('name'))
                r['REJECT_REASON_'+suffix] = joined(response, lambda p:p.get('rejectReason'))
                r['SCORE_OKB_'+suffix] = canonical(response.get('characteristics',{}).get('score_okb'))[0]
            yield r

    def trials():
        for app_id, b, a in raw_pairs():
            for source, response in [('BEFORE',b), ('AFTER',a)]:
                for p in products(response):
                    pd = p.get('scoring',{}).get('pd',{})
                    model = next((m for m in p.get('scoring',{}).get('scoreModels',[]) if m.get('modelName')==pd.get('modelName')), {})
                    yield dict(APP_ID=app_id, SOURCE=source, product_id=str(p['product_id']), decision=p.get('decision',''),
                               partner_id=str(p.get('partner_id','')), partner_type=p.get('partner_type',''),
                               pd_model=pd.get('modelName',''), target_score=pd.get('value'), target_score_type=model.get('type',''),
                               cutoff_name=p.get('cutOff',{}).get('name',''), cutoff_value=p.get('cutOff',{}).get('value'), epr=p.get('epr'))

    def offers():
        for app_id,b,a in raw_pairs():
            for source,response in [('BEFORE',b),('AFTER',a)]:
                for o in response['decisionResult'].get('available_offers',[]):
                    yield dict(APP_ID=app_id,SOURCE=source,product_id=str(o['product_id']),type=o['type'],rank=o.get('rank'))

    def pivot_facts():
        # Generic aggregation preserves typed presence and all memberships.
        yield from aggregate_facts(mart, product_paths=['decisionResult.product_trials.', 'decisionResult.available_offers.'])

    return dict(segments=segments(), product_trials=trials(), offers=offers(), pivot_facts=pivot_facts())
