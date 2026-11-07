"""Report layouts for the SPR response, not for the unrelated company demo."""
HIERARCHY = ['PREFIX','CLASS','SUFFIX','ARRAY_KEY','KEY','VALUE_ADJUSTED']
COMPARISON = ['DIFF_FLAG','SOURCE']
STRATEGY_FIELDS = {
    'decisionResult.decision': {'block':'Решение заявки','key':'decision'},
    'decisionResult.product_trials.decision': {'block':'Решения продуктов (компаний)','key':'decision'},
    'decisionResult.product_trials.rejectReason': {'block':'Причина отказа продукта','key':'rejectReason'},
    'decisionResult.product_trials.rejectReasonCode': {'block':'Код причины отказа','key':'rejectReasonCode'},
    'decisionResult.product_trials.scoring.pd.value': {'block':'Вероятность одобрения','key':'value'},
    'decisionResult.product_trials.scoring.pd.modelName': {'block':'Целевая модель одобрения','key':'modelName'},
    'decisionResult.product_trials.cutOff.value': {'block':'Порог одобрения','key':'value'},
}
VIEWS = [
    {'id':'strategy','label':'Стратегия · ключевые атрибуты',
     'description':'Решения, причины отказа, вероятность одобрения, модель и порог. Без технической иерархии и повторов по продуктам.',
     'rows':['PATH','VALUE_ADJUSTED'],'columns':COMPARISON,'filters':{'PATH':list(STRATEGY_FIELDS)},
     'attributes':STRATEGY_FIELDS},
    {'id':'decisions','label':'Итоговое решение заявки',
     'description':'Распределение итогового решения в каждом срезе, отдельно по признаку изменения.',
     'rows':['VALUE_ADJUSTED'],'columns':COMPARISON,'filters':{'PATH':['decisionResult.decision']}},
    {'id':'buckets','label':'Матрица переходов значений',
     'description':'Бакет до × бакет после для одного атрибута. PATH можно заменить в фильтрах.',
     'rows':['ADJUSTED_BEFORE'],'columns':['ADJUSTED_AFTER'],
     'filters':{'PATH':['decisionResult.decision']}},
]
