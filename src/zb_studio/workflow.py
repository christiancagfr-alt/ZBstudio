"""Google Sheets workflow; single-instance safety only (not distributed transactions)."""
import threading
from datetime import date
from pathlib import Path
import re
import colorsys
from urllib.parse import urlsplit
from .domain import parse_sheet,allocate_numbers,make_filename,date_key,match_filename,OUTPUTS,key_for,header_index
from .config import Settings
from .journal import record

LOCK=threading.RLock()
def a1col(n):
    s='';n+=1
    while n:s=chr(65+(n-1)%26)+s;n=(n-1)//26
    return s

def quoted(name):return "'"+name.replace("'","''")+"'"

def read_grid(api,doc,sheet,metadata=None):
    # Resolve the exact tab title, then read by numeric sheetId to avoid A1
    # parsing ambiguities with punctuation, named ranges and non-Latin titles.
    metadata=metadata or get_metadata(api,doc,sheet)
    result=api.spreadsheets().values().batchGetByDataFilter(
        spreadsheetId=doc,body={'dataFilters':[{'gridRange':{'sheetId':metadata['sheetId']}}],
        'valueRenderOption':'FORMATTED_VALUE','majorDimension':'ROWS'}).execute()
    ranges=result.get('valueRanges',[])
    return ranges[0].get('valueRange',{}).get('values',[]) if ranges else []

def is_green_cell(cell,theme):
    """Recognize green fills by hue and saturation, not green text or white cells."""
    fmt=cell.get('effectiveFormat',{})
    style=fmt.get('backgroundColorStyle',{})
    color=style.get('rgbColor') or theme.get(style.get('themeColor')) or fmt.get('backgroundColor') or {}
    if not isinstance(color,dict):return False
    try:r,g,b=(float(color.get(k,0)) for k in ('red','green','blue'))
    except (TypeError,ValueError):return False
    if not all(0<=v<=1 for v in (r,g,b)):return False
    hue,saturation,value=colorsys.rgb_to_hsv(r,g,b)
    return value>=0.15 and saturation>=0.18 and 75<=hue*360<=165 and g>r and g>b

def post_link(note,hyperlink=''):
    """Use the first web link in a cell note, or its existing cell hyperlink."""
    candidates=re.findall(r'https?://[^\s<>"\'\u3000-\u303f]+',str(note or ''),re.I)
    if hyperlink:candidates.append(str(hyperlink))
    for candidate in candidates:
        candidate=candidate.rstrip('.,;:!?)]}，。；：！？）】》')
        try:
            url=urlsplit(candidate)
            if url.scheme.lower() in ('http','https') and url.hostname and not url.username and not url.password:
                return candidate
        except ValueError:continue
    return ''

def read_output_colors(api,doc,sheet_id,tasks):
    """Read displayed output fills and playback-cell notes in one batch per sheet."""
    columns=sorted({t.columns[key] for t in tasks for key in ('output','views') if key in t.columns and (key=='views' or t.output)})
    if not columns:return
    ranges=[]
    for col in columns:
        rows=[t.row for t in tasks if t.columns.get('views')==col or (t.output and t.columns.get('output')==col)]
        ranges.append({'gridRange':{'sheetId':sheet_id,'startRowIndex':min(rows)-1,'endRowIndex':max(rows),'startColumnIndex':col,'endColumnIndex':col+1}})
    result=api.spreadsheets().getByDataFilter(spreadsheetId=doc,body={'dataFilters':ranges,'includeGridData':True},fields='properties(spreadsheetTheme(themeColors(colorType,color))),sheets(properties(sheetId),data(startRow,startColumn,rowData(values(note,hyperlink,effectiveFormat(backgroundColor,backgroundColorStyle)))))').execute()
    theme={x.get('colorType'):x.get('color',{}).get('rgbColor',{}) for x in result.get('properties',{}).get('spreadsheetTheme',{}).get('themeColors',[])}
    cells={}
    for sheet in result.get('sheets',[]):
        if sheet.get('properties',{}).get('sheetId')!=sheet_id:continue
        for block in sheet.get('data',[]):
            row0=block.get('startRow',0);col0=block.get('startColumn',0)
            for offset,row in enumerate(block.get('rowData',[])):
                for col_offset,cell in enumerate(row.get('values',[])):
                    cells[(row0+offset+1,col0+col_offset)]=cell
    for task in tasks:
        task.viral=bool(task.output and is_green_cell(cells.get((task.row,task.columns.get('output')),{}),theme))
        playback=cells.get((task.row,task.columns.get('views')),{})
        task.views_note=str(playback.get('note') or '')
        task.views_url=post_link(task.views_note,playback.get('hyperlink',''))

def load_tasks(api,cfg:Settings,progress=None,include_metrics=False):
    if not cfg.source_sheets:raise ValueError('尚未启用工作表：请在设置中勾选工作表并点击“保存设置”，再刷新任务')
    tasks=[]
    metadata={s['title']:s for s in list_sheet_metadata(api,cfg.source_spreadsheet_id)} if progress else {}
    for i,name in enumerate(cfg.source_sheets):
        if progress:
            progress(f'正在读取工作表 {i+1}/{len(cfg.source_sheets)}：{name}')
            if name not in metadata:raise ValueError(f'工作表已改名或不存在：{name}，请在设置中重新读取工作表列表')
            grid=read_grid(api,cfg.source_spreadsheet_id,name,metadata[name])
        else:grid=read_grid(api,cfg.source_spreadsheet_id,name)
        parsed=parse_sheet(cfg.source_spreadsheet_id,name,grid,cfg.requester_names.get(name,name))
        if include_metrics and any('views' in t.columns or (t.output and 'output' in t.columns) for t in parsed):
            meta=metadata[name] if progress else get_metadata(api,cfg.source_spreadsheet_id,name)
            if progress:progress(f'正在同步成品颜色、播放量和贴文链接：{name}')
            read_output_colors(api,cfg.source_spreadsheet_id,meta['sheetId'],parsed)
        tasks.extend(parsed)
    if cfg.start_date or cfg.end_date:
        low=date_key(cfg.start_date) if cfg.start_date else ''
        high=date_key(cfg.end_date) if cfg.end_date else '99999999'
        tasks=[t for t in tasks if low<=date_key(t.deadline)<=high]
    return tasks

def list_sheet_metadata(api,doc):
    if not doc.strip():raise ValueError('请先填写 Spreadsheet ID（表格网址 /d/ 与 /edit 之间的部分）')
    result=api.spreadsheets().get(spreadsheetId=doc,fields='sheets(properties(sheetId,title,gridProperties))').execute()
    return [s['properties'] for s in result.get('sheets',[])]

def get_metadata(api,doc,sheet):
    tabs=list_sheet_metadata(api,doc)
    matches=[s for s in tabs if s['title']==sheet]
    if len(matches)!=1:
        names='、'.join('「'+s['title']+'」' for s in tabs)
        raise ValueError(f'此表格中找不到实际工作表「{sheet}」。\n'
                         f'可用的工作表：{names or "（无）"}\n'
                         '请在设置中选择底部标签的实际 Sheet 名称，不是表格文件标题或需求者别名。'
                         '别名填写在右侧，仍用于命名。')
    return matches[0]

def prepare_header_extensions(api,cfg,tasks):
    """Fill missing columns in each person's horizontal group, only if there is a blank gap."""
    updates=[]
    by_group={}
    for t in tasks:by_group[(t.sheet,t.start_col)]=t
    for (sheet,start),t in by_group.items():
        # template normally has all four output fields. Never overwrite neighbor groups.
        missing=[k for k in OUTPUTS if k not in t.columns]
        if missing:raise ValueError(f'{sheet} 人物 {t.person} 缺少列 {missing}；请先在该横向组配置对应表头，避免覆盖相邻人物')
    return updates

def left_header(header):
    """First field group ends at its output column or the next deadline group."""
    starts=[c for c,h in enumerate(header) if key_for(h)=='deadline']
    if not starts or starts[0]!=0:raise ValueError('制作表左侧首列必须为日期表头')
    end=starts[1] if len(starts)>1 else len(header)
    outputs=[c for c in range(end) if key_for(header[c])=='output']
    if outputs:
        end=outputs[0]+1
        if end<len(header) and key_for(header[end])=='views':end+=1
    return header[:end]


def production_location(api,cfg,task):
    """Find matching group in producer's horizontal template; append to first wholly empty row."""
    grid=read_grid(api,cfg.production_spreadsheet_id,cfg.production_sheet)
    header_row=header_index(grid)
    if header_row is None:raise ValueError('制作表未找到包含“截至日期”和“中文”的字段标题行')
    header=grid[header_row]
    if cfg.production_layout=='left_al':
        cols={}
        for c,h in enumerate(left_header(header)):
            key=key_for(h)
            if key:
                if key in cols:raise ValueError('制作表左侧字段组存在重复字段，请核对表头')
                cols[key]=c
        missing=[k for k in ('deadline','chinese','owner','filename','number','output') if k not in cols]
        if missing:raise ValueError(f'制作表左侧字段组缺少必要字段：{missing}')
        return header_row+2,cols
    groups=parse_sheet(cfg.production_spreadsheet_id,cfg.production_sheet,grid,'')
    # Parse group definitions even when task rows are empty.
    starts=[c for c,h in enumerate(header) if key_for(h)=='deadline']
    matches=[]
    for i,start in enumerate(starts):
        group_label= str(grid[0][start]).strip() if start<len(grid[0]) else ''
        # requester+person or category-only depending on template
        if group_label==task.person or group_label==task.label:
            end=starts[i+1] if i+1<len(starts) else len(header)
            cmap={key_for(header[c]):c for c in range(start,end) if key_for(header[c])}
            if all(k in cmap for k in ('deadline','chinese','owner','filename','number')):matches.append((start,cmap))
    if len(matches)!=1:raise ValueError(f'制作表未找到唯一匹配人物组：{task.label}；请核对第1行标题及第3行表头')
    _,cols=matches[0]
    used=[r for r in range(header_row+1,len(grid)) if any(c<len(grid[r]) and str(grid[r][c]).strip() for c in cols.values())]
    row=(max(used)+2) if used else header_row+2
    return row,cols

def updates_for_task(cfg,task,number,name,production_row,production_cols):
    source_fields={'owner':cfg.producer,'filename':name,'number':number,'progress':'制作中'}
    production_fields={'requester':task.requester,'deadline':task.deadline,'chinese':task.chinese,'portuguese':task.portuguese,
       'image':task.image,'reference':task.reference,'requirements':task.requirements,'urgency':task.urgency,'views':task.views,'owner':cfg.producer,'filename':name,'number':number,'progress':'制作中'}
    updates_source=[];updates_prod=[]
    for k,v in source_fields.items():
        if k in task.columns:
            updates_source.append({'range':f'{quoted(task.sheet)}!{a1col(task.columns[k])}{task.row}','values':[[v]]})
    for k,v in production_fields.items():
        if k in production_cols:
            updates_prod.append({'range':f'{quoted(cfg.production_sheet)}!{a1col(production_cols[k])}{production_row}','values':[[v]]})
    return updates_source,updates_prod

def batch_write(api,doc,updates):
    if updates:api.spreadsheets().values().batchUpdate(spreadsheetId=doc,body={'valueInputOption':'RAW','data':updates}).execute()

def claim(api,cfg:Settings,ids:list[str],progress=None):
    """Two-phase preflight + writes. Cross-document writes are NOT atomic.
    For shared multi-computer operation use a central coordinator and durable journal.
    """
    with LOCK:
        notify=progress or (lambda message:None)
        notify('正在读取来源表并检查任务占用…')
        all_tasks=load_tasks(api,cfg,progress) if progress else load_tasks(api,cfg)
        lookup={t.identity:t for t in all_tasks}
        if not ids or len(ids)!=len(set(ids)):raise ValueError('请选择互不重复的任务')
        picked=[lookup.get(i) for i in ids]
        if any(t is None or not t.available for t in picked):raise ValueError('任务不存在或已被他人领取，请刷新')
        prepare_header_extensions(api,cfg,picked)
        if cfg.production_layout=='left_al' and cfg.production_spreadsheet_id==cfg.source_spreadsheet_id and cfg.production_sheet in cfg.source_sheets:
            raise ValueError('制作表不能同时作为任务来源，插入单元格会改变来源行号')
        metadata=get_metadata(api,cfg.production_spreadsheet_id,cfg.production_sheet) if cfg.production_layout=='left_al' else None
        planned=[];reserve={};locations={}
        for task,num in allocate_numbers(all_tasks,ids):
            # duplicate-safe reserve production row across a single batch
            location_key='left' if cfg.production_layout=='left_al' else task.label
            if location_key not in locations:locations[location_key]=production_location(api,cfg,task)
            row,cols=locations[location_key]
            key=tuple(sorted(cols.items()))
            row=max(row,reserve.get(key,0)+1)
            reserve[key]=row
            name=make_filename(task,num,cfg.prefix,cfg.producer,date.today())
            src,dst=updates_for_task(cfg,task,num,name,row,cols)
            planned.append((task,num,name,src,dst))
        # Verify once more immediately before writing.
        notify('正在再次检查来源任务是否被占用…')
        latest={t.identity:t for t in (load_tasks(api,cfg,progress) if progress else load_tasks(api,cfg))}
        if any(t.identity not in latest or not latest[t.identity].available or
               (latest[t.identity].chinese,latest[t.identity].deadline,latest[t.identity].person)!=(t.chinese,t.deadline,t.person)
               for t,_,_,_,_ in planned):raise ValueError('任务在领取前已被占用或移动，请刷新')
        source=[u for _,_,_,su,_ in planned for u in su]
        target=[u for _,_,_,_,tu in planned for u in tu]
        if metadata:
            existing=read_grid(api,cfg.production_spreadsheet_id,cfg.production_sheet)
            production_header=header_index(existing)
            if production_header is None:raise ValueError('制作表表头已改变，请刷新后重试')
            production_width=len(left_header(existing[production_header]))
            names={name for _,_,name,_,_ in planned}
            if any(str(value).strip() in names for row in existing for value in row[:production_width]):
                raise ValueError('制作表已有本批自动命名，可能是上次回写中断；请先核对领取日志，禁止重复插入')
        # Warning: Sheets does not provide atomic operations across two spreadsheet IDs.
        payload={'source_id':cfg.source_spreadsheet_id,'production_id':cfg.production_spreadsheet_id,
                 'tasks':[t.__dict__ for t,_,_,_,_ in planned],'source_updates':source,'production_updates':target}
        production_requests=[]
        if metadata:
            first_row=min(int(re.search(r'(\d+)$',u['range'])[1]) for u in target)
            production_requests=[{'insertRange':{'range':{'sheetId':metadata['sheetId'],
                'startRowIndex':first_row-1,'endRowIndex':first_row-1+len(planned),
                'startColumnIndex':0,'endColumnIndex':production_width},'shiftDimension':'ROWS'}}]
            for update in target:
                cell=update['range'].rsplit('!',1)[1]
                match=re.fullmatch(r'([A-Z]+)(\d+)',cell)
                if not match:raise ValueError('制作表单元格地址无效')
                column=0
                for char in match[1]:column=column*26+ord(char)-ord('A')+1
                column-=1
                if column>=production_width:raise ValueError('制作表目标超出左侧字段组，已停止领取')
                production_requests.append({'updateCells':{'start':{'sheetId':metadata['sheetId'],
                    'rowIndex':int(match[2])-1,'columnIndex':column},
                    'rows':[{'values':[{'userEnteredValue':{'stringValue':str(update['values'][0][0])}}]}],
                    'fields':'userEnteredValue'}})
        payload['production_requests']=production_requests
        operation=record('claim','prepared',payload)
        try:
            notify(f'正在写入制作表：{len(planned)} 条任务…')
            if production_requests:
                # Insert and fill are one Sheets batch, so a validation failure cannot
                # leave an inserted blank block. Source is written only after this.
                api.spreadsheets().batchUpdate(spreadsheetId=cfg.production_spreadsheet_id,
                    body={'requests':production_requests}).execute()
                record('claim','production_written',payload,operation)
            batch_write(api,cfg.source_spreadsheet_id,source)
            notify('正在核验需求表回填…')
            if progress is not None:
                verify_updates(api,cfg.source_spreadsheet_id,source)
            for update in source:notify('已回填 '+update['range'])
            record('claim','source_written',payload,operation)
            if not production_requests:batch_write(api,cfg.production_spreadsheet_id,target)
            record('claim','complete',payload,operation)
        except Exception as e:
            payload['error']=str(e)
            record('claim','needs_review',payload,operation)
            raise ValueError(f'领取未完整完成，已保存核对日志 {operation}；请核对双表，不要重复领取') from e
        return [{'id':t.identity,'deadline':t.deadline,'number':n,'filename':f,'image':t.image,'folder':t.label,'date':date.today().strftime('%Y%m%d')} for t,n,f,_,_ in planned]

def verify_updates(api,doc,updates):
    response=api.spreadsheets().values().batchGet(spreadsheetId=doc,ranges=[u['range'] for u in updates],valueRenderOption='FORMATTED_VALUE').execute()
    actual=response.get('valueRanges',[])
    if len(actual)!=len(updates):raise ValueError('回填核验返回范围不完整')
    for expected,value in zip(updates,actual):
        if value.get('values',[])!=expected['values']:raise ValueError('回填核验失败：'+expected['range'])

def release_task(api,cfg,identity,expected_name,progress):
    """Release only the current user's unfinished task, preserving production history."""
    with LOCK:
        tasks=load_tasks(api,cfg)
        found=[t for t in tasks if t.identity==identity and t.filename==expected_name]
        if len(found)!=1:raise ValueError('任务已移动或命名改变，请刷新')
        t=found[0]
        if t.owner!=cfg.producer or t.output:raise ValueError('只能放弃自己未完成的任务')
        if not t.filename:raise ValueError('任务缺少自动命名，无法安全定位制作记录')
        grid=read_grid(api,cfg.production_spreadsheet_id,cfg.production_sheet)
        h=header_index(grid)
        if h is None:raise ValueError('制作表缺少表头')
        header=left_header(grid[h]) if cfg.production_layout=='left_al' else grid[h]
        starts=[c for c,v in enumerate(header) if key_for(v)=='deadline'];matches=[]
        for i,start in enumerate(starts):
            end=starts[i+1] if i+1<len(starts) else len(header)
            cols={key_for(header[c]):c for c in range(start,end) if key_for(header[c])}
            if not all(k in cols for k in ('filename','owner','progress','output')):continue
            for r in range(h+1,len(grid)):
                val=lambda k:str(grid[r][cols[k]]).strip() if cols[k]<len(grid[r]) else ''
                if val('filename')==t.filename:
                    if val('owner')!=cfg.producer or val('output'):raise ValueError('制作记录归属或完成状态已改变')
                    matches.append((r+1,cols))
        if len(matches)!=1:raise ValueError('制作表无法唯一定位任务，未放弃')
        row,cols=matches[0]
        source=[{'range':f'{quoted(t.sheet)}!{a1col(t.columns[k])}{t.row}','values':[[v]]} for k,v in {'owner':'','filename':'','number':'','progress':'可领取'}.items() if k in t.columns]
        # Archive the old name to distinguish a later re-claim on the same day.
        from uuid import uuid4
        archived=t.filename+'-已放弃-'+uuid4().hex[:8]
        target=[{'range':f'{quoted(cfg.production_sheet)}!{a1col(cols[k])}{row}','values':[[v]]} for k,v in {'progress':'已放弃','filename':archived}.items()]
        payload={'task':t.__dict__,'source_updates':source,'production_updates':target}
        op=record('release','prepared',payload)
        try:
            progress('正在将制作记录标记为已放弃…');batch_write(api,cfg.production_spreadsheet_id,target)
            record('release','production_written',payload,op)
            progress('正在释放来源任务…');batch_write(api,cfg.source_spreadsheet_id,source)
            fresh={x.identity:x for x in load_tasks(api,cfg)}.get(identity)
            if not fresh or fresh.owner or fresh.filename:raise ValueError('来源释放核验失败')
            record('release','complete',payload,op)
        except Exception as e:
            payload['error']=str(e)
            record('release','needs_review',payload,op)
            raise ValueError(f'放弃未完整完成，请核对日志 {op}，不要重复操作') from e
        return identity

def write_completed(api,cfg,task,url):
    if not url.startswith('https://'):raise ValueError('无效的 Google Drive 链接')
    current=[t for t in load_tasks(api,cfg) if t.source_id==task.source_id and t.sheet==task.sheet and t.start_col==task.start_col and t.filename==task.filename]
    if len(current)!=1 or current[0].owner!=cfg.producer or current[0].output:raise ValueError('来源任务已移动、归属改变或已完成，请核对后修复回填')
    task=current[0]
    if 'output' not in task.columns:raise ValueError('需求表缺少成品链接列')
    source=[{'range':f'{quoted(task.sheet)}!{a1col(task.columns["output"])}{task.row}','values':[[url]]}]
    if 'progress' in task.columns:source.append({'range':f'{quoted(task.sheet)}!{a1col(task.columns["progress"])}{task.row}','values':[['已完成']]})
    # Locate production by exact filename, not by stale row.
    grid=read_grid(api,cfg.production_spreadsheet_id,cfg.production_sheet)
    names=[]
    header_row=header_index(grid)
    if header_row is None:raise ValueError('制作表未找到任务表头，未执行回填')
    header=grid[header_row]
    if cfg.production_layout=='left_al':header=left_header(header)
    starts=[c for c,h in enumerate(header) if key_for(h)=='deadline']
    for i,start in enumerate(starts):
        end=starts[i+1] if i+1<len(starts) else len(header)
        cols={key_for(header[c]):c for c in range(start,end) if key_for(header[c])}
        if 'filename' not in cols or 'output' not in cols:continue
        for r in range(header_row+1,len(grid)):
            if cols['filename']<len(grid[r]) and str(grid[r][cols['filename']]).strip()==task.filename:
                names.append((r+1,cols))
    if len(names)!=1:raise ValueError('制作表中无法唯一匹配该自动命名；暂不回填，避免写错')
    row,cols=names[0]
    dest=[{'range':f'{quoted(cfg.production_sheet)}!{a1col(cols["output"])}{row}','values':[[url]]}]
    if 'progress' in cols:dest.append({'range':f'{quoted(cfg.production_sheet)}!{a1col(cols["progress"])}{row}','values':[['已完成']]})
    batch_write(api,cfg.production_spreadsheet_id,dest)
    batch_write(api,cfg.source_spreadsheet_id,source)
