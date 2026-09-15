import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .settings import (
    get_non_negative_int_env,
    get_positive_float_env,
)


class OpenAIEnvironmentSettingTests(SimpleTestCase):
    def test_positive_timeout_is_parsed(self):
        with patch.dict(
            os.environ,
            {"TEST_OPENAI_TIMEOUT": "12.5"},
        ):
            value = get_positive_float_env(
                "TEST_OPENAI_TIMEOUT",
                default=30,
            )

        self.assertEqual(value, 12.5)

    def test_non_positive_timeout_is_rejected(self):
        for invalid_value in ("0", "-1", "invalid"):
            with self.subTest(value=invalid_value), patch.dict(
                os.environ,
                {"TEST_OPENAI_TIMEOUT": invalid_value},
            ):
                with self.assertRaises(ImproperlyConfigured):
                    get_positive_float_env(
                        "TEST_OPENAI_TIMEOUT",
                        default=30,
                    )

    def test_non_negative_retry_count_is_parsed(self):
        with patch.dict(
            os.environ,
            {"TEST_OPENAI_MAX_RETRIES": "0"},
        ):
            value = get_non_negative_int_env(
                "TEST_OPENAI_MAX_RETRIES",
                default=1,
            )

        self.assertEqual(value, 0)

    def test_invalid_retry_count_is_rejected(self):
        for invalid_value in ("-1", "1.5", "invalid"):
            with self.subTest(value=invalid_value), patch.dict(
                os.environ,
                {"TEST_OPENAI_MAX_RETRIES": invalid_value},
            ):
                with self.assertRaises(ImproperlyConfigured):
                    get_non_negative_int_env(
                        "TEST_OPENAI_MAX_RETRIES",
                        default=1,
                    )
