import base64
import hashlib
import hmac
import json
import os
from backend.app.domain.contracts import DIMENSIONS
from backend.app.storage import meta
from backend.app.storage.mart import records

def secret():
    path = meta.RUNTIME/'cell-secret'
    if not path.exists():
        try:
            with path.open('xb') as f:
                f.write(os.urandom(32))
        except FileExistsError:
            pass
    return path.read_bytes()

def token(run_id,filters):
    payload = json.dumps({'run_id':run_id,'filters':filters},sort_keys=True,separators=(',',':')).encode()
    sig = hmac.new(secret(),payload,hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig+payload).decode()

def decode(value,run_id):
    try:
        raw = base64.b64decode(value,altchars=b'-_',validate=True)
        sig,payload = raw[:32],raw[32:]
        if not hmac.compare_digest(sig,hmac.new(secret(),payload,hashlib.sha256).digest()):
            raise ValueError()
        p = json.loads(payload)
        if p['run_id']!=run_id:
            raise ValueError()
        return p['filters']
    except Exception:
        raise ValueError('Invalid pivot cell token') from None

def where(filters):
    clauses,args = [],[]
    for key,values in filters.items():
        if key not in DIMENSIONS or not isinstance(values,list):
            raise ValueError('Unknown pivot dimension or invalid filter')
        if len(values)>1000:
            raise ValueError('Too many filter values')
        clauses.append('f."'+key+'" IN ('+','.join('?' for _ in values)+')' if values else 'FALSE')
        args.extend(values)
    return (' WHERE '+' AND '.join(clauses) if clauses else ''),args

def relation(required):
    """One read-only relation for cells, memberships and attribute highlighting.

    Global attributes belong to each participating product/partner across the
    pair, including products lost in one slice. Product attributes retain their
    own source-specific association. Expand only when these dimensions are used.
    Paired buckets come from each member's comparison row, not an aggregate's
    current SOURCE bucket. Existing immutable run files need no migration.
    """
    product_scope = bool({'product_id','partner_id'} & set(required))
    buckets = bool({'ADJUSTED_BEFORE','ADJUSTED_AFTER'} & set(required))
    selection = 'f.*'
    joins = ''
    if product_scope:
        selection = '''f.* EXCLUDE(product_id,partner_id),
            CASE WHEN f.product_id='' THEN coalesce(p.product_id,'') ELSE f.product_id END AS product_id,
            CASE WHEN f.product_id='' THEN coalesce(p.partner_id,'') ELSE f.partner_id END AS partner_id'''
        joins += ''' LEFT JOIN (SELECT DISTINCT APP_ID,product_id,partner_id FROM product_trials) p
            ON f.product_id='' AND p.APP_ID=m.APP_ID'''
    if buckets:
        selection += ',c.ADJUSTED_BEFORE,c.ADJUSTED_AFTER'
        joins += ''' JOIN comparison_mart c ON c.APP_ID=m.APP_ID
            AND c.PATH=f.PATH AND c.ARRAY_KEY=f.ARRAY_KEY'''
    return f'''WITH scoped AS (SELECT {selection},m.APP_ID
        FROM pivot_facts f JOIN fact_memberships m USING(fact_id){joins}) '''

def cells(con,run_id,request):
    dimensions = request.rows+request.columns
    if any(d not in DIMENSIONS for d in dimensions) or len(set(dimensions))!=len(dimensions) or len(dimensions)>8:
        raise ValueError('Invalid or duplicate pivot dimensions; max 8')
    clause,args = where(request.filters)
    cols = ','.join('f."'+d+'"' for d in dimensions)
    prefix = relation(dimensions+list(request.filters))
    grouped = 'SELECT '+(cols+',' if cols else '')+'count(DISTINCT f.APP_ID) AS count FROM scoped f'+clause+(' GROUP BY '+cols if cols else '')
    totals = None
    if request.include_totals or request.page_size is not None:
        col_cols = ','.join('f."'+d+'"' for d in request.columns)
        total_sql = prefix+'SELECT '+(col_cols+',' if col_cols else '')+'count(DISTINCT f.APP_ID) AS count FROM scoped f'+clause+(' GROUP BY '+col_cols+' ORDER BY '+col_cols if col_cols else '')+' LIMIT 129'
        totals = records(con,total_sql,args)
        if len(totals)>128:
            raise ValueError('Слишком много колонок сводной (более 128). Уточните фильтры или перенесите измерение в строки.')
    total_rows = None
    if request.page_size is not None:
        row_cols = ','.join('"'+d+'"' for d in request.rows)
        ranked = prefix+', grouped AS ('+grouped+'), ranked AS (SELECT *, '+('dense_rank() OVER(ORDER BY '+row_cols+')' if row_cols else '1')+' AS _row_num FROM grouped) '
        total_rows = con.execute(ranked+'SELECT coalesce(max(_row_num),0) FROM ranked',args).fetchone()[0]
        first = (request.page-1)*request.page_size+1
        sql = ranked+'SELECT * EXCLUDE(_row_num) FROM ranked WHERE _row_num BETWEEN ? AND ?'+(' ORDER BY '+','.join('"'+d+'"' for d in dimensions) if dimensions else '')
        rows = records(con,sql,args+[first,first+request.page_size-1])
        # A row page is complete, including every matching column combination.
        truncated = False
    else:
        rows = records(con,prefix+grouped+(' ORDER BY '+cols if cols else '')+' LIMIT 5001',args)
        truncated = len(rows)>5000
    result = []
    for row in (rows if request.page_size is not None else rows[:5000]):
        dims = {d:row[d] for d in dimensions}
        merged = dict(request.filters)
        merged.update({k:[v] for k,v in dims.items()})
        result.append(dict(dimensions=dims,count=row['count'],cell_token=token(run_id,merged)))
    response = dict(cells=result,dimensions=DIMENSIONS,truncated=truncated,
                    pagination=dict(page=request.page,page_size=request.page_size,total_rows=total_rows),
                    unit='unique APP_ID per cell; counts across cells are non-additive')
    if totals is not None:
        response['column_totals'] = [dict(dimensions={d:r[d] for d in request.columns},count=r['count'],
            cell_token=token(run_id,{**request.filters,**{d:[r[d]] for d in request.columns}})) for r in totals]
        total = con.execute(prefix+'SELECT count(DISTINCT f.APP_ID) FROM scoped f'+clause,args).fetchone()[0]
        response['grand_total'] = dict(dimensions={},count=total,cell_token=token(run_id,request.filters))
    if request.collapse_unchanged:
        if request.columns != ['DIFF_FLAG','SOURCE'] or not request.include_totals:
            raise ValueError('Collapsed comparison requires DIFF_FLAG/SOURCE columns and totals')
        # Aggregate memberships again: summing cells would double-count APP_IDs
        # shared by sources, products, or changed values inside the same bucket.
        keys = list(dict.fromkeys(tuple(r[d] for d in request.rows) for r in rows))
        page_args = []
        if keys and request.rows:
            page_filter = ' OR '.join('('+' AND '.join('f."'+d+'" IS NOT DISTINCT FROM ?' for d in request.rows)+')' for _ in keys)
            page_args = [value for key in keys for value in key]
            page_clause = (' AND ' if clause else ' WHERE ')+'('+page_filter+')'
        else:
            page_clause = '' if keys else (' AND FALSE' if clause else ' WHERE FALSE')
        row_columns = ','.join('f."'+d+'"' for d in request.rows)
        aggregates = records(con,prefix+'SELECT '+(row_columns+',' if row_columns else '')+
            'count(DISTINCT f.APP_ID) AS total,count(DISTINCT f.APP_ID) FILTER(WHERE f.DIFF_FLAG=0) AS stable FROM scoped f'+clause+page_clause+
            (' GROUP BY '+row_columns if row_columns else ''),args+page_args)
        response.update(collapse_unchanged=True,row_totals=[],unchanged_cells=[])
        for row in aggregates:
            dims = {d:row[d] for d in request.rows}
            filters = {**request.filters,**{d:[v] for d,v in dims.items()}}
            response['row_totals'].append(dict(dimensions=dims,count=row['total'],cell_token=token(run_id,filters)))
            response['unchanged_cells'].append(dict(dimensions=dims,count=row['stable'],cell_token=token(run_id,{**filters,'DIFF_FLAG':[0]})))
        stable = con.execute(prefix+'SELECT count(DISTINCT f.APP_ID) FILTER(WHERE f.DIFF_FLAG=0) FROM scoped f'+clause,args).fetchone()[0]
        response['unchanged_total'] = dict(dimensions={'DIFF_FLAG':0},count=stable,cell_token=token(run_id,{**request.filters,'DIFF_FLAG':[0]}))
    return response

def apps(con,filters,page=1,page_size=50):
    if '__tree' in filters:
        from backend.app.core.attribute_tree import apps as tree_apps
        return tree_apps(con,filters['__tree'],page,page_size)
    if page<1 or not 1<=page_size<=200:
        raise ValueError('Invalid page')
    clause,args = where(filters)
    from_sql = ' FROM scoped f'+clause
    prefix = relation(filters)
    total = con.execute(prefix+'SELECT count(DISTINCT f.APP_ID)'+from_sql,args).fetchone()[0]
    ids = [r[0] for r in con.execute(prefix+'SELECT DISTINCT f.APP_ID'+from_sql+' ORDER BY f.APP_ID LIMIT ? OFFSET ?',args+[page_size,(page-1)*page_size]).fetchall()]
    return dict(app_ids=ids,total=total,page=page,page_size=page_size)

def matching_attributes(con,app_id,filters):
    if '__tree' in filters:
        from backend.app.core.attribute_tree import matching_attributes as tree_matching
        return tree_matching(con,app_id,filters['__tree'])
    clause,args = where(filters)
    clause += (' AND ' if clause else ' WHERE ')+'f.APP_ID=?'
    return {(r['PATH'],r['ARRAY_KEY']) for r in records(con,relation(filters)+'SELECT DISTINCT f.PATH,f.ARRAY_KEY FROM scoped f'+clause,args+[app_id])}
