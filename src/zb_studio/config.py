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
class Settings(BaseModel):
    voice_enabled:bool=True
    producer:str='佳佳'
    prefix:str='ZB'
    source_spreadsheet_id:str=''
    source_sheets:list[str]=Field(default_factory=list)
    production_spreadsheet_id:str=''
    production_sheet:str=''
    production_layout:Literal['grouped','left_al']='grouped'
    download_path:str=str(Path.home()/'ZB Studio')
    drive_parent_folder_id:str=''
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
