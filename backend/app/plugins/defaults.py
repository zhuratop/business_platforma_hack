from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXCLUSIONS = ['appData', 'ext_data', 'product_catalog', 'tariff_matrix']
ARRAYS = {
    'decisionResult.available_offers': {'mode':'fields','keys':['product_id','type']},
    'decisionResult.product_trials': {'mode':'fields','keys':['product_id']},
    'decisionResult.product_trials.rules': {'mode':'fields','keys':['name']},
    'decisionResult.product_trials.scoring.scoreModels': {'mode':'fields','keys':['modelName']},
    'decisionResult.scoring': {'mode':'fields','keys':['modelName']},
    'decisionResult.scoring.value': {'mode':'index'},
    'ext_data': {'mode':'fields','keys':['body.action']},
    'product_catalog': {'mode':'fields','keys':['mfo_id','product_id']},
    'tariff_matrix': {'mode':'fields','keys':['mfo_id','product_id']},
}

def default_params():
    return {'normalize': {'exclude':list(DEFAULT_EXCLUSIONS), 'arrays':ARRAYS,
                          'buckets': {'decisionResult.product_trials.scoring.pd.value': [
                              {'min':None,'max':0.3,'label':'[0, 0.3]'}, {'min':0.3,'max':0.6,'label':'(0.3, 0.6]'}, {'min':0.6,'max':None,'label':'(0.6, 1]'}]}},
            'reader':{}, 'processing':{'batch_pairs':25}, 'compare':{}, 'facts':{}, 'checks':{},
            'stats':{'bootstrap':5000,'seed':20260827,'alpha':0.05,'products':['5123','15210','91741','12412','751'], 'partners':['1233','1450','1602','1777','1901']},
            'thresholds':{'allowed_approval_drop_pp':None,'allowed_products_drop':None}}
