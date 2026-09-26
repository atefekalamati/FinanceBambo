# -*- coding: utf-8 -*-
"""The three kinds of thing a project spends money on, stated once.

    material      -- bought by quantity: kilograms, cubic metres, pieces.
    work          -- bought by the hour: crews and machines alike.
    general_cost  -- a lump sum with no quantity at all.

WHY THREE AND NOT FOUR

Until 2026-09-26 Finance separated `work` into `labor` and `equipment`. Nothing in the
numbers ever depended on which: both are hours, both are priced per hour, both are settled
against invoices by amount over the rate of the invoice's day. The one place the split
mattered was the import, and there it was a cost: MS Project calls both WORK and does not
say which, so every crew and every machine in a schedule waited for a person to decide --
through an endpoint that existed only on the development host. On the product, they waited
forever. Three kinds is what the file states, what the arithmetic needs, and what the
project owner chose: «تجهیزات و نیروی انسانی باید جزو یک دسته بندی باشند».

THE OLD NAMES

Rows written before 0038 still say `labor` or `equipment`, and issued report snapshots are
frozen with those words. They are not rewritten -- the migration widens the CHECK and
touches no row -- so every reader that meets a stored type passes it through
`canonical_resource_type` first. That function is the whole compatibility story: one place,
and a stored `equipment` is `work` everywhere else.
"""

MATERIAL = "material"
WORK = "work"
GENERAL_COST = "general_cost"

#: The kinds, in the order every breakdown lists them.
RESOURCE_TYPES = (MATERIAL, WORK, GENERAL_COST)

#: What `work` used to be called. Accepted when READ, never written again.
LEGACY_WORK_TYPES = ("labor", "equipment")

#: Everything a stored `resource_type` may hold, for a CHECK or a validator that must
#: still admit the rows that exist.
STORED_RESOURCE_TYPES = RESOURCE_TYPES + LEGACY_WORK_TYPES


def canonical_resource_type(value):
    """`labor` and `equipment` are `work`; anything else is returned as it came.

    `None` stays `None`: an unclassified resource is not silently a kind of work.
    """
    if value in LEGACY_WORK_TYPES:
        return WORK
    return value
