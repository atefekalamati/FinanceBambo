# -*- coding: utf-8 -*-
r"""TEST_ONLY -- DISPOSABLE. Where does this MPP actually keep its progress?

Reads one .mpp and reports which fields carry data. Nothing else: no database connection,
no writes, no mapping change. It answers one question -- MS Project shows columns for
پیشرفت واقعی, ضریب وزنی زمانی and هزینه, while the parser reports every task at 0% -- by
looking at every field those values could be in.

The important part is the custom-field ALIAS table. When a planner adds a column called
"ضریب وزنی زمانی" they are renaming a built-in slot such as Number1, and MS Project stores
that rename in the file. MPXJ exposes it through `getCustomFields()`, so the mapping from
Persian column heading to MPXJ field can be READ rather than guessed. Guessing which of
Number1..Number20 is the weight would be exactly the kind of invention that puts a wrong
number into a financial report.

    probe-env/Scripts/python inspect_mpp_fields.py --input "..\..\..\..\Sources\test_progress.mpp"
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLED_JRE = HERE / "jre" / "jdk-17.0.20.1+1-jre"

#: The custom-field families to sweep, and how many of each MS Project provides.
CUSTOM_FAMILIES = (("TEXT", 30), ("NUMBER", 20), ("COST", 10),
                   ("DURATION", 10), ("DATE", 10), ("FLAG", 20))

#: Task fields that would carry progress if the planner used the standard ones.
STANDARD_TASK_FIELDS = (
    "PERCENT_COMPLETE", "PERCENT_WORK_COMPLETE", "PHYSICAL_PERCENT_COMPLETE",
    "ACTUAL_START", "ACTUAL_FINISH", "ACTUAL_DURATION", "ACTUAL_WORK",
    "REMAINING_WORK", "ACTUAL_COST", "REMAINING_COST", "COST", "WORK", "DURATION",
    "BASELINE_COST", "BASELINE_WORK",
)

RESOURCE_FIELDS = ("ACTUAL_WORK", "ACTUAL_COST", "WORK", "COST", "MATERIAL",
                   "ACTUAL_MATERIAL", "PERCENT_WORK_COMPLETE")

ASSIGNMENT_FIELDS = ("ACTUAL_WORK", "ACTUAL_COST", "WORK", "COST",
                     "PERCENT_WORK_COMPLETE", "MATERIAL", "ACTUAL_MATERIAL",
                     "REMAINING_WORK", "REMAINING_COST")


def start_jvm(java_home=None):
    """Boot the JVM with MPXJ's jars. Same two ordering rules as parse_mpp.py.

    `import mpxj` must precede `startJVM` (its body is the classpath registration), and the
    JRE must be a full one -- a jlink'd runtime without `jdk.charsets` dies in MPXJ's static
    initialiser asking for MacRoman.
    """
    if java_home:
        os.environ["JAVA_HOME"] = str(java_home)
    elif not os.environ.get("JAVA_HOME"):
        if not BUNDLED_JRE.is_dir():
            raise SystemExit("STOP: no JAVA_HOME and no bundled JRE at %s" % BUNDLED_JRE)
        os.environ["JAVA_HOME"] = str(BUNDLED_JRE)
    import jpype
    import jpype.imports  # noqa: F401
    import mpxj           # noqa: F401  -- MUST precede startJVM
    if not jpype.isJVMStarted():
        jpype.startJVM()
    try:
        import org.mpxj as api
        from org.mpxj.reader import UniversalProjectReader
        return api, UniversalProjectReader, "org.mpxj"
    except ImportError:
        import net.sf.mpxj as api
        from net.sf.mpxj.reader import UniversalProjectReader
        return api, UniversalProjectReader, "net.sf.mpxj"


def render(value):
    """A Java value as something printable, or None when it carries nothing.

    Zero is NOT treated as nothing. A reported zero and an absent value are different
    claims, and collapsing them is the specific mistake this whole investigation is about.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_empty(value):
    """Whether a field is unset. `0`, `0.0h` and `false` count as SET, not empty."""
    return value is None or str(value).strip() == ""


def field_of(api, holder, name):
    """`TaskField.NAME` / `ResourceField.NAME` etc., or None when this MPXJ lacks it."""
    try:
        return getattr(getattr(api, holder), name)
    except (AttributeError, TypeError):
        return None


def sweep(api, holder, items, names, label_of=None):
    """For each field name, how many items set it and a few samples.

    Returns a list of `(name, set_count, non_zero_count, samples)` for fields that any item
    sets, in declaration order.
    """
    out = []
    for name in names:
        field = field_of(api, holder, name)
        if field is None:
            continue
        values, non_zero = [], 0
        for item in items:
            try:
                raw = item.get(field)
            except Exception:                                # noqa: BLE001
                continue
            if is_empty(raw):
                continue
            text = render(raw)
            if text is None:
                continue
            values.append((item, text))
            if text.lower() not in ("0", "0.0", "0.00", "0.0h", "0.0d", "0h", "0d",
                                    "false", "0.0%", "$0.00", "0%"):
                non_zero += 1
        if values:
            samples = [(label_of(item) if label_of else str(item), text)
                       for item, text in values[:4]]
            out.append((name, len(values), non_zero, samples))
    return out


def custom_field_aliases(project):
    """Persian column heading -> MPXJ field, read from the file rather than guessed.

    This is the whole point of the script. MS Project stores a renamed column's alias, so
    "ضریب وزنی زمانی" can be resolved to the exact slot it renames. Without this the only
    way to identify the weight column would be to guess among twenty Number fields.
    """
    out = []
    try:
        container = project.getCustomFields()
    except Exception:                                        # noqa: BLE001
        return out
    for entry in container:
        try:
            alias = render(entry.getAlias())
            field = entry.getFieldType()
        except Exception:                                    # noqa: BLE001
            continue
        if alias and field is not None:
            out.append((str(field), alias))
    return out


def task_label(task):
    return "uid=%s %s" % (task.getUniqueID(), (render(task.getName()) or "")[:34])


def report(project, api, package, path):
    tasks = list(project.getTasks())
    resources = list(project.getResources())
    assignments = list(project.getResourceAssignments())
    properties = project.getProjectProperties()

    print("  file                 %s" % path.name)
    print("  written by           %s" % render(properties.getFullApplicationName()))
    print("  MPXJ java package    %s" % package)
    print()
    print("  Tasks                %d" % len(tasks))
    print("  Resources            %d" % len(resources))
    print("  Assignments          %d" % len(assignments))

    # ---------------------------------------------------------------- custom field aliases
    print("\n  === RENAMED COLUMNS (read from the file, not guessed) ===")
    aliases = custom_field_aliases(project)
    if aliases:
        for field, alias in aliases:
            print("    %-16s = %s" % (field, alias))
    else:
        print("    none: this file renames no custom column")

    # ---------------------------------------------------------------------- standard fields
    print("\n  === STANDARD TASK FIELDS WITH DATA ===")
    print("    %-28s %6s %8s  %s" % ("field", "set", "non-zero", "samples"))
    standard = sweep(api, "TaskField", tasks, STANDARD_TASK_FIELDS, task_label)
    for name, count, non_zero, samples in standard:
        print("    %-28s %6d %8d  %s" % (name, count, non_zero,
                                         "; ".join("%s -> %s" % pair for pair in samples[:2])))
    if not standard:
        print("    none")

    # ------------------------------------------------------------------------ custom fields
    print("\n  === CUSTOM TASK FIELDS WITH DATA ===")
    names = [("%s%d" % (family, index)) for family, count in CUSTOM_FAMILIES
             for index in range(1, count + 1)]
    custom = sweep(api, "TaskField", tasks, names, task_label)
    # MPXJ spells the field one way in the alias table (`Number17`) and another in the enum
    # (`NUMBER17`). Keyed case-insensitively so the two actually meet -- matching them
    # literally silently left every alias blank, which made the file look unlabelled.
    alias_by_field = {field.upper(): alias for field, alias in aliases}
    if custom:
        print("    %-14s %6s %8s %-26s %s" % ("field", "set", "non-zero", "renamed to",
                                              "samples"))
        for name, count, non_zero, samples in custom:
            print("    %-14s %6d %8d %-26s %s"
                  % (name, count, non_zero, alias_by_field.get(name, "")[:26],
                     "; ".join(text for _, text in samples[:3])))
    else:
        print("    none of TEXT1-30, NUMBER1-20, COST1-10, DURATION1-10, DATE1-10, "
              "FLAG1-20 carries data")

    # ------------------------------------------------------------- resources & assignments
    print("\n  === RESOURCE FIELDS WITH DATA ===")
    for name, count, non_zero, samples in sweep(
            api, "ResourceField", resources, RESOURCE_FIELDS,
            lambda r: render(r.getName()) or str(r.getUniqueID())):
        print("    %-24s %6d set %6d non-zero   %s"
              % (name, count, non_zero, "; ".join("%s=%s" % p for p in samples[:2])))

    print("\n  === ASSIGNMENT FIELDS WITH DATA ===")
    for name, count, non_zero, samples in sweep(
            api, "AssignmentField", assignments, ASSIGNMENT_FIELDS,
            lambda a: "auid=%s" % a.getUniqueID()):
        print("    %-24s %6d set %6d non-zero   %s"
              % (name, count, non_zero, "; ".join(text for _, text in samples[:2])))

    # Assignment custom fields too: a planner who put progress on the assignment rather
    # than the task would leave every task at 0%, which is exactly the reported symptom.
    assignment_custom = sweep(api, "AssignmentField", assignments, names,
                              lambda a: "auid=%s" % a.getUniqueID())
    print("\n  === CUSTOM ASSIGNMENT FIELDS WITH DATA ===")
    if assignment_custom:
        for name, count, non_zero, samples in assignment_custom:
            print("    %-14s %6d set %6d non-zero   %s"
                  % (name, count, non_zero, "; ".join(text for _, text in samples[:3])))
    else:
        print("    none")

    return tasks, resources, assignments, standard, custom, aliases, assignment_custom


#: Words that make a renamed column a claim about EXECUTION rather than about plan or
#: weighting. A column called "ضریب وزنی زمانی" is a weight; one called "پیشرفت واقعی" is a
#: statement about what was built. Only the second kind can answer "how much is done".
PROGRESS_WORDS = ("پیشرفت", "واقعی", "انجام", "اجرا", "actual", "progress", "complete")

#: A weight or a plan figure. Listed separately because finding these populated is NOT
#: finding progress, and reporting them as progress would be the same class of mistake as
#: reading a date as an activity code.
WEIGHT_WORDS = ("وزنی", "wf", "مبنا", "برنامه")

STANDARD_PROGRESS_FIELDS = ("PERCENT_COMPLETE", "PERCENT_WORK_COMPLETE",
                            "PHYSICAL_PERCENT_COMPLETE", "ACTUAL_WORK", "ACTUAL_COST",
                            "ACTUAL_START", "ACTUAL_FINISH", "ACTUAL_DURATION")


def classify(alias):
    """`progress`, `weight` or `other`, from what the planner named the column."""
    if not alias:
        return "other"
    lowered = alias.lower()
    if any(word in lowered for word in WEIGHT_WORDS):
        return "weight"
    if any(word in lowered for word in PROGRESS_WORDS):
        return "progress"
    return "other"


def verdict(standard, custom, aliases, assignment_custom):
    """What actually carries execution data. FOUND, or NO_PROGRESS_FIELDS_FOUND.

    The distinction this function exists to hold: a renamed column that is present but full
    of zeros is not progress. Reporting "FOUND: Number14 = پیشرفت واقعی" when all 328 of its
    values are zero would answer the question asked and mislead about the answer.
    """
    print("\n  === RESULT ===")
    alias_by_field = {field.upper(): alias for field, alias in aliases}

    standard_progress = [(name, non_zero) for name, _c, non_zero, _s in standard
                         if non_zero and name in STANDARD_PROGRESS_FIELDS]

    named = []      # every renamed column, with its alias and whether it holds anything
    for name, _count, non_zero, _samples in custom:
        alias = alias_by_field.get(name)
        if alias:
            named.append((name, alias, non_zero, classify(alias)))

    progress_named = [row for row in named if row[3] == "progress"]
    progress_filled = [row for row in progress_named if row[2]]
    weights_filled = [row for row in named if row[3] == "weight" and row[2]]
    other_filled = [row for row in named if row[3] == "other" and row[2]]
    assignment_filled = [(n, z) for n, _c, z, _s in assignment_custom if z]

    if not standard_progress and not progress_filled and not assignment_filled:
        print("    NO_PROGRESS_FIELDS_FOUND")
        print()
        print("    Every field that could carry execution is present and empty:")
        for name, alias, _z, _k in progress_named:
            print("      %-10s = %-28s all values zero" % (name, alias))
        for name, _count, non_zero, _s in standard:
            if name in STANDARD_PROGRESS_FIELDS and not non_zero:
                print("      %-10s   %-28s all values zero" % (name, "(standard)"))
        if weights_filled or other_filled:
            print()
            print("    What this file DOES carry -- none of it is executed progress:")
            for name, alias, non_zero, kind in weights_filled + other_filled:
                print("      %-10s = %-28s %d non-zero  [%s]" % (name, alias, non_zero, kind))
        print()
        print("    So `tasks with percent > 0 = 0` is CORRECT for this file. The columns")
        print("    exist because the planner defined them; they were never filled in.")
        return "NO_PROGRESS_FIELDS_FOUND"

    print("    FOUND:")
    for name, non_zero in standard_progress:
        print("      %-10s   %-28s %d task(s) non-zero" % (name, "(standard)", non_zero))
    for name, alias, non_zero, _kind in progress_filled:
        print("      %-10s = %-28s %d non-zero" % (name, alias, non_zero))
    for name, non_zero in assignment_filled:
        print("      %-10s   %-28s %d assignment(s) non-zero"
              % (name, "(assignment custom)", non_zero))
    if progress_filled and not standard_progress:
        print()
        print("    Progress is in CUSTOM fields, not the standard ones. That is why the")
        print("    parser reports 0%: it reads PercentComplete, which this planner left at")
        print("    zero. The mapping below has to change before these numbers are usable.")
    return "FOUND"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--java-home", default=None)
    parser.add_argument("--json", type=Path, default=None,
                        help="also write the field inventory as JSON")
    arguments = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not arguments.input.is_file():
        raise SystemExit("STOP: no such file: %s" % arguments.input)

    print("\n  TEST_ONLY / DISPOSABLE -- reads one .mpp, touches no database\n")
    api, reader, package = start_jvm(arguments.java_home)
    project = reader().read(str(arguments.input))

    (tasks, resources, assignments, standard, custom,
     aliases, assignment_custom) = report(project, api, package, arguments.input)
    outcome = verdict(standard, custom, aliases, assignment_custom)

    if arguments.json:
        arguments.json.write_text(json.dumps({
            "file": arguments.input.name, "outcome": outcome,
            "counts": {"tasks": len(tasks), "resources": len(resources),
                       "assignments": len(assignments)},
            "aliases": [{"field": f, "alias": a} for f, a in aliases],
            "standardTaskFields": [{"field": n, "set": c, "nonZero": z}
                                   for n, c, z, _s in standard],
            "customTaskFields": [{"field": n, "set": c, "nonZero": z}
                                 for n, c, z, _s in custom],
            "customAssignmentFields": [{"field": n, "set": c, "nonZero": z}
                                       for n, c, z, _s in assignment_custom],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n  wrote %s" % arguments.json)

    print("\n  NOTHING WAS WRITTEN TO ANY DATABASE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
