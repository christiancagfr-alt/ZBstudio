"""Local API for a future Windows desktop shell. OAuth only on trusted localhost."""
from pathlib import Path
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from . import google_client
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .config import Settings,load_settings,save_settings
from .google_client import services
from .workflow import load_tasks,claim,write_completed
from .domain import match_filename,date_key,allocate_numbers
from .drive_upload import upload_video
from .assets import save_image
from .journal import record
import tempfile,shutil

app=FastAPI(title='ZB Studio Local API',version='0.2.0')
FRONTEND=Path(__file__).resolve().parents[2]/'frontend'
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','testserver'])
from .http_limits import BodyLimitMiddleware
app.add_middleware(BodyLimitMiddleware)
app.mount('/static',StaticFiles(directory=FRONTEND),name='static')

@app.middleware('http')
async def local_requests(request:Request,call_next):
    if request.client and request.client.host not in ('127.0.0.1','::1','testclient'):return JSONResponse({'detail':'仅允许本机访问'},status_code=403)
    if request.url.path.startswith('/api/') or request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if (origin and origin != str(request.base_url).rstrip('/')) or request.headers.get('x-zb-client')!='desktop':
            return JSONResponse({'detail':'请从 ZB Studio 本机页面发起操作'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/auth/status')
def auth_status():return google_client.auth_status()

@app.post('/api/auth/client')
async def auth_client(file:UploadFile=File(...)):
    try:return google_client.import_client(await file.read(65537))
    except ValueError as e:raise HTTPException(400,str(e)) from e
    finally:await file.close()

@app.post('/api/auth/connect')
def auth_connect():
    try:return google_client.authorize()
    except Exception as e:raise HTTPException(400,'授权未完成，请检查客户端类型、测试用户及浏览器授权结果后重试') from e

@app.post('/api/auth/disconnect')
def auth_disconnect():
    try:return google_client.disconnect()
    except ValueError as e:raise HTTPException(409,str(e)) from e
@app.get('/')
def index():return FileResponse(FRONTEND/'index.html')
@app.get('/api/settings')
def get_settings():return load_settings()
@app.put('/api/settings')
def put_settings(settings:Settings):
    save_settings(settings);return {'saved':True}
@app.get('/api/tasks')
def tasks():
    try:
        sheets,_=services()
        items=load_tasks(sheets,load_settings())
        numbers={t.identity:n for t,n in allocate_numbers(items,[t.identity for t in items])}
        return {'tasks':[t.__dict__ | {'id':t.identity,'available':t.available,'label':t.label,'preview_number':numbers[t.identity]} for t in items]}
    except Exception as e:raise HTTPException(400,str(e)) from e
class ClaimRequest(BaseModel):ids:list[str]
@app.post('/api/claim')
def do_claim(req:ClaimRequest):
    try:
        sheets,_=services();return {'claimed':claim(sheets,load_settings(),req.ids)}
    except Exception as e:raise HTTPException(409,str(e)) from e
class AssetRequest(BaseModel):image_url:str;day:str;person:str;number:str
@app.post('/api/assets/download')
def download_asset(req:AssetRequest):
    try:
        cfg=load_settings();return {'path':save_image(req.image_url,cfg.download_path,req.day,req.person,req.number)}
    except Exception as e:raise HTTPException(400,str(e)) from e
@app.post('/api/uploads/video')
def upload(file:UploadFile=File(...)):
    """Single file upload with exact-name preflight and Drive folder placement."""
    cfg=load_settings()
    if not cfg.drive_parent_folder_id:raise HTTPException(400,'请先配置 Drive 父文件夹 ID')
    filename=Path(file.filename or '').name
    if not filename:raise HTTPException(400,'文件名不能为空')
    try:
        sheets,drive=services()
        tasks=load_tasks(sheets,cfg)
        matches=match_filename(Path(filename).stem,tasks)
        if len(matches)!=1:raise ValueError(f'文件名未唯一匹配任务（匹配数 {len(matches)}），未上传')
        task=matches[0]
        if task.owner!=cfg.producer:raise ValueError('只能上传当前制作人领取的任务')
        if task.output:raise ValueError('任务已回填成品链接，禁止重复上传')
        day=filename.rsplit('-',1)[-1].rsplit('.',1)[0]
        if len(day)!=8 or not day.isdigit():raise ValueError('自动命名末尾缺少8位日期')
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/filename
            with local.open('wb') as dest:shutil.copyfileobj(file.file,dest)
            url=upload_video(drive,local,cfg.drive_parent_folder_id,day,task.label)
        payload={'task':task.__dict__,'url':url,'production_id':cfg.production_spreadsheet_id,'production_sheet':cfg.production_sheet}
        operation=record('upload','pending_writeback',payload)
        try:
            write_completed(sheets,cfg,task,url)
            record('upload','complete',payload,operation)
        except Exception as e:
            raise ValueError(f'Drive 上传成功，但表格回填失败。已保存待修复日志 {operation}，请勿重复上传。云端链接：{url}') from e
        return {'matched':task.identity,'url':url,'filename':filename}
    except Exception as e:raise HTTPException(400,str(e)) from e
