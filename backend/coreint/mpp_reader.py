# -*- coding: utf-8 -*-
"""Reading a Microsoft Project file, behind a port Finance never sees.

Core owns this boundary. ``app/finance`` imports neither this module nor MPXJ nor JPype --
a test in ``test_schedule_contract.py`` forbids it -- and everything downstream consumes
tables, not files.

The implementation carries four hard-won facts about MPXJ on this stack, each of which cost
real debugging time when it was unknown:

  * ``import mpxj`` MUST precede ``jpype.startJVM()``. The package's whole body is a loop
    of ``jpype.addClassPath`` calls, and a classpath entry added after the JVM is up is
    silently ignored -- the failure reads as ``Java package 'org' not found``.
  * The JVM must be a FULL runtime. A jlink'd minimal one (jdk4py) omits ``jdk.charsets``,
    and MPXJ's ``CharsetHelper`` asks for MacRoman in a static initialiser -- the failure is
    ``UnsupportedCharsetException`` thrown during class loading, before any file is opened.
  * The Java package was renamed ``net.sf.mpxj`` -> ``org.mpxj``; both spellings are tried
    so one adapter serves whichever jar is installed.
  * Work and Material are DIFFERENT MPXJ fields with different meanings. ``Work`` is hours;
    ``Material`` is the physical quantity (kilograms, cubic metres). They are extracted into
    separate keys and never substituted -- confusing them turns 48 crane-hours into 48
    kilograms of rebar.

Values that will land in ``numeric`` columns travel as STRINGS built through ``Decimal``,
never as floats. A value the file does not state is ``None`` -- absent is not zero.
"""

import os
import threading
from decimal import Decimal
from pathlib import Path
from typing import Protocol

#: One process, one JVM, one boot. Two concurrent first parses (a manual POST beside the
#: periodic tick) would otherwise both pass the isJVMStarted() check and the loser's
#: startJVM() would fail a perfectly valid import.
_JVM_BOOT_LOCK = threading.Lock()


class MppReaderError(RuntimeError):
    code = "MPP_PARSE_FAILED"


class MpxjNotAvailable(MppReaderError):
    code = "MPXJ_NOT_AVAILABLE"


class JavaRuntimeNotAvailable(MppReaderError):
    code = "JAVA_RUNTIME_NOT_AVAILABLE"


class MppFileCorrupted(MppReaderError):
    code = "MPP_FILE_CORRUPTED"


class ParsedMppProject:
    """Everything one file states, as plain data. No database identifiers exist yet."""

    def __init__(self, application, tasks, resources, assignments, warnings,
                 parser_engine=None):
        self.application = application
        self.tasks = tasks
        self.resources = resources
        self.assignments = assignments
        self.warnings = warnings
        #: Real provenance ("mpxj-<installed version>/jvm-<running java>"), derived at
        #: JVM boot -- None from a reader that cannot honestly claim one.
        self.parser_engine = parser_engine


class MppReaderPort(Protocol):
    """The seam. An importer depends on this shape and on nothing about Java."""

    def read(self, file_path: Path) -> ParsedMppProject: ...


def _text(value):
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _number(value):
    """A Java number as a decimal string, or None. A string, because these become
    ``numeric`` columns and a float in between is how 3200000 becomes 3199999.99..."""
    if value is None:
        return None
    try:
        return format(Decimal(str(value)), "f")
    except Exception:                                        # noqa: BLE001
        return None


def _moment(value):
    return None if value is None else str(value)


class MpxjMppReader:
    """``MppReaderPort`` over MPXJ on a JVM. Loads lazily; boots the JVM once per process."""

    def __init__(self, java_home=None):
        #: An explicit JAVA_HOME wins; otherwise the environment's. Configuration, not a
        #: hard-coded path -- see devhost.environment.mpp_java_home().
        self._java_home = java_home
        self._parser_engine = None
        self._reader_factory = None
        self._api_package = None
        self._time_unit = None
        self._duration = None

    # ------------------------------------------------------------------------- JVM boot
    def _load(self):
        if self._reader_factory is not None:
            return
        with _JVM_BOOT_LOCK:
            self._load_locked()

    def _load_locked(self):
        if self._reader_factory is not None:
            return
        if self._java_home:
            os.environ["JAVA_HOME"] = str(self._java_home)
        if not os.environ.get("JAVA_HOME"):
            raise JavaRuntimeNotAvailable(
                "no JAVA_HOME configured; MPXJ needs a full JRE (a jlink'd minimal "
                "runtime fails inside MPXJ's charset initialiser)")
        try:
            import jpype
            import jpype.imports  # noqa: F401
        except ImportError as error:
            raise MpxjNotAvailable("jpype1 is not installed in this environment") from error
        try:
            import mpxj  # noqa: F401  -- registers the jars; MUST precede startJVM
        except ImportError as error:
            raise MpxjNotAvailable("mpxj is not installed in this environment") from error
        try:
            if not jpype.isJVMStarted():
                jpype.startJVM()
        except Exception as error:                            # noqa: BLE001
            # Only the exception CLASS reaches the message: JVM loader errors embed
            # absolute DLL paths, and this text travels into API bodies and log lines.
            # The chained exception keeps the full detail for local tracebacks.
            raise JavaRuntimeNotAvailable(
                "the JVM failed to start: %s" % type(error).__name__) from error
        try:
            from org.mpxj.reader import UniversalProjectReader
            from org.mpxj import Duration, TimeUnit
            self._api_package = "org.mpxj"
        except ImportError:
            try:
                from net.sf.mpxj.reader import UniversalProjectReader
                from net.sf.mpxj import Duration, TimeUnit
                self._api_package = "net.sf.mpxj"
            except ImportError as error:
                raise MpxjNotAvailable(
                    "MPXJ classes not found on the JVM classpath") from error
        self._reader_factory = UniversalProjectReader
        self._duration, self._time_unit = Duration, TimeUnit
        # Provenance, derived from what is actually running -- never typed by hand.
        try:
            import importlib.metadata
            mpxj_version = importlib.metadata.version("mpxj")
        except Exception:                                     # noqa: BLE001
            mpxj_version = "unknown"
        try:
            java_version = str(jpype.JClass("java.lang.System")
                               .getProperty("java.specification.version"))
        except Exception:                                     # noqa: BLE001
            java_version = "unknown"
        self._parser_engine = ("mpxj-%s/jvm-%s;finance-repo-importer"
                               % (mpxj_version, java_version))

    # -------------------------------------------------------------------------- helpers
    def _hours(self, duration, properties):
        """An MPXJ Duration in hours, as a decimal string. Reading ``getDuration()``
        without checking ``getUnits()`` silently reports 5 days as 5 hours."""
        if duration is None:
            return None
        try:
            if str(duration.getUnits()) == "HOURS":
                return _number(duration.getDuration())
            converted = self._duration.convertUnits(
                duration.getDuration(), duration.getUnits(), self._time_unit.HOURS,
                properties)
            return _number(converted.getDuration())
        except Exception:                                     # noqa: BLE001
            return None

    @staticmethod
    def _rate(rate):
        if rate is None:
            return None
        try:
            return _number(rate.getAmount())
        except Exception:                                     # noqa: BLE001
            return _number(rate)

    # ---------------------------------------------------------------------------- read
    def read(self, file_path) -> ParsedMppProject:
        self._load()
        path = Path(file_path)
        try:
            project = self._reader_factory().read(str(path))
        except Exception as error:                            # noqa: BLE001
            raise MppFileCorrupted(
                "MPXJ could not parse the file: %s" % type(error).__name__) from error
        if project is None:
            raise MppFileCorrupted("MPXJ recognised no project in the file")

        properties = project.getProjectProperties()
        warnings = []

        tasks = []
        for task in project.getTasks():
            tasks.append({
                # Identity, in the documented preference order GUID > UID > ID. All three
                # are stored; note that on the reference schedule the UID was measured
                # stable across saves (1248/1248) while the GUID was fully regenerated --
                # so the GUID is recorded but nothing downstream may treat it as the only
                # identity. The NAME is never an identity.
                "uid": None if task.getUniqueID() is None else int(task.getUniqueID()),
                "guid": _text(task.getGUID()),
                "task_id": None if task.getID() is None else int(task.getID()),
                "name": _text(task.getName()),
                "wbs": _text(task.getWBS()),
                "outline_number": _text(task.getOutlineNumber()),
                "outline_level": (None if task.getOutlineLevel() is None
                                  else int(task.getOutlineLevel())),
                "summary": bool(task.getSummary()),
                "start": _moment(task.getStart()),
                "finish": _moment(task.getFinish()),
                "baseline_start": _moment(task.getBaselineStart()),
                "baseline_finish": _moment(task.getBaselineFinish()),
                "duration": self._hours(task.getDuration(), properties),
                "percent_complete": _number(task.getPercentageComplete()),
                "percent_work_complete": _number(task.getPercentageWorkComplete()),
                "physical_percent_complete": _number(task.getPhysicalPercentComplete()),
                # The custom activity-code convention. Read because Core stores text1;
                # which field REALLY carries a code is host configuration downstream.
                "text1": _text(task.getText(1)),
            })

        resources = []
        for resource in project.getResources():
            native_type = _text(resource.getType())
            initials = _text(resource.getInitials())
            material_label = _text(resource.getMaterialLabel())
            quantity = _number(resource.getMaterial())
            # The unit is only claimed for a resource that actually carries a quantity,
            # and its provenance is recorded: on the reference schedules the planners
            # wrote units in Initials, not MaterialLabel, and a later file doing the
            # opposite must stay distinguishable.
            unit = unit_source = None
            if quantity is not None:
                if material_label:
                    unit, unit_source = material_label, "material_label"
                elif initials:
                    unit, unit_source = initials, "initials"
                else:
                    warnings.append("resource %s carries a quantity but names no unit"
                                    % resource.getUniqueID())
            resources.append({
                "uid": None if resource.getUniqueID() is None else int(resource.getUniqueID()),
                "guid": _text(resource.getGUID()),
                "name": _text(resource.getName()),
                "native_type": native_type,
                "initials": initials,
                "material_label": material_label,
                "quantity": quantity,
                "quantity_unit": unit,
                "quantity_unit_source": unit_source,
                "group": _text(resource.getGroup()),
                "code": _text(resource.getCode()),
                "max_units": _number(resource.getMaxUnits()),
                "standard_rate": self._rate(resource.getStandardRate()),
                "overtime_rate": self._rate(resource.getOvertimeRate()),
                "cost_per_use": _number(resource.getCostPerUse()),
                "work": self._hours(resource.getWork(), properties),
                "actual_work": self._hours(resource.getActualWork(), properties),
                "remaining_work": self._hours(resource.getRemainingWork(), properties),
                "cost": _number(resource.getCost()),
                "actual_cost": _number(resource.getActualCost()),
                "remaining_cost": _number(resource.getRemainingCost()),
            })

        assignments = []
        unlinked = 0
        for assignment in project.getResourceAssignments():
            task_uid = assignment.getTaskUniqueID()
            if task_uid is None:
                warnings.append("assignment %s references no task and was skipped"
                                % assignment.getUniqueID())
                continue
            resource_uid = assignment.getResourceUniqueID()
            if resource_uid is not None:
                resource_uid = int(resource_uid)
            if resource_uid is None:
                # Kept, not dropped: MSP leaves some assignments unattached, and dropping
                # them would lose work that was really planned. The count is a warning.
                unlinked += 1
            assignments.append({
                "assignment_uid": (None if assignment.getUniqueID() is None
                                   else int(assignment.getUniqueID())),
                "task_uid": int(task_uid),
                "resource_uid": resource_uid,
                "units": _number(assignment.getUnits()),
                # Work is TIME, in hours. Quantity is PHYSICAL, from the Material fields.
                # Separate keys, never substituted, and never derived from one another.
                "planned_work": self._hours(assignment.getWork(), properties),
                "actual_work": self._hours(assignment.getActualWork(), properties),
                "remaining_work": self._hours(assignment.getRemainingWork(), properties),
                "planned_quantity": _number(assignment.getMaterial()),
                "actual_quantity": _number(assignment.getActualMaterial()),
                "remaining_quantity": _number(assignment.getRemainingMaterial()),
                "work_complete_percent": _number(assignment.getPercentageWorkComplete()),
                "cost": _number(assignment.getCost()),
                "actual_cost": _number(assignment.getActualCost()),
                "remaining_cost": _number(assignment.getRemainingCost()),
            })
        if unlinked:
            warnings.append("%d assignment(s) name no resource; kept with resource_uid "
                            "null" % unlinked)

        return ParsedMppProject(
            application=_text(properties.getFullApplicationName()),
            tasks=tasks, resources=resources, assignments=assignments,
            warnings=warnings, parser_engine=self._parser_engine)
