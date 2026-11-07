"""Domain-specific dimensions and separate product/offer grains."""
from backend.app.core.normalize import canonical


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
        yield from mart.default_facts(product_paths=['decisionResult.product_trials.', 'decisionResult.available_offers.'])

    return dict(segments=segments(), product_trials=trials(), offers=offers(), pivot_facts=pivot_facts())
