"""Task parsing and naming rules; independent of Google or UI."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
import re
import unicodedata

ALIASES = {
    "requester": ["管理员", "需求者"],
    "deadline": ["截至日期", "截止日期", "日期", "时间"],
    "chinese": ["中文", "中文文案", "文案"],
    "portuguese": ["葡语", "葡萄牙语"],
    "image": ["图片链接", "人物链接", "图片", "人物图片"],
    "reference": ["参考图", "图片缩略图"],
    "owner": ["制作人", "领取人"],
    "progress": ["完成进度", "着急程度/进度", "进度"],
    "requirements": ["制作要求"],
    "urgency": ["着急程度", "紧急程度"],
    "filename": ["自动命名", "成品命名"],
    "number": ["序号", "编号"],
    "output": ["成品链接", "视频链接"],
    "views": ["播放量", "观看量", "播放次数"],
}
OUTPUTS={"owner":"制作人", "filename":"自动命名", "number":"序号", "output":"成品链接"}

def normalize(x):return re.sub(r"\s+", "", str(x or "")).lower()
def key_for(s):
    n=normalize(s)
    for k,vals in ALIASES.items():
        if n in {normalize(v) for v in vals}:return k
    return None

def date_key(value):
    s=str(value or "").strip()
    if isinstance(value, (date, datetime)):return value.strftime("%Y%m%d")
    m=re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})",s)
    if m:return f"{int(m[1]):04d}{int(m[2]):02d}{int(m[3]):02d}"
    if re.match(r"^\d{8}$",s):return s
    return s

def safe_component(s, max_len=110):
    s=unicodedata.normalize('NFC',str(s or '')).strip()
    s=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',s).rstrip(' .')
    s=s[:max_len].rstrip(' .') or '未命名'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',s):s='_'+s
    return s

@dataclass
class Task:
    source_id:str
    sheet:str
    row:int
    start_col:int
    person:str
    requester:str
    deadline:str
    chinese:str
    portuguese:str=''
    image:str=''
    reference:str=''
    owner:str=''
    filename:str=''
    number:str=''
    output:str=''
    progress:str=''
    columns:dict=field(default_factory=dict)
    avatar:str=''
    requirements:str=''
    urgency:str=''
    views:str=''
    viral:bool=False
    views_note:str=''
    views_url:str=''
    @property
    def identity(self):return f"{self.source_id}:{self.sheet}:{self.start_col}:{self.row}"
    @property
    def label(self):return f"{self.requester} {self.person}".strip()
    @property
    def available(self):return not self.owner.strip()

def header_index(grid):
    """Locate a horizontal task header, preserving all original row offsets."""
    for r,row in enumerate(grid[:30]):
        starts=[c for c,v in enumerate(row) if key_for(v)=='deadline']
        for i,start in enumerate(starts):
            end=starts[i+1] if i+1<len(starts) else len(row)
            if any(key_for(v)=='chinese' for v in row[start:end]):return r
    return None

def parse_sheet(spreadsheet_id, sheet, grid, requester=None):
    """Parse the horizontal 10-column person groups; row1 category, row2 avatar, row3 headers."""
    out=[]
    header_row=header_index(grid)
    if header_row is None:
        if any(any(str(v).strip() for v in row) for row in grid):
            raise ValueError(f'工作表「{sheet}」前30行未找到同时包含“截至日期”和“中文”的任务表头，请检查模板')
        return out
    width=max(len(r) for r in grid)
    header=grid[header_row]
    # Identify group starts from deadline headers, not hard-coded A-J/L-U offsets.
    starts=[i for i,v in enumerate(header) if key_for(v)=='deadline']
    for group_idx,start in enumerate(starts):
        end=starts[group_idx+1] if group_idx+1<len(starts) else width
        cmap={}
        for c in range(start,min(end,len(header))):
            k=key_for(header[c])
            if k and k not in cmap:cmap[k]=c
        if not all(k in cmap for k in ('deadline','chinese')):continue
        group_head=(grid[0][start] if start<len(grid[0]) else '')
        person=group_head.strip() if isinstance(group_head,str) else str(group_head)
        if not person:person=f'人物_{group_idx+1}'
        for r_idx in range(header_row+1,len(grid)):
            row=grid[r_idx]
            def get(k):
                c=cmap.get(k)
                return str(row[c]).strip() if c is not None and c<len(row) and row[c] is not None else ''
            if not get('chinese'):continue
            out.append(Task(spreadsheet_id,sheet,r_idx+1,start,person,requester or sheet,
                get('deadline'),get('chinese'),get('portuguese'),get('image'),get('reference'),
                get('owner'),get('filename'),get('number'),get('output'),get('progress'),cmap,
                str(grid[1][start]) if len(grid)>1 and start<len(grid[1]) else '',get('requirements'),get('urgency'),get('views')))
    return out

def allocate_numbers(all_tasks, selected_ids):
    """Stable sheet-order numbers, per source group and task date; unclaimed rows reserve positions."""
    selected=set(selected_ids)
    indexed={}
    for t in sorted(all_tasks,key=lambda x:(x.source_id,x.sheet,x.start_col,x.row)):
        k=(t.source_id,t.sheet,t.start_col,date_key(t.deadline))
        indexed[k]=indexed.get(k,0)+1
        if t.identity in selected:
            yield t,str(indexed[k]).zfill(2)

def make_filename(task,number,prefix,producer,claim_date):
    parts=[number,prefix,task.label,producer,task.chinese,date_key(claim_date)]
    return '-'.join(safe_component(v,180 if i==4 else 100) for i,v in enumerate(parts))

def match_filename(stem,tasks):
    return [t for t in tasks if t.filename and stem==t.filename]
