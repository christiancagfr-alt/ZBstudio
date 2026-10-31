from unittest.mock import MagicMock
import pytest
from zb_studio.config import Settings
from zb_studio.domain import Task
from zb_studio import registration,desktop_service as service

def settings():
    return Settings(producer='制作人',register_spreadsheet_id='doc',register_sheet='登记',register_defaults={'group':'一组','type':'视频'})

@pytest.mark.parametrize('duration,label,seconds',[(59000,'一分钟以内',59),(60000,'一分钟以上',60),(None,'','')])
def test_registration_columns_and_duration(monkeypatch,duration,label,seconds):
    api=MagicMock();monkeypatch.setattr(registration,'get_metadata',lambda *args:{'sheetId':1,'gridProperties':{'columnCount':29}})
    registration.append_record(api,settings(),'https://drive.google.com/file/d/abc/view',duration)
    kwargs=api.spreadsheets().values().append.call_args.kwargs
    row=kwargs['body']['values'][0]
    assert row[1]=='https://drive.google.com/file/d/abc/view' and row[2:4]==['一组','视频']
    assert row[7]=='制作人' and row[27]==label and row[28]==seconds
    assert kwargs['valueInputOption']=='RAW' and kwargs['insertDataOption']=='INSERT_ROWS'

def test_registration_validates_custom_columns_and_missing_columns(monkeypatch):
    cfg=settings();cfg.register_columns={'link':'B','group':'B'}
    with pytest.raises(ValueError,match='重复'):registration.validate(cfg)
    cfg.register_columns={'link':'AD'}
    monkeypatch.setattr(registration,'get_metadata',lambda *args:{'gridProperties':{'columnCount':29}})
    with pytest.raises(ValueError,match='列数不足'):registration.preflight(MagicMock(),cfg)

def test_folder_preflight_rejects_unmatched_before_any_writes(monkeypatch):
    task=Task('doc','s',4,0,'人','甲','2026-10-27','正文',owner='制作人',filename='01-ZB-20261027')
    monkeypatch.setattr(service,'services',lambda:(None,None));monkeypatch.setattr(service,'load_tasks',lambda *a:[task])
    monkeypatch.setattr(service,'resolve_drive_items',lambda *a:[({'id':'1','name':task.filename+'.mp4'},'https://drive.google.com/file/d/1/view'),({'id':'2','name':'wrong.mp4'},'https://drive.google.com/file/d/2/view')])
    writes=[];monkeypatch.setattr(service,'finalize_completion',lambda *a:writes.append(a))
    with pytest.raises(ValueError,match='未唯一匹配'):service.complete_drive_links(Settings(producer='制作人'),['https://drive.google.com/drive/folders/id'],lambda _:None)
    assert not writes

def test_drive_folder_link_is_resolved_and_expanded(monkeypatch):
    from zb_studio import drive_download
    drive=MagicMock()
    drive.files().get().execute.side_effect=[{'id':'folder','name':'folder','mimeType':'application/vnd.google-apps.folder'}, {'id':'file1','name':'01.mp4','mimeType':'video/mp4','videoMediaMetadata':{'durationMillis':'59000'}}]
    monkeypatch.setattr(drive_download,'list_tree',lambda *a:[((),{'id':'file1','name':'01.mp4','mimeType':'video/mp4'})])
    items=service.resolve_drive_items(drive,'https://drive.google.com/drive/folders/folder',lambda _:None)
    assert items[0][0]['videoMediaMetadata']['durationMillis']=='59000'
    assert items[0][1]=='https://drive.google.com/file/d/file1/view'

def test_registration_failure_records_reconciliation(monkeypatch):
    events=[];task=Task('doc','s',4,0,'人','甲','2026-10-27','正文')
    monkeypatch.setattr(service,'record',lambda kind,state,payload,*args:events.append((state,dict(payload))) or 'op')
    monkeypatch.setattr(service,'write_completed',lambda *a:None)
    monkeypatch.setattr(registration,'append_record',lambda *a:(_ for _ in ()).throw(RuntimeError('write failed')))
    with pytest.raises(ValueError,match='勿重复操作'):service.finalize_completion(None,settings(),task,'https://drive.google.com/file/d/abc/view')
    assert [e[0] for e in events]==['pending_writeback','source_and_production_written','needs_review']
    assert events[-1][1]['register_sheet']=='登记'

def test_category_sheet_columns_ignore_headers_and_keep_sheet_order(monkeypatch):
    calls=[]
    def read(api,doc,sheet):
        calls.append((doc,sheet))
        return [['类型','素材来源','软件','难易程度','时长分类'],['视频','原创','剪映','简单','短'],['图片','转载','PR','困难','长'],['视频','','','','']]
    monkeypatch.setattr(registration,'read_grid',read)
    options=registration.read_categories(None,'target-doc')
    assert calls==[('target-doc','分类')]
    assert options=={'type':['视频','图片'],'material':['原创','转载'],'software':['剪映','PR'],'difficulty':['简单','困难'],'duration_class':['短','长']}

def test_custom_duration_classification_comes_from_configuration(monkeypatch):
    cfg=settings();cfg.register_duration_labels={'short':'短','long':'长'}
    api=MagicMock();monkeypatch.setattr(registration,'get_metadata',lambda *args:{'gridProperties':{'columnCount':29}})
    registration.append_record(api,cfg,'https://drive.google.com/file/d/abc/view',59000)
    assert api.spreadsheets().values().append.call_args.kwargs['body']['values'][0][27]=='短'

def test_registration_date_folder_and_manual():
    cfg=settings();cfg.register_date_mode='folder'
    assert service.completion_date(cfg,['20261028','人物'])=='2026-10-28'
    assert service.completion_date(cfg,['2026-10-28','2026-10-29'])=='2026-10-29'
    with pytest.raises(ValueError,match='文件夹名称'):service.completion_date(cfg,['人物'])
    cfg.register_date_mode='manual';cfg.register_date='2026-10-30'
    assert service.completion_date(cfg,[])=='2026-10-30'
