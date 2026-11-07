import io
import json
import zipfile
from pathlib import Path
import pytest
from backend.app.core.importer import validate,unzip,copy_dataset
from backend.app.storage import meta

def dataset(tmp_path):
    (tmp_path/'b').mkdir();(tmp_path/'a').mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'applications':1,'srez':{'BEFORE':{'dir':'b'},'AFTER':{'dir':'a'}}}))
    for path in ['b/x.json','a/x.json']:
        (tmp_path/path).write_text('{}')
    return tmp_path

def test_unpaired_file_is_rejected(tmp_path):
    folder=dataset(tmp_path)
    assert validate(folder)['count']==1
    (folder/'a'/'x.json').rename(folder/'a'/'y.json')
    with pytest.raises(ValueError,match='Unpaired'):
        validate(folder)

def test_manifest_count_rejected(tmp_path):
    folder=dataset(tmp_path)
    (folder/'a'/'y.json').write_text('{}')
    (folder/'b'/'y.json').write_text('{}')
    with pytest.raises(ValueError,match='Manifest'):
        validate(folder)

@pytest.mark.parametrize('name',['../escape.json','/escape.json','C:/escape.json','nested/../../escape.json'])
def test_zip_slip_rejected(tmp_path,monkeypatch,name):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path)
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr(name,'{}')
    archive.seek(0)
    with pytest.raises(ValueError,match='Unsafe'):
        unzip('owner',archive,'test')

def test_snapshot_contains_verified_bytes_and_survives_source_change(tmp_path,monkeypatch):
    source_root=tmp_path/'source';source_root.mkdir()
    source=dataset(source_root)
    monkeypatch.setattr(meta,'RUNTIME',tmp_path/'runtime')
    meta.init()
    ds=copy_dataset('owner',source)
    (source/'b'/'x.json').write_text('{"new":true}')
    assert (Path(ds['path'])/'b'/'x.json').read_text()=='{}'
    assert validate(Path(ds['path']))['checksum']==ds['checksum']
