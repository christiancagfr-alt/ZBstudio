"""Shared direct-call desktop operations; no HTTP server."""
from pathlib import Path
import re
from .google_client import services
from .workflow import load_tasks, claim, write_completed
from .domain import match_filename
from .drive_upload import upload_video
from .journal import record

def query(cfg,progress=None):
    if progress:progress('正在连接 Google 并检查授权…')
    sheets,_=services()
    if progress:progress(f'正在读取 {len(cfg.source_sheets)} 个需求工作表…')
    tasks=load_tasks(sheets,cfg,progress,include_metrics=True)
    if progress:progress(f'读取完成：{len(tasks)} 个任务')
    return tasks

def claim_tasks(cfg,ids,progress):
    progress('正在连接 Google 并检查授权…')
    sheets,_=services()
    result=claim(sheets,cfg,ids,progress)
    failures=[]
    for i,item in enumerate(result):
        progress(f'领取成功 · 下载素材 {i+1}/{len(result)}：{item["folder"]} / {item["number"]}')
        try:
            path=download_claim_image(cfg,item,progress)
            progress('下载成功：'+path)
        except Exception as e:
            failures.append({'item':item,'error':str(e)});progress('下载失败：'+str(e))
            record('download','failed',{'item':item,'error':str(e)})
    return {'claimed':result,'failed_downloads':failures}

def download_claim_image(cfg,item,progress=None):
    progress=progress or (lambda message:None)
    if not cfg.download_path.strip():raise ValueError('请先在设置中选择图片下载目录')
    from .image_fetch import fetch_image
    from .domain import safe_component
    from PySide6.QtGui import QImageReader
    from PySide6.QtCore import QByteArray,QBuffer,QIODevice
    from .domain import date_key
    demand=date_key(item.get('deadline',''))
    short=re.fullmatch(r'(\d{1,2})[-/.月](\d{1,2})日?',demand)
    if short:demand=item['date'][:4]+f'{int(short[1]):02d}{int(short[2]):02d}'
    from .file_safety import checked_child
    from .drive_download import folder_id,download_folder,download_file,extension,FIELDS,FOLDER
    from .image_fetch import drive_id
    folder=checked_child(cfg.download_path,safe_component(item['date']),safe_component(demand or '需求日期未填写'),safe_component(item['folder']));folder.mkdir(parents=True,exist_ok=True)
    fid=folder_id(item['image'])
    if fid:
        _,drive=services();result=download_folder(drive,fid,folder,item['number'],progress)
        record('download','complete',{'item':item,'path':result});return result
    try:data=fetch_image(item['image'],original=True)
    except Exception:
        fid=drive_id(item['image'])
        if not fid:raise
        _,drive=services();metadata=drive.files().get(fileId=fid,fields=FIELDS,supportsAllDrives=True).execute()
        if metadata['mimeType']==FOLDER:result=download_folder(drive,fid,folder,item['number'],progress)
        else:result=str(download_file(drive,metadata,checked_child(folder,safe_component(item['number'])+extension(metadata)),progress,[0]))
        record('download','complete',{'item':item,'path':result});return result
    buf=QBuffer();buf.setData(QByteArray(data));buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(buf);fmt=bytes(reader.format()).decode().lower()
    ext={'jpeg':'jpg','jpg':'jpg','png':'png','webp':'webp'}.get(fmt)
    if not ext or not reader.canRead():raise ValueError('文件不是支持的 JPG/PNG/WEBP 图片')

    dest=folder/(safe_component(item['number'])+'.'+ext)
    import hashlib
    # Keep the simple number when free. Collisions across demand dates/groups
    # receive a stable identity suffix; existing files are never overwritten.
    digest=hashlib.sha256((item.get('id','')+'|'+item.get('filename','')+'|'+item['image']).encode()).hexdigest()[:12]
    suffix=safe_component(item.get('deadline') or '任务')+'-'+digest
    for attempt in range(100):
        candidate=dest if attempt==0 else folder/(safe_component(item['number'])+'-'+suffix+('' if attempt==1 else '-'+str(attempt))+'.'+ext)
        try:
            with candidate.open('xb') as f:f.write(data)
            dest=candidate;break
        except FileExistsError:
            if candidate.read_bytes()==data:dest=candidate;break
    else:raise ValueError('同名文件过多，请检查下载文件夹')
    record('download','complete',{'item':item,'path':str(dest)})
    return str(dest)

def abandon(cfg,identity,name,progress):
    from .workflow import release_task
    sheets,_=services()
    return release_task(sheets,cfg,identity,name,progress)


def resolve_drive_link(drive,link):
    """Resolve a Drive file using the current user's Google authorization."""
    from urllib.parse import urlparse,parse_qs
    from .file_safety import valid_drive_id
    parsed=urlparse(link.strip())
    if parsed.scheme!='https' or parsed.hostname not in ('drive.google.com','docs.google.com') or parsed.username or parsed.password:
        raise ValueError('请输入有效的 Google Drive 文件共享链接')
    match=re.fullmatch(r'/(?:file/d|(?:drive/(?:u/\d+/)?)?folders)/([A-Za-z0-9_-]+)(?:/[^/]*)?/?',parsed.path)
    fid=match.group(1) if match else parse_qs(parsed.query).get('id',[''])[0]
    if not fid:raise ValueError('无法从链接识别 Google Drive 文件 ID，请使用文件共享链接')
    fid=valid_drive_id(fid)
    request=drive.files().get(fileId=fid,fields='id,name,mimeType,trashed,webViewLink,videoMediaMetadata(durationMillis)',supportsAllDrives=True)
    resource_key=parse_qs(parsed.query).get('resourcekey',[''])[0]
    if resource_key:
        valid_drive_id(resource_key)
        request.headers['X-Goog-Drive-Resource-Keys']=fid+'/'+resource_key
    metadata=request.execute()
    if metadata.get('trashed'):raise ValueError('该云端文件已移至回收站')
    if metadata.get('id')!=fid or not metadata.get('name'):raise ValueError('云端文件信息不完整，请检查权限')
    return metadata

def resolve_drive_items(drive,link,progress):
    item=resolve_drive_link(drive,link)
    if item.get('mimeType')!='application/vnd.google-apps.folder':return [(item,link.strip())]
    from .drive_download import list_tree
    result=[]
    for relative,child in list_tree(drive,item['id'],progress):
        if child is None:continue
        if child['mimeType'].startswith('application/vnd.google-apps.'):
            raise ValueError('文件夹含非普通云端文件，请移除后重试：'+child['name'])
        request=drive.files().get(fileId=child['id'],fields='id,name,mimeType,trashed,webViewLink,videoMediaMetadata(durationMillis)',supportsAllDrives=True)
        if child.get('resourceKey'):request.headers['X-Goog-Drive-Resource-Keys']=child['id']+'/'+child['resourceKey']
        file=request.execute()
        file['_folder_names']=[item['name'],*relative]
        url=file.get('webViewLink') or f'https://drive.google.com/file/d/{child["id"]}/view'
        result.append((file,url))
    if not result:raise ValueError('云端文件夹中没有可匹配的成品文件')
    return result

def completion_date(cfg,folders):
    from datetime import date,datetime
    if cfg.register_date_mode=='today':return date.today().isoformat()
    if cfg.register_date_mode=='manual':
        try:return date.fromisoformat(cfg.register_date).isoformat()
        except ValueError:raise ValueError('请选择有效的登记日期') from None
    for name in reversed(folders):
        match=re.search(r'(?<!\d)(\d{4})[-_.年]?(\d{2})[-_.月]?(\d{2})(?!\d)',str(name))
        if match:
            try:return datetime.strptime(''.join(match.groups()),'%Y%m%d').date().isoformat()
            except ValueError:continue
    raise ValueError('文件夹名称中没有有效日期，请选择当天或手动日期')

def finalize_completion(sheets,cfg,task,url,duration_ms=None,record_date=None):
    from .registration import append_record,validate
    validate(cfg)
    payload={'task':task.__dict__,'url':url,'production_id':cfg.production_spreadsheet_id,'production_sheet':cfg.production_sheet,
             'register_id':cfg.register_spreadsheet_id,'register_sheet':cfg.register_sheet,'register_columns':cfg.register_columns,
             'register_defaults':cfg.register_defaults,'duration_ms':duration_ms,'register_date':record_date}
    op=record('upload','pending_writeback',payload)
    try:
        write_completed(sheets,cfg,task,url)
        record('upload','source_and_production_written',payload,op)
        append_record(sheets,cfg,url,duration_ms,record_date)
    except Exception as e:
        payload['error']=str(e);record('upload','needs_review',payload,op)
        raise ValueError(f'成品已在云端，但表格回填未全部完成。日志 {op}；请先核对需求表、制作表和登记表，勿重复操作。') from e
    record('upload','complete',payload,op)

def complete_drive_links(cfg,links,progress):
    """Preflight all cloud files before writing either spreadsheet."""
    from .registration import validate,preflight
    validate(cfg)
    sheets,drive=services();preflight(sheets,cfg);tasks=load_tasks(sheets,cfg);plan=[];seen=set()
    for link in links:
        progress('正在读取云端文件信息…')
        for file,url in resolve_drive_items(drive,link,progress):
            stem=Path(file['name']).stem
            matches=match_filename(stem,tasks)
            if len(matches)!=1 or matches[0].owner!=cfg.producer or matches[0].output:
                raise ValueError(f'未唯一匹配当前制作人的未完成任务：{file["name"]}')
            if matches[0].identity in seen:raise ValueError(f'重复匹配任务：{file["name"]}')
            record_date=completion_date(cfg,file.get('_folder_names',[])) if cfg.register_spreadsheet_id else None
            seen.add(matches[0].identity);plan.append((file,matches[0],url,record_date))
    for i,(file,task,url,record_date) in enumerate(plan):
        duration=file.get('videoMediaMetadata',{}).get('durationMillis')
        finalize_completion(sheets,cfg,task,url,duration,record_date);progress(f'{i+1}/{len(plan)} 已回填：{file["name"]}')
    return len(plan)


def upload_files(cfg,paths,progress):
    from .registration import validate,preflight
    validate(cfg)
    if not cfg.drive_parent_folder_id:raise ValueError('请配置 Drive 父文件夹 ID')
    sheets,drive=services()
    preflight(sheets,cfg)
    tasks=load_tasks(sheets,cfg)
    plan=[];seen=set()
    for raw in paths:
        p=Path(raw)
        if not p.is_file():raise ValueError(f'文件不存在或不是普通文件：{p.name}')
        if p.stem in seen:raise ValueError(f'重复命名：{p.name}')
        seen.add(p.stem)
        matches=match_filename(p.stem,tasks)
        if len(matches)!=1 or matches[0].owner!=cfg.producer or matches[0].output:raise ValueError(f'未唯一匹配当前制作人的未完成任务：{p.name}')
        match=re.search(r'-(\d{8})$',p.stem)
        if not match:raise ValueError('文件名缺少领取日期')
        record_date=completion_date(cfg,[parent.name for parent in reversed(p.parents)]) if cfg.register_spreadsheet_id else None
        plan.append((p,matches[0],match[1],record_date))
    for i,(p,t,day,record_date) in enumerate(plan):
        progress(f'{i+1}/{len(plan)} 正在上传 {p.name}')
        url=upload_video(drive,p,cfg.drive_parent_folder_id,day,t.label)
        duration=None
        if cfg.register_spreadsheet_id:
            try:duration=resolve_drive_link(drive,url).get('videoMediaMetadata',{}).get('durationMillis')
            except Exception:pass  # Google may not have processed the video yet.
        finalize_completion(sheets,cfg,t,url,duration,record_date)
        progress(f'{i+1}/{len(plan)} 已完成 {p.name}')
    return len(plan)
