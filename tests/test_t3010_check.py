"""Tests for the T3010 Pre-Flight Checker.

Every expected total and date in this file is computed by hand in the
comments, from the CRA's published T3010 (24) form structure, the T4033
guide and the CRA's T3010 checklist (sources checked 2026-11-04).

Faulty fixture hand count (examples/faulty-return.json):
  ERRORS (22)
    registration_number_format  1  (12345678RR001: 8 digits, 3-digit ref)
    programs_missing            1  (C2 blank)
    schedule_missing            4  (Schedules 1, 2, 3, 5)
    worksheet_missing           2  (T1236, T1441)
    financial_statements_missing 1
    required_missing            3  (line 5045; director #2 DOB + postal)
    subtotal_mismatch           1  (4570: 20000+10000+0=30000, shows 25000)
    total_mismatch              3  (revenue: components add to 147800,
                                    shows 147500; breakdown adds to
                                    151900, shows 4950=152000; line 5100:
                                    152000+0+9000=161000, shows 158300)
    receipts_mismatch           1  (register 94000.00 vs line 4500 95000)
    statements_mismatch         2  (revenue 147800 vs 147500;
                                    assets 210000 vs 4200 410000)
    director_dates              1  (director #4 starts after period end)
    certification_unsigned      1
    late_filing                 1  (due 2025-09-30, filed 2025-11-15:
                                    31 days in October + 15 = 46 days late)
  WARNINGS (4)
    memo_exceeds                1  (4520 9000 > its parent 4510 8000)
    nal_director_prompt         1  (director #4 not at arm's length, C8 no)
    director_not_serving        1  (director #3 ceased 2023-06-30, before
                                    the 2024-04-01 period start)
    schedule_trigger            1  (C17 yes, Schedule 8 not included;
                                    T2081 is marked included, so it does
                                    not add a second warning)
  INFO (0) — a late filing replaces the deadline note with the error.

Clean fixture hand count (examples/clean-return.json):
  revenue 48250+5000+3200+12000+4500+1500+250 = 74700 = line 4700
  expenditures 2400+1100+58900 = 62400 = line 4950
  breakdown 52100+6800+2900+0+600 = 62400 = line 4950
  total 62400+0+6000 = 68400 = line 5100
  T1236 rows 4000+2000 = 6000 = line 5050
  deadline: 2025-12-31 + 6 months = 2026-06-30; filed 2026-03-20
  -> 0 errors, 0 warnings, 1 info (the deadline note).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
SRC = PACK / "src" / "t3010_check.py"
EXAMPLES = PACK / "examples"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True, cwd=PACK)


def check_payload(data, as_of="2026-01-15"):
    with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False) as handle:
        json.dump(data, handle)
        path = handle.name
    try:
        proc = run_cli("check", path, "--as-of", as_of, "--json")
    finally:
        Path(path).unlink(missing_ok=True)
    return proc


def parse(proc):
    return json.loads(proc.stdout)


def rules(payload, rule):
    return [f for f in payload["findings"] if f["rule"] == rule]


def base_data():
    """A minimal return whose only notes are the two unverifiable
    totals (no component lines supplied) and the deadline note."""
    return {
        "charity": {
            "name": "Test Charity",
            "registration_number": "123456789RR0001",
            "designation": "charitable organization",
            "fiscal_period_start": "2025-01-01",
            "fiscal_period_end": "2025-12-31",
        },
        "financials": {
            "mode": "section_d",
            "basis": "accrual",
            "lines": {
                "4200": 1000, "4350": 100, "4700": 1000, "4950": 800,
                "5000": 700, "5010": 100, "5020": 0, "5030": 0,
                "5040": 0, "5100": 800,
            },
        },
        "section_c": {
            "active": True,
            "programs_description": "Runs a community reading program.",
            "wound_up": False,
            "subordinate_to_head_body": False,
            "gifts_to_qualified_donees": False,
            "activities_outside_canada": False,
            "paid_external_fundraisers": False,
            "director_or_nal_compensation": False,
            "employee_compensation": False,
            "foreign_donations_10000": False,
            "non_cash_gifts_receipted": False,
            "grants_to_grantees": False,
            "grantees_over_5000": False,
            "disbursement_quota_property": False,
        },
        "attachments": {
            "financial_statements_included": True,
            "t1235_included": True,
            "t1236_included": False,
            "t1441_included": False,
            "t2081_included": False,
            "schedule_1_included": False,
            "schedule_2_included": False,
            "schedule_3_included": False,
            "schedule_5_included": False,
            "schedule_8_included": False,
        },
        "directors": [{
            "name": "Test Director",
            "position": "Chair",
            "start_date": "2023-01-01",
            "date_of_birth": "1980-01-01",
            "arms_length": True,
            "postal_code": "V1Y 1A1",
        }],
        "certification": {"signed": True,
                          "signature_date": "2026-01-10"},
    }


def schedule6_data():
    """Schedule 6 figures, hand-added:
    assets 700+300=1000=4200; liabilities 60+40=100=4350;
    revenue 600+400=1000=4700; expenditures 100+700=800=4950."""
    data = base_data()
    data["financials"]["mode"] = "schedule_6"
    data["financials"]["lines"].update({
        "4100": 700, "4110": 300,
        "4300": 60, "4330": 40,
        "4500": 600, "4510": 400,
        "4800": 100, "4880": 700,
    })
    return data


class TestExampleFixtures(unittest.TestCase):
    def test_clean_json_passes(self):
        proc = run_cli("check", str(EXAMPLES / "clean-return.json"),
                       "--as-of", "2026-03-20", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = parse(proc)
        self.assertEqual(payload["verdict"], "PASS")
        self.assertEqual(payload["summary"],
                         {"errors": 0, "warnings": 0, "info": 1})
        self.assertEqual(payload["deadline"]["due_date"], "2026-06-30")
        self.assertEqual(payload["deadline"]["status"], "filed_on_time")
        # filed 2026-03-20; Mar 20 -> Jun 30 is 11+30+31+30 = 102 days
        self.assertIn("102 days before the deadline",
                      payload["findings"][0]["message"])

    def test_clean_csv_passes_with_detail_note(self):
        proc = run_cli("check", str(EXAMPLES / "clean-return.csv"),
                       "--as-of", "2026-03-20", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = parse(proc)
        self.assertEqual(payload["summary"]["errors"], 0)
        self.assertEqual(payload["summary"]["warnings"], 0)
        # deadline note + T1235 rows not carried by CSV (skipped, noted)
        self.assertEqual(payload["summary"]["info"], 2)
        self.assertEqual(
            len(rules(payload, "worksheet_detail_unchecked")), 1)

    def test_faulty_json_exact_counts(self):
        proc = run_cli("check", str(EXAMPLES / "faulty-return.json"),
                       "--as-of", "2025-11-15", "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        payload = parse(proc)
        self.assertEqual(payload["verdict"], "FAIL")
        self.assertEqual(payload["summary"],
                         {"errors": 22, "warnings": 4, "info": 0})
        counts = Counter(f["rule"] for f in payload["findings"])
        self.assertEqual(counts, Counter({
            "registration_number_format": 1,
            "programs_missing": 1,
            "schedule_missing": 4,
            "worksheet_missing": 2,
            "financial_statements_missing": 1,
            "required_missing": 3,
            "subtotal_mismatch": 1,
            "total_mismatch": 3,
            "receipts_mismatch": 1,
            "statements_mismatch": 2,
            "director_dates": 1,
            "certification_unsigned": 1,
            "late_filing": 1,
            "memo_exceeds": 1,
            "nal_director_prompt": 1,
            "director_not_serving": 1,
            "schedule_trigger": 1,
        }))
        self.assertEqual(payload["deadline"]["due_date"], "2025-09-30")
        self.assertEqual(payload["deadline"]["status"], "filed_late")
        late = rules(payload, "late_filing")[0]
        self.assertIn("46 days after the deadline", late["message"])

    def test_text_output_groups_and_disclaimer(self):
        proc = run_cli("check", str(EXAMPLES / "faulty-return.json"),
                       "--as-of", "2025-11-15")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Verdict: FAIL — 22 error(s), 4 warning(s)",
                      proc.stdout)
        self.assertIn("ERRORS (22):", proc.stdout)
        self.assertIn("WARNINGS (4):", proc.stdout)
        self.assertIn("not tax or legal advice", proc.stdout)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)


class TestDeadlineMath(unittest.TestCase):
    # Hand-computed: +6 calendar months, day clamped to the month length.
    CASES = [
        ("2025-12-31", "2026-06-30"),   # CRA example: Dec 31 -> Jun 30
        ("2025-03-31", "2025-09-30"),   # CRA example: Mar 31 -> Sep 30
        ("2025-06-30", "2025-12-31"),   # CRA example: Jun 30 -> Dec 31
        ("2025-08-31", "2026-02-28"),   # Feb 2026 has 28 days
        ("2023-08-31", "2024-02-29"),   # Feb 2024 is a leap month
        ("2025-01-31", "2025-07-31"),   # no clamp needed
        ("2025-10-31", "2026-04-30"),   # April has 30 days
    ]

    def test_deadline_table(self):
        for year_end, due in self.CASES:
            with self.subTest(year_end=year_end):
                proc = run_cli("deadline", "--year-end", year_end,
                               "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(parse(proc)["due_date"], due)

    def test_deadline_statuses(self):
        proc = run_cli("deadline", "--year-end", "2025-12-31",
                       "--filed", "2026-06-30", "--json")
        result = parse(proc)
        self.assertEqual(result["status"], "filed_on_time")
        self.assertEqual(result["filed_late_by_days"], 0)
        proc = run_cli("deadline", "--year-end", "2025-12-31",
                       "--filed", "2026-07-01", "--json")
        result = parse(proc)
        self.assertEqual(result["status"], "filed_late")
        self.assertEqual(result["filed_late_by_days"], 1)
        proc = run_cli("deadline", "--year-end", "2025-12-31",
                       "--as-of", "2026-01-01", "--json")
        result = parse(proc)
        # Jan 1 -> Jun 30, 2026: 30+28+31+30+31+30 = 180 days remaining
        self.assertEqual(result["days_remaining"], 180)
        self.assertEqual(result["status"], "not_yet_due")

    def test_overdue_warning_and_info_directions(self):
        data = base_data()  # due 2026-06-30, not filed
        payload = parse(check_payload(data, as_of="2026-07-01"))
        self.assertEqual(len(rules(payload, "filing_overdue")), 1)
        payload = parse(check_payload(data, as_of="2026-06-30"))
        self.assertEqual(len(rules(payload, "filing_overdue")), 0)
        self.assertEqual(payload["deadline"]["status"], "not_yet_due")


class TestCompleteness(unittest.TestCase):
    def test_blank_name_and_bad_registration(self):
        data = base_data()
        data["charity"]["name"] = ""
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "required_missing")), 1)
        data = base_data()
        data["charity"]["registration_number"] = "12345678RR0001"
        payload = parse(check_payload(data))
        self.assertEqual(
            len(rules(payload, "registration_number_format")), 1)
        data = base_data()  # well-formed: 9 digits + RR + 4 digits
        payload = parse(check_payload(data))
        self.assertEqual(
            len(rules(payload, "registration_number_format")), 0)

    def test_required_line_blank(self):
        data = base_data()
        del data["financials"]["lines"]["5100"]
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "required_missing")
                 if f["field"] == "line 5100"]
        self.assertEqual(len(found), 1)

    def test_conditional_line_4500(self):
        data = base_data()
        data["financials"]["issued_receipts"] = True
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "required_missing")
                 if f["field"] == "line 4500"]
        self.assertEqual(len(found), 1)
        data["financials"]["issued_receipts"] = False
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "required_missing")
                 if f["field"] == "line 4500"]
        self.assertEqual(len(found), 0)

    def test_programs_and_certification(self):
        data = base_data()
        data["section_c"]["programs_description"] = "  "
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "programs_missing")), 1)
        data = base_data()
        data["certification"] = {"signed": False}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "certification_unsigned")), 1)
        data = base_data()
        data["certification"] = {"signed": True}  # no signature date
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "required_missing")
                 if "signature_date" in f["field"]]
        self.assertEqual(len(found), 1)

    def test_period_over_twelve_months_warns(self):
        data = base_data()
        data["charity"]["fiscal_period_start"] = "2024-01-01"
        data["charity"]["fiscal_period_end"] = "2025-01-02"  # 367 days
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "period_length")), 1)
        data = base_data()  # exactly one year: no warning
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "period_length")), 0)


class TestAttachmentsAndTriggers(unittest.TestCase):
    def test_foundation_schedule_1(self):
        data = base_data()
        data["charity"]["designation"] = "public foundation"
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "schedule_missing")
                 if "schedule_1" in f["field"]]
        self.assertEqual(len(found), 1)
        data["attachments"]["schedule_1_included"] = True
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_missing")), 0)

    def test_answer_driven_schedules(self):
        cases = [
            ("activities_outside_canada", "schedule_2_included",
             "schedule_missing"),
            ("employee_compensation", "schedule_3_included",
             "schedule_missing"),
            ("non_cash_gifts_receipted", "schedule_5_included",
             "schedule_missing"),
            ("paid_external_fundraisers", "schedule_4_included",
             "schedule_missing"),
            ("foreign_donations_10000", "schedule_4_included",
             "schedule_missing"),
            ("gifts_to_qualified_donees", "t1236_included",
             "worksheet_missing"),
            ("grantees_over_5000", "t1441_included", "worksheet_missing"),
        ]
        for question, attachment, rule in cases:
            with self.subTest(question=question):
                data = base_data()
                data["section_c"][question] = True
                payload = parse(check_payload(data))
                found = [f for f in rules(payload, rule)
                         if attachment in f["field"]]
                self.assertEqual(len(found), 1)
                data["attachments"][attachment] = True
                payload = parse(check_payload(data))
                found = [f for f in rules(payload, rule)
                         if attachment in f["field"]]
                self.assertEqual(len(found), 0)

    def test_schedule_8_and_t2081_are_warnings_only(self):
        data = base_data()
        data["section_c"]["disbursement_quota_property"] = True
        payload = parse(check_payload(data))
        found = rules(payload, "schedule_trigger")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        data["attachments"]["schedule_8_included"] = True
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_trigger")), 0)

        data = base_data()
        data["charity"]["designation"] = "private foundation"
        data["attachments"]["schedule_1_included"] = True
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "schedule_trigger")
                 if "t2081" in f["field"]]
        self.assertEqual(len(found), 1)
        data["attachments"]["t2081_included"] = True
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_trigger")), 0)

    def test_schedule_6_threshold_boundary(self):
        # exactly $100,000 of revenue: Section D is still allowed
        data = base_data()
        data["financials"]["lines"]["4700"] = 100000
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_6_required")), 0)
        # $100,001: Schedule 6 appears required
        data["financials"]["lines"]["4700"] = 100001
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_6_required")), 1)
        # the user's own Schedule-6-required flag does the same
        data = base_data()
        data["financials"]["schedule_6_required"] = True
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "schedule_6_required")), 1)


class TestCrossFooting(unittest.TestCase):
    def test_section_d_totals_both_directions(self):
        data = base_data()
        # revenue 600+400=1000; expenditures 300+100+400=800
        data["financials"]["lines"].update({
            "4500": 600, "4510": 400,
            "4860": 300, "4810": 100, "4920": 400})
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "total_mismatch")), 0)
        self.assertEqual(len(rules(payload, "total_unverifiable")), 0)
        data["financials"]["lines"]["4700"] = 999
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "total_mismatch")
                 if f["field"] == "line 4700"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["measured"], 999)
        self.assertEqual(found[0]["limit"], 1000)

    def test_breakdown_and_total_expenditures(self):
        data = base_data()
        data["financials"]["lines"]["5000"] = 650  # breakdown now 750
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "total_mismatch")
                 if f["field"] == "line 4950"]
        self.assertEqual(len(found), 1)
        data = base_data()
        data["financials"]["lines"]["5100"] = 900  # 800+0+0 is 800
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "total_mismatch")
                 if f["field"] == "line 5100"]
        self.assertEqual(len(found), 1)

    def test_unverifiable_total_is_info_not_error(self):
        payload = parse(check_payload(base_data()))
        found = rules(payload, "total_unverifiable")
        self.assertEqual(len(found), 2)  # revenue + expenditures
        self.assertTrue(all(f["severity"] == "info" for f in found))
        self.assertEqual(payload["summary"]["errors"], 0)

    def test_schedule_6_assets_liabilities_and_comp_tie(self):
        data = schedule6_data()
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "total_mismatch")), 0)
        data["financials"]["lines"]["4200"] = 1001
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "total_mismatch")
                 if f["field"] == "line 4200"]
        self.assertEqual(len(found), 1)
        # Schedule 3 line 390 carries into Schedule 6 line 4880
        data = schedule6_data()
        data["schedule_3"] = {"total_compensation": 700}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "total_mismatch")), 0)
        data["schedule_3"]["total_compensation"] = 701
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "total_mismatch")
                 if f["field"] == "schedule_3.total_compensation"]
        self.assertEqual(len(found), 1)

    def test_government_subtotal(self):
        data = schedule6_data()
        # add gov revenue 100+50+25=175; recorded 4570 says 100
        data["financials"]["lines"].update({
            "4540": 100, "4550": 50, "4560": 25, "4570": 100,
            "4700": 1175})
        payload = parse(check_payload(data))
        found = rules(payload, "subtotal_mismatch")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["limit"], 175)
        data["financials"]["lines"]["4570"] = 175
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "subtotal_mismatch")), 0)

    def test_memo_lines_and_amortization_sign(self):
        data = base_data()
        data["financials"]["lines"].update({"4500": 500, "4505": 600})
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "memo_exceeds")), 1)
        data["financials"]["lines"]["4505"] = 500
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "memo_exceeds")), 0)
        data = schedule6_data()
        data["financials"]["lines"]["4166"] = 50  # must be negative
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "amortization_sign")), 1)


class TestReceiptsAndStatements(unittest.TestCase):
    def test_receipt_register_tie(self):
        data = base_data()
        data["financials"]["issued_receipts"] = True
        data["financials"]["lines"]["4500"] = 5000
        data["receipts"] = {"eligible_total": "5000.00"}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "receipts_mismatch")), 0)
        data["receipts"] = {"eligible_total": "4999.99"}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "receipts_mismatch")), 1)
        # register has receipts but line 4490 says none were issued
        data = base_data()
        data["financials"]["issued_receipts"] = False
        data["receipts"] = {"eligible_total": "10.00"}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "receipts_mismatch")), 1)
        data["receipts"] = {"eligible_total": "0.00"}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "receipts_mismatch")), 0)

    def test_statement_totals_and_year_end(self):
        data = base_data()
        data["financial_statements"] = {
            "total_revenue": 1000, "total_expenditures": 800,
            "total_assets": 1000, "total_liabilities": 100,
            "fiscal_year_end": "2025-12-31"}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "statements_mismatch")), 0)
        data["financial_statements"]["total_assets"] = 999
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "statements_mismatch")), 1)
        data["financial_statements"]["total_assets"] = 1000
        data["financial_statements"]["fiscal_year_end"] = "2025-06-30"
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "statements_mismatch")), 1)


class TestWorksheets(unittest.TestCase):
    def test_director_required_fields(self):
        data = base_data()
        data["directors"] = [{
            "name": "Test Director", "position": "Chair",
            "arms_length": None}]  # no start, no DOB, no postal code
        payload = parse(check_payload(data))
        found = [f for f in rules(payload, "required_missing")
                 if f["section"] == "t1235"]
        self.assertEqual(len(found), 4)  # start, DOB, arm's length, postal
        data = base_data()  # complete row: nothing fires
        payload = parse(check_payload(data))
        found = [f for f in payload["findings"] if f["section"] == "t1235"]
        self.assertEqual(len(found), 0)

    def test_director_dates(self):
        data = base_data()
        data["directors"][0]["end_date"] = "2022-01-01"  # before start
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "director_dates")), 1)
        data = base_data()
        data["directors"][0]["start_date"] = "2026-02-01"  # after FYE
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "director_dates")), 1)
        data = base_data()
        data["directors"][0]["end_date"] = "2024-06-30"  # before period
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "director_not_serving")), 1)

    def test_nal_director_prompt(self):
        data = base_data()
        data["directors"][0]["arms_length"] = False
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "nal_director_prompt")), 1)
        data["section_c"]["director_or_nal_compensation"] = True
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "nal_director_prompt")), 0)

    def test_t1236_totals(self):
        data = base_data()
        data["section_c"]["gifts_to_qualified_donees"] = True
        data["attachments"]["t1236_included"] = True
        # gifts 4000+2000=6000=line 5050; line 5100: 800+0+6000=6800
        data["financials"]["lines"].update({"5050": 6000, "5100": 6800})
        data["t1236"] = [
            {"organization_name": "Donee A",
             "registration_number": "123456789RR0002",
             "is_qualified_donee": True, "total_gifts": 4000},
            {"organization_name": "Donee B",
             "registration_number": "123456789RR0003",
             "is_qualified_donee": True, "total_gifts": 2000},
        ]
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "donee_total_mismatch")), 0)
        data["t1236"][1]["total_gifts"] = 2001
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "donee_total_mismatch")), 1)
        data["t1236"][0]["registration_number"] = "12345"
        payload = parse(check_payload(data))
        self.assertEqual(
            len(rules(payload, "registration_number_format")), 1)

    def test_schedule_3_bands(self):
        data = base_data()
        # bands 6+5=11 > 10 (the bands count the ten highest only)
        data["schedule_3"] = {
            "full_time_positions": 20,
            "bands": {"305": 6, "310": 5}}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "bands_mismatch")), 1)
        # bands 3 > line 300's 2 positions
        data["schedule_3"] = {
            "full_time_positions": 2, "bands": {"305": 3}}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "bands_mismatch")), 1)
        # bands 3 = line 300's 3 positions: fine
        data["schedule_3"] = {
            "full_time_positions": 3, "bands": {"305": 2, "310": 1}}
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "bands_mismatch")), 0)

    def test_answers_inconsistent(self):
        data = base_data()
        data["financials"]["lines"].update({"5050": 500, "5100": 1300})
        payload = parse(check_payload(data))  # C3 is no, 5050 is 500
        self.assertEqual(len(rules(payload, "answers_inconsistent")), 1)
        data = base_data()
        data["section_c"]["grants_to_grantees"] = True
        data["financials"]["lines"]["5045"] = 0
        payload = parse(check_payload(data))
        self.assertEqual(len(rules(payload, "answers_inconsistent")), 1)


class TestInputErrors(unittest.TestCase):
    def assert_clean_error(self, proc):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("error", payload)

    def test_missing_file(self):
        proc = run_cli("check", str(PACK / "nope.json"), "--json")
        self.assert_clean_error(proc)

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as handle:
            handle.write("{not json")
            path = handle.name
        try:
            proc = run_cli("check", path, "--json")
        finally:
            Path(path).unlink(missing_ok=True)
        self.assert_clean_error(proc)
        self.assertIn("line 1", proc.stdout)

    def test_unsupported_suffix_and_bad_values(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False) as handle:
            handle.write("{}")
            path = handle.name
        try:
            proc = run_cli("check", path, "--json")
        finally:
            Path(path).unlink(missing_ok=True)
        self.assert_clean_error(proc)

        data = base_data()
        data["financials"]["lines"]["4500"] = 100.50  # cents not allowed
        self.assert_clean_error(check_payload(data))
        data = base_data()
        data["financials"]["lines"]["9999"] = 1  # unknown line
        self.assert_clean_error(check_payload(data))
        data = base_data()
        data["charity"]["fiscal_period_end"] = "2025-02-30"  # not real
        self.assert_clean_error(check_payload(data))
        data = base_data()
        data["charity"]["designation"] = "co-operative"
        self.assert_clean_error(check_payload(data))

    def test_csv_unknown_field(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".csv", delete=False) as handle:
            handle.write("field,value\nbogus.field,1\n")
            path = handle.name
        try:
            proc = run_cli("check", path, "--json")
        finally:
            Path(path).unlink(missing_ok=True)
        self.assert_clean_error(proc)

    def test_csv_mutated_total_fails(self):
        text = (EXAMPLES / "clean-return.csv").read_text()
        text = text.replace("line.4700,74700", "line.4700,74701")
        with tempfile.NamedTemporaryFile(
                "w", suffix=".csv", delete=False) as handle:
            handle.write(text)
            path = handle.name
        try:
            proc = run_cli("check", path, "--as-of", "2026-03-20",
                           "--json")
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(proc.returncode, 1)
        payload = parse(proc)
        self.assertGreaterEqual(
            len(rules(payload, "total_mismatch")), 1)

    def test_argument_errors_are_json_exit_2(self):
        proc = run_cli("check", "--json")
        self.assert_clean_error(proc)
        proc = run_cli("deadline", "--year-end", "31-12-2025", "--json")
        self.assert_clean_error(proc)


class TestRulesCommandAndHygiene(unittest.TestCase):
    def test_rules_json(self):
        proc = run_cli("rules", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = parse(proc)
        self.assertEqual(payload["rules_checked"], "2026-11")
        self.assertEqual(payload["sources_checked"], "2026-11-04")
        self.assertIn("4500", payload["modelled_lines"])
        rule_names = {c["rule"] for c in payload["checks"]}
        self.assertIn("receipts_mismatch", rule_names)
        self.assertIn("not tax or legal advice", payload["disclaimer"])

    def test_rules_text(self):
        proc = run_cli("rules")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("late_filing", proc.stdout)
        self.assertIn("Modelled T3010 lines:", proc.stdout)

    def test_tool_has_no_network_code(self):
        source = SRC.read_text()
        for token in ("urllib", "requests", "socket", "http.client",
                      "urlopen"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
