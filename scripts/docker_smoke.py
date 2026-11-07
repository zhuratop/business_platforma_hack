"""Short HTTP acceptance against running API and worker; uses four real pairs."""
import argparse
import http.cookiejar
import io
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request
import zipfile

from scripts.make_multiformat_sample import encode


class Client:
    def __init__(self, base):
        self.base=base.rstrip('/')
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, payload=None, raw=None, headers=None):
        headers=dict(headers or {})
        if payload is not None:
            raw=json.dumps(payload).encode()
            headers['Content-Type']='application/json'
        request=urllib.request.Request(self.base+path,data=raw,headers=headers)
        with self.opener.open(request,timeout=30) as response:
            body=response.read()
        return body

    def api(self,path,payload=None):
        return json.loads(self.request('/api'+path,payload))['data']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--timeout',type=int,default=90)
    args=parser.parse_args()
    alice,bob=Client(args.base_url),Client(args.base_url)
    password=os.environ.get('SPR_DEMO_PASSWORD','demo')
    for client,name in [(alice,'alice'),(bob,'bob')]:
        client.api('/auth/login',{'username':name,'password':password})
    assert b'<div id="root">' in alice.request('/')
    boot=alice.api('/bootstrap')
    root=Path(__file__).resolve().parents[1]/'backend/tests/fixtures/spr'
    files=sorted((root/'BEFORE').glob('*.json'))
    assert files,'Real fixtures are missing in the image'
    archive=io.BytesIO()
    expected={s:0 for s in ['BEFORE','AFTER']}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as target:
        target.writestr('manifest.json',json.dumps({'applications':len(files),'srez':{s:{'dir':s} for s in expected}}))
        for i,file in enumerate(files):
            for j,source in enumerate(expected):
                response=json.loads((root/source/file.name).read_bytes())
                expected[source]+=response['decisionResult']['decision']=='APPROVE'
                fmt=['json','xml','csv'][(i+j)%3]
                target.writestr(f'{source}/{file.stem}.{fmt}',encode(response,fmt))
    boundary='spr-'+secrets.token_hex(12)
    raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="docker-smoke.zip"\r\n'
         'Content-Type: application/zip\r\n\r\n').encode()+archive.getvalue()+f'\r\n--{boundary}--\r\n'.encode()
    dataset=json.loads(alice.request('/api/datasets/upload',raw=raw,headers={'Content-Type':'multipart/form-data; boundary='+boundary}))['data']
    assert dataset['count']==len(files) and dataset['formats']==['csv','json','xml']
    name='Docker smoke: JSON / XML / CSV'
    source=next((c for c in boot['configs'] if c['name']==name),boot['configs'][0])
    config={k:source[k] for k in ['stages','checks','params']}
    config['name']=name
    if source['name']==name:
        config['id']=source['id']
    config['params']['stats']['bootstrap']=100
    config['params']['processing']={'batch_pairs':200}
    config=alice.api('/configs',config)
    run=alice.api('/runs',{'dataset_id':dataset['id'],'config_id':config['id']})
    deadline=time.monotonic()+args.timeout
    while run['status'] not in ['READY','FAILED'] and time.monotonic()<deadline:
        time.sleep(.25)
        run=alice.api('/runs/'+run['id'])
    assert run['status']=='READY',run
    assert len(run['checkpoints'])==7 and run['saved_pairs']==len(files)
    summary=alice.api('/runs/'+run['id']+'/summary')
    assert summary['total_apps']==len(files)
    assert {r['SOURCE']:r['approved'] for r in summary['approvals']}==expected
    tree=alice.api('/runs/'+run['id']+'/pivot/tree',{})
    assert tree['totals']['TOTAL']['count']==len(files)
    assert all(k in tree['totals'] for k in ['BEFORE_0','BEFORE_1','AFTER_0','AFTER_1'])
    checks=alice.api('/runs/'+run['id']+'/checks')['rows']
    assert checks
    report=alice.request('/api/runs/'+run['id']+'/report.html?download=true').decode()
    assert 'id="pivot"' in report and 'id="checks"' in report and 'DIFF_FLAG = 1' in report
    try:
        bob.api('/runs/'+run['id'])
    except urllib.error.HTTPError as error:
        assert error.code==404
    else:
        raise AssertionError('Another user can access the run')
    print(json.dumps({'passed':True,'run_id':run['id'],'paired_apps':len(files),
        'normalized_rows':run['normalized_rows'],'check_rows':len(checks)},indent=2))


if __name__=='__main__':
    main()
