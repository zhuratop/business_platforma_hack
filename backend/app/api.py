import hashlib
import hmac
import json
import secrets
import subprocess
import sys
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
import duckdb
from fastapi import FastAPI,Body,Depends,HTTPException,Request,Response,UploadFile,File
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from backend.app.storage import meta
from backend.app.storage.mart import MartAPI
from backend.app.core import importer,pivot
from backend.app.core.execution import seed,snapshots
from backend.app.domain.contracts import PivotRequest,DIMENSIONS,DIMENSION_GROUPS,DIMENSION_LABELS

@asynccontextmanager
async def lifespan(app):
    meta.init()
    yield

app = FastAPI(title='Система анализа изменений СПР',lifespan=lifespan)

def ok(data=None,id=None,status='ok'):
    return dict(id=id,status=status,data=data)

@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content=dict(id=None,status='error',error=dict(code=str(exc.status_code),message=str(exc.detail),details=None)))

@app.exception_handler(KeyError)
async def missing(request,exc):
    return JSONResponse(status_code=404,content=dict(id=None,status='error',error=dict(code='not_found',message='Объект не найден',details=None)))

@app.exception_handler(ValueError)
async def invalid(request,exc):
    return JSONResponse(status_code=400,content=dict(id=None,status='error',error=dict(code='invalid_input',message=str(exc),details=None)))

@app.exception_handler(RequestValidationError)
async def invalid_request(request,exc):
    return JSONResponse(status_code=422,content=dict(id=None,status='error',error=dict(code='validation_error',message='Неверная схема запроса',details=str(exc))))

@app.exception_handler(SyntaxError)
async def invalid_python(request,exc):
    return JSONResponse(status_code=400,content=dict(id=None,status='error',error=dict(code='python_syntax',message=str(exc),details=None)))

@app.exception_handler(OSError)
@app.exception_handler(zipfile.BadZipFile)
async def invalid_file(request,exc):
    return JSONResponse(status_code=400,content=dict(id=None,status='error',error=dict(code='file_error',message=str(exc),details=None)))

def user(request:Request):
    token = request.cookies.get('spr_session','')
    with meta.db() as c:
        row = c.execute('SELECT u.id,u.name FROM users u JOIN sessions s ON s.owner_id=u.id WHERE s.token=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row is None:
        raise HTTPException(401,'Войдите в систему')
    return dict(row)

def owned_run(id,owner,ready=False):
    run = meta.get('runs',id,owner)
    if ready and run['status']!='READY':
        raise HTTPException(409,'Отчёт доступен после READY')
    return run

def public_run(run):
    return {k:v for k,v in run.items() if k not in ['snapshots','stats','checks','summary','mart_path','owner_id']}

def current_scripts(owner):
    scripts = meta.listing('scripts',owner)
    for script in scripts:
        if script['source']=='file':
            path = Path(script['path']).resolve()
            if path.suffix=='.py' and path.is_file() and any(path.is_relative_to(root) for root in [meta.ROOT/'scripts',meta.RUNTIME/'scripts',meta.DATA_ROOT/'checks']):
                script['code'] = path.read_text(encoding='utf-8-sig')
        script['hash'] = hashlib.sha256(script['code'].encode()).hexdigest()
    from backend.app.core.script_names import named_scripts
    return named_scripts(scripts)

@app.post('/api/auth/login')
def login(response:Response,body:dict=Body(...)):
    with meta.db() as c:
        row = c.execute('SELECT * FROM users WHERE name=?',(body.get('username'),)).fetchone()
        if row is None or not hmac.compare_digest(row['password'],meta.password_hash(body.get('password',''),row['salt'])):
            raise HTTPException(401,'Неверное имя или пароль')
        token = secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],meta.now()))
    response.set_cookie('spr_session',token,httponly=True,samesite='strict',max_age=86400*7)
    seed(row['id'])
    return ok(dict(id=row['id'],name=row['name']))

@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    with meta.db() as c:
        c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('spr_session','').encode()).hexdigest(),))
    response.delete_cookie('spr_session')
    return ok()

@app.get('/api/auth/me')
def me(u=Depends(user)):
    return ok(u)

@app.get('/api/bootstrap')
def bootstrap(u=Depends(user)):
    seed(u['id'])
    from scripts.default_spr.pivot_views import VIEWS
    return ok(dict(user=u,data_root=str(meta.DATA_ROOT),default_dataset=str(meta.DATA_ROOT/'data'/'RUN-20260827-0001'),
                   dimensions=DIMENSIONS,dimension_groups=DIMENSION_GROUPS,dimension_labels=DIMENSION_LABELS,pivot_views=VIEWS,files=[str(p) for p in (meta.ROOT/'scripts').rglob('*.py') if p.parent.name in ['default_spr','checks']],
                   datasets=meta.dataset_listing(u['id']),configs=meta.listing('configs',u['id']),scripts=current_scripts(u['id']),
                   runs=[public_run(r) for r in meta.listing('runs',u['id'])]))

@app.get('/api/datasets')
def datasets(limit:int=100,offset:int=0,u=Depends(user)):
    return ok(meta.dataset_listing(u['id'],min(max(limit,1),200),max(0,offset)))

@app.post('/api/datasets/register')
def register(body:dict=Body(...),u=Depends(user)):
    ds = importer.snapshot(u['id'],Path(body['path']),body.get('name'))
    return ok(ds,ds['id'])

@app.post('/api/datasets/upload')
def upload(file:UploadFile=File(...),u=Depends(user)):
    meta.RUNTIME.mkdir(parents=True,exist_ok=True)
    path = meta.RUNTIME/(meta.uid()+'.zip')
    count = 0
    with path.open('wb') as f:
        while chunk:=file.file.read(1024*1024):
            count += len(chunk)
            if count>importer.MAX_BYTES:
                raise ValueError('ZIP upload exceeds 1 GiB')
            f.write(chunk)
    ds = importer.unzip(u['id'],path,file.filename)
    path.unlink()
    return ok(ds,ds['id'])

@app.get('/api/datasets/{id}')
def dataset(id:str,u=Depends(user)):
    return ok(meta.get('datasets',id,u['id']),id)

@app.get('/api/scripts')
def scripts(u=Depends(user)):
    return ok(current_scripts(u['id']))

@app.post('/api/scripts')
def save_script(body:dict=Body(...),u=Depends(user)):
    if body.get('kind') not in ['normalize','compare','facts','check'] or body.get('source') not in ['editor','file']:
        raise ValueError('Invalid script kind/source')
    if body.get('id'):
        meta.get('scripts',body['id'],u['id'])
    payload = {k:body.get(k) for k in ['name','kind','source','code','path']}
    payload['params'] = body.get('params',{})
    if not isinstance(payload['params'],dict) or not payload['name']:
        raise ValueError('Script name and parameter object required')
    if payload['source']=='file':
        p = Path(payload['path']).resolve()
        if p.suffix!='.py' or not any(p.is_relative_to(root) for root in [meta.ROOT/'scripts',meta.RUNTIME/'scripts',meta.DATA_ROOT/'checks']):
            raise ValueError('Python file outside allowed script roots')
        payload['code'] = p.read_text(encoding='utf-8-sig')
    if not isinstance(payload['code'],str) or len(payload['code'])>1000000:
        raise ValueError('Python code required; max 1 MB')
    compile(payload['code'],payload['name'],'exec')
    s = meta.put('scripts',u['id'],payload,id=body.get('id'))
    s['hash'] = hashlib.sha256(s['code'].encode()).hexdigest()
    return ok(s,s['id'])

@app.post('/api/scripts/upload')
def upload_script(file:UploadFile=File(...),kind:str='check',u=Depends(user)):
    if not (file.filename or '').endswith('.py') or kind not in ['normalize','compare','facts','check']:
        raise ValueError('Upload a .py file and valid kind')
    raw = file.file.read(1000001)
    if len(raw)>1000000:
        raise ValueError('Script exceeds 1 MB')
    code = raw.decode('utf-8-sig')
    compile(code,file.filename,'exec')
    folder = meta.RUNTIME/'scripts'
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/(meta.uid()+'.py')
    path.write_text(code,encoding='utf-8')
    return save_script(dict(name=file.filename,kind=kind,source='file',path=str(path)),u)

@app.post('/api/scripts/validate')
def validate_script(body:dict=Body(...),u=Depends(user)):
    if body.get('script_id'):
        meta.get('scripts',body['script_id'],u['id'])
        s = next(s for s in current_scripts(u['id']) if s['id']==body['script_id'])
    else:
        s = body['script']
    folder = meta.RUNTIME/'validation'
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/(meta.uid()+'.json')
    path.write_text(json.dumps(dict(script=s,params=body.get('params',{})),ensure_ascii=False),encoding='utf-8')
    flags = {'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    try:
        result = subprocess.run([sys.executable,'-m','backend.app.core.validator',str(path)],cwd=meta.ROOT,timeout=20,capture_output=True,**flags)
    except subprocess.TimeoutExpired:
        return ok(dict(valid=False,error='Python timeout after 20 seconds'))
    result_path = path.with_suffix('.result.json')
    if not result_path.exists():
        return ok(dict(valid=False,error=result.stderr.decode(errors='replace')[-16000:]))
    return ok(json.loads(result_path.read_text(encoding='utf-8')))

@app.get('/api/configs')
def configs(u=Depends(user)):
    return ok(meta.listing('configs',u['id']))

@app.post('/api/configs')
def config(body:dict=Body(...),u=Depends(user)):
    if body.get('id'):
        meta.get('configs',body['id'],u['id'])
    for kind in ['normalize','compare','facts']:
        s = meta.get('scripts',body['stages'][kind],u['id'])
        if s['kind']!=kind:
            raise ValueError('Script kind mismatch')
    for id in body.get('checks',[]):
        if meta.get('scripts',id,u['id'])['kind']!='check':
            raise ValueError('Expected check script')
    for v in body.get('params',{}).get('thresholds',{}).values():
        if v is not None and (not isinstance(v,(int,float)) or v<0):
            raise ValueError('Thresholds must be non-negative or null')
    obj = meta.put('configs',u['id'],dict(name=body['name'],stages=body['stages'],checks=body.get('checks',[]),params=body.get('params',{})),id=body.get('id'))
    return ok(obj,obj['id'])

@app.get('/api/runs')
def runs(limit:int=100,offset:int=0,u=Depends(user)):
    return ok([public_run(r) for r in meta.listing('runs',u['id'],min(max(limit,1),200),max(0,offset))])

@app.post('/api/runs')
def start_run(body:dict=Body(...),u=Depends(user)):
    ds = meta.get('datasets',body['dataset_id'],u['id'])
    cfg = meta.get('configs',body['config_id'],u['id'])
    obj = meta.put('runs',u['id'],dict(dataset_id=ds['id'],config_id=cfg['id'],config=cfg,snapshots=snapshots(u['id'],cfg),total=ds['count'],progress=0),'QUEUED')
    return ok(public_run(obj),obj['id'],'QUEUED')

@app.get('/api/runs/{id}')
def run_state(id:str,u=Depends(user)):
    return ok(public_run(owned_run(id,u['id'])),id)

@app.get('/api/runs/{id}/events')
def events(id:str,after:int=0,u=Depends(user)):
    owned_run(id,u['id'])
    with meta.db() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM run_events WHERE run_id=? AND id>? ORDER BY id LIMIT 1000',(id,after))]
    return ok(rows,id)

@app.get('/api/runs/{id}/scripts/{snapshot_id}')
def script_snapshot(id:str,snapshot_id:str,u=Depends(user)):
    run = owned_run(id,u['id'])
    if ':' in snapshot_id:
        eid,sid = snapshot_id.split(':',1)
        execution = meta.get('check_executions',eid,u['id'])
        if execution['run_id']!=id:
            raise KeyError(snapshot_id)
        s = execution['snapshots'][sid]
    else:
        s = run['snapshots'][snapshot_id]
    return ok(s,snapshot_id)

@app.get('/api/runs/{id}/summary')
def run_summary(id:str,u=Depends(user)):
    run = owned_run(id,u['id'])
    return ok(run.get('summary') if run['status']=='READY' else None,id,run['status'])

@app.get('/api/runs/{id}/stats')
def run_stats(id:str,u=Depends(user)):
    run=owned_run(id,u['id'],True)
    from scripts.default_spr.stat_display import display_stats
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        stats=display_stats(con,run['stats'])
    return ok(stats,id)

@app.get('/api/runs/{id}/stats/charts')
def run_stat_charts(id:str,u=Depends(user)):
    run=owned_run(id,u['id'],True)
    from scripts.default_spr.stat_charts import chart_data
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        data=chart_data(con)
    return ok(data,id)

@app.get('/api/runs/{id}/checks')
def checks(id:str,u=Depends(user)):
    run = owned_run(id,u['id'],True)
    from backend.app.core.check_display import with_thresholds
    snapshots=run['snapshots']
    overrides=run['config'].get('params',{}).get('checks',{})
    try:
        execution=meta.get('check_executions',run['report_version'],u['id'])
        if execution['run_id']==id:
            snapshots=execution['snapshots']
            overrides=execution.get('params',{})
    except KeyError:
        pass
    rows=with_thresholds(run['checks'],snapshots,overrides)
    return ok(dict(rows=rows,executions=meta.listing('check_executions',u['id']),version=run['report_version']),id)

@app.post('/api/runs/{id}/checks')
def rerun_checks(id:str,body:dict=Body(...),u=Depends(user)):
    run = owned_run(id,u['id'],True)
    cfg = meta.get('configs',body.get('config_id',run['config_id']),u['id'])
    with meta.db() as c:
        active = [json.loads(r[0]) for r in c.execute("SELECT payload FROM check_executions WHERE owner_id=? AND status NOT IN ('READY','FAILED')",(u['id'],))]
    if any(e['run_id']==id for e in active):
        raise HTTPException(409,'Проверки этого прогона уже выполняются')
    obj = meta.put('check_executions',u['id'],dict(run_id=id,checks=cfg['checks'],snapshots=snapshots(u['id'],cfg),params=cfg.get('params',{}).get('checks',{})),'QUEUED')
    return ok(obj,obj['id'],'QUEUED')

@app.post('/api/runs/{id}/pivot')
def run_pivot(id:str,body:PivotRequest,u=Depends(user)):
    run = owned_run(id,u['id'],True)
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        data = pivot.cells(con,id,body)
    return ok(data,id)

@app.post('/api/runs/{id}/pivot/apps')
def pivot_apps(id:str,body:dict=Body(...),u=Depends(user)):
    run = owned_run(id,u['id'],True)
    filters = pivot.decode(body['cell_token'],id)
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        data = pivot.apps(con,filters,int(body.get('page',1)),int(body.get('page_size',50)))
    return ok(data,id)

@app.get('/api/runs/{id}/apps/{app_id}')
def app_details(id:str,app_id:str,cell_token:str|None=None,u=Depends(user)):
    run = owned_run(id,u['id'],True)
    with duckdb.connect(run['mart_path'],read_only=True) as con:
        mart = MartAPI(con)
        rows = mart.rows(app_ids=[app_id])
        if not rows:
            raise KeyError(app_id)
        matching = pivot.matching_attributes(con,app_id,pivot.decode(cell_token,id)) if cell_token else set()
        for row in rows:
            row['highlight'] = (row['PATH'],row['ARRAY_KEY']) in matching
        return ok(dict(app_id=app_id,rows=rows,segments=[s for s in mart.segments() if s['APP_ID']==app_id]),id)

@app.get('/api/runs/{id}/report.html')
def report(id:str,download:bool=False,u=Depends(user)):
    run = owned_run(id,u['id'],True)
    from backend.app.core.report import render
    content = render(run,run['summary'],run['stats'],run.get('checks',[]))
    disposition = f'attachment; filename="spr-{id}.html"' if download else 'inline'
    return Response(content,media_type='text/html',headers={'Content-Disposition':disposition,'Cache-Control':'no-store'})

@app.get('/api/health')
def health():
    return ok(dict(service='SPR',version='1.0'))

DIST = meta.ROOT/'frontend'/'dist'
if DIST.exists():
    app.mount('/',StaticFiles(directory=DIST,html=True),name='frontend')
