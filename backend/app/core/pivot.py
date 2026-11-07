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

def cells(con,run_id,request):
    dimensions = request.rows+request.columns
    if any(d not in DIMENSIONS for d in dimensions) or len(set(dimensions))!=len(dimensions) or len(dimensions)>8:
        raise ValueError('Invalid or duplicate pivot dimensions; max 8')
    clause,args = where(request.filters)
    cols = ','.join('f."'+d+'"' for d in dimensions)
    sql = 'SELECT '+(cols+',' if cols else '')+'count(DISTINCT m.APP_ID) AS count FROM pivot_facts f JOIN fact_memberships m USING(fact_id)'+clause+(' GROUP BY '+cols+' ORDER BY '+cols if cols else '')+' LIMIT 5001'
    rows = records(con,sql,args)
    truncated = len(rows)>5000
    result = []
    for row in rows[:5000]:
        dims = {d:row[d] for d in dimensions}
        merged = dict(request.filters)
        merged.update({k:[v] for k,v in dims.items()})
        result.append(dict(dimensions=dims,count=row['count'],cell_token=token(run_id,merged)))
    return dict(cells=result,dimensions=DIMENSIONS,truncated=truncated,unit='unique APP_ID per cell; counts across cells are non-additive')

def apps(con,filters,page=1,page_size=50):
    if page<1 or not 1<=page_size<=200:
        raise ValueError('Invalid page')
    clause,args = where(filters)
    from_sql = ' FROM pivot_facts f JOIN fact_memberships m USING(fact_id)'+clause
    total = con.execute('SELECT count(DISTINCT m.APP_ID)'+from_sql,args).fetchone()[0]
    ids = [r[0] for r in con.execute('SELECT DISTINCT m.APP_ID'+from_sql+' ORDER BY m.APP_ID LIMIT ? OFFSET ?',args+[page_size,(page-1)*page_size]).fetchall()]
    return dict(app_ids=ids,total=total,page=page,page_size=page_size)

def matching_attributes(con,app_id,filters):
    clause,args = where(filters)
    clause += (' AND ' if clause else ' WHERE ')+'m.APP_ID=?'
    return {(r['PATH'],r['ARRAY_KEY']) for r in records(con,'SELECT DISTINCT f.PATH,f.ARRAY_KEY FROM pivot_facts f JOIN fact_memberships m USING(fact_id)'+clause,args+[app_id])}
