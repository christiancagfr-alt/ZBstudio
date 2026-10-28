import pytest
from zb_studio import workflow as w
from zb_studio.config import Settings
from zb_studio.domain import Task
COLS={'deadline':0,'chinese':1,'owner':2,'filename':3,'number':4,'progress':5,'output':6}
def task(sheet='需求',start=0):
    return Task('source',sheet,4,start,'长文案','甲','2026-10-27','正文',columns=COLS.copy())
def test_exact_group(monkeypatch):
    monkeypatch.setattr(w,'read_grid',lambda *args:[['超长文案'],[],['截至日期','中文','制作人','自动命名','序号']])
    with pytest.raises(ValueError,match='唯一匹配'):w.production_location(None,Settings(),task())
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
    assert events==['prepared','source_written','needs_review']

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
