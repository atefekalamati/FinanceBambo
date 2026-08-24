from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,field_serializer,field_validator
from .base import ApiModel
from .numeric import strict_decimal,strict_optional_decimal
class ProgressSnapshotResponse(ApiModel):
 organization_id:UUID;project_id:str;progress_snapshot_id:UUID;source_file_version_id:UUID;source_file_name_safe:str;imported_at:datetime;imported_by:UUID;status:Literal["ready","superseded"];reporting_date:date
 # Position in this project's own snapshot history, derived rather than stored: the table
 # is append-only, so row order is the history and version 1 stays version 1. Optional
 # because the feed's header comes from the host provider, which cannot know it.
 version:int|None=None
 is_latest:bool|None=None
 # Where the snapshot came from. None means it was not recorded, which is the honest
 # answer for rows imported before the column existed -- a filename extension is not
 # evidence of a tool.
 source_type:Literal["microsoft_project","primavera","manual","other"]|None=None
class ProgressFeedResponse(ApiModel):
 snapshot:ProgressSnapshotResponse;assignments:list[dict]
class ProgressOverrideCreate(ApiModel):
 progress_snapshot_id:UUID;override_value:Decimal=Field(max_digits=18,decimal_places=4);reason:str=Field(min_length=1)
 @field_validator("override_value",mode="before")
 @classmethod
 def strict_progress_numbers(cls,v):return strict_decimal(v)
 @field_validator("reason")
 @classmethod
 def validate_reason(cls,v):
  if not v.strip():raise ValueError("reason must not be blank")
  return v.strip()
class ProgressOverrideResponse(ProgressOverrideCreate):
 id:UUID;estimate_line_id:UUID;computed_value:Decimal;created_by:UUID;created_at:datetime;source:Literal["manual_override"]="manual_override"
 @field_serializer("computed_value","override_value")
 def decimal_string(self,v):return format(v,"f")
 @classmethod
 def from_domain(cls,v):return cls(id=v.id,estimateLineId=v.estimate_line_id,progressSnapshotId=v.progress_snapshot_id,computedValue=v.computed_value,overrideValue=v.override_value,reason=v.reason,createdBy=v.created_by,createdAt=v.created_at)
 @classmethod
 def from_row(cls,row):return cls(id=row["id"],estimateLineId=row["estimate_line_id"],progressSnapshotId=row["progress_snapshot_id"],computedValue=row["computed_value"],overrideValue=row["override_value"],reason=row["reason"],createdBy=row["created_by"],createdAt=row["created_at"])
