"""Adapters that connect the Finance module to the real BAMBO Core schema.

WHY THIS IS A SEPARATE PACKAGE
`app/finance` is a library: it declares ports and never learns who implements them, which
is what lets it be tested without a Core database and deployed without a composition root.
`devhost` is the opposite extreme -- static fixtures that must never be deployed. Neither
is the right home for code that reads Core's own tables, so this is a third place:
production-intended adapters that depend on the Core schema and on the Finance ports, and
on nothing in between.

Nothing here is imported by `app/`. The dependency runs one way, adapters -> ports, so
adding, replacing or deleting this package cannot change a Finance calculation.

WHAT IS AND IS NOT ASSUMED
Every table and column read here was verified against the real Core schema. Where Core
offers no answer, these adapters say so rather than deriving one:

  * Core has no resource-assignment table, so the progress adapter reports task-level rows
    and never invents an assignment.
  * `msp_tasks` carries percentages but no quantities, so no executed quantity is
    manufactured from a percentage alone.
  * `finance_report.issue` does not exist in Core's permission catalogue, so it is denied.
    It is not mapped onto a permission that does exist.

Each of those is a real limit of the integration, and each is documented where it bites.
"""
