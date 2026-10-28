import json
import pytest
from fastapi.testclient import TestClient
from zb_studio import google_client as g
from zb_studio.app import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'home',lambda:tmp_path)
    from zb_studio import token_store
    class MemoryStore:
        value=None
        def get_password(self,*a):return self.value
        def set_password(self,*a):self.value=a[-1]
        def delete_password(self,*a):self.value=None
    store=MemoryStore();monkeypatch.setattr(token_store,'backend',lambda:store)
    monkeypatch.delenv('ZB_GOOGLE_CLIENT_SECRET',raising=False)
    return TestClient(app,headers={'X-ZB-Client':'desktop'})

def oauth():
    return {'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'fake-secret','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token'}}

def test_import(client,tmp_path):
    r=client.post('/api/auth/client',files={'file':('a.json',json.dumps(oauth()))})
    assert r.status_code==200 and r.json()['configured']
    assert 'fake-secret' not in r.text
    assert (tmp_path/'google_client.json').exists()

@pytest.mark.parametrize('data',[{}, {'web':{}},{'type':'service_account'},{'installed':{'auth_uri':'https://evil.test'}}])
def test_invalid(client,data):
    assert client.post('/api/auth/client',files={'file':('a.json',json.dumps(data))}).status_code==400

def test_limits_and_origin(client):
    assert client.post('/api/auth/client',files={'file':('a.json',b'x'*65537)}).status_code==400
    assert client.post('/api/auth/disconnect',headers={'Origin':'https://evil.test'}).status_code==403
    assert TestClient(app).post('/api/auth/disconnect').status_code==403

def test_client_change_and_disconnect(client,tmp_path):
    g.import_client(json.dumps(oauth()))
    token=tmp_path/'google_token.json'
    token.write_text('{"refresh_token":"fake"}')
    assert g.auth_status()['needs_reauth']
    data=oauth();data['installed']['client_id']='other.apps.googleusercontent.com'
    g.import_client(json.dumps(data))
    assert not token.exists()
    token.write_text('{"refresh_token":"fake"}')
    assert client.post('/api/auth/disconnect').status_code==200
    assert not token.exists() and (tmp_path/'google_client.json').exists()

def test_no_implicit_browser(client):
    with pytest.raises(ValueError,match='系统设置'):g.credentials()

def test_assets(client):
    for path in ['/','/static/app.js','/static/app.css']:
        assert client.get(path).status_code==200
