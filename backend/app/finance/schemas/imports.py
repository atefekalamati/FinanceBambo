from typing import Literal
from uuid import UUID
from .base import ApiModel
class ImportIssue(ApiModel):
 row:int;field:str;reason:str
class ImportPreviewResponse(ApiModel):
 preview_id:UUID;kind:Literal["estimate","prices"];row_count:int;errors:list[ImportIssue];can_commit:bool
class ImportCommit(ApiModel):
 preview_id:UUID
class ImportCommitResponse(ApiModel):
 preview_id:UUID;status:Literal["committed"];committed_count:int
