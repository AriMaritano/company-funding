"""Offline contract tests for the Fundable funding adapter."""

from __future__ import annotations

import unittest

from funding import run_funding_benchmark as runner
from funding import smoke_test_funding_providers as smoke


def raw(company: dict | None) -> dict:
    return {
        "http_status": 200,
        "response": {"data": {"company": company}},
        "latency_ms": 12,
    }


class FundableContractTest(unittest.TestCase):
    def test_provider_is_registered_and_rate_limited(self) -> None:
        required, call = smoke.PROVIDERS["fundable"]
        self.assertEqual(required, ("FUNDABLE_API_KEY",))
        self.assertIs(call, smoke.fundable)
        self.assertGreater(runner.MIN_START_INTERVAL_SECONDS["fundable"], 0)

    def test_normalizes_latest_deal(self) -> None:
        response = raw({
            "latest_deal": {
                "type": "Series A",
                "pre": True,
                "date": "2026-08-20",
                "total_round_raised": 12_000_000,
            },
            "total_raised": 15_000_000,
            "num_funding_rounds": 3,
        })
        self.assertEqual(runner.status_for("fundable", response), ("ok", None))
        self.assertEqual(runner.normalize("fundable", response), {
            "latest_stage": "pre Series A",
            "latest_date": "2026-08-20",
            "latest_amount": 12_000_000,
            "total_raised": 15_000_000,
            "round_count": 3,
        })

    def test_empty_company_is_not_found(self) -> None:
        self.assertEqual(
            runner.status_for("fundable", raw(None)),
            ("not_found", "no company"),
        )


if __name__ == "__main__":
    unittest.main()
