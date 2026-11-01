from pathlib import Path
import mimetypes
from .domain import safe_component
from .file_safety import drive_literal,valid_drive_id

UPLOAD_CHUNK_SIZE=8*1024*1024

def ensure_folder(drive,name,parent):
    safe=drive_literal(name);parent=valid_drive_id(parent)
    q=f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' and '{parent}' in parents and trashed = false"
    entries=drive.files().list(q=q,fields='files(id,name),nextPageToken',pageSize=100,supportsAllDrives=True,includeItemsFromAllDrives=True).execute().get('files',[])
    if len(entries)>1:raise ValueError(f'父文件夹里存在重复目录：{name}')
    if entries:return entries[0]['id']
    item=drive.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},fields='id',supportsAllDrives=True).execute()
    return item['id']

def upload_video(drive,file_path,root_id,day,person,progress=None):
    from googleapiclient.http import MediaFileUpload
    path=Path(file_path)
    if not path.is_file():raise FileNotFoundError(path)
    day_dir=ensure_folder(drive,safe_component(day),root_id)
    person_dir=ensure_folder(drive,safe_component(person),day_dir)
    mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    resumable=path.stat().st_size>0
    media=MediaFileUpload(str(path),mimetype=mime,chunksize=UPLOAD_CHUNK_SIZE,resumable=resumable)
    request=drive.files().create(body={'name':path.name,'parents':[person_dir]},media_body=media,fields='id,webViewLink',supportsAllDrives=True)
    if hasattr(request,'http'):
        inner=getattr(request.http,'http',request.http)
        if hasattr(inner,'redirect_codes'):
            inner.redirect_codes=inner.redirect_codes-{308}
    if not resumable:
        response=request.execute(num_retries=3)
    else:
        response=None;last=-1
        while response is None:
            status,response=request.next_chunk(num_retries=3)
            if progress and status:
                percent=int(status.progress()*100)
                if percent//10!=last:progress(f'上传进度 {path.name} · {percent}%');last=percent//10
    return response.get('webViewLink') or f"https://drive.google.com/file/d/{response['id']}/view"
