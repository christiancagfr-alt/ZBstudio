"""Drive folder downloads: deterministic order, separate image/video numbering.
No shell, archive extraction, or execution of downloaded files.
"""
from pathlib import Path
from urllib.parse import urlparse
import re
import hashlib
import os
import tempfile
from collections import defaultdict
from .image_fetch import image_url
from .domain import safe_component
from .file_safety import checked_child,valid_drive_id

FOLDER='application/vnd.google-apps.folder'
SHORTCUT='application/vnd.google-apps.shortcut'
MAX_FILES=10000
MAX_BYTES=20*1024**3
FIELDS='id,name,mimeType,size,md5Checksum,resourceKey,capabilities(canDownload)'
EXPORTS={'application/vnd.google-apps.document':('application/pdf','.pdf'),
         'application/vnd.google-apps.spreadsheet':('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xlsx'),
         'application/vnd.google-apps.presentation':('application/pdf','.pdf'),
         'application/vnd.google-apps.drawing':('application/pdf','.pdf')}


def folder_id(value):
    u=urlparse(image_url(value))
    if u.scheme!='https' or u.hostname!='drive.google.com':return None
    m=re.search(r'/folders/([A-Za-z0-9_-]+)(?:/|$)',u.path)
    return m[1] if m else None


def natural_key(item):
    return (tuple((0,int(x)) if x.isdigit() else (1,x.casefold()) for x in re.split(r'(\d+)',item['name'])),item['id'])


def list_tree(drive,root_id,progress):
    entries=[];seen=set();total=0
    def walk(fid,relative,depth):
        nonlocal total
        valid_drive_id(fid)
        if depth>20:raise ValueError('云端文件夹层级超过20层')
        if fid in seen:raise ValueError('云端文件夹出现循环引用')
        seen.add(fid);children=[];token=None
        while True:
            args=dict(q=f"'{fid}' in parents and trashed = false",fields=f'nextPageToken,incompleteSearch,files({FIELDS})',pageSize=1000,supportsAllDrives=True,includeItemsFromAllDrives=True)
            if token:args['pageToken']=token
            response=drive.files().list(**args).execute()
            if response.get('incompleteSearch'):raise ValueError('Google 返回不完整目录，未开始下载，请检查权限')
            children.extend(response.get('files',[]))
            if len(children)+len(entries)>MAX_FILES:raise ValueError('文件夹内容超过10000项')
            next_token=response.get('nextPageToken')
            if next_token and next_token==token:raise ValueError('Google 文件列表分页重复')
            token=next_token
            if not token:break
        for item in sorted(children,key=natural_key):
            mime=item['mimeType'];valid_drive_id(item['id'])
            if mime==SHORTCUT:raise ValueError('文件夹包含快捷方式，请使用实际文件或文件夹链接：'+item['name'])
            if mime==FOLDER:
                label=safe_component(item['name'],70)+'-'+hashlib.sha256(item['id'].encode()).hexdigest()[:8]
                entries.append((relative+(label,),None));walk(item['id'],relative+(label,),depth+1)
            else:
                if item.get('capabilities',{}).get('canDownload') is False:raise ValueError('无权下载：'+item['name'])
                if mime.startswith('application/vnd.google-apps.') and mime not in EXPORTS:raise ValueError('暂不支持导出该云端类型：'+item['name'])
                total+=int(item.get('size',0))
                if total>MAX_BYTES:raise ValueError('单次目录下载超过20GB，请拆分任务')
                entries.append((relative,item))
        progress(f'已读取目录：{len(entries)} 项')
    walk(root_id,(),0)
    return entries


def extension(item):
    mime=item['mimeType']
    if mime in EXPORTS:return EXPORTS[mime][1]
    known={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif','video/mp4':'.mp4','video/quicktime':'.mov','video/webm':'.webm','video/x-matroska':'.mkv'}
    if mime in known:return known[mime]
    suffix=Path(item['name']).suffix.lower()
    return suffix if re.fullmatch(r'\.[a-z0-9]{1,12}',suffix) else '.bin'


def checksum(path):
    digest=hashlib.md5(usedforsecurity=False)
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def download_file(drive,item,target,progress,budget):
    from googleapiclient.http import MediaIoBaseDownload
    target=Path(target)
    if target.exists() and item.get('md5Checksum') and not target.is_symlink() and checksum(target)==item['md5Checksum']:
        progress('已存在，跳过：'+target.name);return target
    target.parent.mkdir(parents=True,exist_ok=True)
    mime=item['mimeType']
    request=drive.files().export_media(fileId=valid_drive_id(item['id']),mimeType=EXPORTS[mime][0]) if mime in EXPORTS else drive.files().get_media(fileId=valid_drive_id(item['id']),supportsAllDrives=True)
    if item.get('resourceKey'):request.headers['X-Goog-Drive-Resource-Keys']=item['id']+'/'+item['resourceKey']
    handle,temporary=tempfile.mkstemp(prefix='.zb-',suffix='.part',dir=target.parent)
    try:
        with os.fdopen(handle,'wb') as stream:
            downloader=MediaIoBaseDownload(stream,request,chunksize=1024*1024);done=False;previous=0;last=-1
            while not done:
                status,done=downloader.next_chunk(num_retries=2)
                current=stream.tell();budget[0]+=current-previous;previous=current
                if budget[0]>MAX_BYTES:raise ValueError('下载内容超过20GB限制')
                percent=int(status.progress()*100) if status else 0
                if percent//10!=last:progress(f'{target.name} · {percent}%');last=percent//10
        temporary=Path(temporary)
        if item.get('md5Checksum') and checksum(temporary)!=item['md5Checksum']:raise ValueError('文件校验失败：'+item['name'])
        for attempt in range(100):
            candidate=target if attempt==0 else target.with_name(target.stem+'-'+hashlib.sha256(item['id'].encode()).hexdigest()[:8]+('' if attempt==1 else '-'+str(attempt))+target.suffix)
            if candidate.exists() and not candidate.is_symlink() and checksum(candidate)==checksum(temporary):return candidate
            try:os.link(temporary,candidate);return candidate
            except FileExistsError:continue
        raise ValueError('同名文件过多')
    finally:
        Path(temporary).unlink(missing_ok=True)


def download_folder(drive,fid,base,number,progress):
    root=drive.files().get(fileId=valid_drive_id(fid),fields=FIELDS,supportsAllDrives=True).execute()
    if root.get('mimeType')!=FOLDER:raise ValueError('链接不是可访问的 Google Drive 文件夹')
    folder=checked_child(base,safe_component(number));entries=list_tree(drive,fid,progress)
    folder.mkdir(parents=True,exist_ok=True);counters=defaultdict(int);budget=[0];failures=[]
    total=sum(item is not None for _,item in entries);index=0
    for relative,item in entries:
        if budget[0]>MAX_BYTES:raise ValueError('达到单次20GB下载限制，已成功文件保留')
        destination=checked_child(folder,*relative);destination.mkdir(parents=True,exist_ok=True)
        if item is None:continue
        kind='image' if item['mimeType'].startswith('image/') else 'video' if item['mimeType'].startswith('video/') else 'other'
        counters[kind]+=1;index+=1
        if kind=='other':destination=checked_child(destination,'附件')
        target=checked_child(destination,f'{safe_component(number)}-{counters[kind]}{extension(item)}')
        progress(f'文件夹下载 {index}/{total}：{item["name"]} → {target.name}')
        try:result=download_file(drive,item,target,progress,budget);progress('下载成功：'+str(result))
        except Exception as e:failures.append(item['name']);progress('下载失败：'+item['name']+' · '+str(e))
    if failures:raise ValueError(f'文件夹中 {len(failures)}/{total} 个文件下载失败；已成功文件保留，可重试。')
    return str(folder)
