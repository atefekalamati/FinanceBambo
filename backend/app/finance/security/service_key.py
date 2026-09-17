# -*- coding: utf-8 -*-
"""A shared secret that lets one automation trigger one endpoint. Nothing else.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT

Finance authenticates nobody. Identity arrives from the host through
`auth_context_provider`, and every route is gated on a permission that host resolved.
That is the module's contract and this file does not change it.

What it adds is one exception, scoped as tightly as it can be: the daily material price
import is triggered by n8n after it finishes writing the sheet, and n8n is not a person.
It holds no session, appears in no directory, and giving it a user account would put a
login in a password manager somewhere and call that an identity. So it presents a shared
secret instead, and the secret is accepted on ONE route.

    it authenticates       the material price import trigger, and nothing else
    it authorises          nothing -- there is no permission check to skip, because the
                           key IS the whole claim, and the route it opens reads a sheet
                           the server configured and writes prices from it
    it can choose          nothing -- not the sheet, not the organization, not the data.
                           The project must already have a configured provider

WHY THE KEY MAY NOT PICK AN ORGANIZATION

A caller that could name a tenant could import one tenant's prices into another's books.
The organization is read from the provider configuration of the project in the path, so a
project nobody set up for price imports is not reachable with this key at all -- and the
key cannot widen what it touches by asking differently.

WHAT NEVER HAPPENS TO THE KEY

It is read from the environment on every check and held nowhere. It is never logged,
never returned, never compared with `==` (which leaks its length through timing), and
never written to the database. `describe()` exists so an operator can ask whether the
host is configured without the answer containing the secret.
"""

import hmac
import os

from ..domain.errors import FinanceDomainError

#: The header n8n sends. Named for what it opens rather than for the caller, because a
#: second automation would present the same kind of thing for a different route.
SERVICE_KEY_HEADER = "X-FINANCE-SERVICE-KEY"

SERVICE_KEY_SETTING = "FINANCE_MATERIAL_PRICE_IMPORT_SERVICE_KEY"

#: Shorter than this is not a secret, it is a typo that happens to authenticate. A host
#: configured with one refuses to accept ANY key rather than accepting a guessable one --
#: failing closed, because the alternative is a door that looks locked.
MINIMUM_KEY_LENGTH = 32

#: What the run records about who asked. Not a user id: there is no user, and inventing
#: one would put a name in an audit trail that belongs to nobody.
SYSTEM_INITIATOR = "system"


class ServiceKeyRejected(FinanceDomainError):
    """A key was presented and it was not the configured one.

    401 rather than 403: the caller has not proved who it is. There is no permission it
    could be granted that would change the answer.
    """

    status = 401
    code = "FINANCE_SERVICE_KEY_REJECTED"


def configured_key():
    """The key this host accepts, or None when service triggering is switched off.

    Too short counts as not configured. A host that was given a four-character key has a
    setting somebody got wrong, and accepting it would be worse than refusing every
    automated call until it is fixed.
    """
    value = (os.environ.get(SERVICE_KEY_SETTING) or "").strip()
    if len(value) < MINIMUM_KEY_LENGTH:
        return None
    return value


def describe():
    """Whether service triggering is usable, in a form safe to print or return."""
    value = (os.environ.get(SERVICE_KEY_SETTING) or "").strip()
    return {
        "header": SERVICE_KEY_HEADER,
        "configured": configured_key() is not None,
        # Length only, and only so an operator can tell "unset" from "set but rejected as
        # too short". It is never enough to reconstruct anything.
        "keyLength": len(value),
        "minimumLength": MINIMUM_KEY_LENGTH,
    }


def presented(request):
    """The key this request carried, or None. Absence is not an error here."""
    value = (request.headers.get(SERVICE_KEY_HEADER) or "").strip()
    return value or None


def authenticate(request):
    """`True` when this request proved it is the configured automation.

    Returns `False` when NO key was presented -- that is a human request and the caller
    goes on to the ordinary permission gate, which is what keeps manual operation exactly
    as it was.

    Raises when a key WAS presented and is not the configured one, including when the
    host has none configured at all. A caller that tried to authenticate and failed must
    be told so; quietly falling through to the user gate would turn a wrong secret into a
    confusing 403 about a permission the automation was never going to have.
    """
    offered = presented(request)
    if offered is None:
        return False
    expected = configured_key()
    if expected is None:
        raise ServiceKeyRejected(
            "this host accepts no service key for material price imports")
    # Constant time. `==` returns as soon as two bytes differ, and the time that takes is
    # a measurement of how much of the key an attacker has guessed.
    if not hmac.compare_digest(offered, expected):
        raise ServiceKeyRejected("the service key presented is not accepted")
    return True
