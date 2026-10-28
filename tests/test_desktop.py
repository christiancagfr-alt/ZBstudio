import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from zb_studio.desktop import Window
from zb_studio.config import Settings
from zb_studio.domain import Task
from zb_studio import desktop_service as service
import pytest

@pytest.fixture
def window(monkeypatch,tmp_path):
    from zb_studio import journal
    monkeypatch.setattr(journal,'path',lambda:tmp_path/'settings.json')
    app=QApplication.instance() or QApplication([])
    w=Window(Settings());yield w;w.close();app.processEvents()

def test_native_alias_filter_and_claim_selection(window):
    t=Task('doc','张三需求表3',4,0,'长文案','张三','2026-10-27','测试文案')
    window.loaded([t]);assert window.task_table.item(0,2).text()=='张三 长文案'
    assert window.task_table.item(0,0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    window.search.setText('无匹配');assert window.task_table.rowCount()==0
    window.search.setText('张三');assert window.task_table.rowCount()==1
    window.navigate(0,True);assert window.task_table.rowCount()==0

def test_settings_alias_row_keeps_alias_when_name_changes(window):
    window.add_source('张三需求表3','张三')
    window.sources.item(0,0).setText('张三需求表4')
    assert window.sources.item(0,1).text()=='张三'

def test_upload_preflight_blocks_entire_batch(tmp_path,monkeypatch):
    good=tmp_path/'01-ZB-test-20261027.mp4';good.write_bytes(b'fake')
    bad=tmp_path/'unmatched.mp4';bad.write_bytes(b'fake')
    task=Task('doc','s',4,0,'人','张三','2026-10-27','文案',owner='佳佳',filename=good.stem)
    monkeypatch.setattr(service,'services',lambda:(None,None))
    monkeypatch.setattr(service,'load_tasks',lambda *args:[task])
    uploads=[];monkeypatch.setattr(service,'upload_video',lambda *args:uploads.append(args))
    with pytest.raises(ValueError,match='未唯一匹配'):
        service.upload_files(Settings(drive_parent_folder_id='root'),[good,bad],lambda s:None)
    assert not uploads

def test_discovery_keeps_edited_alias_and_enabled_state(window):
    window.add_source('🧸辛一-佳佳-经营专业','自定义名字',True,42)
    window.choose_source_sheet([{'sheetId':42,'title':'辛一-新名称'},{'sheetId':43,'title':'🍇中磊-佳佳-经营'}])
    assert window.sources.item(0,0).text()=='辛一-新名称'
    assert window.sources.item(0,1).text()=='自定义名字'
    assert window.sources.item(0,2).checkState()==Qt.CheckState.Checked
    assert window.sources.item(1,1).text()=='中磊'
    assert window.sources.item(1,2).checkState()==Qt.CheckState.Unchecked

def test_only_checked_sources_saved_and_catalog_preserved(window,monkeypatch):
    import zb_studio.desktop as desktop
    saved=[];monkeypatch.setattr(desktop,'save_settings',lambda cfg:saved.append(cfg))
    window.add_source('张三需求表3','张三',True,1)
    window.add_source('李四需求表','李四',False,2)
    window.save()
    assert saved[0].source_sheets==['张三需求表3']
    assert saved[0].requester_names=={'张三需求表3':'张三'}
    assert len(saved[0].source_catalog)==2

def test_new_spreadsheet_does_not_reuse_old_numeric_ids(window):
    window.add_source('张三','人工别名',True,1)
    window.fields['source_spreadsheet_id'].setText('new-document')
    window.requested_source_doc='new-document'
    window.choose_source_sheet([{'sheetId':1,'title':'李四-需求'}])
    assert window.sources.item(0,1).text()=='李四'
    assert window.sources.item(0,2).checkState()==Qt.CheckState.Unchecked

@pytest.mark.parametrize('title,expected',[
    ('🧸辛一-佳佳-经营专业','辛一'),('辛一—测试专业','辛一'),
    ('🍇中磊-佳佳-经营','中磊'),('张三需求表3','张三'),('张三','张三')])
def test_alias_suggestions(title,expected):
    from zb_studio.source_settings import suggest_alias
    assert suggest_alias(title)==expected

def test_card_selection_context_and_zoom(window):
    from zb_studio.thumbnails import Thumbnail
    task=Task('doc','sheet',4,0,'主营专业','林夕','10-27','测试')
    window.loaded([task]);window.select_group(('doc','sheet',0))
    assert '林夕 主营专业' in window.count.text()
    assert '共 1 个任务' in window.count.text()
    card=window.group_cards[('doc','sheet',0)]
    assert card.property('selected') is True
    assert card.findChild(Thumbnail).zoom is False
    assert window.task_table.cellWidget(0,6).zoom is True
    assert not window.windowIcon().isNull()
    window.clear_group();assert '全部人物' in window.count.text()

def test_select_all_and_status_buttons_refresh(window):
    a=Task('doc','s',4,0,'人物','张三','2026-10-27','正文')
    b=Task('doc','s',5,0,'人物','张三','2026-10-27','正文',owner='别人')
    window.loaded([a,b]);window.toggle_all(True)
    assert window.task_table.item(0,0).checkState()==Qt.CheckState.Checked
    assert not window.task_table.item(1,0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert window.task_table.cellWidget(0,8) is not None
    a.owner='别人';window.refresh_table()
    assert window.task_table.cellWidget(0,8) is None

def test_compact_layout_and_silent_notifications(window,monkeypatch):
    window.resize(1024,640);window.show();QApplication.processEvents()
    assert window.task_table.height()>=180
    assert window.activity.parentWidget()==window.pages.widget(4)
    assert not window.activity.isVisible()
    window.cfg.voice_enabled=False;window.announce('下载完成')
    assert not hasattr(window,'speech')
    window.log('测试进度');window.show_history()
    assert window.pages.currentIndex()==4 and '测试进度' in window.activity.toPlainText()
    window.navigate(0);assert window.hall_controls.isVisible()


def test_voice_preference_and_stat_alignment(window,monkeypatch):
    import zb_studio.desktop as desktop
    saved=[];monkeypatch.setattr(desktop,'save_settings',lambda cfg:saved.append(cfg))
    window.voice_enabled.setChecked(False);window.save()
    assert saved[-1].voice_enabled is False
    t=Task('doc','s',4,0,'人物','张三','2026-10-27','正文')
    window.loaded([t]);window.refresh_stats()
    assert window.stats.item(0,1).textAlignment()==Qt.AlignmentFlag.AlignCenter
    assert window.stats.columnWidth(1)==76
    assert not window.stats.horizontalHeader().stretchLastSection()
