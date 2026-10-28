from pathlib import Path
from unittest.mock import MagicMock
import hashlib
import pytest
from zb_studio import drive_download as d
from zb_studio.domain import safe_component


def file(fid,name,mime):return {'id':fid,'name':name,'mimeType':mime,'size':'3'}


def test_folder_pages_sort_and_separate_sequences(tmp_path,monkeypatch):
    drive=MagicMock();drive.files().get().execute.return_value={'id':'root','mimeType':d.FOLDER}
    drive.files().list().execute.side_effect=[{'nextPageToken':'p2','files':[file('b','img10.png','image/png'),file('v','video2.mp4','video/mp4')]},{'files':[file('a','img2.png','image/png'),file('w','video1.mp4','video/mp4')]}]
    seen=[]
    def download(api,item,path,*args):seen.append((item['id'],Path(path).relative_to(tmp_path).as_posix()));return path
    monkeypatch.setattr(d,'download_file',download)
    d.download_folder(drive,'root',tmp_path,'01',lambda s:None)
    assert seen==[('a','01/01-1.png'),('b','01/01-2.png'),('w','01/01-1.mp4'),('v','01/01-2.mp4')]


def test_nested_folder_and_incomplete_search(tmp_path):
    drive=MagicMock();drive.files().list().execute.side_effect=[{'files':[file('sub','../escape',d.FOLDER)]},{'files':[file('a','a.png','image/png')]}]
    entries=d.list_tree(drive,'root',lambda s:None)
    assert len(entries)==2 and '/' not in entries[0][0][0]
    drive.files().list().execute.side_effect=None;drive.files().list().execute.return_value={'incompleteSearch':True}
    with pytest.raises(ValueError,match='不完整'):d.list_tree(drive,'root',lambda s:None)


def test_file_download_retry_and_no_overwrite(tmp_path,monkeypatch):
    import googleapiclient.http
    payload=b'new'
    class Download:
        def __init__(self,stream,*a,**k):self.stream=stream
        def next_chunk(self,**k):self.stream.write(payload);return None,True
    monkeypatch.setattr(googleapiclient.http,'MediaIoBaseDownload',Download)
    target=tmp_path/'01-1.png';target.write_bytes(b'old');item=file('a','a.png','image/png');item['md5Checksum']=hashlib.md5(payload).hexdigest()
    result=d.download_file(MagicMock(),item,target,lambda s:None,[0])
    assert target.read_bytes()==b'old' and result.read_bytes()==payload
    assert d.download_file(MagicMock(),item,target,lambda s:None,[0])==result
    assert not list(tmp_path.glob('*.part'))


def test_checksum_failure_does_not_commit(tmp_path,monkeypatch):
    import googleapiclient.http
    class Download:
        def __init__(self,stream,*a,**k):self.stream=stream
        def next_chunk(self,**k):self.stream.write(b'bad');return None,True
    monkeypatch.setattr(googleapiclient.http,'MediaIoBaseDownload',Download)
    item=file('a','a.png','image/png');item['md5Checksum']='wrong'
    with pytest.raises(ValueError,match='校验失败'):d.download_file(MagicMock(),item,tmp_path/'a.png',lambda s:None,[0])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('name',['CON','con.txt','NUL','COM1.png','LPT9'])
def test_reserved_names(name):assert safe_component(name).startswith('_')


def test_folder_link_and_non_google_host():
    assert d.folder_id('https://drive.google.com/drive/u/0/folders/abc-123?usp=sharing')=='abc-123'
    assert d.folder_id('https://evil.test/drive/folders/id') is None


def test_vault_migration_and_failure_preserves_plaintext(tmp_path,monkeypatch):
    from zb_studio import token_store as t
    store=MagicMock();store.get_password.return_value=None;monkeypatch.setattr(t,'backend',lambda:store)
    legacy=tmp_path/'token.json';legacy.write_text('{"refresh_token":"test"}')
    store.set_password.side_effect=RuntimeError('locked')
    with pytest.raises(ValueError):t.load(legacy)
    assert legacy.exists()
    store.set_password.side_effect=lambda *a:setattr(store.get_password,'return_value',a[-1])
    assert t.load(legacy)=='{"refresh_token":"test"}' and not legacy.exists()


def test_ssrf_rejects_private_dns_before_http(monkeypatch):
    from zb_studio import image_fetch as f
    monkeypatch.setattr(f.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(ValueError,match='内网'):f.public_bytes('https://attacker.example/a.png')


def test_local_api_gets_require_header():
    from fastapi.testclient import TestClient
    from zb_studio.app import app
    with TestClient(app) as client:
        assert client.get('/api/settings').status_code==403
        assert client.get('/api/settings',headers={'X-ZB-Client':'desktop','Origin':'https://evil.test'}).status_code==403

def test_api_body_limit_before_parser():
    from fastapi.testclient import TestClient
    from zb_studio.app import app
    with TestClient(app,headers={'X-ZB-Client':'desktop'}) as client:
        assert client.put('/api/settings',content=b'{}',headers={'Content-Length':str(2*1024*1024)}).status_code==413
