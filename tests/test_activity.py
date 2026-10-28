from datetime import date
from unittest.mock import MagicMock
import pytest
from zb_studio.domain import Task
from zb_studio.config import Settings
from zb_studio import workflow as w
from zb_studio.reporting import report


def test_report_counts_snapshot_and_events_separately():
    t=Task('s','sheet',4,0,'人物','张三','10-27','正文',owner='佳佳')
    events=[{'kind':kind,'state':state,'updated':'2026-10-27T12:00:00+00:00','payload':{'tasks':[t.__dict__]}} for kind,state in [('claim','complete'),('release','complete'),('claim','needs_review')]]
    data=report([t],events,date(2026,10,1),date(2026,10,31))
    assert data['rows']==[['张三 人物',1,0,1,0,1]]
    assert data['days']['2026-10-27']=={'claim':1,'release':1,'upload':0}
    assert len(data['days'])==31


def test_verify_source_mismatch_fails():
    api=MagicMock();api.spreadsheets().values().batchGet().execute.return_value={'valueRanges':[{'values':[['别人']]}]}
    with pytest.raises(ValueError,match='核验失败'):
        w.verify_updates(api,'s',[{'range':"'sheet'!H4",'values':[['佳佳']]}])


@pytest.mark.parametrize('owner,output',[('别人',''),('佳佳','https://drive.google.com/file/d/test')])
def test_release_cannot_clear_other_or_completed_task(monkeypatch,owner,output):
    t=Task('s','sheet',4,0,'人物','张三','10-27','正文',owner=owner,output=output,filename='name')
    monkeypatch.setattr(w,'load_tasks',lambda *args:[t])
    writes=[];monkeypatch.setattr(w,'batch_write',lambda *args:writes.append(args))
    with pytest.raises(ValueError,match='只能放弃'):
        w.release_task(None,Settings(producer='佳佳'),t.identity,'name',lambda s:None)
    assert not writes


def test_release_preserves_history_and_checks_source(monkeypatch):
    t=Task('s','sheet',4,0,'人物','张三','10-27','正文',owner='佳佳',filename='name',columns={'owner':2,'filename':3,'number':4,'progress':5})
    fresh=Task('s','sheet',4,0,'人物','张三','10-27','正文')
    snapshots=iter([[t],[fresh]])
    monkeypatch.setattr(w,'load_tasks',lambda *args:next(snapshots))
    monkeypatch.setattr(w,'read_grid',lambda *args:[['截至日期','中文','制作人','自动命名','序号','完成进度','成品链接'],['10-27','正文','佳佳','name','01','制作中','']])
    writes=[];events=[]
    monkeypatch.setattr(w,'batch_write',lambda api,doc,data:writes.append((doc,data)))
    monkeypatch.setattr(w,'record',lambda kind,state,*args:events.append(state) or 'op')
    cfg=Settings(producer='佳佳',production_spreadsheet_id='p',source_spreadsheet_id='s',production_layout='left_al')
    assert w.release_task(None,cfg,t.identity,'name',lambda s:None)==t.identity
    assert writes[0][0]=='p' and writes[1][0]=='s'
    assert any(u['values']==[['已放弃']] for u in writes[0][1])
    assert any(u['values']==[['']] for u in writes[1][1])
    assert events==['prepared','production_written','complete']

def test_download_failure_does_not_undo_claim(monkeypatch):
    from zb_studio import desktop_service as service
    monkeypatch.setattr(service,'services',lambda:(None,None))
    item={'id':'id','folder':'张三 人物','number':'01'}
    monkeypatch.setattr(service,'claim',lambda *args:[item])
    def fail(*args):raise OSError('下载失败')
    monkeypatch.setattr(service,'download_claim_image',fail)
    events=[];monkeypatch.setattr(service,'record',lambda *args:events.append(args))
    result=service.claim_tasks(Settings(),['id'],lambda s:None)
    assert result['claimed']==[item] and len(result['failed_downloads'])==1
    assert events[0][:2]==('download','failed')

def test_thirteen_columns_keep_urgency_separate(monkeypatch):
    from zb_studio.domain import parse_sheet
    head=['截至日期','管理员','中文','葡语','人物链接','参考图','制作要求','着急程度','制作人','完成进度','自动命名','序号','成品链接']
    source=[['长文案'],[],head,['2026-10-28','张三','正文','texto','','','竖屏','加急']]
    t=parse_sheet('s','需求',source,'张三')[0]
    assert t.requirements=='竖屏' and t.urgency=='加急' and t.columns['progress']==9
    monkeypatch.setattr(w,'read_grid',lambda *args:[head+head])
    cfg=Settings(production_layout='left_al',production_sheet='制作')
    row,cols=w.production_location(None,cfg,t)
    assert cols['output']==12 and len(w.left_header(head+head))==13
    src,dst=w.updates_for_task(cfg,t,'01','name',row,cols)
    assert not any(u['range'].endswith('H4') for u in src)
    assert any(u['range'].endswith('J4') and u['values']==[['制作中']] for u in src)
    assert any(u['range'].endswith('G2') and u['values']==[['竖屏']] for u in dst)
    assert any(u['range'].endswith('H2') and u['values']==[['加急']] for u in dst)


def test_image_collisions_and_retries_preserve_existing(tmp_path,monkeypatch):
    from zb_studio import desktop_service as service,image_fetch
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtCore import QBuffer,QIODevice
    def png(color):
        image=QImage(2,2,QImage.Format.Format_RGB32);image.fill(QColor(color))
        buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG');return bytes(buffer.data())
    first,second=png('red'),png('blue');current=[first]
    monkeypatch.setattr(image_fetch,'fetch_image',lambda *a,**k:current[0])
    monkeypatch.setattr(service,'record',lambda *a:None)
    cfg=Settings(download_path=str(tmp_path));item={'id':'a','image':'url','number':'01','date':'20261028','deadline':'10-27','folder':'张三 人物'}
    a=service.download_claim_image(cfg,item);current[0]=second;item.update(id='b',deadline='10-28')
    b=service.download_claim_image(cfg,item)
    from pathlib import Path
    assert a!=b and Path(a).read_bytes()==first and Path(b).read_bytes()==second
    assert service.download_claim_image(cfg,item)==b

def test_download_separates_demand_dates(tmp_path,monkeypatch):
    from zb_studio import desktop_service as service,image_fetch
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QBuffer,QIODevice
    from pathlib import Path
    image=QImage(2,2,QImage.Format.Format_RGB32);image.fill(0)
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
    monkeypatch.setattr(image_fetch,'fetch_image',lambda *a,**k:bytes(buffer.data()))
    monkeypatch.setattr(service,'record',lambda *a:None)
    cfg=Settings(download_path=str(tmp_path))
    base={'id':'a','image':'url','number':'01','date':'20261028','folder':'林夕 长文案需求'}
    a=Path(service.download_claim_image(cfg,dict(base,deadline='10-27')))
    b=Path(service.download_claim_image(cfg,dict(base,deadline='2026-10-28')))
    assert a.relative_to(tmp_path).parts==('20261028','20261027','林夕 长文案需求','01.png')
    assert b.relative_to(tmp_path).parts==('20261028','20261028','林夕 长文案需求','01.png')
