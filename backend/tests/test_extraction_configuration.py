# -*- coding: utf-8 -*-
"""How the extraction providers get their configuration, and how they fail without it.

THE BUG THIS PINS

`devhost.environment.setting()` reads the process environment first and `.env` behind it.
The extraction providers cannot use it -- `extraction/` is the lower layer and importing a
devhost accessor into it would invert the dependency -- so they read `os.environ` directly.
A host started without an explicit export therefore had `AVALAI_API_KEY` in its `.env`,
`setting()` able to see it, and `build_extraction_provider()` returning None.

It failed silently in the worst way: both AI extraction and speech degrade by design
rather than raising, so the host served every endpoint and produced drafts with no
structuring, with nothing in the answer saying why.

`export_env_file()` closes it at the composition root. These tests pin that it does, that
it never overrides a deliberate export, and that it never hands back a secret.
"""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from devhost import environment
from extraction.providers import llm_invoice
from extraction.providers.avalai_speech import AvalAISpeechProvider, DEFAULT_MODEL

#: Never a real key. Long enough to be recognisable in a diff if one ever leaks into a log.
FAKE_KEY = "test-only-not-a-real-key-0000"

MANAGED = ("AVALAI_API_KEY", "FINANCE_AI_API_KEY", "AVALAI_MODEL", "FINANCE_AI_MODEL",
           "FINANCE_AI_PROVIDER", "FINANCE_AI_EXTRACTION_ENABLED", "AVALAI_BASE_URL",
           "FINANCE_STT_PROVIDER", "FINANCE_STT_MODEL")


class EnvironmentCase(unittest.TestCase):
    """Every name this suite touches is restored, so one test cannot configure another."""

    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in MANAGED}
        for name in MANAGED:
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def write_env(self, text):
        """A throwaway `.env`, with `environment.ENV_FILE` pointed at it."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / ".env"
        io.open(path, "w", encoding="utf-8").write(text)
        original = environment.ENV_FILE
        environment.ENV_FILE = path
        self.addCleanup(lambda: setattr(environment, "ENV_FILE", original))
        return path


class ExportingTheEnvFileTests(EnvironmentCase):
    def test_a_name_in_the_file_reaches_os_environ(self):
        self.write_env("AVALAI_API_KEY=%s\nFINANCE_AI_PROVIDER=avalai\n" % FAKE_KEY)
        added = environment.export_env_file()
        self.assertIn("AVALAI_API_KEY", added)
        self.assertEqual(FAKE_KEY, os.environ["AVALAI_API_KEY"],
                         "the provider reads os.environ and now finds it")

    def test_a_deliberate_export_is_never_overwritten(self):
        # Same precedence `setting()` applies. An operator who exported something meant it.
        os.environ["FINANCE_AI_PROVIDER"] = "openai"
        self.write_env("FINANCE_AI_PROVIDER=avalai\n")
        added = environment.export_env_file()
        self.assertEqual("openai", os.environ["FINANCE_AI_PROVIDER"])
        self.assertNotIn("FINANCE_AI_PROVIDER", added)

    def test_it_returns_names_and_never_values(self):
        self.write_env("AVALAI_API_KEY=%s\n" % FAKE_KEY)
        added = environment.export_env_file()
        self.assertEqual(("AVALAI_API_KEY",), added)
        for name in added:
            self.assertNotIn(FAKE_KEY, name, "a value must never travel with a name")

    def test_no_file_is_not_an_error(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        original = environment.ENV_FILE
        environment.ENV_FILE = Path(directory.name) / "absent.env"
        self.addCleanup(lambda: setattr(environment, "ENV_FILE", original))
        self.assertEqual((), environment.export_env_file())

    def test_the_host_prints_names_only(self):
        import inspect

        from devhost import __main__ as entry

        source = inspect.getsource(entry.main)
        self.assertIn("export_env_file()", source)
        self.assertIn('", ".join(exported)', source,
                      "the NAMES are printed; a value would be a credential in a log")


class InvoiceReaderConfigurationTests(EnvironmentCase):
    def test_absent_configuration_disables_the_reader_without_raising(self):
        self.assertIsNone(llm_invoice.build_extraction_provider(),
                          "an unconfigured host extracts without a second opinion")

    def test_the_switch_alone_is_not_enough(self):
        os.environ["FINANCE_AI_EXTRACTION_ENABLED"] = "true"
        os.environ["FINANCE_AI_PROVIDER"] = "avalai"
        self.assertIsNone(llm_invoice.build_extraction_provider(),
                          "no key, so nothing is built")

    def test_a_complete_configuration_builds_the_reader(self):
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "avalai",
                           "AVALAI_API_KEY": FAKE_KEY,
                           "AVALAI_MODEL": "gemini-2.5-flash-lite"})
        provider = llm_invoice.build_extraction_provider()
        self.assertIsNotNone(provider)
        # The private attributes on purpose: this is a configuration test, and what it has
        # to prove is that the value an operator set is the value the provider will send.
        self.assertEqual("gemini-2.5-flash-lite", provider._model)
        self.assertEqual("avalai", provider.provider)

    def test_the_page_model_is_configurable_separately_from_the_text_one(self):
        # They are different tasks and the right answer differs. On page2.jpg the measured
        # spread was total: three models read all 18 monetary fields correctly and gpt-4o
        # read none of them, so a host that cannot name its page model cannot be corrected.
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "avalai",
                           "AVALAI_API_KEY": FAKE_KEY,
                           "AVALAI_MODEL": "gpt-4o-mini",
                           "FINANCE_AI_VISION_MODEL": "gemini-2.5-flash-lite"})
        provider = llm_invoice.build_extraction_provider()
        self.assertEqual("gpt-4o-mini", provider._model, "text stays as configured")
        self.assertEqual("gemini-2.5-flash-lite", provider._vision_model)

    def test_the_vendor_specific_page_model_wins(self):
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "avalai",
                           "AVALAI_API_KEY": FAKE_KEY,
                           "AVALAI_VISION_MODEL": "gemini-2.5-flash",
                           "FINANCE_AI_VISION_MODEL": "gemini-2.5-flash-lite"})
        self.assertEqual("gemini-2.5-flash",
                         llm_invoice.build_extraction_provider()._vision_model)

    def test_the_page_model_reaches_the_request(self):
        # Configuring it is only half the claim; the other half is that it is what gets
        # sent when a page is in hand.
        sent = {}

        def post(url, payload, key, timeout):
            sent.update(payload)
            return 200, b'{"choices":[{"message":{"content":"{}"}}]}'

        provider = llm_invoice.LLMInvoiceExtractionProvider(
            key=FAKE_KEY, model="text-model", vision_model="page-model",
            post=post, sleep=lambda _s: None)
        try:
            provider.extract_invoice("text", {}, image=bytes([0xFF, 0xD8, 0xFF]),
                                     media_type="image/jpeg")
        except Exception:                                   # noqa: BLE001 - shape only
            pass
        self.assertEqual("page-model", sent.get("model"))

    def test_the_finance_wide_key_is_accepted_as_a_fallback(self):
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "avalai",
                           "FINANCE_AI_API_KEY": FAKE_KEY})
        self.assertIsNotNone(llm_invoice.build_extraction_provider(),
                             "a host configuring every provider through one name works")

    def test_the_vendor_key_wins_over_the_finance_wide_one(self):
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "avalai",
                           "AVALAI_API_KEY": FAKE_KEY,
                           "FINANCE_AI_API_KEY": "the-other-one"})
        provider = llm_invoice.build_extraction_provider()
        self.assertEqual(FAKE_KEY, provider._key)

    def test_an_unsupported_provider_is_refused_rather_than_guessed(self):
        os.environ.update({"FINANCE_AI_EXTRACTION_ENABLED": "true",
                           "FINANCE_AI_PROVIDER": "a-gateway-nobody-added",
                           "AVALAI_API_KEY": FAKE_KEY})
        self.assertIsNone(llm_invoice.build_extraction_provider())

    def test_the_adapter_names_no_model_in_its_code(self):
        """Checked against the CODE, not the text.

        `adapters.py` mentions gpt-4o in a COMMENT recording measured token counts, which
        is evidence and belongs there. What must not exist is a model name the adapter can
        actually send. Comments are absent from the AST, so scanning string constants
        separates the two exactly.
        """
        import ast

        tree = ast.parse(io.open(BACKEND_ROOT / "extraction" / "adapters.py",
                                 encoding="utf-8").read())
        docstrings = {id(ast.get_docstring(n, clean=False))
                      for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))}
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n.value) not in docstrings]
        # Names that would be SENT to an API. `whisper-local` is deliberately not among
        # them: it is the local adapter's own name, which is provenance written onto the
        # draft, not a model anybody selected.
        for model in ("gemini", "gpt-4o", "gpt-5", "claude-", "groq."):
            with self.subTest(model=model):
                named = [v for v in literals if model in v.lower()]
                self.assertEqual([], named,
                                 "the adapter must not name a model; configuration does")


class SpeechConfigurationTests(EnvironmentCase):
    def test_the_default_model_applies_when_nothing_names_one(self):
        self.assertEqual(DEFAULT_MODEL, AvalAISpeechProvider(api_key=FAKE_KEY).model)

    def test_the_environment_overrides_the_default(self):
        os.environ["FINANCE_STT_MODEL"] = "groq.whisper-large-v3"
        self.assertEqual("groq.whisper-large-v3", AvalAISpeechProvider(api_key=FAKE_KEY).model)

    def test_an_explicit_argument_overrides_the_environment(self):
        os.environ["FINANCE_STT_MODEL"] = "groq.whisper-large-v3"
        self.assertEqual("other",
                         AvalAISpeechProvider(api_key=FAKE_KEY, model="other").model)

    def test_a_key_in_the_environment_configures_the_provider(self):
        os.environ["AVALAI_API_KEY"] = FAKE_KEY
        self.assertTrue(AvalAISpeechProvider().configured)

    def test_the_finance_wide_key_is_accepted_here_too(self):
        os.environ["FINANCE_AI_API_KEY"] = FAKE_KEY
        self.assertTrue(AvalAISpeechProvider().configured)

    def test_no_key_means_not_configured_rather_than_a_crash(self):
        self.assertFalse(AvalAISpeechProvider().configured)

    def test_the_local_provider_remains_the_default_choice(self):
        # The fallback must stay: a host that upgrades and changes no setting transcribes
        # exactly as it did yesterday.
        from devhost.app import speech_provider

        self.assertEqual((), speech_provider(), "nothing set -> local Whisper, as before")
        os.environ["FINANCE_STT_PROVIDER"] = "something-else"
        self.assertEqual((), speech_provider())

    def test_naming_avalai_selects_the_hosted_provider(self):
        from devhost.app import speech_provider

        os.environ["FINANCE_STT_PROVIDER"] = "avalai"
        os.environ["AVALAI_API_KEY"] = FAKE_KEY
        provider, adapter_name = speech_provider()
        self.assertEqual("avalai-speech", adapter_name)
        self.assertIsInstance(provider, AvalAISpeechProvider)


class NoSecretLeaksTests(EnvironmentCase):
    def test_the_speech_provider_reports_presence_and_never_the_key(self):
        os.environ["AVALAI_API_KEY"] = FAKE_KEY
        provider = AvalAISpeechProvider()
        self.assertTrue(provider.configured)
        self.assertNotIn(FAKE_KEY, repr(provider.configured))
        self.assertNotIn(FAKE_KEY, str(provider.model))

    def test_the_host_banner_says_present_or_missing(self):
        import inspect

        from devhost import app

        source = inspect.getsource(app.speech_provider)
        self.assertIn('"PRESENT" if provider.configured else "MISSING"', source)

    def test_no_credential_is_assigned_a_literal_anywhere_in_the_backend(self):
        """No `API_KEY = "..."` in the source, whatever the vendor's prefix happens to be.

        Checked structurally rather than by scanning for a prefix: `aa-` and `sk-` both
        occur in ordinary text -- every `aaaaaaaa-aaaa-` test UUID contains the first --
        so a prefix scan is noise that gets muted. What matters is that nothing NAMED like
        a credential is ever bound to a hard-coded string.
        """
        import ast

        offenders = []
        # `API_KEY` and not bare `KEY`: `SERVICE_KEY_HEADER` and `HOST_FILE_VERSION_KEY`
        # are the NAMES of a header and of a dictionary key, and flagging those would make
        # this test noise that somebody eventually mutes.
        secretish = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD")
        exempt = ("_HEADER", "_SETTING", "_NAME", "_NAMES", "_ENV", "_PREFIX")
        for folder in ("extraction", "devhost", "app"):
            for path in (BACKEND_ROOT / folder).rglob("*.py"):
                tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Assign):
                        continue
                    if not (isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)
                            and len(node.value.value) >= 16):
                        continue
                    for target in node.targets:
                        name = getattr(target, "id", "") or getattr(target, "attr", "")
                        upper = name.upper()
                        if upper.endswith(exempt):
                            continue
                        if any(word in upper for word in secretish):
                            offenders.append("%s:%d %s" % (path.name, node.lineno, name))
        self.assertEqual([], offenders)

    def test_the_names_of_the_variables_are_in_the_source_but_nothing_else(self):
        # The provider must name which variables an operator should set -- that is how
        # somebody configures it -- while never carrying a value.
        text = io.open(BACKEND_ROOT / "extraction" / "providers" / "avalai_speech.py",
                       encoding="utf-8").read()
        self.assertIn("AVALAI_API_KEY", text)
        self.assertIn("FINANCE_AI_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
