"""Historical event counts are local journal events, not inferred snapshots."""
from datetime import date,datetime,timedelta
from .domain import date_key
from decimal import Decimal, InvalidOperation
import re

def parse_views(value):
    """Recognize common displayed counts; leave unknown formats uncounted."""
    text=str(value or '').strip().replace(',','').replace('，','')
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(万|亿|千|[kKmM])?',text)
    if not match:return None
    factor={'万':10000,'亿':100000000,'千':1000,'k':1000,'m':1000000}.get((match[2] or '').lower(),1)
    try:return int(Decimal(match[1])*factor)
    except (InvalidOperation,ValueError):return None

def report(tasks,operations,start,end):
    def task_day(value):
        key=date_key(value)
        if len(key)==8 and key.isdigit():return key
        import re
        m=re.fullmatch(r'(\d{1,2})[-/.](\d{1,2})',str(value).strip())
        return f'{start.year:04d}{int(m[1]):02d}{int(m[2]):02d}' if m else ''
    selected=[t for t in tasks if start.strftime('%Y%m%d')<=task_day(t.deadline)<=end.strftime('%Y%m%d')]
    groups={};views={}
    for t in selected:
        row=groups.setdefault((t.source_id,t.sheet,t.label),[0,0,0,0,0]);row[0]+=1;row[1]+=int(not t.owner and not t.output);row[2]+=int(bool(t.owner));row[3]+=int(bool(t.output));row[4]+=int(bool(t.output) and t.viral)
        key=(t.source_id,t.sheet,t.label);total,known,unknown=views.get(key,(0,0,0))
        if t.views:
            number=parse_views(t.views)
            if number is None:unknown+=1
            else:total+=number;known+=1
        views[key]=(total,known,unknown)
    days={};d=start
    while d<=end:days[d.isoformat()]={'claim':0,'release':0,'upload':0};d+=timedelta(days=1)
    allowed={(t.source_id,t.sheet) for t in tasks}
    abandoned={}
    for op in operations:
        if op['state']!='complete' or op['kind'] not in ('claim','release','upload'):continue
        day=datetime.fromisoformat(op['updated']).astimezone().date().isoformat()
        if day not in days:continue
        p=op['payload'];items=p.get('tasks') or ([p['task']] if p.get('task') else [])
        for t in items:
            if (t.get('source_id'),t.get('sheet')) not in allowed:continue
            days[day][op['kind']]+=1
            if op['kind']=='release':
                label=f"{t.get('requester','')} {t.get('person','')}".strip();key=(t.get('source_id',''),t.get('sheet',''),label);abandoned[key]=abandoned.get(key,0)+1
    def views_label(key):
        total,known,unknown=views.get(key,(0,0,0))
        return (f'{total:,}' if known else '—')+('（部分未识别）' if unknown else '')
    return {'rows':[[sheet,label,*groups.get((source,sheet,label),[0,0,0,0,0]),views_label((source,sheet,label)),abandoned.get((source,sheet,label),0)] for source,sheet,label in sorted(set(groups)|set(abandoned))], 'days':days}
