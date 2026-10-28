"""Historical event counts are local journal events, not inferred snapshots."""
from datetime import date,datetime,timedelta
from .domain import date_key

def report(tasks,operations,start,end):
    def task_day(value):
        key=date_key(value)
        if len(key)==8 and key.isdigit():return key
        import re
        m=re.fullmatch(r'(\d{1,2})[-/.](\d{1,2})',str(value).strip())
        return f'{start.year:04d}{int(m[1]):02d}{int(m[2]):02d}' if m else ''
    selected=[t for t in tasks if start.strftime('%Y%m%d')<=task_day(t.deadline)<=end.strftime('%Y%m%d')]
    groups={}
    for t in selected:
        row=groups.setdefault(t.label,[0,0,0,0]);row[0]+=1;row[1]+=int(not t.owner and not t.output);row[2]+=int(bool(t.owner));row[3]+=int(bool(t.output))
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
                label=f"{t.get('requester','')} {t.get('person','')}".strip();abandoned[label]=abandoned.get(label,0)+1
    return {'rows':[[label,*groups.get(label,[0,0,0,0]),abandoned.get(label,0)] for label in sorted(set(groups)|set(abandoned))], 'days':days}
