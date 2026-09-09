from decimal import Decimal
from datetime import date,datetime
from typing import Literal
from uuid import UUID
from pydantic import Field,field_serializer
from .base import ApiModel
class ImportIssue(ApiModel):
 row:int;field:str;reason:str
class ImportPreviewRow(ApiModel):
 row_number:int
 status:Literal["valid","invalid"]
 errors:list[ImportIssue]
 resource_code:str|None=None
 resource_id:UUID|None=None
 resource_title:str|None=None
 base_unit:str|None=None
 activity_external_id:str|None=None
 activity_title:str|None=None
 assignment_external_id:str|None=None
 original_quantity:Decimal|None=None
 source:str|None=None
 unit_price:Decimal|None=None
 currency:str|None=None
 normalized_unit_price_irr:Decimal|None=None
 effective_from:date|None=None
 scope:str|None=None
 @field_serializer("original_quantity","unit_price","normalized_unit_price_irr")
 def serialize_decimal(self,value):return None if value is None else format(value,"f")
class ImportPreviewResponse(ApiModel):
 preview_id:UUID;kind:Literal["estimate","prices"];row_count:int;valid_count:int;invalid_count:int;rows:list[ImportPreviewRow];errors:list[ImportIssue];can_commit:bool
 # Set when these exact bytes were already committed for this project and kind. canCommit
 # carries the decision; these say why, so the UI can name the earlier import.
 duplicate_file:bool=False
 duplicate_of_import_id:UUID|None=None
 duplicate_committed_at:datetime|None=None
class ImportFromLink(ApiModel):
 """A Google Sheets link, previewed as though the workbook behind it were uploaded."""
 source_url:str=Field(min_length=1,max_length=2048)
class ImportCommit(ApiModel):
 preview_id:UUID
class ImportCommitResponse(ApiModel):
 preview_id:UUID;status:Literal["committed"];committed_count:int
