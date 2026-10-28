"""Explicit desktop OAuth. Secrets remain in the local backend."""
import json
import os
import threading
from pathlib import Path
from platformdirs import user_data_dir
from . import token_store
SCOPES=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/drive.readonly']
AUTH_LOCK=threading.Lock()

def home():
    folder=Path(user_data_dir('ZB Studio'))
    folder.mkdir(parents=True,exist_ok=True)
    return folder

def secret_path():
    local=home()/'google_client.json'
    return local if local.exists() else Path(os.environ.get('ZB_GOOGLE_CLIENT_SECRET','__missing__'))

def private_write(path,content):
    import tempfile
    fd,temp=tempfile.mkstemp(prefix='.zb-secret-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(content)
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


def validate_client(raw):
    try:
        data=json.loads(raw)
        client=data['installed']
        if not all(isinstance(client.get(k),str) and client[k].strip() for k in ('client_id','client_secret')):raise ValueError()
        if not client['client_id'].endswith('.apps.googleusercontent.com'):raise ValueError()
        if client.get('auth_uri')!='https://accounts.google.com/o/oauth2/auth':raise ValueError()
        if client.get('token_uri')!='https://oauth2.googleapis.com/token':raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):
        raise ValueError('请选择 Google Cloud 下载的桌面应用 OAuth JSON，不能使用服务账号或网页客户端文件') from None
    return data

def auth_status():
    configured=secret_path().is_file()
    try:
        raw=token_store.load(home()/'google_token.json')
        data=json.loads(raw) if raw else {}
        connected=bool(data.get('refresh_token'))
        needs_reauth=connected and not set(SCOPES).issubset(set(data.get('scopes',[])))
        return {'configured':configured,'connected':connected and not needs_reauth,'busy':AUTH_LOCK.locked(),'needs_reauth':needs_reauth}
    except ValueError:
        return {'configured':configured,'connected':False,'busy':AUTH_LOCK.locked(),'credential_store_unavailable':True}


def import_client(raw):
    if len(raw)>65536:raise ValueError('授权配置文件不得超过 64 KB')
    data=validate_client(raw)
    if not AUTH_LOCK.acquire(blocking=False):raise ValueError('授权正在进行，请完成后再更换文件')
    try:
        path=home()/'google_client.json'
        previous=json.loads(path.read_text('utf-8')) if path.exists() else None
        if previous!=data:
            private_write(path,json.dumps(data))
            token_store.clear(home()/'google_token.json')
    finally:AUTH_LOCK.release()
    return auth_status()

def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not AUTH_LOCK.acquire(blocking=False):raise ValueError('授权正在进行，请在浏览器中完成')
    try:
        path=secret_path()
        if not path.is_file():raise ValueError('请先导入 Google 桌面授权 JSON 文件')
        flow=InstalledAppFlow.from_client_config(validate_client(path.read_bytes()),SCOPES,autogenerate_code_verifier=True)
        creds=flow.run_local_server(host='127.0.0.1',port=0,timeout_seconds=180,prompt='consent',access_type='offline',authorization_prompt_message='',success_message='Authorization complete. Return to ZB Studio.')
        token_store.save(creds.to_json())
    finally:AUTH_LOCK.release()
    return auth_status()

def disconnect():
    if not AUTH_LOCK.acquire(blocking=False):raise ValueError('请等待当前授权结束')
    try:token_store.clear(home()/'google_token.json')
    finally:AUTH_LOCK.release()
    return auth_status()

def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    with AUTH_LOCK:
        token=home()/'google_token.json'
        raw=token_store.load(token)
        if not raw:raise ValueError('请在系统设置中点击 Google 授权')
        info=json.loads(raw)
        if not set(SCOPES).issubset(set(info.get('scopes',[]))):raise ValueError('新增云端文件夹读取权限，请在系统设置重新 Google 授权')
        creds=Credentials.from_authorized_user_info(info)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_store.save(creds.to_json())
        if not creds.valid:raise ValueError('Google 授权已失效，请重新授权')
        return creds

def services():
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    auth=credentials()
    return tuple(build(name,version,http=AuthorizedHttp(auth,http=httplib2.Http(timeout=30)),cache_discovery=False) for name,version in [('sheets','v4'),('drive','v3')])
