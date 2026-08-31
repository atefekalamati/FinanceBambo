"""Which databases the Finance runtime is allowed to open.

The rule is checked by address as well as by name. `bambo` -- Core's own database -- lives on
the same server as `bambo_canonical_local`, so a name-only rule would let a DSN reach it, and
Finance would write its rows into Core. The one that actually happened is milder and harder to
see: `.env` still names the superseded `bambo_finance_dev`, so an unset environment variable
lands a correctly-started host on an empty database that reports no error at all.

A local database that is neither of those stays allowed. The demo builders and this suite need
one, and a lock that broke them would be switched off rather than obeyed.
"""

import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from devhost import environment as env

CENTRAL = "192.168.100.200"


def dsn(host, database, port=5432):
    return f"postgresql://user:secret@{host}:{port}/{database}"


class RuntimeDatabaseLockTests(unittest.TestCase):
    def refuse(self, name, value):
        with self.assertRaises(env.MissingConfiguration):
            env.check_runtime_dsn(name, value)

    def test_the_central_database_is_permitted(self):
        value = dsn(CENTRAL, "bambo_canonical_local")
        self.assertEqual(value, env.check_runtime_dsn("FINANCE_DEV_DSN", value))

    def test_core_s_own_database_is_refused_anywhere(self):
        self.refuse("FINANCE_DEV_DSN", dsn(CENTRAL, "bambo"))
        self.refuse("FINANCE_CORE_DSN", dsn("127.0.0.1", "bambo"))

    def test_any_other_database_on_the_central_server_is_refused(self):
        self.refuse("FINANCE_DEV_DSN", dsn(CENTRAL, "bambo_finance_rc"))
        self.refuse("FINANCE_CORE_DSN", dsn(CENTRAL, "postgres"))

    def test_the_superseded_local_database_is_refused(self):
        self.refuse("FINANCE_DEV_DSN", dsn("127.0.0.1", "bambo_finance_dev", 55432))

    def test_another_local_database_is_left_alone(self):
        value = dsn("127.0.0.1", "bambo_finance_rc", 5440)
        self.assertEqual(value, env.check_runtime_dsn("FINANCE_DEV_DSN", value))

    def test_the_keyword_form_is_read_rather_than_skipped(self):
        self.refuse("FINANCE_DEV_DSN", f"host={CENTRAL} port=5432 dbname=bambo user=u")

    def test_a_dsn_that_cannot_be_read_is_passed_through_not_guessed(self):
        # A rule applied to a misread address reads as enforcement while enforcing something
        # else, which is worse than declining to judge.
        self.assertEqual("nonsense", env.check_runtime_dsn("FINANCE_DEV_DSN", "nonsense"))
        self.assertIsNone(env.check_runtime_dsn("FINANCE_CORE_DSN", None))

    def test_the_error_names_the_setting_and_never_the_credential(self):
        try:
            env.check_runtime_dsn("FINANCE_DEV_DSN", dsn(CENTRAL, "bambo"))
        except env.MissingConfiguration as error:
            message = str(error)
            self.assertIn("FINANCE_DEV_DSN", message)
            self.assertNotIn("secret", message)
            self.assertNotIn("postgresql://", message)
        else:
            self.fail("expected a refusal")


class RuntimePairingTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("FINANCE_DEV_DSN", "FINANCE_CORE_DSN")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def pair(self, finance, core):
        os.environ["FINANCE_DEV_DSN"] = finance
        os.environ["FINANCE_CORE_DSN"] = core

    def test_finance_and_core_may_not_sit_on_opposite_servers(self):
        # Every request would be answered, and answered against a Core that knows nothing
        # about the data being returned. No error, and a wrong answer.
        self.pair(dsn(CENTRAL, "bambo_canonical_local"),
                  dsn("127.0.0.1", "bambo_finance_rc", 5440))
        with self.assertRaises(env.MissingConfiguration):
            env.check_runtime_pairing()

    def test_both_on_the_central_database_is_permitted(self):
        self.pair(dsn(CENTRAL, "bambo_canonical_local"), dsn(CENTRAL, "bambo_canonical_local"))
        env.check_runtime_pairing()

    def test_both_local_is_permitted(self):
        self.pair(dsn("127.0.0.1", "bambo_finance_rc", 5440),
                  dsn("127.0.0.1", "bambo_finance_rc", 5440))
        env.check_runtime_pairing()

    def test_no_core_database_configured_is_not_a_pairing_error(self):
        os.environ["FINANCE_DEV_DSN"] = dsn("127.0.0.1", "bambo_finance_rc", 5440)
        os.environ.pop("FINANCE_CORE_DSN", None)
        env.check_runtime_pairing()


if __name__ == "__main__":
    unittest.main()
