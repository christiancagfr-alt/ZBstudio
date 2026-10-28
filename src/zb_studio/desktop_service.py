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
    tasks=load_tasks(sheets,cfg,progress) if progress else load_tasks(sheets,cfg)
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


def upload_files(cfg,paths,progress):
    if not cfg.drive_parent_folder_id:raise ValueError('请配置 Drive 父文件夹 ID')
    sheets,drive=services()
    tasks=load_tasks(sheets,cfg)
    plan=[];seen=set()
    for raw in paths:
        p=Path(raw)
        if not p.is_file() or p.suffix.lower() not in ('.mp4','.mov','.mkv','.webm'):raise ValueError(f'不支持的文件：{p.name}')
        if p.stem in seen:raise ValueError(f'重复命名：{p.name}')
        seen.add(p.stem)
        matches=match_filename(p.stem,tasks)
        if len(matches)!=1 or matches[0].owner!=cfg.producer or matches[0].output:raise ValueError(f'未唯一匹配当前制作人的未完成任务：{p.name}')
        match=re.search(r'-(\d{8})$',p.stem)
        if not match:raise ValueError('文件名缺少领取日期')
        plan.append((p,matches[0],match[1]))
    for i,(p,t,day) in enumerate(plan):
        progress(f'{i+1}/{len(plan)} 正在上传 {p.name}')
        url=upload_video(drive,p,cfg.drive_parent_folder_id,day,t.label)
        payload={'task':t.__dict__,'url':url,'production_id':cfg.production_spreadsheet_id,'production_sheet':cfg.production_sheet}
        op=record('upload','pending_writeback',payload)
        try:write_completed(sheets,cfg,t,url)
        except Exception as e:raise ValueError(f'上传成功、回填失败，请勿重传。日志 {op}，链接 {url}') from e
        record('upload','complete',payload,op)
        progress(f'{i+1}/{len(plan)} 已完成 {p.name}')
    return len(plan)
