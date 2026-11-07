"""Lazy hierarchy over the immutable normalized union, with typed values."""
import json

from pydantic import BaseModel,Field
from typing import Any,Literal

from backend.app.core.pivot import token
from backend.app.storage.mart import records


class TreeRequest(BaseModel):
    path:str=Field(default='',max_length=4096)
    stage:Literal['path','keys','values']='path'
    array_key:str|None=Field(default=None,max_length=4096)
    filters:dict[str,list[Any]]=Field(default_factory=dict)
    page:int=Field(default=1,ge=1)
    page_size:int=Field(default=50,ge=1,le=100)


def scope(spec):
    clauses,args=[],[]
    path=spec.get('path','')
    if spec.get('exact'):
        clauses.append('n.PATH=?');args.append(path)
    elif path:
        clauses.append('(n.PATH=? OR starts_with(n.PATH,?))');args.extend([path,path+'.'])
    for field,column in [('array_key','ARRAY_KEY'),('value_kind','VALUE_KIND'),('value','ADJUSTED_VALUE')]:
        if spec.get(field) is not None:
            clauses.append('n."'+column+'" IS NOT DISTINCT FROM ?');args.append(spec[field])
    for key,values in spec.get('filters',{}).items():
        if key=='SOURCE' and all(v in ['BEFORE','AFTER'] for v in values) and len(values)<=2:
            column='n.SOURCE'
        elif key=='DIFF_FLAG' and all(type(v) is int and v in [0,1] for v in values) and len(values)<=2:
            column='c.DIFF_FLAG'
        else:
            raise ValueError('Дерево поддерживает только фильтры SOURCE и DIFF_FLAG')
        clauses.append(column+' IN ('+','.join('?' for _ in values)+')' if values else 'FALSE');args.extend(values)
    return '''WITH scoped AS (SELECT n.*,c.DIFF_FLAG FROM normalized_union n
        JOIN comparison_mart c USING(APP_ID,PATH,ARRAY_KEY)'''+(' WHERE '+' AND '.join(clauses) if clauses else '')+') ',args


def cells(run_id,spec,counts):
    result={}
    for source,count in zip(['BEFORE','AFTER','TOTAL'],counts):
        filters=dict(spec.get('filters',{}))
        if source!='TOTAL':filters['SOURCE']=[source]
        dimensions={}
        if spec.get('path'):dimensions['PATH']=spec['path']
        for key,name in [('array_key','ARRAY_KEY'),('value_kind','VALUE_KIND'),('value','VALUE_ADJUSTED')]:
            if spec.get(key) is not None:dimensions[name]=spec[key]
        if source!='TOTAL':dimensions['SOURCE']=source
        result[source]=dict(dimensions=dimensions,count=count,
                            cell_token=token(run_id,{'__tree':{**spec,'filters':filters}}))
    return result


COUNTS="""count(DISTINCT APP_ID) FILTER(WHERE SOURCE='BEFORE') AS before_count,
    count(DISTINCT APP_ID) FILTER(WHERE SOURCE='AFTER') AS after_count,
    count(DISTINCT APP_ID) AS total_count"""


def children(con,run_id,request):
    spec=dict(path=request.path,exact=request.stage!='path',filters=request.filters)
    if request.stage=='values':spec['array_key']=request.array_key
    prefix,args=scope(spec)
    if request.stage=='path':
        # Empty component represents scalar values at a path that also has children
        # in other JSON responses, preserving changes of JSON shape.
        depth=len(request.path.split('.'))+1 if request.path else 1
        group_sql=f'''SELECT CASE WHEN PATH=? THEN '' ELSE split_part(PATH,'.',{depth}) END AS component,
            {COUNTS},bool_or(ARRAY_KEY<>'') AS arrays
            FROM scoped GROUP BY component'''
        query_args=args+[request.path]
    elif request.stage=='keys':
        group_sql=f'SELECT ARRAY_KEY AS component,{COUNTS} FROM scoped GROUP BY ARRAY_KEY'
        query_args=args
    else:
        group_sql=f'SELECT ADJUSTED_VALUE AS component,VALUE_KIND AS value_kind,{COUNTS} FROM scoped GROUP BY ADJUSTED_VALUE,VALUE_KIND'
        query_args=args
    grouped=prefix+', grouped AS ('+group_sql+') '
    order='component,value_kind' if request.stage=='values' else 'component'
    rows=records(con,grouped+'SELECT *,count(*) OVER() AS group_count FROM grouped ORDER BY '+order+' LIMIT ? OFFSET ?',
                 query_args+[request.page_size,(request.page-1)*request.page_size])
    total_nodes=rows[0]['group_count'] if rows else con.execute(grouped+'SELECT count(*) FROM grouped',query_args).fetchone()[0]
    # A path with both scalar values and deeper fields must expose both branches.
    descendants={r[0] for r in con.execute(prefix+"SELECT DISTINCT PATH FROM scoped",args).fetchall()} if request.stage=='path' else set()
    nodes=[]
    for row in rows:
        component=row['component']
        if request.stage=='path':
            path=(request.path+'.' if request.path else '')+component if component else request.path
            nested=any(p.startswith(path+'.') for p in descendants) if component else False
            next_stage='path' if nested else 'keys' if row['arrays'] else 'values'
            child_spec=dict(path=path,exact=not nested,filters=request.filters)
            next_request=dict(path=path,stage=next_stage,array_key=None if row['arrays'] else '')
            label=component or 'Значения этого атрибута'
            kind='path'
        elif request.stage=='keys':
            path=request.path
            child_spec={**spec,'array_key':component}
            next_request=dict(path=path,stage='values',array_key=component)
            label=component if component else 'Без ключа массива'
            kind='array'
        else:
            path=request.path
            child_spec={**spec,'value_kind':row['value_kind'],'value':component}
            next_request=None
            if row['value_kind']=='null':label='null'
            elif row['value_kind']=='string':label=json.dumps(component,ensure_ascii=False)
            else:label=str(component)
            kind='value'
        identity=dict(path=path,kind=kind,stage=request.stage,component=component,array_key=child_spec.get('array_key'),value_kind=row.get('value_kind'))
        nodes.append(dict(id=json.dumps(identity,sort_keys=True,ensure_ascii=False),path=path,label=label,kind=kind,
            value_kind=row.get('value_kind'),has_children=next_request is not None,request=next_request,
            cells=cells(run_id,child_spec,[row['before_count'],row['after_count'],row['total_count']])))
    totals=con.execute(prefix+'SELECT '+COUNTS+' FROM scoped',args).fetchone()
    return dict(nodes=nodes,totals=cells(run_id,spec,totals),
                pagination=dict(page=request.page,page_size=request.page_size,total_nodes=total_nodes,
                                has_more=request.page*request.page_size<total_nodes),
                unit='unique APP_ID in each node; child counts and source counts are non-additive')


def apps(con,spec,page=1,page_size=50):
    if page<1 or not 1<=page_size<=200:raise ValueError('Invalid page')
    prefix,args=scope(spec)
    total=con.execute(prefix+'SELECT count(DISTINCT APP_ID) FROM scoped',args).fetchone()[0]
    ids=[r[0] for r in con.execute(prefix+'SELECT DISTINCT APP_ID FROM scoped ORDER BY APP_ID LIMIT ? OFFSET ?',args+[page_size,(page-1)*page_size]).fetchall()]
    return dict(app_ids=ids,total=total,page=page,page_size=page_size)


def matching_attributes(con,app_id,spec):
    prefix,args=scope(spec)
    return {(p,k) for p,k in con.execute(prefix+'SELECT DISTINCT PATH,ARRAY_KEY FROM scoped WHERE APP_ID=?',args+[app_id]).fetchall()}
