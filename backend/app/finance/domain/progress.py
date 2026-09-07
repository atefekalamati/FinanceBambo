"""How an assignment's reported progress becomes an executed quantity.

The branches below are a precedence, not a menu: the first source that can answer wins,
and each later one is a fallback carrying a lower `quality`.

WHY `measurement_type` EXISTS
`source_method` names the field a number came from. It does not say whether that number is
a measurement of physical work in the resource's own unit, and the difference matters
because `domain/reports.py` turns the result straight into money:

    executed_value = money(executed * current)   # current is IRR per kg, per m3, per hour

`actualQuantity` is stated in the resource's unit, so that product is money.

`actualWork` is effort. The schedule contract (`domain/schedule.py`) keeps work and
quantity in separate fields precisely because they are different things, and it states no
unit for work at all -- so `actualWork * IRR-per-kg` is money only if the resource happens
to be priced in whatever unit the effort was counted in. Nothing available here can
establish that: the assignment's `unit` is the resource's unit, not the work's, and
`PRODUCTION_MSP_AUDIT_FA.md` section 6 is still an open question against real data.

So the value is passed through unchanged and labelled: `measurement_type` says what kind
of number it is, `quality` drops below every fallback that at least produces a value in
the right unit, and PROGRESS_WORK_NOT_QUANTITY says so out loud.

WHY IT IS PASSED THROUGH AT ALL
Refusing it would push the line into "no progress" and report 0% executed, which is a
different wrong answer rather than an absent one. Which of the two is correct is a product
decision this module does not own, so it keeps the existing number and stops claiming the
number is something it is not.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from .resources import FinanceRecordNotFound

#: What kind of number `effective_quantity` is, independent of which field supplied it.
#:   measured_quantity   -- reported in the resource's own unit
#:   work_effort         -- reported as effort; its unit is not stated by the source
#:   derived_from_percent-- planned quantity scaled by a percentage, so in the right unit
#:   stated_quantity     -- a person put the number there, with an audit record
MEASUREMENT_TYPES=("measured_quantity","work_effort","derived_from_percent","stated_quantity")

#: Effort used as a quantity sits below `task_progress_fallback` (0.6) on purpose: a
#: fallback derived from a percentage is at least denominated in the resource's unit, and
#: this is not. The number is only ever reported, never multiplied into a metric.
WORK_AS_QUANTITY_QUALITY=Decimal("0.5")

#: How much a reader should trust the quantity, coarser than `measurement_type` and meant
#: for a reader who only wants to know whether to trust it:
#:   measured -- the assignment stated this quantity, or a person did with an audit record
#:   fallback -- it stands in for a quantity nobody stated: derived from a percentage, or
#:               taken from effort in a unit the source never declared
#: The finer reason stays in `measurement_type`, and the two are derived from one table so
#: they cannot drift apart. Report-level statuses -- unavailable, and the two unmapped ones
#: -- are about an estimate line rather than an assignment, so they live in
#: `domain/reports.py` and never appear here.
PROGRESS_MEASURED="measured"
PROGRESS_FALLBACK="fallback"
MEASUREMENT_STATUS={"measured_quantity":PROGRESS_MEASURED,"stated_quantity":PROGRESS_MEASURED,
 "derived_from_percent":PROGRESS_FALLBACK,"work_effort":PROGRESS_FALLBACK}

#: Resource kinds whose own unit IS time, so reported hours are a quantity in that unit.
TIME_BASED_RESOURCE_TYPES = ("labor", "equipment")


def _work_is_a_quantity(a):
    """Whether reported work may stand in as this resource's executed quantity.

    Only for a resource the source EXPLICITLY calls labour or equipment. For a material,
    hours are not kilograms and never were: multiplying 48 crane-hours by the price of a
    kilogram of rebar produces a number that looks like money and means nothing. An
    unclassified resource is not treated as time-based either -- "we do not know" is not
    the same claim as "it is measured in hours", and guessing here is exactly how the
    wrong unit reaches a report.
    """
    return a.get("resourceType") in TIME_BASED_RESOURCE_TYPES


def resolve_progress_quantity(a):
 warnings=[]
 o=a.get("manualOverride")
 if o is not None:
  required=("previousCalculatedValue","newValue","reason","userId","occurredAt","progressSnapshotId")
  if o.get("source")!="manual_override" or any(not o.get(k) for k in required):raise ValueError("manual override requires complete audit metadata")
  computed=Decimal(o["previousCalculatedValue"]);effective=Decimal(o["newValue"])
  return {"computed_quantity":computed,"effective_quantity":effective,"source_method":"manual_override","measurement_type":"stated_quantity","progress_status":MEASUREMENT_STATUS["stated_quantity"],"quality":Decimal("1"),"warnings":warnings}
 if a.get("actualQuantity") is not None:
  value=Decimal(a["actualQuantity"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","measurement_type":"measured_quantity","progress_status":MEASUREMENT_STATUS["measured_quantity"],"quality":Decimal("1"),"warnings":warnings}
 if a.get("actualWork") is not None and _work_is_a_quantity(a):
  # Hours, for a resource whose OWN unit is time. Labour and equipment are billed by the
  # hour, so "48 hours executed" is a quantity in that resource's unit and the arithmetic
  # downstream is sound. The quality stays below a measured quantity because the source
  # still never restated it as one.
  value=Decimal(a["actualWork"])
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_actual","measurement_type":"work_effort","progress_status":MEASUREMENT_STATUS["work_effort"],"quality":WORK_AS_QUANTITY_QUALITY,
   "warnings":[{"code":"PROGRESS_WORK_NOT_QUANTITY","message":"Executed quantity was taken from reported work effort on a time-based resource; the source stated no measured quantity."}]}
 planned=a.get("plannedQuantity")
 if planned is not None and a.get("assignmentWorkCompletePercent") is not None:
  value=Decimal(planned)*Decimal(a["assignmentWorkCompletePercent"])/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"assignment_work_percent","measurement_type":"derived_from_percent","progress_status":MEASUREMENT_STATUS["derived_from_percent"],"quality":Decimal("0.8"),"warnings":warnings}
 percent=(a.get("task") or {}).get("taskProgressPercent")
 if planned is not None and percent is not None:
  value=Decimal(planned)*Decimal(percent)/100
  return {"computed_quantity":value,"effective_quantity":value,"source_method":"task_progress_fallback","measurement_type":"derived_from_percent","progress_status":MEASUREMENT_STATUS["derived_from_percent"],"quality":Decimal("0.6"),"warnings":[{"code":"TASK_PROGRESS_FALLBACK","message":"Executed quantity was resolved from task progress because assignment-level progress was unavailable."}]}
 raise ValueError("manual override is required when no calculation source exists")

def consumed_quantity(a):
 """Effective quantity and the field it came from.

 Kept as a two-tuple: `services/progress.py` needs exactly this to record an override's
 baseline. A caller that needs to know what kind of number it received reads
 `resolve_progress_quantity` directly, as `domain/reports.py` does.
 """
 resolved=resolve_progress_quantity(a)
 return resolved["effective_quantity"],resolved["source_method"]

def snapshot_metadata(feed,organization_id,project_id,snapshot_id):
 """The feed's header, proven to describe the snapshot that was actually asked for.

 `ProgressSnapshotProvider` is implemented by the host and its port constrains nothing
 about the reply, so Finance has to treat every shape as possible: no reply at all, a
 reply with no header, a header that is empty, or a header describing another tenant's
 snapshot. Reading straight through any of those raised KeyError or TypeError and left
 the caller with a 500, which says "this service is broken" about a request that was
 simply for something the provider does not have.

 All of them end as FinanceRecordNotFound -- a 404 in the existing envelope. Not found
 rather than a validation error on purpose: the requester named a snapshot id, and
 answering "malformed" for a header belonging to another tenant would confirm that the
 id exists somewhere. A caller who may not see it and a caller asking for something
 absent get the same answer.
 """
 metadata=feed.get("snapshot") if isinstance(feed,Mapping) else None
 if not isinstance(metadata,Mapping):raise FinanceRecordNotFound("progress snapshot not found")
 if (str(metadata.get("organizationId"))!=str(organization_id)
   or metadata.get("projectId")!=project_id
   or str(metadata.get("progressSnapshotId"))!=str(snapshot_id)):
  raise FinanceRecordNotFound("progress snapshot not found")
 return metadata

def snapshot_assignments(feed):
 """The feed's assignment rows, whatever the provider put in their place.

 A snapshot with no assignments is a legitimate answer -- a schedule can be imported
 before anyone reports against it -- so an absent or null list is an empty one here, not
 an error. Only the header decides whether the snapshot exists; see `snapshot_metadata`.
 A string is rejected along with everything else that is not a sequence of rows, because
 iterating one would silently produce a feed of characters.
 """
 rows=feed.get("assignments") if isinstance(feed,Mapping) else None
 if isinstance(rows,Sequence) and not isinstance(rows,(str,bytes)):return list(rows)
 return []


def assignment_keys(row):
 """The identifier pair a progress-feed row is found by."""
 return row.get("assignmentExternalId"),(row.get("task") or {}).get("activityCode")

def line_keys(row):
 """The same pair as an estimate line -- or an override of one -- states it."""
 return row.get("assignment_external_id"),row.get("activity_external_id")

class ProgressPairing:
 """Which progress-feed row belongs to which estimate line.

 The rule: they are paired when their assignment external ids match, and failing that
 when their activity external ids match. The assignment id wins because it is the more
 specific claim -- an activity can carry many assignments, so an activity match says only
 that the two are about the same piece of schedule, not about the same resource.

 WHY THIS IS ONE OBJECT USED TWICE
 The rule was written three times: once in `domain/reports.py` to find a line's
 assignment, once in `services/progress.py` for the same thing, and once in
 `apply_progress_overrides` below to go the other way -- from a feed row to the override
 stored against a line. The last is the same pairing with the roles swapped, which is why
 `keys` is a parameter: it says which of the two vocabularies the indexed rows speak, and
 the direction follows from what the caller then matches against.

 THE TWO THAT DISAGREED
 They were not merely duplicated, they gave different answers. `domain/reports.py` built
 two indexes and consulted the assignment one first, so the assignment id always won.
 `services/progress.py` scanned the feed and took the first row satisfying either test, so
 row order won: a line naming ASG-2 on activity ACT-1 paired with ASG-9 whenever ASG-9
 merely shared ACT-1 and came first. An override's baseline could therefore be computed
 from a different assignment than the one the report had used for that same line. This
 class keeps the report's precedence, which is the one the code was reaching for.

 Ties within one index are resolved as they always were: the last row wins, because both
 previous versions built plain dicts.
 """

 __slots__=("_by_assignment","_by_activity","_activity_of","_corroborate")

 def __init__(self,rows,keys,corroborate=False):
  """`corroborate` demands that a match agree on BOTH identifiers, when both are stated.

  Off by default, which is the rule every existing caller relies on: the assignment id is
  the more specific claim and wins on its own. It is turned on for a feed whose rows come
  from a Finance source version the estimate lines were never recorded against -- see
  `calculate_live_report`. There, an assignment id is a bare integer from someone else's
  schedule, and bare integers collide: measured on the real data, five estimate lines
  matched a bridge assignment by id alone and twenty-two more matched by WBS alone, while
  requiring BOTH to agree left zero. Those twenty-seven were pairing "rebar for the piers"
  with "wall plastering" on the strength of a shared number.
  """
  self._by_assignment={};self._by_activity={};self._activity_of={};self._corroborate=corroborate
  for row in rows:
   assignment_external_id,activity_external_id=keys(row)
   if assignment_external_id:
    self._by_assignment[assignment_external_id]=row
    self._activity_of[assignment_external_id]=activity_external_id
   if activity_external_id:self._by_activity[activity_external_id]=row

 def match(self,assignment_external_id,activity_external_id):
  """The paired row, or None.

  No guard against a blank or absent identifier here: `__init__` refuses to index one, so
  looking one up finds nothing. Guarding in both places would leave neither able to fail
  on its own, and this is also exactly what `domain/reports.py` did before -- a plain
  lookup of whatever the line claimed.
  """
  paired=self._by_assignment.get(assignment_external_id)
  if paired is not None and not self._contradicted(assignment_external_id,activity_external_id):
   return paired
  if self._corroborate:
   # A lone activity match is the weaker claim of the two, and in corroboration mode a
   # claim that could not survive the stronger test is not promoted to the answer.
   return None
  return self._by_activity.get(activity_external_id)

 def _contradicted(self,assignment_external_id,activity_external_id):
  """Whether the activity codes disagree about a pair the assignment ids matched.

  Only consulted in corroboration mode, and only when BOTH sides state an activity: with
  nothing to contradict, the assignment id stands on its own exactly as it always has.
  """
  if not self._corroborate or not activity_external_id:return False
  known=self._activity_of.get(assignment_external_id)
  if not known:return False
  return str(known).strip()!=str(activity_external_id).strip()


#: Keys a host feed header uses for the Core identifiers. Named here so the adapter, the
#: repository and the tests cannot disagree about the spelling.
HOST_SNAPSHOT_KEY = "hostSnapshotId"
HOST_FILE_VERSION_KEY = "hostFileVersionId"

def finance_version_id(metadata):
    """The Finance source-version UUID this header names, or None.

    A header describes one of Finance's OWN persisted source versions when it names no
    Core snapshot and carries a `sourceFileVersionId` equal to its `progressSnapshotId`:
    the version is its own identity. Deliberately not keyed on `sourceType` -- that field
    names the KIND of file (a Project file either way) and its vocabulary is closed by the
    API schema, so overloading it would have meant either a schema change or a lie.
    """
    if metadata.get(HOST_SNAPSHOT_KEY) is not None:
        return None
    try:
        version = UUID(str(metadata.get("sourceFileVersionId")))
    except (TypeError, ValueError, AttributeError):
        return None
    try:
        if UUID(str(metadata.get("progressSnapshotId"))) != version:
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    return version


class HostReferenceInvalid(ValueError):
    """The host named a Core snapshot in a form Finance cannot record."""


def _host_identifier(value, label):
    """A Core bigint identifier, or None when the host did not supply one.

    Accepts the integer a host would naturally send and the string a JSON boundary tends to
    produce, and refuses everything else. A bool is refused explicitly because it is an int
    subclass and True would otherwise become snapshot 1.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise HostReferenceInvalid("%s must be a Core identifier, not a boolean" % label)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip():
        try:
            number = int(value.strip())
        except ValueError:
            raise HostReferenceInvalid("%s is not a Core identifier: %r" % (label, value)) from None
    else:
        raise HostReferenceInvalid("%s is not a Core identifier: %r" % (label, value))
    if number <= 0:
        # Core sequences start at 1, so zero or negative is a mistake, not a value.
        raise HostReferenceInvalid("%s must be positive, got %d" % (label, number))
    return number


def host_reference(metadata):
    """The Core snapshot and file-version identifiers a feed header carries.

    Returns `(host_snapshot_id, host_file_version_id)`, either of which may be None: a host
    that does not publish Core identifiers is not an error, it simply cannot be pinned to.
    Absent is absent -- never guessed, never zero.
    """
    if not isinstance(metadata, Mapping):
        return None, None
    return (_host_identifier(metadata.get(HOST_SNAPSHOT_KEY), HOST_SNAPSHOT_KEY),
            _host_identifier(metadata.get(HOST_FILE_VERSION_KEY), HOST_FILE_VERSION_KEY))


@dataclass(frozen=True)
class ProgressReference:
    """One immutable Finance-side reference to a Core progress snapshot.

    Finance owns `id` and `progress_snapshot_id`: the first is the row, the second is the
    opaque identifier that appears in URLs and in issued report payloads. Neither is a Core
    value. `host_snapshot_id` and `host_file_version_id` are the Core identity, and they are
    what makes the reference reusable -- the same Core snapshot must never produce a second
    Finance reference.

    `source_file_version_id` stays None for a reference ingested from Core. There is no
    Finance-side file identifier to record, and inventing a UUID would look like a Host
    reference while being nothing of the kind.
    """

    id: UUID
    organization_id: UUID
    project_id: str
    progress_snapshot_id: UUID
    host_snapshot_id: int
    host_file_version_id: int | None
    source_file_name_safe: str
    reporting_date: object
    snapshot_status: str
    imported_by: UUID | None
    imported_at: datetime
    source_type: str | None = None
    source_file_version_id: UUID | None = None

def reference_reporting_date(value, fallback=None):
    """The reporting date a header claims, as a date.

    A host crossing a JSON boundary sends "2026-08-02", not a date object. Storing the
    string unparsed put a str into a column the report then compares against a date, which
    raised TypeError and surfaced as a 500 -- a host sending a perfectly valid date could
    break the report. Parsed here, once, for every caller.

    Returns None when the value is neither a date nor an ISO date string and no fallback is
    given. A reference whose reporting date is unknown cannot be selected by the date-based
    query that finds it, so it is better not to record one than to record one that can
    never be found.
    """
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return fallback
    return fallback


def reference_from_header(metadata, scope, new_id, now, fallback_reporting_date=None):
    """Build the Finance reference a host header describes, or None.

    One conversion for both callers -- the live report pinning the current snapshot, and the
    progress service recording one. Two copies of this drifted apart once already in this
    codebase's history, on the very similar assignment-matching rule.

    None is returned, rather than an exception raised, for every reason a header may be
    unusable: wrong tenant, no Core identifier, no usable reporting date. Each means "there
    is nothing here to pin to", which is a legitimate state the caller reports honestly.
    """
    if not isinstance(metadata, Mapping):
        return None
    if (str(metadata.get("organizationId")) != str(scope.organization_id)
            or metadata.get("projectId") != scope.project_id):
        return None
    host_snapshot_id, host_file_version_id = host_reference(metadata)
    version_id = None
    if host_snapshot_id is None:
        # Without a Core identifier there is nothing to be idempotent about -- unless the
        # header is one of Finance's own source versions, whose identity is the version
        # UUID it carries. Any other header naming no identifier is nothing to pin to: a
        # reference that cannot name what it refers to is worse than no reference at all.
        version_id = finance_version_id(metadata)
        if version_id is None:
            return None
    reporting_date = reference_reporting_date(metadata.get("reportingDate"),
                                              fallback_reporting_date)
    if reporting_date is None:
        return None
    # progress_snapshot_refs.imported_by is NOT NULL. Through the router an actor is always
    # present -- AuthContext.user_id is a required UUID and the scope is built from it -- so
    # this only fires for a caller outside that path. Refusing here turns what would be a
    # NOT NULL violation at the database boundary into the same honest "nothing to pin to"
    # answer every other unusable header gets. A user id is never invented to fill it.
    imported_by = metadata.get("importedBy") or getattr(scope, "actor_user_id", None)
    if imported_by is None:
        return None
    return ProgressReference(
        id=new_id(), organization_id=scope.organization_id, project_id=scope.project_id,
        # A Core snapshot gets a Finance-minted opaque id; a Finance source version IS its
        # own id, and the provider answers to exactly that value.
        progress_snapshot_id=version_id or new_id(),
        host_snapshot_id=host_snapshot_id,
        host_file_version_id=host_file_version_id,
        source_file_version_id=version_id,
        source_file_name_safe=metadata.get("sourceFileNameSafe") or "",
        reporting_date=reporting_date,
        snapshot_status=metadata.get("status") or "ready",
        imported_by=imported_by,
        imported_at=metadata.get("importedAt") or now(),
        # The column's vocabulary names the KIND of source file; a Finance version of a
        # Microsoft Project file is still a Microsoft Project file. Provenance is carried by
        # host_snapshot_id IS NULL and source_file_version_id, not by a new source_type.
        source_type=("microsoft_project" if version_id is not None
                     else metadata.get("sourceType")))


def _override_payload(row,snapshot_id):
 return {"previousCalculatedValue":str(row["computed_value"]),"newValue":str(row["override_value"]),"reason":row["reason"],"userId":str(row["created_by"]),"occurredAt":row["created_at"].isoformat(),"source":"manual_override","progressSnapshotId":str(snapshot_id)}

def apply_progress_overrides(assignments,overrides,snapshot_id):
 # The reverse direction: the overrides are indexed by the line identifiers they carry,
 # and each feed row is matched against them. Same rule, same precedence, read backwards.
 pairing=ProgressPairing(overrides,line_keys)
 result=[]
 for source in assignments:
  row=dict(source)
  override=pairing.match(*assignment_keys(row))
  if override is not None:row["manualOverride"]=_override_payload(override,snapshot_id)
  result.append(row)
 return result

@dataclass(frozen=True)
class ProgressOverride:
 id:UUID;organization_id:UUID;project_id:str;estimate_line_id:UUID;progress_snapshot_ref_id:UUID;progress_snapshot_id:UUID;computed_value:Decimal;override_value:Decimal;reason:str;created_by:UUID;created_at:datetime
