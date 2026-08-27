"""Offline contract tests for collision-safe public freshness paths."""

from __future__ import annotations

import unittest

from export_llm_judged_snapshot import freshness_label


class FreshnessLabelTest(unittest.TestCase):
    def test_preserves_legacy_month_snapshot_path(self) -> None:
        self.assertEqual(
            freshness_label({"slug": "company-funding-freshness-2026-08"}),
            "2026-08",
        )

    def test_uses_full_date_for_new_snapshot(self) -> None:
        self.assertEqual(
            freshness_label({"slug": "company-funding-freshness-2026-08-26"}),
            "2026-08-26",
        )

    def test_rejects_undated_slug(self) -> None:
        with self.assertRaises(RuntimeError):
            freshness_label({"slug": "company-funding-freshness-latest"})


if __name__ == "__main__":
    unittest.main()
