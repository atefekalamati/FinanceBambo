from datetime import date,datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field,field_serializer,field_validator
from .base import ApiModel
from .numeric import strict_decimal,strict_optional_decimal
class ProgressSnapshotResponse(ApiModel):
 organization_id:UUID;project_id:str;progress_snapshot_id:UUID;source_file_name_safe:str;imported_at:datetime
 # Optional since the Finance-owned file source: a snapshot read from a schedule file
 # by a timer has no importer, and inventing a user id to fill a required field would
 # put a person's name on work nobody did. A Core-ingested reference always has one.
 imported_by:UUID|None=None
 # What the host calls this actor, filled at the API boundary and never stored.
 # None when the host has no directory or does not know the id; the reader then sees
 # the id, exactly as before. See `app.finance.domain.actors`.
 imported_by_name:str|None=None
 status:Literal["ready","superseded"];reporting_date:date
 # Optional since revision 0006. A reference ingested from Core has no Finance-side file
 # identifier to record, and inventing a UUID would look like a Host reference while being
 # nothing of the kind. Rows that predate 0006 still carry theirs.
 source_file_version_id:UUID|None=None
 # The Core identity of this snapshot: msp_snapshots.id and msp_file_versions.id, which are
 # bigint. These are CORE_REFERENCE values -- Finance stores them, Core owns them. None on
 # a reference that was never linked to a Core snapshot, which is every row imported before
 # this integration existed.
 host_snapshot_id:int|None=None
 host_file_version_id:int|None=None
 # Position in this project's own snapshot history, derived rather than stored: the table
 # is append-only, so row order is the history and version 1 stays version 1. Optional
 # because the feed's header comes from the host provider, which cannot know it.
 version:int|None=None
 is_latest:bool|None=None
 # Whether this snapshot came from the project's ACTIVE source version -- the schedule
 # its estimate lines are mapped to and priced from. Distinct from `is_latest`, which is
 # about arrival order: a snapshot of an unrelated file can be the newest row and still not
 # be this project's schedule.
 #
 # Three values, not two. False is a CLAIM -- "this is not the project's schedule" -- and
 # `mark_active_source` makes that claim explicitly for every row it returns, including
 # when the project has no active version at all. None means the answer was not computed
 # here, which is the feed endpoint's case: its header is built from the provider's
 # metadata, which knows nothing about version ranking, and the two fields above are None
 # for exactly that reason. Defaulting to False made the feed assert that the active
 # schedule was NOT the active schedule -- seen on `test_progress.mpp`, where the listing
 # said true and the feed for that same snapshot said false in the same breath.
 is_active_source:bool|None=None
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
 # What the host calls this actor, filled at the API boundary and never stored.
 # None when the host has no directory or does not know the id; the reader then sees
 # the id, exactly as before. See `app.finance.domain.actors`.
 created_by_name:str|None=None
 @field_serializer("computed_value","override_value")
 def decimal_string(self,v):return format(v,"f")
 @classmethod
 def from_domain(cls,v):return cls(id=v.id,estimateLineId=v.estimate_line_id,progressSnapshotId=v.progress_snapshot_id,computedValue=v.computed_value,overrideValue=v.override_value,reason=v.reason,createdBy=v.created_by,createdAt=v.created_at)
 @classmethod
 def from_row(cls,row):return cls(id=row["id"],estimateLineId=row["estimate_line_id"],progressSnapshotId=row["progress_snapshot_id"],computedValue=row["computed_value"],overrideValue=row["override_value"],reason=row["reason"],createdBy=row["created_by"],createdAt=row["created_at"])
