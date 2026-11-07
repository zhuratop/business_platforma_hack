"""Names from the immutable SPR response, including already completed runs."""

def named_families(con,stats):
    names={}
    for family,id_field,name_field in [('products','product_id','product_name'),('partners','partner_id','partner_name')]:
        rows=con.execute('''SELECT i.VALUE,list_sort(list(DISTINCT n.VALUE))
            FROM normalized_union i JOIN normalized_union n
            ON i.APP_ID=n.APP_ID AND i.SOURCE=n.SOURCE AND i.ARRAY_KEY=n.ARRAY_KEY
            WHERE i.PATH=? AND n.PATH=? AND n.VALUE_KIND='string' AND n.VALUE<>''
            GROUP BY i.VALUE''',[f'decisionResult.product_trials.{id_field}',f'decisionResult.product_trials.{name_field}']).fetchall()
        names[family]={str(id):' / '.join(values) for id,values in rows}
    families={}
    for family,items in stats.get('families',{}).items():
        fallback='Продукт' if family=='products' else 'Партнёр' if family=='partners' else 'Группа'
        families[family]=[{**item,'group_name':names.get(family,{}).get(str(item['group']),f"{fallback} {item['group']}"),
                         'name_available':str(item['group']) in names.get(family,{})} for item in items]
    return {**stats,'families':families}
