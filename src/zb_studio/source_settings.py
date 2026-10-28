"""Source discovery and conservative editable alias suggestions."""
import re
import unicodedata

def suggest_alias(title):
    text=title.strip()
    while text and unicodedata.category(text[0])[0] not in ('L','N'):
        text=text[1:]
    first=re.split(r'[\s\-—–_·•|/｜]+',text,maxsplit=1)[0]
    first=re.split(r'(?:需求表|工作表|制作表)',first,maxsplit=1)[0]
    return first.strip() or title.strip()

def merge_sources(tabs,previous):
    by_id={r['sheet_id']:r for r in previous if r.get('sheet_id') is not None}
    by_name={r['name']:r for r in previous}
    result=[]
    for tab in tabs:
        old=by_id.get(tab['sheetId'],by_name.get(tab['title'],{}))
        result.append({'sheet_id':tab['sheetId'],'name':tab['title'],
                       'alias':old.get('alias') or suggest_alias(tab['title']),
                       'enabled':old.get('enabled',False)})
    return result
