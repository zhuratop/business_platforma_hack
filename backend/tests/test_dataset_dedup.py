import json
from concurrent.futures import ThreadPoolExecutor

from backend.app.core import importer
from backend.app.storage import meta


def setup_store(tmp_path,monkeypatch):
    monkeypatch.setattr(meta,'RUNTIME',tmp_path/'runtime')
    meta.init()


def test_repeat_import_reuses_owner_snapshot_but_keeps_changed_content(tmp_path,monkeypatch):
    setup_store(tmp_path,monkeypatch)
    folder = tmp_path/'source'
    for source in ['BEFORE','AFTER']:
        (folder/source).mkdir(parents=True)
        (folder/source/'app.json').write_text('{"value":1}')
    (folder/'manifest.json').write_text(json.dumps({'applications':1,'srez':{s:{'dir':s} for s in ['BEFORE','AFTER']}}))
    first = importer.copy_dataset('alice',folder,'Same name')
    again = importer.copy_dataset('alice',folder,'Different label')
    assert again == first
    assert len(list((meta.RUNTIME/'uploads').iterdir())) == 1
    other = importer.copy_dataset('bob',folder)
    assert other['id'] != first['id'] and other['owner_id'] == 'bob'
    (folder/'AFTER'/'app.json').write_text('{"value":2}')
    changed = importer.copy_dataset('alice',folder,'Same name')
    assert changed['id'] != first['id']
    assert len(meta.dataset_listing('alice')) == 2


def test_legacy_duplicates_are_hidden_before_pagination_and_still_readable(tmp_path,monkeypatch):
    setup_store(tmp_path,monkeypatch)
    for id,checksum in [('old','one'),('new','one'),('different','two')]:
        meta.put('datasets','alice',{'checksum':checksum,'name':'Same','created':id},'VALIDATED',id)
    visible = meta.dataset_listing('alice')
    assert len(visible) == 2 and {r['checksum'] for r in visible} == {'one','two'}
    assert meta.dataset_listing('alice',1,1) == visible[1:2]
    assert meta.get('datasets','old','alice')['checksum'] == 'one'
    assert meta.dataset_listing('bob') == []


def test_simultaneous_registration_does_not_create_duplicates(tmp_path,monkeypatch):
    setup_store(tmp_path,monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda i:meta.register_dataset('alice',{'checksum':'same','name':'Test','path':'snapshot'},str(i)),range(4)))
    assert len({r['id'] for r in rows}) == 1
    assert len(meta.listing('datasets','alice')) == 1
