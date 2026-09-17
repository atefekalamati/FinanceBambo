# -*- coding: utf-8 -*-
"""The one shared secret in Finance, and the fence around it.

WHY THIS EXISTS AT ALL

Finance authenticates nobody: identity comes from the host and every route is gated on a
permission that host resolved. This is the single deliberate exception. n8n triggers the
daily material price import after it writes the sheet, and n8n is not a person -- it holds
no session, appears in no directory, and giving it a user account would put a login in a
password manager and call that an identity.

So the fence matters more than the gate. These tests are mostly about what the key CANNOT
do:

    it opens one route                  and no other
    it chooses no tenant                the organization comes from provider configuration
    it chooses no sheet                 that was already server-side
    it grants no permission             there is nothing to escalate to
    a wrong key is refused              not quietly dropped into a permission error
    a short key is no key               a host configured with one accepts nothing

And the human path is unchanged: a request with no key is gated exactly as it was.
"""

import os
import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.security.service_key import (MINIMUM_KEY_LENGTH, SERVICE_KEY_HEADER,
                                              SERVICE_KEY_SETTING, ServiceKeyRejected,
                                              SYSTEM_INITIATOR, authenticate,
                                              configured_key, describe)

GOOD_KEY = "k" * MINIMUM_KEY_LENGTH


class Request:
    """Just the headers; that is all `authenticate` reads."""

    def __init__(self, **headers):
        self.headers = dict(headers)


class KeyEnvironment(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get(SERVICE_KEY_SETTING)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop(SERVICE_KEY_SETTING, None)
        else:
            os.environ[SERVICE_KEY_SETTING] = self.saved

    def set_key(self, value):
        if value is None:
            os.environ.pop(SERVICE_KEY_SETTING, None)
        else:
            os.environ[SERVICE_KEY_SETTING] = value


class ConfigurationTests(KeyEnvironment):
    def test_unset_means_no_service_triggering(self):
        self.set_key(None)
        self.assertIsNone(configured_key())

    def test_a_short_key_is_treated_as_no_key(self):
        """A host given a four-character secret has a setting somebody got wrong.

        Accepting it would be worse than refusing every automated call until it is fixed:
        a door that looks locked is more dangerous than one visibly open.
        """
        for value in ("", "  ", "short", "k" * (MINIMUM_KEY_LENGTH - 1)):
            with self.subTest(len(value)):
                self.set_key(value)
                self.assertIsNone(configured_key())

    def test_a_key_of_sufficient_length_configures_the_host(self):
        self.set_key(GOOD_KEY)
        self.assertEqual(GOOD_KEY, configured_key())

    def test_describe_never_returns_the_key(self):
        self.set_key("s3cret-value-nobody-should-ever-see-in-a-log")
        told = describe()
        self.assertTrue(told["configured"])
        self.assertNotIn("s3cret", str(told))
        self.assertEqual(SERVICE_KEY_HEADER, told["header"])


class AuthenticationTests(KeyEnvironment):
    def test_no_header_is_a_human_request_not_an_error(self):
        """This is what keeps manual operation exactly as it was."""
        self.set_key(GOOD_KEY)
        self.assertFalse(authenticate(Request()))

    def test_the_configured_key_authenticates(self):
        self.set_key(GOOD_KEY)
        self.assertTrue(authenticate(Request(**{SERVICE_KEY_HEADER: GOOD_KEY})))

    def test_a_wrong_key_is_refused_rather_than_ignored(self):
        """Falling through to the user gate would turn a wrong secret into a confusing
        403 about a permission the automation was never going to hold."""
        self.set_key(GOOD_KEY)
        with self.assertRaises(ServiceKeyRejected) as caught:
            authenticate(Request(**{SERVICE_KEY_HEADER: "x" * MINIMUM_KEY_LENGTH}))
        self.assertEqual(401, caught.exception.status)
        self.assertEqual("FINANCE_SERVICE_KEY_REJECTED", caught.exception.code)

    def test_a_key_on_a_host_that_configured_none_is_refused(self):
        self.set_key(None)
        with self.assertRaises(ServiceKeyRejected):
            authenticate(Request(**{SERVICE_KEY_HEADER: GOOD_KEY}))

    def test_a_prefix_of_the_key_does_not_authenticate(self):
        self.set_key(GOOD_KEY)
        with self.assertRaises(ServiceKeyRejected):
            authenticate(Request(**{SERVICE_KEY_HEADER: GOOD_KEY[:-1]}))

    def test_the_refusal_never_repeats_the_key(self):
        self.set_key(GOOD_KEY)
        with self.assertRaises(ServiceKeyRejected) as caught:
            authenticate(Request(**{SERVICE_KEY_HEADER: "wrong-" + GOOD_KEY}))
        message = str(caught.exception)
        self.assertNotIn(GOOD_KEY, message)
        self.assertNotIn("wrong-", message)

    def test_the_comparison_is_constant_time(self):
        """Pinned as source, because `==` returns as soon as two bytes differ and that
        time is a measurement of how much of the key an attacker has guessed."""
        import inspect

        from app.finance.security import service_key
        source = inspect.getsource(service_key.authenticate)
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("offered == expected", source)


class FenceTests(unittest.TestCase):
    """What the key may not reach."""

    def test_only_the_import_trigger_consults_it(self):
        """One route. A second call site would be a second door with the same key."""
        import re

        source = (BACKEND_ROOT / "app" / "finance" / "router.py").read_text(
            encoding="utf-8")
        uses = re.findall(r"service_key\.authenticate\(", source)
        self.assertEqual(1, len(uses),
                         "the service key must authenticate exactly one endpoint")

    def test_the_automated_scope_carries_no_actor_and_no_permissions(self):
        """Nothing to escalate to: the key IS the claim, and it grants no role."""
        import inspect

        from app.finance import router
        source = inspect.getsource(router._service_scope)
        self.assertIn("actor_user_id=None", source)
        self.assertNotIn("permission_codes", source)

    def test_the_organization_is_read_from_configuration_not_the_request(self):
        """A key that could name a tenant could import one tenant's prices into another's
        books, and holding the key says nothing about which tenant it speaks for."""
        import inspect

        from app.finance import router
        source = inspect.getsource(router._service_scope)
        self.assertIn("projects_with_active_providers", source)
        self.assertIn('row["organization_id"]', source)

    def test_an_automated_run_is_attributed_to_the_system_not_a_person(self):
        self.assertEqual("system", SYSTEM_INITIATOR)
        self.assertNotIn("user", SYSTEM_INITIATOR)


class ResponseProvenanceTests(unittest.TestCase):
    def test_the_answer_states_what_asked_and_who(self):
        from app.finance.schemas.material_prices import ImportRunStartedResponse
        for field in ("trigger_source", "initiated_by"):
            self.assertIn(field, ImportRunStartedResponse.model_fields)

    def test_a_skipped_automated_run_still_says_it_was_automated(self):
        from app.finance.schemas.material_prices import ImportRunStartedResponse
        answer = ImportRunStartedResponse(
            status="skipped", run=None, inserted=0, already_present=0, rejected=0,
            trigger_source="n8n_daily_material_price_update",
            initiated_by=SYSTEM_INITIATOR, message="skipped")
        self.assertEqual("system", answer.initiated_by)
        self.assertIsNone(answer.run)


if __name__ == "__main__":
    unittest.main()
