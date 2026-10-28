from zb_studio.domain import parse_sheet,allocate_numbers,make_filename,date_key,match_filename,safe_component

def sheet():
    grid=[['主套专业','','','','','','','','','','','长文案专业'],
          ['avatar','','','','','','','','','','','avatar'],
          ['截至日期','中文','葡语','图片链接','图片缩略图','制作人','着急程度/进度','自动命名','序号','成品链接','','截至日期','中文','葡语','图片链接','图片缩略图','制作人','着急程度/进度','自动命名','序号','成品链接'],
          ['2026-10-26','第一条','P1','https://example.com/1.jpg','','','','','','','','2026-10-26','另一个','P2','','','','','','',''],
          ['2026-10-26','第二条','P3','','','','','','','','','2026-10-27','新一天','P4','','','','','','',''],
          ['2026-10-27','第三条','P5','','','','','','','','']]
    return parse_sheet('abc','辛一',grid,'辛一')

def test_horizontal_and_numbers():
    tasks=sheet();assert len(tasks)==5
    assert tasks[0].label=='辛一 主套专业'
    assert tasks[2].label=='辛一 主套专业'
    assert tasks[3].label=='辛一 长文案专业'
    results=list(allocate_numbers(tasks,[t.identity for t in tasks]))
    mapping={t.identity:num for t,num in results}
    assert [mapping[t.identity] for t in tasks]==['01','02','01','01','01']

def test_subselection_preserves_original_order():
    tasks=sheet(); picked=list(allocate_numbers(tasks,[tasks[1].identity]))
    assert picked[0][1]=='02'

def test_filename():
    t=sheet()[0]
    name=make_filename(t,'01','ZB','佳佳','2026-10-26')
    assert name=='01-ZB-辛一 主套专业-佳佳-第一条-20261026'
    t.filename=name
    assert match_filename(name,[t])==[t]
    assert safe_component('x/a:b*')=='x_a_b_'

import pytest
@pytest.mark.parametrize('row_index',[2,3,4])
def test_variable_header_rows_preserve_source_positions(row_index):
    grid=[['长文案']]+[[] for _ in range(row_index-1)]+[['截至日期','中文','制作人'],['2026-10-28','第一条',''],['2026-10-28','第二条','']]
    ts=parse_sheet('doc','需求',grid,'张三')
    assert [t.row for t in ts]==[row_index+2,row_index+3]
    assert [n for t,n in allocate_numbers(ts,[ts[1].identity])]==['02']

def test_invalid_header_reports_problem_instead_of_zero():
    with pytest.raises(ValueError,match='任务表头'):parse_sheet('doc','需求',[['说明'],[],['不支持的字段']])
