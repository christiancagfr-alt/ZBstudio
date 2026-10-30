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
    w=Window(Settings(producer='佳佳'));yield w;w.close();app.processEvents()

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
    assert window.stats.columnWidth(2)==76
    assert not window.stats.horizontalHeader().stretchLastSection()

def test_my_production_filters_viral_and_shows_views(window):
    a=Task('doc','s',4,0,'人物','甲','2026-10-27','正文',owner='佳佳',output='link',views='1.2万',viral=True)
    b=Task('doc','s',5,0,'人物','甲','2026-10-27','正文',owner='佳佳',output='link2',views='99')
    window.loaded([a,b]);window.navigate(0,True);window.viral_filter.setCurrentIndex(1)
    assert window.task_table.rowCount()==1
    assert window.task_table.item(0,11).text()=='1.2万'
    assert window.task_table.item(0,12).text()=='爆帖'
    window.viral_filter.setCurrentIndex(2)
    assert window.task_table.rowCount()==1 and window.task_table.item(0,11).text()=='99'

def test_playback_note_link_is_clickable_in_my_production(window,monkeypatch):
    import zb_studio.desktop as desktop
    from PySide6.QtWidgets import QLabel
    opened=[];monkeypatch.setattr(desktop.QDesktopServices,'openUrl',lambda url:opened.append(url.toString()) or True)
    task=Task('doc','s',4,0,'人物','甲','2026-10-27','正文',owner='佳佳',views='1.2万',views_note='贴文 https://example.com/post/1',views_url='https://example.com/post/1')
    window.loaded([task]);window.navigate(0,True)
    link=window.task_table.cellWidget(0,11)
    assert isinstance(link,QLabel) and '1.2万' in link.text()
    assert link.alignment()==Qt.AlignmentFlag.AlignCenter
    assert window.task_table.item(0,11).text()==''
    assert link.toolTip()==task.views_note
    link.linkActivated.emit(task.views_url)
    assert opened==['https://example.com/post/1']

def test_copy_stats_includes_headers_and_all_visible_rows(window,monkeypatch):
    import csv,io
    from PySide6.QtCore import QDate
    window.stats_from.setDate(QDate(2026,10,1));window.stats_to.setDate(QDate(2026,10,31))
    task=Task('doc','表一',4,0,'人物','甲','2026-10-27','正文',output='link',viral=True,views='100000+')
    window.loaded([task]);window.refresh_stats();window.copy_stats()
    rows=list(csv.reader(io.StringIO(QApplication.clipboard().text()),delimiter='\t'))
    assert rows[0][0:2]==['需求表','需求者 / 人物']
    assert rows[1][0:2]==['表一','甲 人物']
    assert rows[0][6]=='爆帖数量' and '播放量合计' not in rows[0]
    assert rows[1][6]=='1'
