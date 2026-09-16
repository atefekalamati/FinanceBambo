"""Putting a person's name beside the id that stands for them.

WHY THIS EXISTS
Finance stores actors as bare UUIDs, because the people are the host's and duplicating them
here would be a second source of truth that drifts. That is the right storage decision and
it stays. What it cost was the reading: nine places in the UI printed
`53a1ac1b-d87f-4125-9ba9-a7d64166af88` where a reader needed «مدیر سیستم», and a financial
document that cannot say who confirmed it in words a person recognises is a document nobody
can audit by looking.

So the id keeps its place and a name is carried BESIDE it, never instead of it. Every
response still contains the identifier it always did -- clients that match on it keep
working, and the name is additive.

WHY A NAME MAY BE ABSENT, AND WHY THAT IS NOT AN ERROR
`None` is a legitimate answer everywhere here. A host with no Core directory at all, a user
row that has been deleted, an actor column that was always nullable -- each of them means
"this id has no name to show", which the UI renders as the id itself. Inventing a
placeholder like «کاربر نامشخص» at this layer would hide the difference between "nobody
asked" and "asked, and the host does not know them".

WHAT IS DELIBERATELY NOT TRAVERSED
`before_values` and `after_values` on an audit event are free-form JSON written by whatever
recorded the event. They may well contain a key called `created_by`; that key is part of the
recorded evidence, not part of this envelope, and writing a name into it would edit the
audit trail while claiming to decorate it. So traversal follows lists and the named container
keys in `CONTAINER_KEYS`, and steps into nothing else.
"""

from typing import Any, Iterable, Mapping

#: Every actor column the API exposes, paired with the field its name travels in, written in
#: the snake_case the database and the schema attributes use.
ACTOR_FIELDS: tuple[tuple[str, str], ...] = (
    ("imported_by", "imported_by_name"),
    ("submitted_by", "submitted_by_name"),
    ("confirmed_by", "confirmed_by_name"),
    ("created_by", "created_by_name"),
    ("actor_user_id", "actor_user_name"),
    # Who said what a market listing is. `labelledByName` was declared on the material
    # price response and filled by nothing, so it was null on every row -- the id was
    # there and the name it was supposed to travel with never arrived.
    ("labelled_by", "labelled_by_name"),
)

#: The only dict keys traversal descends through. Everything else -- notably an audit
#: event's recorded `before_values`/`after_values` -- is evidence to be carried unchanged,
#: not a container to be decorated. See the module docstring.
CONTAINER_KEYS: tuple[str, ...] = ("items", "lines", "revisions", "snapshot")


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


#: Each pair in both spellings, because both really arrive here. A service hands the router
#: rows straight from psycopg, whose keys are snake_case; a progress feed's header is the
#: HOST's JSON, whose keys are camelCase and which is exactly where the progress page reads
#: its importer. Matching one spelling silently skipped the other. `to_camel` is reimplemented
#: rather than imported, because the domain layer does not depend on the schema layer.
ACTOR_SPELLINGS: tuple[tuple[str, str], ...] = tuple(
    dict.fromkeys([(i, n) for i, n in ACTOR_FIELDS]
                  + [(_camel(i), _camel(n)) for i, n in ACTOR_FIELDS]))


def _read(payload: Any, key: str) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(key)
    return getattr(payload, key, None)


def _has(payload: Any, key: str) -> bool:
    if isinstance(payload, Mapping):
        return key in payload
    return hasattr(payload, key)


def _traversable(value: Any) -> bool:
    """Whether a child is something to walk into rather than a leaf to leave alone."""
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return False
    return isinstance(value, (list, tuple, Mapping)) or hasattr(value, "__dict__")


def _children(payload: Any) -> Iterable[Any]:
    """The sub-payloads traversal is allowed to visit.

    A container key may hold a list (`items`, `lines`, `revisions`) or a single object
    (`snapshot`, the header a progress feed wraps). Both are walked -- the feed's header is
    where the reported screen actually reads its importer from, and a list-only rule silently
    skipped it.
    """
    if isinstance(payload, (list, tuple)):
        return payload
    if isinstance(payload, Mapping):
        return [payload[key] for key in CONTAINER_KEYS if _traversable(payload.get(key))]
    return [value for value in (getattr(payload, key, None) for key in CONTAINER_KEYS)
            if _traversable(value)]


def collect_actor_ids(payload: Any) -> set[str]:
    """Every actor id anywhere in this response, as strings, ready for one lookup.

    Returned as a set because a list of fifty invoices submitted by three people is three
    names, and asking the host fifty times for them would be the N+1 this function exists to
    make impossible.
    """
    found: set[str] = set()
    if isinstance(payload, (list, tuple)):
        for item in payload:
            found |= collect_actor_ids(item)
        return found
    if payload is None or isinstance(payload, (str, bytes, int, float, bool)):
        return found
    for id_field, _ in ACTOR_SPELLINGS:
        value = _read(payload, id_field)
        if value is not None:
            found.add(str(value))
    for child in _children(payload):
        found |= collect_actor_ids(child)
    return found


def apply_actor_names(payload: Any, names: Mapping[str, str]) -> Any:
    """Fill each name field from `names`, in place, and return the same payload.

    A field is only written when the payload already declares it -- a Mapping gets the key
    unconditionally (rows are ours to decorate), while an object gets it only if the
    attribute exists, because the response models forbid extras and inventing one there
    would turn a missing name into a 500.

    An id with no entry in `names` leaves the field as `None`. That is the honest answer and
    the UI falls back to showing the id.
    """
    if isinstance(payload, (list, tuple)):
        for item in payload:
            apply_actor_names(item, names)
        return payload
    if payload is None or isinstance(payload, (str, bytes, int, float, bool)):
        return payload
    for id_field, name_field in ACTOR_SPELLINGS:
        value = _read(payload, id_field)
        if value is None:
            continue
        name = names.get(str(value))
        if isinstance(payload, dict):
            payload[name_field] = name
        elif _has(payload, name_field):
            try:
                setattr(payload, name_field, name)
            except (AttributeError, ValueError):
                # A frozen or validating model that will not take the name keeps its id and
                # nothing else changes. A decoration is never worth failing a response for.
                pass
    for child in _children(payload):
        apply_actor_names(child, names)
    return payload
