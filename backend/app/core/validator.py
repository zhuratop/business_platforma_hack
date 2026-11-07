import contextlib
import itertools
import json
import sys
import traceback
import duckdb
from backend.app.core.execution import compile_script,run_checks,LimitedOutput
from backend.app.core.normalize import compare_rows
from backend.app.storage import meta
from backend.app.storage.mart import initialize,write,MartAPI
from backend.app.plugins.defaults import default_params
from scripts.default_spr.normalize import normalize
from scripts.default_spr.facts import build_facts
from backend.app.core import importer


def reader_preview(request, namespace):
    dataset = request.get('dataset')
    if dataset is None:
        root = meta.ROOT/'backend'/'tests'/'fixtures'/'spr'
        dataset = {'path':str(root),'dirs':{'BEFORE':'BEFORE','AFTER':'AFTER'}}
    app,b,a = next(importer.pairs(dataset,namespace['read_input'],request.get('params',{})))
    return app,[{'SOURCE':source,'APP_ID':app,'fields':len(response),'response':response}
                for source,response in [('BEFORE',b),('AFTER',a)]]

def main(path):
    request = json.loads(path.read_text(encoding='utf-8'))
    script = request['script']
    out = LimitedOutput()
    try:
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            ns = compile_script(script)
            if script['kind']=='reader':
                app_id,rows = reader_preview(request,ns)
                result = dict(valid=True,rows=rows,stdout=out.getvalue(),sample=app_id)
                path.with_suffix('.result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
                return
            sample_root = meta.DATA_ROOT/'samples'
            if not sample_root.exists():
                sample_root = meta.ROOT/'backend'/'tests'/'fixtures'/'spr'
            file = sorted((sample_root/'BEFORE').glob('*.json'))[0]
            b,a = json.loads(file.read_bytes()),json.loads((sample_root/'AFTER'/file.name).read_bytes())
            app_id = file.stem
            params = request.get('params',{})
            before = list(normalize(b,app_id,'BEFORE',default_params()['normalize']))
            after = list(normalize(a,app_id,'AFTER',default_params()['normalize']))
            kind = script['kind']
            if kind=='normalize':
                rows = list(itertools.islice(ns['normalize'](b,app_id,'BEFORE',params or default_params()['normalize']),20))
                required = {'APP_ID','SOURCE','PATH','ARRAY_KEY','VALUE','ADJUSTED_VALUE','VALUE_KIND','PREFIX','CLASS','SUFFIX','KEY'}
                if not rows or any(required-r.keys() for r in rows):
                    raise ValueError('Invalid NormalizedRow contract')
            elif kind=='compare':
                rows = list(itertools.islice(ns['compare'](before,after,params),20))
                if not rows or any({'APP_ID','PATH','ARRAY_KEY','DIFF_FLAG','CHANGE_TYPE','VALUE_BEFORE','VALUE_AFTER'}-r.keys() for r in rows):
                    raise ValueError('Invalid ComparisonRow contract')
            else:
                con = duckdb.connect(':memory:')
                try:
                    initialize(con)
                    write(con,'normalized_union',before+after)
                    write(con,'comparison_mart',compare_rows(before,after,{}))
                    facts = build_facts(MartAPI(con),lambda:iter([(app_id,b,a)]),{})
                    for key,table in [('segments','app_segments'),('product_trials','product_trials'),('offers','offers')]:
                        write(con,table,facts[key])
                    if kind=='check':
                        rows = run_checks(MartAPI(con),{'test':script},['test'],{})
                    elif kind=='facts':
                        facts = ns['build_facts'](MartAPI(con),lambda:iter([(app_id,b,a)]),params)
                        rows = {k:list(itertools.islice(v,10)) for k,v in facts.items()}
                        if set(rows)!= {'segments','product_trials','offers','pivot_facts'}:
                            raise ValueError('build_facts must return all four streams')
                    else:
                        raise ValueError('Unknown script kind')
                finally:
                    con.close()
        result = dict(valid=True,rows=rows,stdout=out.getvalue(),sample=app_id)
    except BaseException as e:
        result = dict(valid=False,error=str(e),traceback=traceback.format_exc()[-16000:],stdout=out.getvalue())
    path.with_suffix('.result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':
    from pathlib import Path
    main(Path(sys.argv[1]))
