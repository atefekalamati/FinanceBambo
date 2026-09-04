# -*- coding: utf-8 -*-
r"""TEST_ONLY -- NON_PRODUCTION -- MANUAL_EXECUTION_ONLY -- DISPOSABLE

Read one .mpp with MPXJ and write a JSON fixture. That is the whole job.

THIS IS NOT THE PRODUCTION MSP PARSER AND MUST NEVER BECOME ONE.
The production path is MPP -> Core's MPXJ importer -> the msp_* tables, and that importer
lives outside this repository. This probe exists to prove one thing quickly: that a real
.mpp can be read and turned into rows the Finance side already knows how to consume. It
opens no database connection -- there is no psycopg import here and no DSN argument -- so
the only thing it can damage is its own output file.

Delete the whole `mpp_parser_probe/` directory to remove it. Nothing outside it refers to it.

WHAT IT REFUSES TO DO
  * invent a value. A field MS Project does not carry is written `null`, never `0` and never
    derived from another field. `--strict` turns any such gap into a visible warning;
  * derive a quantity from work, duration or a percentage. `work` is hours; `quantity` is
    kilograms and cubic metres. They are read from different MPXJ fields and never
    substituted for one another;
  * classify a resource as labour or equipment. MS Project has no such distinction, so
    `bambo_resource_type` is always null and a human fills it in later;
  * write to any database.

    python parse_mpp.py --input "..\..\..\..\Sources\زمان بندی پل.mpp" --output fixture.json
"""

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: The JRE this probe was verified against. `install-jdk` put it here; see README.md. An
#: already-set JAVA_HOME wins, so a machine with its own JVM needs no bundled copy.
BUNDLED_JRE = HERE / "jre" / "jdk-17.0.20.1+1-jre"

#: MSP resource types, exactly as the `msp_resources_native_type_check` constraint spells
#: them. Anything else is reported rather than mapped onto one of these.
NATIVE_TYPES = frozenset({"WORK", "MATERIAL", "COST"})

#: Where the unit string was read from. `msp_resources_quantity_unit_source_check` allows
#: only these four. For this file it is always `initials`: the Resource Sheet's "Initials"
#: column is where this project's author wrote کیلوگرم and مترمکعب.
UNIT_SOURCE_INITIALS = "initials"


def start_jvm(java_home=None):
    """Boot the JVM with MPXJ's jars on the classpath.

    Two ordering rules, both of which cost an afternoon when broken:

    `import mpxj` must happen BEFORE `startJVM`. The package's whole body is a loop calling
    `jpype.addClassPath`, and a classpath entry added after the JVM is up is ignored --
    the failure is `ImportError: Java package 'org' not found`, which reads like a bad
    install rather than a sequencing mistake.

    The JRE must be a full one. A jlink'd minimal runtime (jdk4py, for instance) omits the
    `jdk.charsets` module, and MPXJ's `CharsetHelper` asks for MacRoman in a static
    initialiser -- so the failure is `UnsupportedCharsetException: MacRoman` thrown from
    class loading, before your file is even opened.
    """
    if java_home:
        os.environ["JAVA_HOME"] = str(java_home)
    elif not os.environ.get("JAVA_HOME"):
        if not BUNDLED_JRE.is_dir():
            raise SystemExit(
                "STOP: no JAVA_HOME and no bundled JRE at %s.\n"
                "      See README.md -- one command downloads it." % BUNDLED_JRE)
        os.environ["JAVA_HOME"] = str(BUNDLED_JRE)

    try:
        import jpype
        import jpype.imports  # noqa: F401
    except ImportError as error:
        raise SystemExit("STOP: jpype1 is not installed. See README.md.") from error
    try:
        import mpxj  # noqa: F401  -- registers the jars; MUST precede startJVM
    except ImportError as error:
        raise SystemExit("STOP: mpxj is not installed. See README.md.") from error

    if not jpype.isJVMStarted():
        jpype.startJVM()

    # MPXJ renamed its Java package from `net.sf.mpxj` to `org.mpxj`. Production runs
    # 16.4.1; this probe installed 16.7.0. Both spellings are tried rather than one being
    # declared correct, so the probe keeps working against whichever jar is present.
    try:
        from org.mpxj.reader import UniversalProjectReader
        return UniversalProjectReader, "org.mpxj"
    except ImportError:
        from net.sf.mpxj.reader import UniversalProjectReader
        return UniversalProjectReader, "net.sf.mpxj"


def number(value):
    """A Java number as a decimal string, or None.

    A string, not a float. These values become `numeric(18,6)` and `numeric(18,4)` columns,
    and the seed script feeds them to `Decimal`. Letting a float carry a rate through JSON
    is how 3200000.0 becomes 3199999.9999999995.
    """
    if value is None:
        return None
    try:
        return format(Decimal(str(value)), "f")
    except Exception:                                        # noqa: BLE001
        return None


def hours(duration):
    """A MPXJ Duration in hours, as a decimal string, or None.

    MS Project stores work in whatever unit the author chose. Reading `getDuration()`
    without checking `getUnits()` silently reports 5 days as 5 hours.
    """
    if duration is None:
        return None
    try:
        units = str(duration.getUnits())
        if units == "HOURS":
            return number(duration.getDuration())
        from org.mpxj import Duration, TimeUnit
    except ImportError:
        from net.sf.mpxj import Duration, TimeUnit
    except Exception:                                        # noqa: BLE001
        return None
    try:
        return number(Duration.convertUnits(
            duration.getDuration(), duration.getUnits(), TimeUnit.HOURS,
            _CONVERSION_PROPERTIES[0]).getDuration())
    except Exception:                                        # noqa: BLE001
        return None


#: Duration conversion needs the project's own hours-per-day/week. Held in a one-slot list
#: so `hours()` stays a plain function while still seeing the open project.
_CONVERSION_PROPERTIES = [None]


def text(value):
    """A Java string as a Python one, or None. Empty and whitespace-only become None.

    An empty Initials cell is an absent unit, not a unit named "". The difference decides
    whether a quantity is allowed into the table at all.
    """
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def moment(value):
    """A MPXJ date-time as an ISO string, or None. No timezone is invented."""
    return None if value is None else str(value)


def read_tasks(project):
    """Every task, including the summary rows and the project row (UID 0).

    Summary tasks are kept. A rollup that silently dropped them would be a different tree
    from the one in the file, and the point of this probe is to show what the file says.
    """
    out = []
    for task in project.getTasks():
        parent = task.getParentTask()
        duration = task.getDuration()
        out.append({
            "task_uid": task.getUniqueID(),
            "task_id": task.getID(),
            "name": text(task.getName()),
            "wbs": text(task.getWBS()),
            # Distinct from WBS, and not interchangeable with it: Core's own task query
            # orders by outline_number, so a null here reorders the whole feed.
            "outline_number": text(task.getOutlineNumber()),
            "outline_level": task.getOutlineLevel(),
            "parent_task_uid": (parent.getUniqueID() if parent is not None else None),
            "summary": bool(task.getSummary()),
            "milestone": bool(task.getMilestone()),
            "start": moment(task.getStart()),
            "finish": moment(task.getFinish()),
            "duration": number(duration.getDuration()) if duration is not None else None,
            "duration_unit": str(duration.getUnits()) if duration is not None else None,
            "duration_hours": hours(duration),
            "percent_complete": number(task.getPercentageComplete()),
            "percent_work_complete": number(task.getPercentageWorkComplete()),
            "physical_percent_complete": number(task.getPhysicalPercentComplete()),
            # The activity-code field Finance matches on. Read because Core stores it, not
            # because this probe interprets it.
            "text1": text(task.getText(1)),
            "work_hours": hours(task.getWork()),
            "actual_work_hours": hours(task.getActualWork()),
        })
    return out


def read_resources(project, warnings):
    """The Resource Sheet, in the shape `seed_msp_resource_assignments.py` inserts.

    The unit comes from Initials. That is a convention this project's author chose, not
    something MS Project enforces, which is exactly why `quantity_unit_source` records
    where the string was read from -- a later file using MaterialLabel instead stays
    distinguishable from this one.
    """
    out = []
    for resource in project.getResources():
        native = text(resource.getType())
        if native is not None and native not in NATIVE_TYPES:
            warnings.append("resource %s has MSP type %r, which the table's CHECK does not "
                            "allow" % (resource.getUniqueID(), native))
        initials = text(resource.getInitials())
        material_label = text(resource.getMaterialLabel())
        quantity = number(resource.getMaterial())

        # The unit is only claimed for a resource that actually carries a quantity. Copying
        # Initials onto a WORK resource would put "کیلوگرم" beside a number of hours.
        unit = unit_source = None
        if quantity is not None:
            if material_label:
                unit, unit_source = material_label, "material_label"
            elif initials:
                unit, unit_source = initials, UNIT_SOURCE_INITIALS
            else:
                warnings.append(
                    "resource %s (%s) carries quantity %s but names no unit; the "
                    "msp_resource_assignments CHECK will refuse a quantity without one"
                    % (resource.getUniqueID(), text(resource.getName()) or "unnamed",
                       quantity))

        out.append({
            "resource_uid": resource.getUniqueID(),
            "resource_guid": text(resource.getGUID()),
            "resource_name": text(resource.getName()),
            "native_type": native,
            # Never set here. MS Project has no labour/equipment distinction to read, and a
            # guess would be indistinguishable from a fact once it is in the column.
            "bambo_resource_type": None,
            "resource_quantity": quantity,
            "resource_quantity_unit": unit,
            "quantity_unit_source": unit_source,
            "initials": initials,
            "material_label": material_label,
            "resource_group": text(resource.getGroup()),
            "code": text(resource.getCode()),
            "max_units": number(resource.getMaxUnits()),
            "standard_rate": _rate(resource.getStandardRate()),
            "overtime_rate": _rate(resource.getOvertimeRate()),
            "cost_per_use": number(resource.getCostPerUse()),
            "work": hours(resource.getWork()),
            "actual_work": hours(resource.getActualWork()),
            "remaining_work": hours(resource.getRemainingWork()),
            "source_cost": number(resource.getCost()),
            "source_actual_cost": number(resource.getActualCost()),
            "source_remaining_cost": number(resource.getRemainingCost()),
            "raw_fields_json": {"unitOfMeasure": text(resource.getUnitOfMeasure()),
                                "peakUnits": number(resource.getPeakUnits())},
        })
    return out


def _rate(rate):
    """A MPXJ Rate's amount. The time base travels in raw_fields_json, not silently lost."""
    if rate is None:
        return None
    try:
        return number(rate.getAmount())
    except Exception:                                        # noqa: BLE001
        return number(rate)


def read_assignments(project, units_by_resource, warnings):
    """Every resource assignment, in the seed script's shape.

    `planned_quantity` is Assignment.Material -- a physical amount. It is not Work. Work is
    hours. The two are adjacent in every MSP dialog and substituting one for the other
    turns 48 crane-hours into 48 kilograms of rebar, which is the specific defect this
    field separation exists to prevent.
    """
    out = []
    unlinked = 0
    for assignment in project.getResourceAssignments():
        resource_uid = assignment.getResourceUniqueID()
        if resource_uid is not None:
            resource_uid = int(resource_uid)
        task_uid = assignment.getTaskUniqueID()
        if task_uid is None:
            warnings.append("assignment %s references no task and was skipped"
                            % assignment.getUniqueID())
            continue
        if resource_uid is None:
            unlinked += 1

        planned_quantity = number(assignment.getMaterial())
        actual_quantity = number(assignment.getActualMaterial())
        remaining_quantity = number(assignment.getRemainingMaterial())
        unit = units_by_resource.get(resource_uid)
        if planned_quantity is not None and unit is None:
            warnings.append(
                "assignment %s carries quantity %s but its resource names no unit"
                % (assignment.getUniqueID(), planned_quantity))

        out.append({
            "assignment_uid": assignment.getUniqueID(),
            "task_uid": int(task_uid),
            "resource_uid": resource_uid,
            "units": number(assignment.getUnits()),
            "planned_work": hours(assignment.getWork()),
            "actual_work": hours(assignment.getActualWork()),
            "remaining_work": hours(assignment.getRemainingWork()),
            "planned_quantity": planned_quantity,
            "actual_quantity": actual_quantity,
            "remaining_quantity": remaining_quantity,
            # Only when there is something to measure. A unit beside a null quantity is
            # noise, and the CHECK cares about the other direction.
            "quantity_unit": unit if (planned_quantity is not None
                                      or actual_quantity is not None) else None,
            "assignment_work_complete_percent": number(
                assignment.getPercentageWorkComplete()),
            "source_cost": number(assignment.getCost()),
            "source_actual_cost": number(assignment.getActualCost()),
            "source_remaining_cost": number(assignment.getRemainingCost()),
            "raw_fields_json": {"remainingUnits": number(assignment.getRemainingUnits())},
        })
    if unlinked:
        warnings.append("%d assignment(s) name no resource; they are kept with "
                        "resource_uid null, which the seed script permits" % unlinked)
    return out


def summarise(fixture, warnings):
    """What was read, printed before anything is written."""
    tasks = fixture["tasks"]
    resources = fixture["resources"]
    assignments = fixture["assignments"]

    kinds = {}
    for row in resources:
        kinds[row["native_type"]] = kinds.get(row["native_type"], 0) + 1

    print()
    print("  Tasks count:       %d" % len(tasks))
    print("  Resources count:   %d" % len(resources))
    print("  Assignments count: %d" % len(assignments))
    print()
    print("  resources by MSP type      %s"
          % ", ".join("%s=%d" % kv for kv in sorted(kinds.items(), key=lambda p: str(p[0]))))
    print("  resources with a quantity  %d"
          % sum(1 for r in resources if r["resource_quantity"] is not None))
    print("  resources with a unit      %d"
          % sum(1 for r in resources if r["resource_quantity_unit"] is not None))
    print("  assignments with quantity  %d"
          % sum(1 for a in assignments if a["planned_quantity"] is not None))
    print("  assignments with actual    %d"
          % sum(1 for a in assignments if a["actual_quantity"] is not None))
    print("  assignments with no unit   %d  (must be 0; a CHECK forbids it)"
          % sum(1 for a in assignments
                if a["planned_quantity"] is not None and not a["quantity_unit"]))
    print("  unlinked assignments       %d"
          % sum(1 for a in assignments if a["resource_uid"] is None))
    print("  tasks with percent > 0     %d"
          % sum(1 for t in tasks
                if t["percent_complete"] not in (None, "0") and Decimal(
                    t["percent_complete"] or 0) > 0))
    print("  distinct task_uid used     %d"
          % len({a["task_uid"] for a in assignments}))

    if warnings:
        print()
        print("  WARNINGS (%d)" % len(warnings))
        for line in warnings[:20]:
            print("    - %s" % line)
        if len(warnings) > 20:
            print("    ... and %d more" % (len(warnings) - 20))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path, help="the .mpp to read")
    parser.add_argument("--output", required=True, type=Path, help="fixture JSON to write")
    parser.add_argument("--java-home", default=None,
                        help="a full JRE; defaults to JAVA_HOME, then the bundled copy")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if anything was warned about")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    print("\n  TEST_ONLY / NON_PRODUCTION / DISPOSABLE")
    print("  this reads a .mpp and writes JSON -- it opens no database\n")

    if not arguments.input.is_file():
        raise SystemExit("STOP: no such file: %s" % arguments.input)

    reader, package = start_jvm(arguments.java_home)
    print("  MPXJ java package    %s" % package)
    print("  reading              %s" % arguments.input.name)

    project = reader().read(str(arguments.input))
    properties = project.getProjectProperties()
    _CONVERSION_PROPERTIES[0] = properties
    print("  written by           %s" % text(properties.getFullApplicationName()))

    warnings = []
    resources = read_resources(project, warnings)
    units_by_resource = {row["resource_uid"]: row["resource_quantity_unit"]
                         for row in resources}
    fixture = {
        "source_file": arguments.input.name,
        "generated_by": "scripts/test_only/mpp_parser_probe/parse_mpp.py (TEST ONLY)",
        "mpxj_java_package": package,
        "project_title": text(properties.getProjectTitle()),
        "application": text(properties.getFullApplicationName()),
        "resources": resources,
        "assignments": read_assignments(project, units_by_resource, warnings),
        "tasks": read_tasks(project),
    }

    summarise(fixture, warnings)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  wrote %s (%.1f KB)"
          % (arguments.output, arguments.output.stat().st_size / 1024))
    print("  NOTHING WAS WRITTEN TO ANY DATABASE.")

    if warnings and arguments.strict:
        print("\n  --strict: %d warning(s)." % len(warnings))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
