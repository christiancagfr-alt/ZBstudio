from pydantic import BaseModel,Field
from pathlib import Path
import json
from platformdirs import user_data_dir
from typing import Literal
class SourceSheet(BaseModel):
    sheet_id:int|None=None
    name:str
    alias:str
    enabled:bool=False
    task_type:Literal['video','image']='video'
class SourceDocument(BaseModel):
    spreadsheet_id:str
    sheets:list[SourceSheet]=Field(default_factory=list)

def source_documents(cfg):
    if cfg.source_documents:return cfg.source_documents
    if not cfg.source_spreadsheet_id:return []
    rows=cfg.source_catalog or [SourceSheet(name=n,alias=cfg.requester_names.get(n,n),enabled=True) for n in cfg.source_sheets]
    return [SourceDocument(spreadsheet_id=cfg.source_spreadsheet_id,sheets=rows)]

def default_register_columns():
    return {'date':'A','link':'B','group':'C','type':'D','difficulty':'E','material':'F','software':'G','producer':'H','duration':'AC','duration_class':'AB'}
class Settings(BaseModel):
    voice_enabled:bool=True
    dark_mode:bool=False
    producer:str=''
    prefix:str='ZB'
    source_spreadsheet_id:str=''
    source_sheets:list[str]=Field(default_factory=list)
    source_documents:list[SourceDocument]=Field(default_factory=list)
    production_spreadsheet_id:str=''
    production_sheet:str=''
    production_layout:Literal['grouped','left_al']='grouped'
    header_aliases:dict[str,list[str]]=Field(default_factory=dict)
    sequence_start:int=Field(default=1,ge=1,le=999999)
    sequence_mode:Literal['combined','per_source']='combined'
    sequence_override:int|None=Field(default=None,ge=1,le=999999)
    collapsed_source_ids:list[str]=Field(default_factory=list)
    primary_source_collapsed:bool=False
    download_path:str=str(Path.home()/'ZB Studio')
    drive_parent_folder_id:str=''
    register_spreadsheet_id:str=''
    register_sheet:str=''
    register_columns:dict[str,str]=Field(default_factory=default_register_columns)
    register_defaults:dict[str,str]=Field(default_factory=dict)
    register_duration_labels:dict[str,str]=Field(default_factory=lambda:{'short':'一分钟以内','long':'一分钟以上'})
    register_category_options:dict[str,list[str]]=Field(default_factory=dict)
    register_date_mode:Literal['today','folder','manual']='today'
    register_date:str=''
    start_date:str=''
    end_date:str=''
    requester_names:dict[str,str]=Field(default_factory=dict)
    source_catalog:list[SourceSheet]=Field(default_factory=list)

def path():
    p=Path(user_data_dir('ZB Studio'))
    p.mkdir(parents=True,exist_ok=True)
    return p/'settings.json'
def load_settings():
    p=path()
    return Settings.model_validate_json(p.read_text('utf-8')) if p.exists() else Settings()
def save_settings(cfg:Settings):
    path().write_text(cfg.model_dump_json(indent=2),'utf-8')
