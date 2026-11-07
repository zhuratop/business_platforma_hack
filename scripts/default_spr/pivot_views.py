"""Report layouts for the SPR response, not for the unrelated company demo."""
HIERARCHY = ['PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','VALUE_ADJUSTED']
COMPARISON = ['DIFF_FLAG','SOURCE']
VIEWS = [
    {'id':'strategy','label':'Стратегия · ключевые атрибуты',
     'description':'Решения заявок и продуктов, правила, целевой скор и пороги.',
     'rows':HIERARCHY,'columns':COMPARISON,'filters':{'PATH':[
         'decisionResult.decision','decisionResult.product_trials.decision',
         'decisionResult.product_trials.rules.hit',
         'decisionResult.product_trials.scoring.pd.modelName',
         'decisionResult.product_trials.scoring.pd.value',
         'decisionResult.product_trials.cutOff.name','decisionResult.product_trials.cutOff.value']}},
    {'id':'decisions','label':'Итоговое решение заявки',
     'description':'Распределение итогового решения в каждом срезе, отдельно по признаку изменения.',
     'rows':['VALUE_ADJUSTED'],'columns':COMPARISON,'filters':{'PATH':['decisionResult.decision']}},
    {'id':'buckets','label':'Матрица переходов значений',
     'description':'Бакет до × бакет после для одного атрибута. PATH можно заменить в фильтрах.',
     'rows':['ADJUSTED_BEFORE'],'columns':['ADJUSTED_AFTER'],
     'filters':{'PATH':['decisionResult.decision']}},
]
