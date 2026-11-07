"""Adapter for example/, deliberately independent of the SPR response adapter."""
from backend.app.core.normalize import flatten

PARAMS = {
 'exclude':['company.decisionResult.calculatedAt'],
 'arrays':{'company.scoreCardResult':{'mode':'fields','keys':['name']},'company.rejectReasons':{'mode':'value'}},
 'aliases':{
  **{f'company.scoreCardResult.{k}':f'company.scoreCardResult.scoreCard.{k}' for k in ['name','value','version']},
  **{f'company.limitResult.{k}':f'company.limitResult.Limit.{k}' for k in ['limit','currency']},
  'company.rejectReasons':'company.rejectReasons.reason.code'},
 'buckets':{'company.scoreCardResult.value':[
  {'min':0,'max':0.3,'label':'(0 - 0.3]'}, {'min':0.3,'max':0.6,'label':'(0.3 - 0.6]'}],
  'company.limitResult.limit':[{'min':0,'max':100000,'label':'(0 - 100K]'}, {'min':100000,'max':250000,'label':'(100K - 250K]'}]}}

def normalize(response, app_id, source, params=None):
    return flatten(response, app_id, source, {**PARAMS, **(params or {})})
