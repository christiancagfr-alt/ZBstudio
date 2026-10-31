"""Append completion records to a separately configured Google Sheet."""
import math
import re
from datetime import date
from .workflow import quoted, get_metadata, read_grid

LABELS={'date':'日期','link':'成品链接','group':'组别','type':'类型','difficulty':'难易程度','material':'素材来源','software':'软件','producer':'制作人','duration':'视频时长','duration_class':'时长分类'}

def read_categories(api,spreadsheet_id):
    """Read candidate values by column from the target spreadsheet's 分类 tab."""
    if not spreadsheet_id.strip():raise ValueError('请先填写登记表 Spreadsheet ID')
    rows=read_grid(api,spreadsheet_id,'分类')
    keys=('type','material','software','difficulty','duration_class')
    result={key:[] for key in keys}
    for row_index,row in enumerate(rows):
        for col,key in enumerate(keys):
            value=str(row[col]).strip() if col<len(row) and row[col] is not None else ''
            if row_index==0 and value==LABELS[key]:continue
            if value and value not in result[key]:result[key].append(value)
    return result

def validate(cfg):
    if not cfg.register_spreadsheet_id and not cfg.register_sheet:return False
    if not cfg.register_spreadsheet_id or not cfg.register_sheet:raise ValueError('登记表需要同时填写 Spreadsheet ID 和工作表名称')
    columns={}
    for key,value in cfg.register_columns.items():
        if key not in LABELS:raise ValueError('登记表存在不支持的字段：'+key)
        col=str(value).strip().upper()
        if not re.fullmatch(r'[A-Z]{1,3}',col):raise ValueError(f'{LABELS[key]}列号无效，请使用 A、B、AC 等列字母')
        index=0
        for ch in col:index=index*26+ord(ch)-64
        if index>18278 or index in columns.values():raise ValueError('登记表列号重复或无效')
        columns[key]=index
    if not columns:raise ValueError('登记表至少配置一个字段')
    return columns

def preflight(api,cfg):
    columns=validate(cfg)
    if not columns:return False
    meta=get_metadata(api,cfg.register_spreadsheet_id,cfg.register_sheet)
    width=max(columns.values())
    if width>meta.get('gridProperties',{}).get('columnCount',0):raise ValueError('登记表列数不足，请先在 Google 表格中增加列')
    return columns

def append_record(api,cfg,url,duration_ms=None,completion_date=None):
    columns=preflight(api,cfg)
    if not columns:return False
    width=max(columns.values())
    seconds=math.ceil(int(duration_ms)/1000) if duration_ms is not None else None
    values={'date':completion_date or date.today().isoformat(),'link':url,'producer':cfg.producer,**cfg.register_defaults,
            'duration':seconds if seconds is not None else '',
            'duration_class':cfg.register_duration_labels.get('short' if seconds<=59 else 'long','') if seconds is not None else ''}
    row=['']*width
    for key,index in columns.items():row[index-1]=values.get(key,'')
    # APPEND searches the table and inserts one row atomically within this sheet.
    # A failed/unknown response requires human reconciliation, not blind retry.
    api.spreadsheets().values().append(spreadsheetId=cfg.register_spreadsheet_id,range=quoted(cfg.register_sheet),valueInputOption='RAW',insertDataOption='INSERT_ROWS',body={'values':[row]}).execute()
    return True
