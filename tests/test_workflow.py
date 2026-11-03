import pytest
from zb_studio import workflow as w
from zb_studio.config import Settings
from zb_studio.domain import Task
COLS={'deadline':0,'chinese':1,'owner':2,'filename':3,'number':4,'progress':5,'output':6}
def task(sheet='需求',start=0):
    return Task('source',sheet,4,start,'长文案','甲','2026-10-27','正文',columns=COLS.copy())
def test_exact_group(monkeypatch):
    monkeypatch.setattr(w,'read_grid',lambda *args:[['超长文案'],[],['截至日期','中文','制作人','自动命名','序号']])
    with pytest.raises(ValueError,match='唯一匹配') as error:w.production_location(None,Settings(),task())
    assert '制作表写入方式' in str(error.value)
    assert '左侧第一组' in str(error.value)
def test_reserve_target_rows(monkeypatch):
    items=[task(),task('另一需求',11)]
    monkeypatch.setattr(w,'load_tasks',lambda *args:items)
    monkeypatch.setattr(w,'production_location',lambda *args:(4,COLS))
    monkeypatch.setattr(w,'record',lambda *args:'op')
    writes=[]
    monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append((doc,data)))
    cfg=Settings(source_spreadsheet_id='source',production_spreadsheet_id='target',production_sheet='制作')
    w.claim(None,cfg,[t.identity for t in items])
    ranges=[u['range'] for doc,data in writes if doc=='target' for u in data]
    assert len(ranges)==len(set(ranges))
    assert "'制作'!A4" in ranges and "'制作'!A5" in ranges
def test_partial_claim(monkeypatch):
    t=task();events=[]
    monkeypatch.setattr(w,'load_tasks',lambda *args:[t])
    monkeypatch.setattr(w,'production_location',lambda *args:(4,COLS))
    monkeypatch.setattr(w,'record',lambda kind,state,payload,*args:events.append(state) or 'op')
    def write(api,doc,updates):
        if doc=='target':raise RuntimeError('network down')
    monkeypatch.setattr(w,'batch_write',write)
    with pytest.raises(ValueError,match='核对日志'):
        w.claim(None,Settings(source_spreadsheet_id='source',production_spreadsheet_id='target'),[t.identity])
    assert events==['prepared','source_partial_written','source_written','needs_review']

def test_requester_alias_survives_sheet_rename_and_is_written(monkeypatch):
    """Physical sheet names route writes; stable aliases drive generated business names."""
    from zb_studio.domain import make_filename
    head=['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接']
    grid=[['长文案'],[],head,['2026-10-27','正文']]
    reads=[]
    def read(api,doc,sheet):
        reads.append(sheet)
        return grid
    monkeypatch.setattr(w,'read_grid',read)
    cfg=Settings(producer='佳佳',source_spreadsheet_id='source',source_sheets=['张三需求表3'],requester_names={'张三需求表3':'张三'})
    first=w.load_tasks(None,cfg)[0]
    name=make_filename(first,'01','ZB',cfg.producer,'2026-10-27')
    assert name=='01-ZB-张三 长文案-佳佳-正文-20261027'
    assert first.label=='张三 长文案'
    src,dst=w.updates_for_task(cfg,first,'01',name,4,COLS)
    assert all(u['range'].startswith("'张三需求表3'!") for u in src)
    assert any(u['values']==[[name]] for u in src)
    assert any(u['values']==[[name]] for u in dst)
    cfg.source_sheets=['张三新需求表']
    cfg.requester_names={'张三新需求表':'张三'}
    renamed=w.load_tasks(None,cfg)[0]
    assert make_filename(renamed,'01','ZB',cfg.producer,'2026-10-27')==name
    assert reads==['张三需求表3','张三新需求表']

def test_numeric_sheet_read_and_missing_title_message():
    from unittest.mock import MagicMock
    api=MagicMock()
    api.spreadsheets().get().execute.return_value={'sheets':[{'properties':{'sheetId':42,'title':"张三'需求表3"}}]}
    api.spreadsheets().values().batchGetByDataFilter().execute.return_value={'valueRanges':[{'valueRange':{'values':[['正文']]}}]}
    assert w.read_grid(api,'doc',"张三'需求表3")==[['正文']]
    body=api.spreadsheets().values().batchGetByDataFilter.call_args.kwargs['body']
    assert body['dataFilters']==[{'gridRange':{'sheetId':42}}]
    with pytest.raises(ValueError,match='实际工作表') as error:w.read_grid(api,'doc','张三')
    assert "张三'需求表3" in str(error.value)

def test_production_header_on_fifth_row(monkeypatch):
    head=['截至日期','中文','制作人','自动命名','序号']
    monkeypatch.setattr(w,'read_grid',lambda *args:[['长文案'],['资料'],[],[],head])
    row,cols=w.production_location(None,Settings(),task())
    assert row==6 and cols['chinese']==1

def test_left_al_layout_uses_headers_and_preserves_right_side(monkeypatch):
    head=['截至日期','管理员','中文','葡语','人物链接','参考图','','制作人','完成进度','自动命名','序号','成品链接']
    grid=[head+head,['','','','','','','备注占用']+['']*5+['右侧任务']]
    monkeypatch.setattr(w,'read_grid',lambda *args:grid)
    cfg=Settings(production_layout='left_al',production_sheet='模板')
    row,cols=w.production_location(None,cfg,task())
    assert row==2 and cols['owner']==7 and cols['output']==11
    src,dst=w.updates_for_task(cfg,task(),'01','name',row,cols)
    assert any(u['range']=="'模板'!B2" and u['values']==[['甲']] for u in dst)
    assert all(u['range'].split('!')[1][0] in 'ABCDEFGHIJKL' for u in dst)

def test_left_al_empty_starts_under_header(monkeypatch):
    monkeypatch.setattr(w,'read_grid',lambda *args:[['截至日期','中文','制作人','自动命名','序号','成品链接']+['']*6+['右侧']])
    assert w.production_location(None,Settings(production_layout='left_al'),task())[0]==2

def test_left_top_insertion_is_bounded_and_batch_ordered(monkeypatch):
    from unittest.mock import MagicMock
    items=[task(),task('第二来源')]
    monkeypatch.setattr(w,'load_tasks',lambda *a:items)
    monkeypatch.setattr(w,'production_location',lambda *a:(2,COLS))
    monkeypatch.setattr(w,'get_metadata',lambda *a:{'sheetId':123})
    monkeypatch.setattr(w,'record',lambda *a:'op')
    writes=[];monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append(doc))
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号','完成进度','','','','','','成品链接']])
    api=MagicMock();cfg=Settings(source_spreadsheet_id='source',production_spreadsheet_id='target',production_sheet='模板',production_layout='left_al')
    w.claim(api,cfg,[t.identity for t in items])
    req=api.spreadsheets().batchUpdate.call_args.kwargs['body']['requests']
    assert req[0]=={'insertRange':{'range':{'sheetId':123,'startRowIndex':1,'endRowIndex':3,'startColumnIndex':0,'endColumnIndex':12},'shiftDimension':'ROWS'}}
    assert {r['updateCells']['start']['rowIndex'] for r in req[1:]}=={1,2}
    assert writes==['source']


def test_custom_headers_work_for_production_and_empty_other_group(monkeypatch):
    headers=['任务日期','内容文案','负责人员','命名结果','任务编号','成品地址']
    monkeypatch.setattr(w,'read_grid',lambda *a:[headers+headers,[],[]])
    cfg=Settings(production_layout='left_al',header_aliases={'deadline':['任务日期'],'chinese':['内容文案'],'owner':['负责人员'],'filename':['命名结果'],'number':['任务编号'],'output':['成品地址']})
    row,cols=w.production_location(None,cfg,task())
    assert row==2 and cols['owner']==2 and cols['output']==5


def test_multiple_sources_same_sheet_name_route_writes(monkeypatch,tmp_path):
    from zb_studio.config import SourceDocument,SourceSheet
    from datetime import date
    from zb_studio import journal
    monkeypatch.setattr(journal,'path',lambda:tmp_path/'settings.json')
    one=task('同名');two=task('同名');two.source_id='other'
    monkeypatch.setattr(w,'load_tasks',lambda *a:[one,two])
    monkeypatch.setattr(w,'production_location',lambda *a:(4,COLS))
    monkeypatch.setattr(w,'record',lambda *a:'op')
    writes=[];monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append((doc,data)))
    docs=[SourceDocument(spreadsheet_id='source',sheets=[SourceSheet(name='同名',alias='甲',enabled=True)]),SourceDocument(spreadsheet_id='other',sheets=[SourceSheet(name='同名',alias='乙',enabled=True)])]
    cfg=Settings(producer='小王',production_sheet='制作',production_spreadsheet_id='target',source_documents=docs,download_path=str(tmp_path))
    result=w.claim(None,cfg,[one.identity,two.identity])
    assert [x['number'] for x in result]==['01','02']
    assert {doc for doc,_ in writes[:2]}=={'source','other'} and writes[-1][0]=='target'
    assert all(len(data)==4 for doc,data in writes[:2])

def test_person_category_written_to_production():
    cfg=Settings(producer='小王',production_sheet='制作')
    cols=COLS|{'requester':7,'person':8}
    _,dest=w.updates_for_task(cfg,task(),'01','名',2,cols)
    assert any(u['range']=="'制作'!I2" and u['values']==[['长文案']] for u in dest)


def test_today_number_continues_from_prior_claim(monkeypatch,tmp_path):
    from zb_studio import journal
    from datetime import date
    monkeypatch.setattr(journal,'path',lambda:tmp_path/'settings.json')
    existing=task('第一');existing.owner='佳佳';existing.filename='07-ZB-旧-'+date.today().strftime('%Y%m%d')
    new=task('第二')
    monkeypatch.setattr(w,'load_tasks',lambda *a:[existing,new])
    monkeypatch.setattr(w,'production_location',lambda *a:(4,COLS))
    monkeypatch.setattr(w,'record',lambda *a:'op')
    monkeypatch.setattr(w,'batch_write',lambda *a:None)
    result=w.claim(None,Settings(producer='佳佳',production_spreadsheet_id='prod',production_sheet='制作',download_path=str(tmp_path)),[new.identity])
    assert result[0]['number']=='08' and result[0]['filename'].startswith('08-ZB-')


def test_load_multiple_documents_with_same_tab(monkeypatch):
    from zb_studio.config import SourceDocument,SourceSheet
    header=['截至日期','中文','制作人']
    monkeypatch.setattr(w,'read_grid',lambda api,doc,sheet:[['人物'],[],header,['2026-11-02',doc,'']])
    cfg=Settings(source_documents=[SourceDocument(spreadsheet_id='a',sheets=[SourceSheet(name='同名',alias='甲',enabled=True)]),SourceDocument(spreadsheet_id='b',sheets=[SourceSheet(name='同名',alias='乙',enabled=True)])])
    tasks=w.load_tasks(None,cfg)
    assert [(t.source_id,t.requester,t.chinese) for t in tasks]==[('a','甲','a'),('b','乙','b')]


def test_claim_order_is_request_order_not_source_or_deadline(monkeypatch,tmp_path):
    from zb_studio import journal
    monkeypatch.setattr(journal,'path',lambda:tmp_path/'settings.json')
    first=task('先领取');first.deadline='2026-12-31'
    second=task('后领取');second.deadline='2026-01-01'
    monkeypatch.setattr(w,'load_tasks',lambda *a:[second,first])
    monkeypatch.setattr(w,'production_location',lambda *a:(4,COLS))
    monkeypatch.setattr(w,'record',lambda *a:'op')
    monkeypatch.setattr(w,'batch_write',lambda *a:None)
    cfg=Settings(producer='佳佳',production_spreadsheet_id='prod',production_sheet='制作',download_path=str(tmp_path))
    result=w.claim(None,cfg,[first.identity,second.identity])
    assert [(x['id'],x['number']) for x in result]==[(first.identity,'01'),(second.identity,'02')]
    assert result[0]['filename'].startswith('01-')


def test_per_spreadsheet_sequence_and_requested_start(monkeypatch,tmp_path):
    a=task('sheet1');b=task('sheet2');c=task('sheet1');c.source_id='other';c.requester='乙'
    monkeypatch.setattr(w,'load_tasks',lambda *args:[a,b,c])
    monkeypatch.setattr(w,'production_location',lambda *a:(2,COLS))
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接']])
    monkeypatch.setattr(w,'record',lambda *a:'op');monkeypatch.setattr(w,'batch_write',lambda *a:None)
    cfg=Settings(producer='佳佳',production_sheet='制作',production_spreadsheet_id='prod',download_path=str(tmp_path),sequence_mode='per_source',sequence_start=20)
    result=w.claim(None,cfg,[a.identity,b.identity,c.identity])
    assert [x['number'] for x in result]==['20','21','20']

def test_manual_sequence_reuses_after_cleanup_but_stops_on_collision(monkeypatch,tmp_path):
    from datetime import date
    from zb_studio import journal
    monkeypatch.setattr(journal,'path',lambda:tmp_path/'settings.json')
    t=task();monkeypatch.setattr(w,'load_tasks',lambda *a:[t])
    monkeypatch.setattr(w,'production_location',lambda *a:(2,COLS))
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接']])
    writes=[];monkeypatch.setattr(w,'batch_write',lambda *a:writes.append(a));monkeypatch.setattr(w,'record',lambda *a:'op')
    cfg=Settings(producer='佳佳',production_sheet='制作',production_spreadsheet_id='prod',download_path=str(tmp_path),sequence_override=1)
    folder=tmp_path/date.today().strftime('%Y%m%d');folder.mkdir();(folder/'01.png').write_bytes(b'old')
    with pytest.raises(ValueError,match='序号 01 已被'):w.claim(None,cfg,[t.identity])
    assert not writes
    (folder/'01.png').unlink()
    result=w.claim(None,cfg,[t.identity]);assert result[0]['number']=='01'

def test_manual_sequence_checks_existing_production_name(monkeypatch,tmp_path):
    from datetime import date
    t=task();name=w.make_filename(t,'01','ZB','佳佳',date.today())
    monkeypatch.setattr(w,'load_tasks',lambda *a:[t]);monkeypatch.setattr(w,'production_location',lambda *a:(2,COLS))
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接'],['','','',name]])
    writes=[];monkeypatch.setattr(w,'batch_write',lambda *a:writes.append(a))
    cfg=Settings(producer='佳佳',production_sheet='制作',production_spreadsheet_id='prod',download_path=str(tmp_path),sequence_override=1)
    with pytest.raises(ValueError,match='已有本批自动命名'):w.claim(None,cfg,[t.identity])
    assert not writes


def test_hall_edit_matches_production_and_source(monkeypatch):
    t=task();t.owner='甲';t.filename='unique';t.columns=COLS.copy()
    monkeypatch.setattr(w,'load_tasks',lambda *a:[t])
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接'],['日期','文案','甲','unique','','','']])
    monkeypatch.setattr(w,'record',lambda *a:'op');monkeypatch.setattr(w,'verify_updates',lambda *a:None)
    writes=[];monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append((doc,data)))
    w.edit_task_field(None,Settings(production_spreadsheet_id='prod',production_sheet='制作'),t,'owner','乙')
    assert [x[0] for x in writes]==['prod','source']
    assert all(x[1][0]['values']==[['乙']] for x in writes)

def test_hall_edit_rejects_conflicting_production(monkeypatch):
    t=task();t.owner='甲';t.filename='unique';t.columns=COLS.copy()
    monkeypatch.setattr(w,'load_tasks',lambda *a:[t])
    monkeypatch.setattr(w,'read_grid',lambda *a:[['截至日期','中文','制作人','自动命名','序号'],['日期','文案','别人','unique','']])
    writes=[];monkeypatch.setattr(w,'batch_write',lambda *a:writes.append(a))
    with pytest.raises(ValueError,match='不一致'):w.edit_task_field(None,Settings(),t,'owner','乙')
    assert not writes


def test_hall_edit_unclaimed_changes_source_only(monkeypatch):
    t=task();t.columns=COLS.copy()
    monkeypatch.setattr(w,'load_tasks',lambda *a:[t]);monkeypatch.setattr(w,'record',lambda *a:'op');monkeypatch.setattr(w,'verify_updates',lambda *a:None)
    writes=[];monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append((doc,data)))
    w.edit_task_field(None,Settings(),t,'owner','别人')
    assert len(writes)==1 and writes[0][0]=='source'

def test_hall_edit_blocks_changed_source_and_bad_link(monkeypatch):
    t=task();other=task();other.owner='新名字';monkeypatch.setattr(w,'load_tasks',lambda *a:[other])
    with pytest.raises(ValueError,match='已被修改'):w.edit_task_field(None,Settings(),t,'owner','甲')
    with pytest.raises(ValueError,match='链接'):w.edit_task_field(None,Settings(),t,'output','file:///local/file')
