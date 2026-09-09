"""Grouping the live report by WBS node.

**No financial formula lives in this module.** Money is produced by
`calculate_live_report`, called once per node over that node's own rows, so a node's numbers
come from the canonical engine and there is no second implementation to drift from it. What
is here is the part that engine has no opinion about: which estimate line belongs to which
stage of the plan, and how those stages nest.

WHERE THE TREE COMES FROM
The stages are Core's, not Finance's. Every activity in the newest MSP snapshot carries a
`wbsCode`, and the set of those codes -- plus the ancestors implied by them -- is the tree.
That has a consequence worth stating: a stage with no estimate lines is still a stage, and
still appears, with zeros. A stage that vanished because Finance happened to have no rows
for it would read as "nothing planned here" when it means "nothing recorded here yet".

WHY THE PARENT LINK IS A STRING SPLIT
Core records no parent for a task. `msp_tasks` has `outline_level` and `outline_number` and
`wbs`, and no column naming a parent row -- so there is no authoritative relation to prefer,
and the dotted code is what remains. This is a fallback, and the docstring says so where the
next reader will look: if Core ever exposes a parent, `parent_of` is the one function that
has to change.
"""

from decimal import Decimal

SEPARATOR = "."
ZERO = Decimal(0)

#: The resource types the breakdown reports, in the order the rest of Finance uses.
RESOURCE_TYPES = ("material", "labor", "equipment", "general_cost")


def segments(code):
    """`"1.8.2"` -> `("1", "8", "2")`. Blank segments are dropped, not kept as empties."""
    if not code:
        return ()
    return tuple(part for part in str(code).strip().split(SEPARATOR) if part.strip())


def normalize(code):
    """The canonical spelling of a code, or None if it names nothing.

    `" 1.8. "` and `"1..8"` both name node `1.8`. Without this, one estimate line spelled a
    fraction differently would sit in a stage of its own.
    """
    parts = segments(code)
    return SEPARATOR.join(part.strip() for part in parts) if parts else None


def parent_of(code):
    """The parent node's code, or None for a root.

    A string split, because Core supplies no parent relation -- see the module docstring.
    """
    parts = segments(code)
    return SEPARATOR.join(parts[:-1]) if len(parts) > 1 else None


def ancestors(code):
    """Every proper ancestor of a code, outermost first: `1.8.2` -> `("1", "1.8")`."""
    parts = segments(code)
    return tuple(SEPARATOR.join(parts[:index]) for index in range(1, len(parts)))


def level_of(code):
    """1 for a root node, 2 for its children, and so on."""
    return len(segments(code))


def build_tree(activities):
    """Every WBS node the plan implies, keyed by code.

    `activities` is an iterable of activity mappings carrying `activityExternalId` and
    `wbsCode`. Ancestors are materialised even when no activity names them directly: a plan
    that has `1.8.2` has a stage `1.8`, whether or not anything was scheduled at that level.

    Each node carries:
      `title`          the title of the activity whose code is exactly this node's, else None
      `parentWbsCode`  from `parent_of`
      `children`       direct child codes, sorted naturally
      `activityCodes`  every activity at or below this node
    """
    nodes = {}

    def ensure(code):
        if code not in nodes:
            nodes[code] = {"wbsCode": code, "title": None, "parentWbsCode": parent_of(code),
                           "children": set(), "activityCodes": set()}
        return nodes[code]

    titled = {}
    for activity in activities:
        code = normalize(activity.get("wbsCode"))
        if code is None:
            # An activity with no WBS code belongs to no stage. It is not silently placed
            # at the root -- that would put work under a heading nobody planned it under.
            continue
        node = ensure(code)
        for ancestor in ancestors(code):
            ensure(ancestor)
        # First activity whose code is exactly this node's names it. Activities arrive in
        # outline order, so the first is the outermost, which is the one describing the
        # stage rather than a step inside it.
        titled.setdefault(code, activity.get("title"))
        identifier = activity.get("activityExternalId")
        if identifier is None:
            continue
        node["activityCodes"].add(identifier)
        for ancestor in ancestors(code):
            nodes[ancestor]["activityCodes"].add(identifier)

    for code, title in titled.items():
        nodes[code]["title"] = title
    for code, node in nodes.items():
        parent = node["parentWbsCode"]
        if parent is not None and parent in nodes:
            nodes[parent]["children"].add(code)
    return nodes


def sort_key(code):
    """Natural order: `1.10` after `1.9`, not before it.

    A plain string sort puts `1.10` between `1.1` and `1.2`, which reorders a stage list in
    a way a reader reads as wrong before they can say why. Numeric segments sort as numbers;
    anything else sorts as text, after the numbers at that depth.
    """
    key = []
    for part in segments(code):
        if part.isdigit():
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part))
    return tuple(key)


#: MS Project's project summary task. When "show project summary task" is on it is written
#: into the plan as a row like any other, carrying the project's own name and this code. It
#: is not a stage of the work and no plan numbers a real stage zero.
PROJECT_SUMMARY_CODE = "0"


def project_root(nodes, occupied=()):
    """The one stage that holds the whole plan, when the file wraps it in one.

    A planner may put every phase at the top of the plan -- `1` foundations, `2` structure,
    `3` finishes -- or wrap the lot in a single task named after the project, with the
    phases inside it at `1.1`, `1.2`, `1.3`. Both are ordinary, and the difference is
    invisible to a rule that only counts dots: in the second shape "the top of the tree" is
    the project itself, and a report of it is one row saying the project costs what the
    project costs.

    BAMBO's own MSP report resolves this the same way. Its «پیشرفت سطح ۱» lists `1.1`,
    `1.2`, `1.3` and its «پیشرفت سطح ۲» lists `1.2.1`, `1.5.4` -- one step deeper than the
    dots alone would say, because it counts from inside the wrapper. Two reports of one
    project that disagree about which rows are its phases is the outcome worth avoiding.

    `occupied` is the codes that carry estimate lines of their own. A wrapper is a
    container; one that has been costed directly is a stage, and reporting its children in
    its place would drop that cost out of every row while the totals still counted it.

    Returns the wrapper's code, or None when the plan has real stages at its top.
    """
    roots = [code for code in nodes
             if level_of(code) == 1 and code != PROJECT_SUMMARY_CODE]
    if len(roots) != 1:
        return None
    only = roots[0]
    # A lone root with nothing under it is the whole plan, not a wrapper around it.
    if not nodes[only]["children"]:
        return None
    return None if only in set(occupied) else only


def select(nodes, level=None, parent_wbs_code=None, occupied=()):
    """The codes to report, in natural order.

    `parent_wbs_code` wins over `level` when both are given: it is the more specific
    request, and answering the broader one would silently ignore what the caller asked for.
    Direct children only -- never the whole subtree, so a level-2 request stays a level-2
    answer.

    A `level` is counted from the project, not from the string. Where the plan wraps itself
    in a single task, level 1 is that task's children -- see `project_root`.
    """
    if parent_wbs_code is not None:
        parent = normalize(parent_wbs_code)
        if parent is None or parent not in nodes:
            return []
        chosen = nodes[parent]["children"]
    else:
        depth = 1 if level is None else int(level)
        root = project_root(nodes, occupied)
        if root is None:
            chosen = [code for code in nodes if level_of(code) == depth]
        else:
            # Measured from inside the wrapper, and kept inside it: a stage of this depth
            # somewhere else in the tree is not a level of this project.
            inside = root + SEPARATOR
            chosen = [code for code in nodes
                      if level_of(code) == depth + level_of(root) and code.startswith(inside)]
    return sorted(chosen, key=sort_key)


def subtree(nodes, code):
    """A node's code together with every descendant's, as a set."""
    found = {code}
    stack = [code]
    while stack:
        current = stack.pop()
        for child in nodes.get(current, {}).get("children", ()):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


def line_nodes(estimate_rows, activities_by_code):
    """`estimate_line_id -> wbs code`, plus the lines that reach no code.

    A line reaches a code through its activity. A line naming no activity, an activity the
    catalogue does not know, or an activity carrying no WBS code, reaches nothing -- and is
    returned separately rather than being dropped, because money on it still has to be
    accounted for somewhere the reader can see.
    """
    placed, unplaced = {}, []
    for row in estimate_rows:
        activity = activities_by_code.get(row.get("activity_external_id"))
        code = normalize(activity.get("wbsCode")) if activity else None
        if code is None:
            unplaced.append(row["id"])
        else:
            placed[row["id"]] = code
    return placed, unplaced


def split_invoices(invoice_rows, placed_lines):
    """Invoice rows in three groups, by why they can or cannot reach a WBS node.

    Returns `(by_line, unattributed, unplaced)`:
      `by_line`       estimate_line_id -> rows, for lines that reached a node
      `unattributed`  rows carrying no `estimate_line_id` at all
      `unplaced`      rows whose estimate line reached no WBS code

    The last two are counted separately on purpose. Both are money outside the tree, but one
    means "this purchase was never tied to an estimate line" and the other means "it was,
    and that line's activity has no stage". Different people fix those, so one number for
    both would tell the reader nothing about what to do.
    """
    by_line, unattributed, unplaced = {}, [], []
    for row in invoice_rows:
        identifier = row.get("estimate_line_id")
        if identifier is None:
            unattributed.append(row)
        elif identifier in placed_lines:
            by_line.setdefault(identifier, []).append(row)
        else:
            unplaced.append(row)
    return by_line, unattributed, unplaced


def actual_of(rows):
    """The signed actual cost of a set of invoice rows.

    The same definition the live report uses: the final line amount times the invoice's
    financial effect sign, so a reversal subtracts.
    """
    total = ZERO
    for row in rows:
        total += Decimal(row["final_line_amount_irr"]) * Decimal(row["financial_effect_sign"])
    return total
