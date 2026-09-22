# -*- coding: utf-8 -*-
"""A setting is trimmed whichever source it came from.

WHY THIS FILE EXISTS

`.env` on Windows has CRLF endings. Sourcing it into a shell --
`eval "$(grep ... .env)"` -- puts the carriage return INTO the variable, and the process
then holds a value one character longer than the file shows. `load_env_file` has always
trimmed; the `os.environ` branch of `setting` did not, so which source a value arrived
from decided whether it was clean.

What that looked like in practice: the AvalAI key carried a trailing `\r`, the provider
built `Authorization: Bearer <key>\r`, and urllib refused it with

    ValueError: Invalid header value b'Bearer aa-...'

three layers away from the `.env` line responsible, and reported to the operator as a
generic "provider did not answer". A valid key looked like a rejected one.
"""

import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from devhost.environment import setting

NAME = "FINANCE_TEST_SETTING_WHITESPACE"


class EnvironmentValueTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(NAME)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(NAME, None)
        else:
            os.environ[NAME] = self._saved

    def test_a_carriage_return_from_a_crlf_env_file_is_trimmed(self):
        os.environ[NAME] = "aa-secret-value\r"
        self.assertEqual("aa-secret-value", setting(NAME))

    def test_trailing_and_leading_whitespace_is_trimmed(self):
        os.environ[NAME] = "  postgresql://host/db \t"
        self.assertEqual("postgresql://host/db", setting(NAME))

    def test_a_clean_value_is_unchanged(self):
        os.environ[NAME] = "self_hosted"
        self.assertEqual("self_hosted", setting(NAME))

    def test_an_absent_name_still_falls_through_to_the_default(self):
        os.environ.pop(NAME, None)
        self.assertEqual("fallback", setting(NAME, "fallback"))

    def test_the_trimmed_value_is_usable_as_an_http_header(self):
        """The exact failure: urllib refuses a header value containing a carriage return."""
        import urllib.request

        os.environ[NAME] = "aa-secret-value\r"
        request = urllib.request.Request("https://example.invalid/")
        # Unstripped, this raises ValueError. Through `setting` it must not.
        request.add_header("Authorization", "Bearer %s" % setting(NAME))
        self.assertEqual("Bearer aa-secret-value", request.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
