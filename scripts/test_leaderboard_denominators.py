"""Regression tests for pooled freshness observation denominators."""

from __future__ import annotations

import unittest

from export_llm_judged_snapshot import leaderboard


def run(snapshot: str) -> dict:
    return {
        "case_slug": "same-company",
        "provider_slug": "example",
        "provider_name": "Example",
        "snapshot": snapshot,
        "status": "ok",
        "normalized": {
            "latest_stage": "Series A",
            "latest_date": None,
            "latest_amount": None,
            "total_raised": None,
            "round_count": None,
        },
        "metrics": {
            "stage_eligible": 1,
            "stage_returned": 1,
            "stage_correct": 1,
            "llm_judge": {"reason": "match", "decision_basis": "stage"},
        },
    }


class LeaderboardDenominatorTest(unittest.TestCase):
    def test_same_company_in_two_snapshots_counts_as_two_observations(self) -> None:
        row = leaderboard([run("freshness-a"), run("freshness-b")])[0]
        self.assertEqual(row["case_count"], 2)
        self.assertEqual(row["total_cases"], 2)
        self.assertEqual(row["cases_attempted"], 2)
        self.assertEqual(row["snapshot_count"], 2)


if __name__ == "__main__":
    unittest.main()
