from datetime import date
from unittest.mock import MagicMock

from zb_studio.domain import Task,parse_sheet
from zb_studio.workflow import read_output_colors,is_green_cell,left_header,post_link
from zb_studio.reporting import report
from zb_studio import desktop_service
from zb_studio.config import Settings


def test_new_headers_and_multiple_groups_keep_positions():
    header=['截至日期','中文','葡语','图片链接','图片缩略图','制作要求','着急程度','制作人','进度','自动命名','序号','成品链接','播放量']
    grid=[['人物一']+['']*12+['人物二'],[],header+header,['10-27','第一']+['']*9+['link','12,345','10-27','第二']+['']*9+['link2','6万']]
    one,two=parse_sheet('doc','sheet',grid,'需求者')
    assert (one.views,two.views)==('12,345','6万')
    assert (one.columns['output'],two.columns['output'])==(11,24)
    assert len(left_header(header+header))==13


def test_effective_green_fill_and_theme_color():
    green={'effectiveFormat':{'backgroundColorStyle':{'rgbColor':{'red':0.71,'green':0.84,'blue':0.66}}}}
    assert is_green_cell(green,{})
    assert is_green_cell({'effectiveFormat':{'backgroundColorStyle':{'themeColor':'ACCENT1'}}},{'ACCENT1':{'red':0,'green':0.8,'blue':0}})
    assert not is_green_cell({'effectiveFormat':{'backgroundColor':{'red':1,'green':1,'blue':1}}},{})
    assert not is_green_cell({'effectiveFormat':{'backgroundColor':{'red':0,'green':0.3,'blue':0.9}}},{})
    assert not is_green_cell({}, {})


def test_color_ranges_map_to_source_rows_and_groups():
    one=Task('doc','s',4,0,'一','甲','2026-10-27','a',output='link',columns={'output':11})
    two=Task('doc','s',7,13,'二','甲','2026-10-27','b',output='link2',columns={'output':24})
    missing=Task('doc','s',5,0,'一','甲','2026-10-27','c',columns={'output':11})
    api=MagicMock()
    green={'effectiveFormat':{'backgroundColor':{'green':0.8}}}
    api.spreadsheets().getByDataFilter().execute.return_value={'sheets':[{'properties':{'sheetId':42},'data':[{'startRow':3,'startColumn':11,'rowData':[{'values':[green]}]},{'startRow':6,'startColumn':24,'rowData':[{'values':[{}]}]}]}]}
    read_output_colors(api,'doc',42,[one,two,missing])
    assert one.viral and not two.viral and not missing.viral
    filters=api.spreadsheets().getByDataFilter.call_args.kwargs['body']['dataFilters']
    assert [item['gridRange']['startColumnIndex'] for item in filters]==[11,24]


def test_playback_notes_and_links_follow_original_rows_and_groups():
    one=Task('doc','s',4,0,'一','甲','2026-10-27','a',views='123',columns={'views':12})
    two=Task('doc','s',7,13,'二','甲','2026-10-27','b',views='4万',columns={'views':25})
    api=MagicMock()
    api.spreadsheets().getByDataFilter().execute.return_value={'sheets':[{'properties':{'sheetId':42},'data':[
        {'startRow':3,'startColumn':12,'rowData':[{'values':[{'note':'贴文：https://example.com/post/1\n备注'}]}]},
        {'startRow':6,'startColumn':25,'rowData':[{'values':[{'hyperlink':'https://example.com/post/2'}]}]}]}]}
    read_output_colors(api,'doc',42,[one,two])
    assert one.views_note=='贴文：https://example.com/post/1\n备注'
    assert one.views_url=='https://example.com/post/1'
    assert two.views_url=='https://example.com/post/2'
    filters=api.spreadsheets().getByDataFilter.call_args.kwargs['body']['dataFilters']
    assert [item['gridRange']['startColumnIndex'] for item in filters]==[12,25]
    assert post_link('javascript:alert(1)')==''
    assert post_link('https://user:password@example.com')==''
    assert post_link('网址：https://example.com/post/1。')=='https://example.com/post/1'


def test_report_counts_green_finished_tasks_per_sheet():
    a=Task('doc','one',4,0,'人物','甲','2026-10-27','a',owner='制作人',output='link',viral=True,views='1.2万')
    b=Task('doc','one',5,0,'人物','甲','2026-10-27','b',owner='制作人',output='link2',views='500')
    c=Task('doc','two',4,0,'人物','甲','2026-10-27','c',owner='制作人',output='link3')
    rows=report([a,b,c],[],date(2026,10,1),date(2026,10,31))['rows']
    assert rows==[['one','甲 人物',2,0,2,2,1,0],['two','甲 人物',1,0,1,1,0,0]]


def test_viral_count_does_not_depend_on_playback_value():
    a=Task('doc','one',4,0,'人物','甲','2026-10-27','a',output='link',viral=True,views='100000+')
    b=Task('doc','one',5,0,'人物','甲','2026-10-27','b',output='link2',views='未统计')
    row=report([a,b],[],date(2026,10,1),date(2026,10,31))['rows'][0]
    assert row[5:7]==[2,1]


def test_upload_accepts_image_and_preserves_extension(tmp_path,monkeypatch):
    path=tmp_path/'01-ZB-test-20261027.png';path.write_bytes(b'image')
    task=Task('doc','s',4,0,'人','甲','2026-10-27','正文',owner='制作人',filename=path.stem)
    monkeypatch.setattr(desktop_service,'services',lambda:(None,None))
    monkeypatch.setattr(desktop_service,'load_tasks',lambda *args,**kwargs:[task])
    sent=[];monkeypatch.setattr(desktop_service,'upload_video',lambda drive,p,*args:sent.append(p.name) or 'https://drive.google.com/file/d/1/view')
    monkeypatch.setattr(desktop_service,'write_completed',lambda *args:None)
    monkeypatch.setattr(desktop_service,'record',lambda *args:'op')
    assert desktop_service.upload_files(Settings(producer='制作人',drive_parent_folder_id='root'),[path],lambda _:None)==1
    assert sent==[path.name]
