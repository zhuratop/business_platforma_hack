import hashlib
import io
import json
from pathlib import Path
from backend.app.storage import meta
from backend.app.plugins.defaults import ROOT,default_params

class LimitedOutput(io.StringIO):
    def write(self,s):
        remaining = max(0,16000-self.tell())
        super().write(s[:remaining])
        return len(s)

def compile_script(snapshot):
    namespace = {'__name__':'user_procedure','__file__':snapshot.get('path') or snapshot['name']}
    exec(compile(snapshot['code'],snapshot.get('path') or snapshot['name'],'exec'),namespace)
    return namespace

def seed(owner):
    if meta.listing('configs',owner):
        return
    stages = {}
    for kind in ['normalize','compare','facts']:
        file = ROOT/'scripts'/'default_spr'/f'{kind}.py'
        s = meta.put('scripts',owner,dict(name=file.name,kind=kind,source='file',path=str(file),code=file.read_text(encoding='utf-8'),params={}))
        stages[kind] = s['id']
    checks = []
    for file in sorted((ROOT/'scripts'/'checks').glob('check_*.py')):
        s = meta.put('scripts',owner,dict(name=file.name,kind='check',source='file',path=str(file),code=file.read_text(encoding='utf-8'),params={}))
        checks.append(s['id'])
    meta.put('configs',owner,dict(name='СПР · основной контракт',stages=stages,checks=checks,params=default_params()))

def snapshots(owner,config):
    result = {}
    for id in list(config['stages'].values())+config.get('checks',[]):
        s = meta.get('scripts',id,owner)
        if s['source']=='file':
            path = Path(s['path']).resolve()
            if path.suffix!='.py' or not any(path.is_relative_to(root) for root in [ROOT/'scripts',meta.RUNTIME/'scripts',meta.DATA_ROOT/'checks']):
                raise ValueError('Python file is outside allowed script roots')
            s['code'] = path.read_text(encoding='utf-8-sig')
        s['hash'] = hashlib.sha256(s['code'].encode()).hexdigest()
        result[id] = s
    return result

CHECK_FIELDS = {'LABEL','SOURCE','ARGUMENT','CNT','TOTAL','METRIC','APP_IDS','RESULT','CONFIDENCE'}

def run_checks(mart,snaps,check_ids,params,event=lambda *a:None):
    result = []
    seen = set()
    for id in check_ids:
        s = snaps[id]
        check = compile_script(s).get('CHECK')
        if not isinstance(check,dict) or not callable(check.get('entrypoint')) or not isinstance(check.get('id'),str) or not isinstance(check.get('label'),str) or not isinstance(check.get('params'),dict):
            raise ValueError(f'{s["name"]}: expected CHECK contract')
        if check['id'] in seen:
            raise ValueError(f'Duplicate CHECK.id: {check["id"]}')
        seen.add(check['id'])
        p = {**check['params'],**s.get('params',{}),**params.get(check['id'],{})}
        rows = check['entrypoint'](mart,p)
        if not isinstance(rows,list):
            raise ValueError('CHECK must return list[dict]')
        for r in rows:
            if not isinstance(r,dict) or CHECK_FIELDS-r.keys() or r['SOURCE'] not in ['BEFORE','AFTER'] or r['RESULT'] not in ['PASS','FAIL'] or r['CONFIDENCE'] not in ['LOW','HIGH']:
                raise ValueError(f'{s["name"]}: invalid check result {str(r)[:400]}')
            if not isinstance(r['APP_IDS'],list) or len(r['APP_IDS'])>p.get('app_ids_limit',20) or any(not isinstance(v,str) for v in r['APP_IDS']):
                raise ValueError('CHECK APP_IDS contract violation')
            if not all(isinstance(r[k],int) and r[k]>=0 for k in ['CNT','TOTAL']) or not isinstance(r['METRIC'],(int,float)):
                raise ValueError('CHECK numeric contract violation')
            result.append({**r,'check_id':check['id'],'snapshot_id':id})
        event(id,len(rows))
    return result
