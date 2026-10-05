"""Contract tests for the two Tako Answer funding arms (no API calls).

Tako's Answer API runs at two efforts, so effort has to be the only thing that
differs between the arms. Both must also send the shared instruction and output
schema verbatim, or the comparison with the other vendors stops meaning
anything.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from funding import run_structured_web_research as runner


CASE = {
    "candidate_id": "contract-case",
    "company_name": "Example Company",
    "company_domain": "example.com",
    # Reference columns ride along in the real CSV row. None of them may ever
    # reach a provider request.
    "ground_truth_stage": "Series B",
    "ground_truth_announced_on": "2026-01-15",
    "ground_truth_amount": "45000000",
}

VALUE = {
    "latest_stage": "Series B",
    "latest_announced_on": "2026-01-15",
    "latest_amount": 45_000_000,
    "currency": "USD",
    "total_raised": 60_000_000,
    "funding_round_count": 3,
}

# The shapes the API sends: internal_error fires after the answer is written,
# so the answer and cards still ship; arbiter_failed leaves the answer empty.
INTERNAL_ERROR = {
    "answer": "It raised a Series B.",
    "cards": [{"id": "c1"}],
    "structured_output_error": {"code": "internal_error", "message": "Tako couldn't check the filled output against your schema."},
}
ARBITER_FAILED = {
    "answer": "",
    "structured_output_error": {"code": "arbiter_failed", "message": "No answer was generated for this query, so the schema wasn't filled."},
}


class TakoAnswerEffortParity(unittest.TestCase):
    def test_effort_is_the_only_difference(self) -> None:
        fast = runner.tako_answer_payload(CASE, "fast")
        deep = runner.tako_answer_payload(CASE, "deep")
        self.assertEqual(fast["effort"], "fast")
        self.assertEqual(deep["effort"], "deep")
        del fast["effort"], deep["effort"]
        self.assertEqual(fast, deep, "Tako arms diverge beyond effort")

    def test_query_matches_the_shared_instruction(self) -> None:
        for effort in runner.TAKO_ANSWER_EFFORTS:
            self.assertEqual(runner.tako_answer_payload(CASE, effort)["query"], runner.instruction(CASE))

    def test_both_arms_send_the_shared_output_schema(self) -> None:
        for effort in runner.TAKO_ANSWER_EFFORTS:
            self.assertIs(runner.tako_answer_payload(CASE, effort)["output_schema"], runner.OUTPUT_SCHEMA)

    def test_no_reference_data_reaches_the_request(self) -> None:
        for effort in runner.TAKO_ANSWER_EFFORTS:
            blob = json.dumps(runner.tako_answer_payload(CASE, effort))
            for leak in ("Series B", "2026-01-15", "45000000", "ground_truth"):
                self.assertNotIn(leak, blob)

    def test_registered_arms_send_their_own_effort(self) -> None:
        sent = {}

        def fake(url, headers, payload=None, timeout=180):
            sent[payload["effort"]] = payload
            return {"structured_output": VALUE}

        with patch.dict("os.environ", {"TAKO_API_KEY": "test-key"}), patch.object(runner, "request_json", fake):
            for effort in runner.TAKO_ANSWER_EFFORTS:
                runner.PROVIDERS[f"tako-answer-{effort}"](CASE)
        self.assertEqual(set(sent), set(runner.TAKO_ANSWER_EFFORTS))
        for effort in runner.TAKO_ANSWER_EFFORTS:
            self.assertEqual(runner.REQUIRED_ENV[f"tako-answer-{effort}"], "TAKO_API_KEY")


class TakoAnswerEnvelope(unittest.TestCase):
    def _run(self, response: dict):
        def fake(url, headers, payload=None, timeout=180):
            self.assertEqual(headers["X-API-Key"], "test-key")
            # Without it Cloudflare 403s every call (error 1010).
            self.assertNotIn("Python-urllib", headers.get("User-Agent", "Python-urllib"))
            return response

        with patch.dict("os.environ", {"TAKO_API_KEY": "test-key"}), patch.object(runner, "request_json", fake):
            return runner.tako_answer(CASE, effort="fast")

    def test_structured_output_is_the_normalized_result(self) -> None:
        normalized, raw = self._run({"answer": "It raised a Series B.", "structured_output": VALUE, "usage": {"total_cost_usd": 0.01}})
        self.assertEqual(normalized, VALUE)
        self.assertEqual(raw["answer"], "It raised a Series B.")
        self.assertEqual(raw["usage"], {"total_cost_usd": 0.01})
        self.assertEqual(raw["_request_effort"], "fast")

    def test_an_answer_without_structured_output_is_recorded_verbatim(self) -> None:
        error = {"code": "validation_failed", "message": "x"}
        normalized, raw = self._run({"answer": "It raised a Series B.", "structured_output_error": error})
        self.assertEqual(normalized, {"unparsed_text": "It raised a Series B."})
        self.assertEqual(raw["structured_output_error"], error)

    def test_arbiter_failed_and_internal_error_are_errors(self) -> None:
        for response in (ARBITER_FAILED, INTERNAL_ERROR):
            code = response["structured_output_error"]["code"]
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                self._run(response)

    def test_validation_failed_without_an_answer_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "validation_failed"):
            self._run({"answer": "", "structured_output_error": {"code": "validation_failed", "message": "x"}})


class TakoAnswerSavedRow(unittest.TestCase):
    """The board reads the row run_one saves, so pin its status and raw per outcome."""

    def _save(self, response: dict) -> dict:
        with tempfile.TemporaryDirectory() as raw_dir, patch.dict("os.environ", {"TAKO_API_KEY": "test-key"}), patch.object(
            runner, "request_json", lambda *args, **kwargs: response
        ):
            runner.run_one("tako-answer-fast", CASE, Path(raw_dir))
            return json.loads(runner.output_path("tako-answer-fast", CASE, Path(raw_dir)).read_text())

    def test_structured_output_saves_an_ok_row(self) -> None:
        row = self._save({"answer": "It raised a Series B.", "structured_output": VALUE})
        self.assertEqual((row["status"], row["normalized"]), ("ok", VALUE))

    def test_validation_failed_saves_an_ok_row_that_keeps_the_answer_and_error(self) -> None:
        error = {"code": "validation_failed", "message": "x"}
        row = self._save({"answer": "It raised a Series B.", "cards": [{"id": "c1"}], "structured_output_error": error})
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["normalized"], {"unparsed_text": "It raised a Series B."})
        self.assertEqual(row["raw"]["structured_output_error"], error)
        self.assertEqual(row["raw"]["cards"], [{"id": "c1"}])

    def test_arbiter_failed_and_internal_error_save_error_rows_naming_the_code(self) -> None:
        for response in (ARBITER_FAILED, INTERNAL_ERROR):
            code = response["structured_output_error"]["code"]
            with self.subTest(code=code):
                row = self._save(response)
                self.assertEqual(row["status"], "error")
                self.assertIn(code, row["failure_reason"])


if __name__ == "__main__":
    unittest.main()
