from pathlib import Path
import mimetypes
from .domain import safe_component
from .file_safety import drive_literal,valid_drive_id

def ensure_folder(drive,name,parent):
    safe=drive_literal(name);parent=valid_drive_id(parent)
    q=f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' and '{parent}' in parents and trashed = false"
    entries=drive.files().list(q=q,fields='files(id,name),nextPageToken',pageSize=100).execute().get('files',[])
    if len(entries)>1:raise ValueError(f'父文件夹里存在重复目录：{name}')
    if entries:return entries[0]['id']
    item=drive.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},fields='id').execute()
    return item['id']

def upload_video(drive,file_path,root_id,day,person):
    from googleapiclient.http import MediaFileUpload
    path=Path(file_path)
    if not path.is_file():raise FileNotFoundError(path)
    day_dir=ensure_folder(drive,safe_component(day),root_id)
    person_dir=ensure_folder(drive,safe_component(person),day_dir)
    media=MediaFileUpload(str(path),mimetype=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',resumable=True)
    request=drive.files().create(body={'name':path.name,'parents':[person_dir]},media_body=media,fields='id,webViewLink')
    response=None
    while response is None:
        _,response=request.next_chunk()
    return response.get('webViewLink') or f"https://drive.google.com/file/d/{response['id']}/view"
