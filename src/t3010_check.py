#!/usr/bin/env python3
"""T3010 Pre-Flight Checker — pre-flight checks for a charity's own T3010 data.

A T3010 (Registered Charity Information Return) draft passes three kinds of
checks before it is filed:

COMPLETENESS — the fields, worksheets and schedules the CRA itself requires
for this return are present (blank required field -> ERROR; a conditional
requirement is a WARN that states the condition, never a silent pass).

INTERNAL CONSISTENCY — the figures on the return reconcile with each other
and with the charity's own supporting totals (statement totals vs. their
components, tax-receipted gifts vs. the receipt-register total the user
supplies, return totals vs. the financial-statement totals the user
supplies).  Arithmetic is exact; a mismatch is an ERROR showing both
numbers.  The tool computes nothing it cannot derive from the user's own
data — it never estimates an amount the charity should have reported.

FILING MATH — the return is due within six months after the fiscal
year-end (Income Tax Act s. 149.1(14); CRA guidance "When is my return
due?" gives the same examples: December 31 -> June 30, March 31 ->
September 30, June 30 -> December 31).  The deadline is computed from the
user's own dates and shown with the arithmetic.

Schedule triggers (a compensated director, grants to grantees, the
disbursement-quota question, excess corporate holdings for a private
foundation) are flagged only as "schedule X appears required because you
answered Y" — a prompt to check, never a determination.

This tool checks a draft against the CRA's published T3010 form (24),
the T4033 guide and the CRA's own T3010 checklist.  It does NOT file
anything, it is NOT a CRA product, and a clean run does NOT mean the
return complies with the Income Tax Act.  It is not tax or legal advice.

Pure Python 3.10+ standard library.  No network access.  Local files only.
Exit codes: 0 = no errors, 1 = at least one ERROR finding, 2 = the input
itself could not be read or parsed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

RULES_CHECKED = "2026-11"
SOURCES = [
    "T3010 Registered Charity Information Return (24) - form structure, "
    "Canada Revenue Agency (canada.ca)",
    "T4033 Completing the Registered Charity Information Return - guide, "
    "Canada Revenue Agency",
    "Checklist for completing the T3010 charity information return - "
    "Canada Revenue Agency (the CRA's own list of required parts and "
    "common errors)",
    "Filing deadline: Income Tax Act s. 149.1(14) and CRA charities "
    "guidance - the return is due within six months after the fiscal "
    "year-end; verify against current CRA guidance before filing.",
]
SOURCES_CHECKED = "2026-11-04"
DISCLAIMER = (
    "Pre-flight checks only. This tool is not a CRA product, a clean run "
    "does not mean the return complies with the Income Tax Act, and this "
    "is not tax or legal advice. Verify every figure against your records "
    "and check the current T3010 form, the T4033 guide and CRA guidance "
    "before filing."
)

# severity order for sorting and display
SEVERITIES = ("error", "warning", "info")

CHECKS = [
    {"rule": "required_missing", "severity": "error",
     "basis": "T3010 (24) / T4033 / CRA T3010 checklist — fields, lines "
              "and worksheet details the CRA requires for this return are "
              "blank (charity name, registration number, designation, "
              "fiscal period, lines 4200/4350/4700/4950/5000/5010/5100, "
              "line 4500 when receipts were issued, line 5045 when grants "
              "were made, line 5050 when gifts to qualified donees were "
              "made, T1235 director details incl. dates of birth, arm's "
              "length status and postal codes)."},
    {"rule": "registration_number_format", "severity": "error",
     "basis": "T4033 — a charity registration number is the 9-digit "
              "business number + RR + a 4-digit reference number "
              "(e.g. 123456789RR0001)."},
    {"rule": "total_mismatch", "severity": "error",
     "basis": "T3010 (24) / CRA T3010 checklist — a printed total must "
              "equal the sum of its components: revenue (line 4700), "
              "expenditures (line 4950), the expenditures breakdown "
              "(lines 5000-5040), total expenditures (line 5100), and on "
              "Schedule 6 total assets (line 4200) and total liabilities "
              "(line 4350)."},
    {"rule": "subtotal_mismatch", "severity": "error",
     "basis": "Schedule 6 — line 4570 (total revenue from government) "
              "must equal lines 4540 + 4550 + 4560."},
    {"rule": "receipts_mismatch", "severity": "error",
     "basis": "T4033 / receipt-gate — line 4500 must equal the eligible "
              "amount of tax-receipted gifts in the charity's own receipt "
              "register (the total the user supplies from that register)."},
    {"rule": "statements_mismatch", "severity": "error",
     "basis": "CRA T3010 checklist — the financial statements must have "
              "the same fiscal year-end as the return, and their totals "
              "must agree with lines 4700, 5100, 4200 and 4350."},
    {"rule": "financial_statements_missing", "severity": "error",
     "basis": "T4033 / CRA checklist — a complete return always includes "
              "the charity's financial statements."},
    {"rule": "worksheet_missing", "severity": "error",
     "basis": "T4033 — Form T1235 (directors/trustees) is always "
              "required; Form T1236 is required when gifts were made to "
              "qualified donees or other organizations (question C3); "
              "Form T1441 is required when a single grantee received more "
              "than $5,000 in qualifying disbursements."},
    {"rule": "schedule_missing", "severity": "error",
     "basis": "T4033 / T3010 (24) complete-return list — Schedule 1 for "
              "public and private foundations, Schedule 2 when the "
              "charity carried on activities outside Canada (C4), "
              "Schedule 3 when the charity had compensation expenses "
              "(C9), Schedule 4 when it paid external fundraisers (C7) "
              "or took a $10,000+ donation from a non-resident donor "
              "(C10), Schedule 5 when non-cash gifts were receipted "
              "(C11)."},
    {"rule": "schedule_6_required", "severity": "error",
     "basis": "T4033 — Schedule 6 (full financial statements detail) "
              "must be completed instead of Section D when total revenue "
              "exceeds $100,000 (also when property not used in "
              "charitable activities exceeds $25,000, or the charity has "
              "permission to accumulate funds)."},
    {"rule": "certification_unsigned", "severity": "error",
     "basis": "T3010 (24) section E — the return must be certified and "
              "signed by a director, trustee or like official."},
    {"rule": "late_filing", "severity": "error",
     "basis": "Income Tax Act s. 149.1(14) — the return is due within "
              "six months after the fiscal year-end; the CRA does not "
              "grant extensions, and not filing can lead to revocation."},
    {"rule": "director_dates", "severity": "error",
     "basis": "Form T1235 — a director's start date falls after the "
              "fiscal period end, or the end date is before the start "
              "date: the term dates cannot describe this return's period."},
    {"rule": "bands_mismatch", "severity": "error",
     "basis": "Schedule 3 — the compensation bands (lines 305-345) "
              "count the ten highest compensated permanent full-time "
              "positions: the band counts cannot exceed 10 in total, and "
              "cannot exceed the number of permanent full-time "
              "compensated positions (line 300)."},
    {"rule": "donee_total_mismatch", "severity": "error",
     "basis": "Form T1236 — the total gifts to qualified donees on the "
              "worksheet must agree with line 5050 of the return."},
    {"rule": "programs_missing", "severity": "error",
     "basis": "T3010 (24) question C2 / CRA checklist — the return must "
              "describe the charity's charitable programs (or explain why "
              "it was inactive); describing fundraising here is a named "
              "CRA error."},
    {"rule": "filing_overdue", "severity": "warning",
     "basis": "Income Tax Act s. 149.1(14) — as of the check date the "
              "deadline has passed and no filing date was supplied."},
    {"rule": "schedule_trigger", "severity": "warning",
     "basis": "T4033 — Schedule 8 appears required when the answer to "
              "the disbursement-quota question (C17) is yes; Form T2081 "
              "applies to private foundations. Prompts to check, not "
              "determinations."},
    {"rule": "nal_director_prompt", "severity": "warning",
     "basis": "T3010 (24) question C8 / Form T1235 — a director who is "
              "not at arm's length is listed; if the charity compensated "
              "directors or non-arm's length persons, C8 must be answered "
              "yes."},
    {"rule": "memo_exceeds", "severity": "warning",
     "basis": "Schedule 6 / Section D — memo lines are subsets: line "
              "4505 (10-year gifts) is part of line 4500; lines 4520 and "
              "4525 are included in line 4510. A memo larger than its "
              "parent line cannot be right."},
    {"rule": "director_not_serving", "severity": "warning",
     "basis": "Form T1235 — the worksheet lists the directors who served "
              "during the fiscal period; a director whose term ended "
              "before the period began does not belong on this return's "
              "worksheet."},
    {"rule": "answers_inconsistent", "severity": "warning",
     "basis": "T3010 (24) — a Section C answer contradicts the figures: "
              "gifts/grants reported while the matching question is "
              "answered no, or the question answered yes while the "
              "matching total line is 0."},
    {"rule": "period_length", "severity": "warning",
     "basis": "T4033 — a charity's fiscal period is normally 12 months; "
              "a longer period needs a CRA-approved change of fiscal "
              "year-end."},
    {"rule": "amortization_sign", "severity": "warning",
     "basis": "T4033 Schedule 6 — accumulated amortization (line 4166) "
              "is entered as a negative amount (show a minus sign)."},
    {"rule": "total_unverifiable", "severity": "info",
     "basis": "A total line is present but none of its component lines "
              "were supplied, so the total could not be cross-footed from "
              "the data given."},
    {"rule": "worksheet_detail_unchecked", "severity": "info",
     "basis": "A worksheet is marked as included but its rows were not "
              "supplied in the data file (the CSV format carries scalar "
              "fields and T3010 lines only), so row-level checks for "
              "that worksheet were skipped rather than passed."},
    {"rule": "filing_deadline", "severity": "info",
     "basis": "Income Tax Act s. 149.1(14) — return due within six "
              "months after the fiscal year-end (CRA examples: Dec 31 -> "
              "Jun 30, Mar 31 -> Sep 30, Jun 30 -> Dec 31)."},
]

CHECK_BY_RULE = {c["rule"]: c for c in CHECKS}

LINE_LABELS = {
    "4100": "Cash, bank accounts and short-term investments",
    "4110": "Accounts receivable",
    "4120": "Amounts receivable from non-arm's length persons",
    "4130": "Inventories",
    "4140": "Long-term investments",
    "4150": "Land and buildings in Canada",
    "4160": "Other capital assets in Canada",
    "4165": "Capital assets outside Canada",
    "4166": "Accumulated amortization of capital assets (negative)",
    "4170": "Other assets",
    "4180": "10-year gifts (asset detail; not part of the line 4200 "
            "total, which adds lines 4100 to 4170)",
    "4200": "Total assets",
    "4300": "Accounts payable and accrued liabilities",
    "4310": "Deferred revenue",
    "4320": "Other liabilities",
    "4330": "Long-term debt",
    "4350": "Total liabilities",
    "4490": "Issued tax receipts for charitable donations (yes/no)",
    "4500": "Total eligible amount of tax-receipted gifts",
    "4505": "Total amount of 10-year gifts received (included in 4500)",
    "4510": "Total amount received from other registered charities",
    "4520": "Specified gifts (included in line 4510)",
    "4525": "Enduring property (included in line 4510)",
    "4530": "Total other gifts received (receipts not issued)",
    "4540": "Revenue from the federal government",
    "4550": "Revenue from provincial or territorial governments",
    "4560": "Revenue from municipal or regional governments",
    "4570": "Total revenue from government",
    "4571": "Total tax-receipted revenue from outside Canada",
    "4575": "Total non tax-receipted revenue from outside Canada",
    "4580": "Interest and investment income",
    "4590": "Proceeds from disposition of assets",
    "4600": "Net gain (loss) on disposition of assets",
    "4620": "Memberships, dues and association fees (not receipted)",
    "4630": "Total non tax-receipted revenue from fundraising",
    "4640": "Total revenue from sale of goods and services",
    "4650": "Other revenue",
    "4700": "Total revenue",
    "4800": "Advertising and promotion",
    "4810": "Travel and vehicle expenses",
    "4820": "Interest and bank charges",
    "4830": "Licences, memberships and dues",
    "4840": "Office supplies and expenses",
    "4850": "Occupancy costs",
    "4860": "Professional and consulting fees",
    "4870": "Education and training for staff and volunteers",
    "4880": "Total expenditure on all compensation",
    "4890": "Fair market value of donated goods used in programs",
    "4891": "Purchased supplies and assets bought",
    "4900": "Amortization of capital assets",
    "4910": "Research grants and scholarships/bursaries",
    "4920": "All other expenditures",
    "4950": "Total expenditures (before gifts and qualifying "
            "disbursements)",
    "5000": "Total expenditures on charitable activities",
    "5010": "Total expenditures on management and administration",
    "5020": "Total expenditures on fundraising",
    "5030": "Total expenditures on public policy dialogue and "
            "development activities",
    "5040": "Total other expenditures included in line 4950",
    "5045": "Total amount of grants made to non-qualified donees "
            "(grantees)",
    "5050": "Total amount of gifts made to all qualified donees",
    "5100": "Total expenditures",
}

SECTION_D_REVENUE = ["4500", "4510", "4530", "4570", "4571", "4575",
                     "4630", "4640", "4650"]
SCHEDULE_6_REVENUE = ["4500", "4510", "4530", "4540", "4550", "4560",
                      "4571", "4575", "4580", "4590", "4600", "4620",
                      "4630", "4640", "4650"]
SECTION_D_EXPENDITURES = ["4860", "4810", "4920"]
SCHEDULE_6_EXPENDITURES = ["4800", "4810", "4820", "4830", "4840",
                           "4850", "4860", "4870", "4880", "4890",
                           "4891", "4900", "4910", "4920"]
EXPENDITURE_BREAKDOWN = ["5000", "5010", "5020", "5030", "5040"]
SCHEDULE_6_ASSETS = ["4100", "4110", "4120", "4130", "4140", "4150",
                     "4160", "4165", "4166", "4170"]
SCHEDULE_6_LIABILITIES = ["4300", "4310", "4320", "4330"]
COMPENSATION_BANDS = ["305", "310", "315", "320", "325", "330", "335",
                      "340", "345"]

REGISTRATION_RE = re.compile(r"^\d{9}RR\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SCHEDULE_6_REVENUE_THRESHOLD = 100000

DESIGNATIONS = ("charitable organization", "public foundation",
                "private foundation")


class ToolError(Exception):
    """An input problem: clean message, exit 2, never a traceback."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def parse_date(value, field: str) -> date:
    if not isinstance(value, str) or not DATE_RE.match(value.strip()):
        raise ToolError(f"{field}: expected a date as YYYY-MM-DD, "
                        f"got {value!r}")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ToolError(f"{field}: {value!r} is not a real calendar date")


def parse_money(value, field: str) -> int:
    """T3010 amounts are whole dollars. Returns integer dollars."""
    if isinstance(value, bool):
        raise ToolError(f"{field}: expected a whole-dollar amount, "
                        f"got {value!r}")
    if isinstance(value, int):
        return value
    try:
        dec = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError):
        raise ToolError(f"{field}: expected a whole-dollar amount, "
                        f"got {value!r}")
    if dec != dec.to_integral_value():
        raise ToolError(
            f"{field}: T3010 amounts are reported to the nearest dollar "
            f"with no cents (T4033); got {value!r} — round it in your "
            f"records first, the tool will not round silently")
    return int(dec)


def parse_cents(value, field: str) -> int:
    """A supporting total that may carry cents (e.g. a receipt register)."""
    if isinstance(value, bool):
        raise ToolError(f"{field}: expected an amount, got {value!r}")
    try:
        dec = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError):
        raise ToolError(f"{field}: expected an amount, got {value!r}")
    cents = dec * 100
    if cents != cents.to_integral_value():
        raise ToolError(f"{field}: expected an amount with at most two "
                        f"decimal places, got {value!r}")
    return int(cents)


def parse_count(value, field: str) -> int:
    number = parse_money(value, field)
    if number < 0:
        raise ToolError(f"{field}: a count cannot be negative, "
                        f"got {value!r}")
    return number


def parse_bool(value, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("yes", "y", "true", "1"):
            return True
        if low in ("no", "n", "false", "0", ""):
            return False
    raise ToolError(f"{field}: expected yes/no (true/false), "
                    f"got {value!r}")


def opt_bool(obj: dict, key: str, field: str):
    """Optional boolean: None when the key is absent (unknown)."""
    if key not in obj or obj.get(key) is None:
        return None
    return parse_bool(obj[key], field)


def _last_day(year: int, month: int) -> int:
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    return (next_first - date(year, month, 1)).days


def add_months(day: date, months: int) -> date:
    """Add calendar months the way the CRA's own examples do.

    A month-end date stays a month-end date: 2025-06-30 + 6 ->
    2025-12-31 (not Dec 30), 2025-12-31 + 6 -> 2026-06-30,
    2025-03-31 + 6 -> 2025-09-30, 2025-08-31 + 6 -> 2026-02-28,
    2023-08-31 + 6 -> 2024-02-29 (leap). Any other day keeps its
    day number, clamped to the target month's length.
    """
    total = (day.year * 12 + (day.month - 1)) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    target_last = _last_day(year, month)
    if day.day == _last_day(day.year, day.month):
        return date(year, month, target_last)
    return date(year, month, min(day.day, target_last))


def fmt_money(dollars: int) -> str:
    return f"${dollars:,}"


def fmt_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


# ---------------------------------------------------------------------------
# input loading — JSON (full model) and CSV (scalars + lines only)
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"cannot read {path}: {exc.strerror or exc}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"{path}: invalid JSON at line {exc.lineno} "
                        f"column {exc.colno}: {exc.msg}")
    if not isinstance(data, dict):
        raise ToolError(f"{path}: the top level must be a JSON object")
    return data


CSV_SCALAR_KEYS = {
    "charity.name": ("charity", "name"),
    "charity.registration_number": ("charity", "registration_number"),
    "charity.designation": ("charity", "designation"),
    "charity.fiscal_period_start": ("charity", "fiscal_period_start"),
    "charity.fiscal_period_end": ("charity", "fiscal_period_end"),
    "financials.mode": ("financials", "mode"),
    "financials.basis": ("financials", "basis"),
    "financials.schedule_6_required": ("financials",
                                       "schedule_6_required"),
    "financials.owns_land_buildings": ("financials",
                                       "owns_land_buildings"),
    "financials.nal_transactions": ("financials", "nal_transactions"),
    "financials.issued_receipts": ("financials", "issued_receipts"),
    "receipts.eligible_total": ("receipts", "eligible_total"),
    "financial_statements.total_revenue": ("financial_statements",
                                           "total_revenue"),
    "financial_statements.total_expenditures":
        ("financial_statements", "total_expenditures"),
    "financial_statements.total_assets": ("financial_statements",
                                          "total_assets"),
    "financial_statements.total_liabilities":
        ("financial_statements", "total_liabilities"),
    "financial_statements.fiscal_year_end": ("financial_statements",
                                             "fiscal_year_end"),
    "certification.signed": ("certification", "signed"),
    "certification.signature_date": ("certification", "signature_date"),
    "certification.filed_date": ("certification", "filed_date"),
}
CSV_SECTION_C_KEYS = [
    "active", "programs_description", "wound_up",
    "subordinate_to_head_body", "gifts_to_qualified_donees",
    "activities_outside_canada", "paid_external_fundraisers",
    "director_or_nal_compensation", "employee_compensation",
    "foreign_donations_10000", "non_cash_gifts_receipted",
    "grants_to_grantees", "grantees_over_5000",
    "disbursement_quota_property",
]
CSV_ATTACHMENT_KEYS = [
    "financial_statements_included", "t1235_included", "t1236_included",
    "t1441_included", "t2081_included", "schedule_1_included",
    "schedule_2_included", "schedule_3_included", "schedule_4_included",
    "schedule_5_included",
    "schedule_6_included", "schedule_8_included",
]


def load_csv(path: Path) -> dict:
    data: dict = {}
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"cannot read {path}: {exc.strerror or exc}")
    with handle:
        reader = csv.reader(handle)
        rows = [r for r in reader if r and any(c.strip() for c in r)]
    if not rows:
        raise ToolError(f"{path}: the file is empty")
    header = [c.strip().lower() for c in rows[0]]
    if header[:2] != ["field", "value"]:
        raise ToolError(f"{path}: the first row must be the header "
                        f"'field,value'")
    for lineno, row in enumerate(rows[1:], start=2):
        if len(row) != 2:
            raise ToolError(f"{path} line {lineno}: expected exactly "
                            f"two columns (field,value)")
        key, value = row[0].strip(), row[1].strip()
        if key in CSV_SCALAR_KEYS:
            section, name = CSV_SCALAR_KEYS[key]
            data.setdefault(section, {})[name] = value
        elif key.startswith("line."):
            number = key[5:]
            if number not in LINE_LABELS:
                raise ToolError(f"{path} line {lineno}: unknown T3010 "
                                f"line {number!r}")
            data.setdefault("financials", {}).setdefault(
                "lines", {})[number] = value
        elif key.startswith("section_c."):
            name = key[len("section_c."):]
            if name not in CSV_SECTION_C_KEYS:
                raise ToolError(f"{path} line {lineno}: unknown section "
                                f"C field {name!r}")
            data.setdefault("section_c", {})[name] = value
        elif key.startswith("attachments."):
            name = key[len("attachments."):]
            if name not in CSV_ATTACHMENT_KEYS:
                raise ToolError(f"{path} line {lineno}: unknown "
                                f"attachment field {name!r}")
            data.setdefault("attachments", {})[name] = value
        else:
            raise ToolError(f"{path} line {lineno}: unknown field "
                            f"{key!r} (see README for the CSV field list)")
    return data


def load_return(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix == ".csv":
        return load_csv(path)
    raise ToolError(f"{path}: unsupported file type {suffix!r} — use a "
                    f".json or .csv data file (see README)")


# ---------------------------------------------------------------------------
# normalization — raw dict -> typed model; every bad value is a ToolError
# ---------------------------------------------------------------------------

def _section(data: dict, name: str) -> dict:
    value = data.get(name) or {}
    if not isinstance(value, dict):
        raise ToolError(f"{name}: expected an object")
    return value


def _opt_date(obj: dict, key: str, field: str):
    value = obj.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_date(value, field)


def _opt_money(obj: dict, key: str, field: str):
    value = obj.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_money(value, field)


def normalize(data: dict) -> dict:
    charity_in = _section(data, "charity")
    fin_in = _section(data, "financials")
    sec_c_in = _section(data, "section_c")
    att_in = _section(data, "attachments")
    fs_in = _section(data, "financial_statements")
    cert_in = _section(data, "certification")
    receipts_in = _section(data, "receipts")

    designation_raw = charity_in.get("designation")
    designation = None
    if isinstance(designation_raw, str) and designation_raw.strip():
        designation = re.sub(r"[\s\-]+", "_",
                             designation_raw.strip().lower())
        designation = designation.replace("_", " ")
        if designation not in DESIGNATIONS:
            raise ToolError(
                "charity.designation: expected one of "
                + ", ".join(DESIGNATIONS) + f"; got {designation_raw!r}")

    mode_raw = fin_in.get("mode")
    mode = None
    if isinstance(mode_raw, str) and mode_raw.strip():
        mode = mode_raw.strip().lower().replace("-", "_")
        if mode not in ("section_d", "schedule_6"):
            raise ToolError("financials.mode: expected 'section_d' or "
                            f"'schedule_6', got {mode_raw!r}")
    elif mode_raw is not None and not (
            isinstance(mode_raw, str) and not mode_raw.strip()):
        raise ToolError("financials.mode: expected 'section_d' or "
                        f"'schedule_6', got {mode_raw!r}")

    basis_raw = fin_in.get("basis")
    basis = None
    if isinstance(basis_raw, str) and basis_raw.strip():
        basis = basis_raw.strip().lower()
        if basis not in ("accrual", "cash"):
            raise ToolError("financials.basis: expected 'accrual' or "
                            f"'cash' (line 4020), got {basis_raw!r}")

    lines_in = fin_in.get("lines") or {}
    if not isinstance(lines_in, dict):
        raise ToolError("financials.lines: expected an object keyed by "
                        "T3010 line number")
    lines = {}
    for number, value in lines_in.items():
        key = str(number).strip()
        if key not in LINE_LABELS:
            raise ToolError(f"financials.lines: unknown T3010 line "
                            f"{key!r}")
        if value is None or (isinstance(value, str)
                             and not value.strip()):
            lines[key] = None
        else:
            lines[key] = parse_money(value, f"line {key}")

    directors_in = data.get("directors") or []
    if not isinstance(directors_in, list):
        raise ToolError("directors: expected a list (the T1235 worksheet "
                        "rows)")
    directors = []
    for idx, row in enumerate(directors_in, start=1):
        if not isinstance(row, dict):
            raise ToolError(f"directors[{idx}]: expected an object")
        directors.append({
            "index": idx,
            "name": (row.get("name") or "").strip()
            if isinstance(row.get("name"), str) else row.get("name"),
            "position": (row.get("position") or "").strip()
            if isinstance(row.get("position"), str)
            else row.get("position"),
            "start_date": _opt_date(row, "start_date",
                                    f"directors[{idx}].start_date"),
            "end_date": _opt_date(row, "end_date",
                                  f"directors[{idx}].end_date"),
            "date_of_birth": _opt_date(
                row, "date_of_birth",
                f"directors[{idx}].date_of_birth"),
            "arms_length": opt_bool(row, "arms_length",
                                    f"directors[{idx}].arms_length"),
            "postal_code": (row.get("postal_code") or "").strip()
            if isinstance(row.get("postal_code"), str)
            else row.get("postal_code"),
        })

    t1236_in = data.get("t1236") or []
    if not isinstance(t1236_in, list):
        raise ToolError("t1236: expected a list (the T1236 worksheet "
                        "rows)")
    t1236 = []
    for idx, row in enumerate(t1236_in, start=1):
        if not isinstance(row, dict):
            raise ToolError(f"t1236[{idx}]: expected an object")
        t1236.append({
            "index": idx,
            "organization_name": row.get("organization_name"),
            "registration_number": row.get("registration_number"),
            "is_qualified_donee": opt_bool(
                row, "is_qualified_donee",
                f"t1236[{idx}].is_qualified_donee"),
            "total_gifts": _opt_money(row, "total_gifts",
                                      f"t1236[{idx}].total_gifts"),
        })

    sched3_in = _section(data, "schedule_3")
    sched3 = None
    if sched3_in:
        bands_in = sched3_in.get("bands") or {}
        if not isinstance(bands_in, dict):
            raise ToolError("schedule_3.bands: expected an object keyed "
                            "by band line (305-345)")
        bands = {}
        for band in COMPENSATION_BANDS:
            value = bands_in.get(band, bands_in.get(int(band)))
            if value is None or (isinstance(value, str)
                                 and not value.strip()):
                bands[band] = None
            else:
                bands[band] = parse_count(value, f"schedule_3 band {band}")
        sched3 = {
            "full_time_positions": _opt_money(
                sched3_in, "full_time_positions",
                "schedule_3.full_time_positions (line 300)"),
            "bands": bands,
            "part_time_count": _opt_money(
                sched3_in, "part_time_count",
                "schedule_3.part_time_count (line 370)"),
            "part_time_compensation": _opt_money(
                sched3_in, "part_time_compensation",
                "schedule_3.part_time_compensation (line 380)"),
            "total_compensation": _opt_money(
                sched3_in, "total_compensation",
                "schedule_3.total_compensation (line 390)"),
        }

    receipts_total_cents = None
    if receipts_in.get("eligible_total") is not None and not (
            isinstance(receipts_in.get("eligible_total"), str)
            and not receipts_in["eligible_total"].strip()):
        receipts_total_cents = parse_cents(receipts_in["eligible_total"],
                                           "receipts.eligible_total")

    return {
        "charity": {
            "name": charity_in.get("name"),
            "registration_number":
                charity_in.get("registration_number"),
            "designation": designation,
            "fiscal_period_start": _opt_date(
                charity_in, "fiscal_period_start",
                "charity.fiscal_period_start"),
            "fiscal_period_end": _opt_date(
                charity_in, "fiscal_period_end",
                "charity.fiscal_period_end"),
        },
        "financials": {
            "mode": mode,
            "basis": basis,
            "schedule_6_required": opt_bool(
                fin_in, "schedule_6_required",
                "financials.schedule_6_required"),
            "owns_land_buildings": opt_bool(
                fin_in, "owns_land_buildings",
                "financials.owns_land_buildings"),
            "nal_transactions": opt_bool(
                fin_in, "nal_transactions",
                "financials.nal_transactions"),
            "issued_receipts": opt_bool(fin_in, "issued_receipts",
                                        "financials.issued_receipts"),
            "lines": lines,
        },
        "section_c": {
            "active": opt_bool(sec_c_in, "active", "section_c.active"),
            "programs_description": sec_c_in.get("programs_description"),
            "wound_up": opt_bool(sec_c_in, "wound_up",
                                 "section_c.wound_up"),
            "subordinate_to_head_body": opt_bool(
                sec_c_in, "subordinate_to_head_body",
                "section_c.subordinate_to_head_body"),
            "gifts_to_qualified_donees": opt_bool(
                sec_c_in, "gifts_to_qualified_donees",
                "section_c.gifts_to_qualified_donees (C3)"),
            "activities_outside_canada": opt_bool(
                sec_c_in, "activities_outside_canada",
                "section_c.activities_outside_canada (C4)"),
            "paid_external_fundraisers": opt_bool(
                sec_c_in, "paid_external_fundraisers",
                "section_c.paid_external_fundraisers (C7)"),
            "director_or_nal_compensation": opt_bool(
                sec_c_in, "director_or_nal_compensation",
                "section_c.director_or_nal_compensation (C8)"),
            "employee_compensation": opt_bool(
                sec_c_in, "employee_compensation",
                "section_c.employee_compensation (C9)"),
            "foreign_donations_10000": opt_bool(
                sec_c_in, "foreign_donations_10000",
                "section_c.foreign_donations_10000 (C10)"),
            "non_cash_gifts_receipted": opt_bool(
                sec_c_in, "non_cash_gifts_receipted",
                "section_c.non_cash_gifts_receipted (C11)"),
            "grants_to_grantees": opt_bool(
                sec_c_in, "grants_to_grantees",
                "section_c.grants_to_grantees (C16)"),
            "grantees_over_5000": opt_bool(
                sec_c_in, "grantees_over_5000",
                "section_c.grantees_over_5000"),
            "disbursement_quota_property": opt_bool(
                sec_c_in, "disbursement_quota_property",
                "section_c.disbursement_quota_property (C17)"),
        },
        "attachments": {key: opt_bool(att_in, key, f"attachments.{key}")
                        for key in CSV_ATTACHMENT_KEYS},
        "financial_statements": {
            "total_revenue": _opt_money(fs_in, "total_revenue",
                                        "financial_statements."
                                        "total_revenue"),
            "total_expenditures": _opt_money(
                fs_in, "total_expenditures",
                "financial_statements.total_expenditures"),
            "total_assets": _opt_money(fs_in, "total_assets",
                                       "financial_statements."
                                       "total_assets"),
            "total_liabilities": _opt_money(
                fs_in, "total_liabilities",
                "financial_statements.total_liabilities"),
            "fiscal_year_end": _opt_date(fs_in, "fiscal_year_end",
                                         "financial_statements."
                                         "fiscal_year_end"),
        },
        "certification": {
            "signed": opt_bool(cert_in, "signed", "certification.signed"),
            "signature_date": _opt_date(cert_in, "signature_date",
                                        "certification.signature_date"),
            "filed_date": _opt_date(cert_in, "filed_date",
                                    "certification.filed_date"),
        },
        "receipts": {"eligible_total_cents": receipts_total_cents},
        "directors": directors,
        "directors_provided": "directors" in data,
        "t1236": t1236,
        "schedule_3": sched3,
    }


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def _finding(findings, section, field, rule, measured, limit, message):
    findings.append({
        "section": section,
        "field": field,
        "rule": rule,
        "severity": CHECK_BY_RULE[rule]["severity"],
        "measured": measured,
        "limit": limit,
        "message": message,
    })


def _sum_check(findings, lines, components, total_line, what):
    """Cross-foot one total. Returns the recorded total (or None)."""
    recorded = lines.get(total_line)
    present = [(n, lines[n]) for n in components if lines.get(n) is not None]
    if recorded is None:
        return None
    if not present:
        _finding(findings, "financials", f"line {total_line}",
                 "total_unverifiable", None, None,
                 f"{what}: line {total_line} shows "
                 f"{fmt_money(recorded)} but none of its component lines "
                 f"were supplied, so the total could not be cross-footed "
                 f"from the data given.")
        return recorded
    computed = sum(v for _, v in present)
    if computed != recorded:
        parts = " + ".join(f"{n} {fmt_money(v)}" for n, v in present)
        _finding(findings, "financials", f"line {total_line}",
                 "total_mismatch", recorded, computed,
                 f"{what}: line {total_line} shows "
                 f"{fmt_money(recorded)} but its components add to "
                 f"{fmt_money(computed)} ({parts}). Difference: "
                 f"{fmt_money(recorded - computed)}.")
    return recorded


def run_checks(model: dict, as_of: date | None) -> dict:
    findings: list[dict] = []
    charity = model["charity"]
    fin = model["financials"]
    lines = fin["lines"]
    sec_c = model["section_c"]
    att = model["attachments"]
    fs = model["financial_statements"]
    cert = model["certification"]

    # ---- Section A: charity information -------------------------------
    name = charity["name"]
    if not (isinstance(name, str) and name.strip()):
        _finding(findings, "section_a", "charity.name", "required_missing",
                 None, None,
                 "The charity's legal name is blank — Section A of the "
                 "T3010 requires it.")
    reg = charity["registration_number"]
    if reg is None or (isinstance(reg, str) and not reg.strip()):
        _finding(findings, "section_a", "charity.registration_number",
                 "required_missing", None, None,
                 "The charity registration number is blank — Section A "
                 "of the T3010 requires it.")
    elif not (isinstance(reg, str) and REGISTRATION_RE.match(reg.strip())):
        _finding(findings, "section_a", "charity.registration_number",
                 "registration_number_format", reg,
                 "9 digits + RR + 4 digits (e.g. 123456789RR0001)",
                 f"Registration number {reg!r} is not in the CRA format: "
                 f"the 9-digit business number, then RR, then a 4-digit "
                 f"reference number (e.g. 123456789RR0001).")
    if charity["designation"] is None:
        _finding(findings, "section_a", "charity.designation",
                 "required_missing", None, None,
                 "The charity's designation is blank — Section A requires "
                 "one of: charitable organization, public foundation, "
                 "private foundation.")
    period_start = charity["fiscal_period_start"]
    period_end = charity["fiscal_period_end"]
    if period_start is None:
        _finding(findings, "section_a", "charity.fiscal_period_start",
                 "required_missing", None, None,
                 "The fiscal period start is blank — the return must "
                 "state the fiscal period it covers.")
    if period_end is None:
        _finding(findings, "section_a", "charity.fiscal_period_end",
                 "required_missing", None, None,
                 "The fiscal period end (fiscal year-end) is blank — the "
                 "return must state it, and the filing deadline is "
                 "computed from it.")
    if period_start and period_end:
        if period_end < period_start:
            raise ToolError(
                "charity.fiscal_period_end is before "
                "charity.fiscal_period_start — fix the data file; a "
                "fiscal period cannot end before it begins")
        span_days = (period_end - period_start).days + 1
        if span_days > 366:
            _finding(findings, "section_a", "charity.fiscal_period",
                     "period_length", f"{span_days} days", "12 months",
                     f"The fiscal period runs {span_days} days "
                     f"({period_start.isoformat()} to "
                     f"{period_end.isoformat()}). A fiscal period is "
                     f"normally 12 months; a longer period needs a "
                     f"CRA-approved change of fiscal year-end (T4033).")

    # ---- filing deadline ----------------------------------------------
    deadline = None
    if period_end is not None:
        due = add_months(period_end, 6)
        filed = cert["filed_date"]
        if filed is not None:
            status = "filed_on_time" if filed <= due else "filed_late"
        elif as_of is not None and as_of > due:
            status = "overdue"
        elif as_of is not None:
            status = "not_yet_due"
        else:
            status = "computed"
        deadline = {
            "fiscal_year_end": period_end.isoformat(),
            "due_date": due.isoformat(),
            "rule": "fiscal year-end + 6 months (Income Tax Act "
                    "s. 149.1(14))",
            "as_of": as_of.isoformat() if as_of else None,
            "days_remaining": (due - as_of).days if as_of else None,
            "filed_date": filed.isoformat() if filed else None,
            "status": status,
        }
        message = (f"Filing deadline: fiscal year-end "
                   f"{period_end.isoformat()} + 6 months = due "
                   f"{due.isoformat()} (Income Tax Act s. 149.1(14); "
                   f"CRA grants no extensions — verify against current "
                   f"CRA guidance).")
        if filed is not None and filed <= due:
            message += (f" Filed {filed.isoformat()}, "
                        f"{(due - filed).days} days before the deadline.")
        if filed is not None and filed > due:
            _finding(findings, "filing", "certification.filed_date",
                     "late_filing", filed.isoformat(), due.isoformat(),
                     f"The return was filed {filed.isoformat()}, "
                     f"{(filed - due).days} days after the deadline "
                     f"{due.isoformat()} (fiscal year-end "
                     f"{period_end.isoformat()} + 6 months). The CRA "
                     f"does not grant extensions; a return that is not "
                     f"filed on time can lead to revocation of "
                     f"registration.")
        elif filed is None and as_of is not None and as_of > due:
            _finding(findings, "filing", "filing_deadline",
                     "filing_overdue", as_of.isoformat(), due.isoformat(),
                     f"As of {as_of.isoformat()} the deadline "
                     f"{due.isoformat()} has passed "
                     f"({(as_of - due).days} days ago) and no filing "
                     f"date was supplied. " + message)
        else:
            _finding(findings, "filing", "filing_deadline",
                     "filing_deadline", due.isoformat(), None, message)

    # ---- Section C: questions ------------------------------------------
    if sec_c["active"] is None:
        _finding(findings, "section_c", "section_c.active",
                 "required_missing", None, None,
                 "Question C1 (was the charity active during the fiscal "
                 "period?) is unanswered — every Section C question must "
                 "be answered.")
    description = sec_c["programs_description"]
    if not (isinstance(description, str) and description.strip()):
        _finding(findings, "section_c", "section_c.programs_description",
                 "programs_missing", None, None,
                 "Question C2 is blank. The return must describe the "
                 "charity's charitable programs in its own words (or, if "
                 "it was inactive, explain why). Describing fundraising "
                 "activities here instead is a named CRA error.")
    if sec_c["active"] is True:
        for key, where in (("wound_up", "C18/line 1600"),
                           ("subordinate_to_head_body", "C19/line 1510")):
            if sec_c[key] is None:
                question = ("wound up, dissolved or terminated"
                            if key == "wound_up" else
                            "a subordinate of a head body")
                _finding(findings, "section_c", f"section_c.{key}",
                         "required_missing", None, None,
                         f"Question ({where}) — was the charity "
                         f"{question} during the fiscal period? — is "
                         f"unanswered.")

    # ---- complete-return parts -----------------------------------------
    if att["financial_statements_included"] is not True:
        _finding(findings, "attachments",
                 "attachments.financial_statements_included",
                 "financial_statements_missing",
                 att["financial_statements_included"], True,
                 "The financial statements are not marked as included. "
                 "A complete T3010 return always includes the charity's "
                 "financial statements, with the same fiscal year-end "
                 "as the return (T4033; CRA checklist).")
    if att["t1235_included"] is not True:
        _finding(findings, "attachments", "attachments.t1235_included",
                 "worksheet_missing", att["t1235_included"], True,
                 "Form T1235 (Directors/Trustees and Like Officials "
                 "Worksheet) is not marked as included. It is always "
                 "required with a T3010.")
    designation = charity["designation"]
    if designation in ("public foundation", "private foundation") \
            and att["schedule_1_included"] is not True:
        _finding(findings, "attachments", "attachments.schedule_1_"
                 "included", "schedule_missing",
                 att["schedule_1_included"], True,
                 f"Schedule 1 (Foundations) appears required because "
                 f"the designation is '{designation}', and it is not "
                 f"marked as included.")
    if sec_c["activities_outside_canada"] is True \
            and att["schedule_2_included"] is not True:
        _finding(findings, "attachments", "attachments.schedule_2_"
                 "included", "schedule_missing",
                 att["schedule_2_included"], True,
                 "Schedule 2 (Outside Canada) appears required because "
                 "question C4 (activities outside Canada) is answered "
                 "yes, and it is not marked as included.")
    if sec_c["employee_compensation"] is True \
            and att["schedule_3_included"] is not True:
        _finding(findings, "attachments", "attachments.schedule_3_"
                 "included", "schedule_missing",
                 att["schedule_3_included"], True,
                 "Schedule 3 (Compensation) appears required because "
                 "question C9 (compensation expenses) is answered yes, "
                 "and it is not marked as included.")
    if sec_c["paid_external_fundraisers"] is True \
            or sec_c["foreign_donations_10000"] is True:
        if att["schedule_4_included"] is not True:
            reasons = []
            if sec_c["paid_external_fundraisers"] is True:
                reasons.append("question C7 (paid external "
                               "fundraisers) is answered yes — "
                               "Schedule 4, Table 1")
            if sec_c["foreign_donations_10000"] is True:
                reasons.append("question C10 (a donation of $10,000 "
                               "or more from a non-resident donor) is "
                               "answered yes — Schedule 4, Table 2")
            _finding(findings, "attachments",
                     "attachments.schedule_4_included",
                     "schedule_missing", att["schedule_4_included"],
                     True,
                     "Schedule 4 appears required because "
                     + "; ".join(reasons) + ", and it is not marked "
                     "as included.")
    if sec_c["non_cash_gifts_receipted"] is True \
            and att["schedule_5_included"] is not True:
        _finding(findings, "attachments", "attachments.schedule_5_"
                 "included", "schedule_missing",
                 att["schedule_5_included"], True,
                 "Schedule 5 (Non-cash gifts) appears required because "
                 "question C11 (non-cash gifts for which receipts were "
                 "issued) is answered yes, and it is not marked as "
                 "included.")
    if sec_c["gifts_to_qualified_donees"] is True \
            and att["t1236_included"] is not True:
        _finding(findings, "attachments", "attachments.t1236_included",
                 "worksheet_missing", att["t1236_included"], True,
                 "Form T1236 (Qualified Donees / Amounts Provided to "
                 "Other Organizations Worksheet) appears required "
                 "because question C3 (gifts to qualified donees or "
                 "other organizations) is answered yes, and it is not "
                 "marked as included.")
    if sec_c["grantees_over_5000"] is True \
            and att["t1441_included"] is not True:
        _finding(findings, "attachments", "attachments.t1441_included",
                 "worksheet_missing", att["t1441_included"], True,
                 "Form T1441 (Qualifying Disbursements — Grants to "
                 "Grantees Worksheet) appears required because a "
                 "grantee received more than $5,000, and it is not "
                 "marked as included.")
    if sec_c["disbursement_quota_property"] is True \
            and att["schedule_8_included"] is not True:
        _finding(findings, "attachments", "attachments.schedule_8_"
                 "included", "schedule_trigger",
                 att["schedule_8_included"], True,
                 "Schedule 8 (Calculation of Quota) appears required "
                 "because question C17 (the disbursement-quota property "
                 "threshold) is answered yes, and it is not marked as "
                 "included. Check whether it applies — this is a "
                 "prompt, not a determination.")
    if designation == "private foundation" \
            and att["t2081_included"] is not True:
        _finding(findings, "attachments", "attachments.t2081_included",
                 "schedule_trigger", att["t2081_included"], True,
                 "Form T2081 (Excess Corporate Holdings Worksheet) "
                 "applies to private foundations, and it is not marked "
                 "as included. Check whether it applies to this "
                 "foundation — this is a prompt, not a determination.")

    # ---- financial mode --------------------------------------------------
    mode = fin["mode"]
    if mode is None:
        _finding(findings, "financials", "financials.mode",
                 "required_missing", None, None,
                 "financials.mode is blank — state 'section_d' or "
                 "'schedule_6' so the right cross-checks can run.")
    revenue_total = lines.get("4700")
    if mode == "section_d" and (
            fin["schedule_6_required"] is True
            or (revenue_total is not None
                and revenue_total > SCHEDULE_6_REVENUE_THRESHOLD)):
        if fin["schedule_6_required"] is True and not (
                revenue_total is not None
                and revenue_total > SCHEDULE_6_REVENUE_THRESHOLD):
            why = ("financials.schedule_6_required is marked true "
                   "(property not used in charitable activities over "
                   "$25,000, or permission to accumulate funds)")
        else:
            why = (f"total revenue (line 4700) is "
                   f"{fmt_money(revenue_total)}, over the $100,000 "
                   f"threshold")
        _finding(findings, "financials", "financials.mode",
                 "schedule_6_required", "section_d", "schedule_6",
                 f"Schedule 6 appears required because {why}, but the "
                 f"figures were supplied as Section D. Complete "
                 f"Schedule 6 instead of Section D — never both "
                 f"(T4033).")

    # ---- required lines and cross-footing --------------------------------
    if mode is not None:
        for number in ("4200", "4350", "4700", "4950", "5000", "5010",
                       "5100"):
            if lines.get(number) is None:
                _finding(findings, "financials", f"line {number}",
                         "required_missing", None, None,
                         f"Line {number} ({LINE_LABELS[number]}) is "
                         f"blank — the return's financial section must "
                         f"report it (enter 0 if the true amount is "
                         f"zero).")
    if fin["issued_receipts"] is True and lines.get("4500") is None:
        _finding(findings, "financials", "line 4500", "required_missing",
                 None, None,
                 "Line 4500 (total eligible amount of tax-receipted "
                 "gifts) is blank, but line 4490 says the charity "
                 "issued tax receipts. The two must agree.")
    if sec_c["grants_to_grantees"] is True and lines.get("5045") is None:
        _finding(findings, "financials", "line 5045", "required_missing",
                 None, None,
                 "Line 5045 (total grants to non-qualified donees) is "
                 "blank, but question C16 says the charity made grants "
                 "to grantees. Report the total (and see Form T1441).")
    if sec_c["gifts_to_qualified_donees"] is True \
            and lines.get("5050") is None:
        _finding(findings, "financials", "line 5050", "required_missing",
                 None, None,
                 "Line 5050 (total gifts to qualified donees) is "
                 "blank, but question C3 says the charity made such "
                 "gifts. Report the total.")
    if mode == "schedule_6" and sec_c["employee_compensation"] is True \
            and lines.get("4880") is None:
        _finding(findings, "financials", "line 4880", "required_missing",
                 None, None,
                 "Line 4880 (total expenditure on all compensation) is "
                 "blank, but question C9 says the charity had "
                 "compensation expenses. It is the Schedule 3 line 390 "
                 "total carried into Schedule 6.")

    if mode == "section_d":
        _sum_check(findings, lines, SECTION_D_REVENUE, "4700",
                   "Total revenue")
        _sum_check(findings, lines, SECTION_D_EXPENDITURES, "4950",
                   "Total expenditures")
    elif mode == "schedule_6":
        _sum_check(findings, lines, SCHEDULE_6_REVENUE, "4700",
                   "Total revenue")
        _sum_check(findings, lines, SCHEDULE_6_EXPENDITURES, "4950",
                   "Total expenditures")
        _sum_check(findings, lines, SCHEDULE_6_ASSETS, "4200",
                   "Total assets")
        _sum_check(findings, lines, SCHEDULE_6_LIABILITIES, "4350",
                   "Total liabilities")
        gov_parts = [lines.get(n) for n in ("4540", "4550", "4560")]
        if lines.get("4570") is not None and any(
                v is not None for v in gov_parts):
            computed = sum(v or 0 for v in gov_parts)
            if computed != lines["4570"]:
                _finding(findings, "financials", "line 4570",
                         "subtotal_mismatch", lines["4570"], computed,
                         f"Government revenue: line 4570 shows "
                         f"{fmt_money(lines['4570'])} but lines 4540 + "
                         f"4550 + 4560 add to {fmt_money(computed)}.")
    _sum_check(findings, lines, EXPENDITURE_BREAKDOWN, "4950",
               "Expenditures breakdown (lines 5000-5040 must equal "
               "line 4950)")
    parts_5100 = {n: lines.get(n) for n in ("4950", "5045", "5050")}
    if lines.get("5100") is not None and parts_5100["4950"] is not None:
        computed = (parts_5100["4950"] + (parts_5100["5045"] or 0)
                    + (parts_5100["5050"] or 0))
        if computed != lines["5100"]:
            _finding(findings, "financials", "line 5100",
                     "total_mismatch", lines["5100"], computed,
                     f"Total expenditures: line 5100 shows "
                     f"{fmt_money(lines['5100'])} but line 4950 "
                     f"({fmt_money(parts_5100['4950'])}) + line 5045 "
                     f"({fmt_money(parts_5100['5045'] or 0)}) + line "
                     f"5050 ({fmt_money(parts_5100['5050'] or 0)}) add "
                     f"to {fmt_money(computed)}.")

    # memo lines are subsets of their parent lines
    for memo, parent in (("4505", "4500"), ("4520", "4510"),
                         ("4525", "4510")):
        if lines.get(memo) is not None and lines.get(parent) is not None \
                and lines[memo] > lines[parent]:
            _finding(findings, "financials", f"line {memo}",
                     "memo_exceeds", lines[memo], lines[parent],
                     f"Line {memo} ({LINE_LABELS[memo]}) shows "
                     f"{fmt_money(lines[memo])}, more than line "
                     f"{parent} ({fmt_money(lines[parent])}) — but line "
                     f"{memo} is a part of line {parent}, not in "
                     f"addition to it.")
    if lines.get("4166") is not None and lines["4166"] > 0:
        _finding(findings, "financials", "line 4166",
                 "amortization_sign", lines["4166"], "negative or zero",
                 f"Line 4166 (accumulated amortization) shows "
                 f"{fmt_money(lines['4166'])}. Enter it as a negative "
                 f"amount — show a minus sign (T4033, Schedule 6).")

    # answers vs figures
    if sec_c["gifts_to_qualified_donees"] is False \
            and (lines.get("5050") or 0) > 0:
        _finding(findings, "financials", "line 5050",
                 "answers_inconsistent", lines["5050"], 0,
                 f"Line 5050 shows {fmt_money(lines['5050'])} of gifts "
                 f"to qualified donees, but question C3 is answered no. "
                 f"One of the two is wrong.")
    if sec_c["gifts_to_qualified_donees"] is True \
            and lines.get("5050") == 0:
        _finding(findings, "financials", "line 5050",
                 "answers_inconsistent", 0, "more than 0",
                 "Question C3 says the charity made gifts to qualified "
                 "donees, but line 5050 is 0.")
    if sec_c["grants_to_grantees"] is False \
            and (lines.get("5045") or 0) > 0:
        _finding(findings, "financials", "line 5045",
                 "answers_inconsistent", lines["5045"], 0,
                 f"Line 5045 shows {fmt_money(lines['5045'])} of grants "
                 f"to non-qualified donees, but question C16 is "
                 f"answered no. One of the two is wrong.")
    if sec_c["grants_to_grantees"] is True and lines.get("5045") == 0:
        _finding(findings, "financials", "line 5045",
                 "answers_inconsistent", 0, "more than 0",
                 "Question C16 says the charity made grants to "
                 "grantees, but line 5045 is 0.")
    if fin["issued_receipts"] is True and lines.get("4500") == 0:
        _finding(findings, "financials", "line 4500",
                 "answers_inconsistent", 0, "more than 0",
                 "Line 4490 says the charity issued tax receipts, but "
                 "line 4500 (eligible amount of receipted gifts) is 0.")

    # ---- receipt register tie-in -----------------------------------------
    register_cents = model["receipts"]["eligible_total_cents"]
    if register_cents is not None:
        if fin["issued_receipts"] is False and register_cents > 0:
            _finding(findings, "receipts", "receipts.eligible_total",
                     "receipts_mismatch", fmt_cents(register_cents),
                     "line 4490 = no",
                     f"The receipt register total supplied is "
                     f"{fmt_cents(register_cents)}, but line 4490 says "
                     f"the charity did not issue tax receipts. One of "
                     f"the two is wrong.")
        elif lines.get("4500") is not None \
                and register_cents != lines["4500"] * 100:
            _finding(findings, "receipts", "line 4500",
                     "receipts_mismatch", fmt_cents(register_cents),
                     fmt_money(lines["4500"]),
                     f"Line 4500 shows {fmt_money(lines['4500'])} of "
                     f"tax-receipted gifts, but the receipt register "
                     f"total supplied is {fmt_cents(register_cents)}. "
                     f"Difference: "
                     f"{fmt_cents(abs(register_cents - lines['4500'] * 100))}. "
                     f"Every receipted gift on the return must be in "
                     f"the register, and every eligible receipt in the "
                     f"register must be on line 4500.")

    # ---- financial statements tie-in -------------------------------------
    if fs["fiscal_year_end"] is not None and period_end is not None \
            and fs["fiscal_year_end"] != period_end:
        _finding(findings, "financial_statements",
                 "financial_statements.fiscal_year_end",
                 "statements_mismatch",
                 fs["fiscal_year_end"].isoformat(),
                 period_end.isoformat(),
                 f"The financial statements end "
                 f"{fs['fiscal_year_end'].isoformat()} but the return's "
                 f"fiscal year-end is {period_end.isoformat()}. The "
                 f"CRA requires the statements to have the same fiscal "
                 f"year-end as the return (CRA checklist).")
    for key, line_no, label in (
            ("total_revenue", "4700", "total revenue"),
            ("total_expenditures", "5100", "total expenditures"),
            ("total_assets", "4200", "total assets"),
            ("total_liabilities", "4350", "total liabilities")):
        stated = fs[key]
        if stated is not None and lines.get(line_no) is not None \
                and stated != lines[line_no]:
            _finding(findings, "financial_statements",
                     f"financial_statements.{key}",
                     "statements_mismatch", stated, lines[line_no],
                     f"The financial statements show {label} of "
                     f"{fmt_money(stated)}, but line {line_no} of the "
                     f"return shows {fmt_money(lines[line_no])}. "
                     f"Difference: {fmt_money(stated - lines[line_no])}.")

    # ---- T1235: directors --------------------------------------------------
    directors = model["directors"]
    if att["t1235_included"] is True and not directors:
        if model.get("directors_provided"):
            _finding(findings, "t1235", "directors", "required_missing",
                     0, "at least 1",
                     "Form T1235 is marked as included but the "
                     "directors list supplied is empty. The worksheet "
                     "must list every director/trustee/like official "
                     "who served during the fiscal period.")
        else:
            _finding(findings, "t1235", "directors",
                     "worksheet_detail_unchecked", None, None,
                     "Form T1235 is marked as included, but no director "
                     "rows were supplied in this data file (the CSV "
                     "format does not carry worksheet rows), so the "
                     "T1235 row-level checks were skipped — not passed. "
                     "Use the JSON format to check director details.")
    nal_names = []
    for person in directors:
        idx = person["index"]
        label = person["name"] if isinstance(person["name"], str) \
            and person["name"] else f"director #{idx}"
        for key, caption in (("name", "full name"),
                             ("position", "position"),
                             ("postal_code", "postal code")):
            if not (isinstance(person[key], str) and person[key]):
                _finding(findings, "t1235", f"directors[{idx}].{key}",
                         "required_missing", None, None,
                         f"T1235: {label} has no {caption}. The CRA "
                         f"checklist requires the worksheet to include "
                         f"each director's {caption}.")
        if person["start_date"] is None:
            _finding(findings, "t1235", f"directors[{idx}].start_date",
                     "required_missing", None, None,
                     f"T1235: {label} has no start date (date of "
                     f"appointment). The worksheet requires it.")
        if person["date_of_birth"] is None:
            _finding(findings, "t1235",
                     f"directors[{idx}].date_of_birth",
                     "required_missing", None, None,
                     f"T1235: {label} has no date of birth. The CRA "
                     f"checklist requires dates of birth for all "
                     f"directors/trustees/like officials.")
        if person["arms_length"] is None:
            _finding(findings, "t1235", f"directors[{idx}].arms_length",
                     "required_missing", None, None,
                     f"T1235: {label} has no arm's length status. The "
                     f"CRA checklist requires it for every director.")
        start, end = person["start_date"], person["end_date"]
        if start and end and end < start:
            _finding(findings, "t1235", f"directors[{idx}].end_date",
                     "director_dates", end.isoformat(), start.isoformat(),
                     f"T1235: {label} shows an end date "
                     f"({end.isoformat()}) before the start date "
                     f"({start.isoformat()}).")
        if start and period_end and start > period_end:
            _finding(findings, "t1235", f"directors[{idx}].start_date",
                     "director_dates", start.isoformat(),
                     period_end.isoformat(),
                     f"T1235: {label} shows a start date "
                     f"({start.isoformat()}) after the fiscal period "
                     f"end ({period_end.isoformat()}) — they did not "
                     f"serve during this return's period.")
        if end and period_start and end < period_start:
            _finding(findings, "t1235", f"directors[{idx}].end_date",
                     "director_not_serving", end.isoformat(),
                     period_start.isoformat(),
                     f"T1235: {label}'s term ended {end.isoformat()}, "
                     f"before this fiscal period began "
                     f"({period_start.isoformat()}). The worksheet "
                     f"lists directors who served during the period — "
                     f"check whether they belong on this return.")
        if person["arms_length"] is False:
            nal_names.append(label)
    if nal_names and sec_c["director_or_nal_compensation"] is False:
        _finding(findings, "t1235", "directors.arms_length",
                 "nal_director_prompt", ", ".join(nal_names),
                 "question C8 answered with these directors in mind",
                 f"T1235 lists {len(nal_names)} director(s) who are "
                 f"not at arm's length ({', '.join(nal_names)}), and "
                 f"question C8 (compensation to directors or "
                 f"non-arm's length persons) is answered no. If any of "
                 f"them — or any other non-arm's length person — was "
                 f"compensated, C8 must be yes. A prompt to check, not "
                 f"a determination.")

    # ---- T1236: qualified donees -------------------------------------------
    donee_total = 0
    any_donee_rows = False
    for row in model["t1236"]:
        idx = row["index"]
        reg = row["registration_number"]
        if isinstance(reg, str) and reg.strip() \
                and not REGISTRATION_RE.match(reg.strip()):
            _finding(findings, "t1236",
                     f"t1236[{idx}].registration_number",
                     "registration_number_format", reg,
                     "9 digits + RR + 4 digits",
                     f"T1236 row {idx}: registration number {reg!r} "
                     f"is not in the CRA format. The CRA checklist "
                     f"requires the registration number of every "
                     f"qualified donee on the worksheet.")
        if row["is_qualified_donee"] is not False \
                and row["total_gifts"] is not None:
            donee_total += row["total_gifts"]
            any_donee_rows = True
    if any_donee_rows and lines.get("5050") is not None \
            and donee_total != lines["5050"]:
        _finding(findings, "t1236", "t1236 total_gifts",
                 "donee_total_mismatch", donee_total, lines["5050"],
                 f"The T1236 rows for qualified donees add to "
                 f"{fmt_money(donee_total)}, but line 5050 shows "
                 f"{fmt_money(lines['5050'])}. Difference: "
                 f"{fmt_money(donee_total - lines['5050'])}.")

    # ---- Schedule 3: compensation -------------------------------------------
    sched3 = model["schedule_3"]
    if sched3 is not None:
        band_counts = [v for v in sched3["bands"].values()
                       if v is not None]
        if band_counts:
            band_total = sum(band_counts)
            if band_total > 10:
                _finding(findings, "schedule_3", "schedule_3.bands",
                         "bands_mismatch", band_total, 10,
                         f"The Schedule 3 band counts (lines 305-345) "
                         f"add to {band_total}, but the bands count only "
                         f"the ten highest compensated permanent "
                         f"full-time positions — the total cannot "
                         f"exceed 10.")
            positions = sched3["full_time_positions"]
            if positions is not None and band_total > positions:
                _finding(findings, "schedule_3", "schedule_3.bands",
                         "bands_mismatch", band_total, positions,
                         f"The Schedule 3 band counts add to "
                         f"{band_total}, more than the {positions} "
                         f"permanent full-time compensated positions "
                         f"reported at line 300.")
        total_comp = sched3["total_compensation"]
        if mode == "schedule_6" and total_comp is not None \
                and lines.get("4880") is not None \
                and total_comp != lines["4880"]:
            _finding(findings, "schedule_3",
                     "schedule_3.total_compensation",
                     "total_mismatch", total_comp, lines["4880"],
                     f"Schedule 3 line 390 (total compensation) shows "
                     f"{fmt_money(total_comp)}, but Schedule 6 line "
                     f"4880 shows {fmt_money(lines['4880'])}. Line 390 "
                     f"is carried into line 4880 — the two must agree.")

    # ---- Section E: certification -------------------------------------------
    if cert["signed"] is not True:
        _finding(findings, "certification", "certification.signed",
                 "certification_unsigned", cert["signed"], True,
                 "The return is not marked as certified and signed. "
                 "Section E of the T3010 must be signed by a director, "
                 "trustee or like official of the charity.")
    elif cert["signature_date"] is None:
        _finding(findings, "certification", "certification."
                 "signature_date", "required_missing", None, None,
                 "The return is marked signed but no signature date "
                 "was supplied — Section E includes the date signed.")

    section_order = {"section_a": 0, "section_c": 1, "financials": 2,
                     "receipts": 3, "financial_statements": 4,
                     "t1235": 5, "t1236": 6, "schedule_3": 7,
                     "attachments": 8, "certification": 9, "filing": 10}
    sev_rank = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (sev_rank[f["severity"]],
                                 section_order.get(f["section"], 99),
                                 f["field"], f["rule"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s)
              for s in SEVERITIES}
    return {
        "charity": {
            "name": name if isinstance(name, str) else None,
            "registration_number":
                reg if isinstance(reg, str) else None,
            "designation": designation,
            "fiscal_period_start":
                period_start.isoformat() if period_start else None,
            "fiscal_period_end":
                period_end.isoformat() if period_end else None,
            "financial_mode": mode,
        },
        "deadline": deadline,
        "summary": {"errors": counts["error"],
                    "warnings": counts["warning"],
                    "info": counts["info"]},
        "verdict": "FAIL" if counts["error"] else "PASS",
        "findings": findings,
    }


def compute_deadline(year_end: date, as_of: date | None,
                     filed: date | None) -> dict:
    due = add_months(year_end, 6)
    result = {
        "fiscal_year_end": year_end.isoformat(),
        "plus_months": 6,
        "due_date": due.isoformat(),
        "rule": "Income Tax Act s. 149.1(14): the T3010 is due within "
                "six months after the fiscal year-end. CRA examples: "
                "Dec 31 -> Jun 30, Mar 31 -> Sep 30, Jun 30 -> Dec 31. "
                "The CRA does not grant extensions. Verify against "
                "current CRA guidance.",
        "rules_checked": RULES_CHECKED,
        "sources": SOURCES,
        "sources_checked": SOURCES_CHECKED,
        "disclaimer": DISCLAIMER,
    }
    if as_of is not None:
        result["as_of"] = as_of.isoformat()
        result["days_remaining"] = (due - as_of).days
    if filed is not None:
        result["filed_date"] = filed.isoformat()
        result["filed_late_by_days"] = max(0, (filed - due).days)
        result["status"] = "filed_late" if filed > due else "filed_on_time"
    elif as_of is not None:
        result["status"] = "overdue" if as_of > due else "not_yet_due"
    return result


# ---------------------------------------------------------------------------
# rendering + CLI
# ---------------------------------------------------------------------------

def render_text(result: dict, source: str) -> str:
    out = []
    charity = result["charity"]
    title = charity["name"] or "(unnamed charity)"
    out.append(f"T3010 pre-flight check — {title}")
    out.append(f"Source file: {source}")
    out.append(f"Rules checked: {RULES_CHECKED} "
               f"(sources checked {SOURCES_CHECKED})")
    period = ""
    if charity["fiscal_period_start"] and charity["fiscal_period_end"]:
        period = (f" · fiscal period {charity['fiscal_period_start']} "
                  f"to {charity['fiscal_period_end']}")
    mode = f" · financials: {charity['financial_mode']}" \
        if charity["financial_mode"] else ""
    out.append(f"Designation: {charity['designation'] or '?'}{period}"
               f"{mode}")
    out.append("")
    summary = result["summary"]
    if result["verdict"] == "PASS":
        out.append(f"Verdict: PASS — no errors "
                   f"({summary['warnings']} warning(s), "
                   f"{summary['info']} note(s))")
    else:
        out.append(f"Verdict: FAIL — {summary['errors']} error(s), "
                   f"{summary['warnings']} warning(s), "
                   f"{summary['info']} note(s)")
    for severity, heading in (("error", "ERRORS"),
                              ("warning", "WARNINGS"),
                              ("info", "NOTES")):
        group = [f for f in result["findings"]
                 if f["severity"] == severity]
        if not group:
            continue
        out.append("")
        out.append(f"{heading} ({len(group)}):")
        for f in group:
            out.append(f"  [{f['rule']}] {f['field']}: {f['message']}")
    out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)


def render_rules(as_json: bool) -> str:
    payload = {
        "rules_checked": RULES_CHECKED,
        "sources": SOURCES,
        "sources_checked": SOURCES_CHECKED,
        "modelled_lines": LINE_LABELS,
        "checks": CHECKS,
        "disclaimer": DISCLAIMER,
    }
    if as_json:
        return json.dumps(payload, indent=2)
    out = [f"T3010 pre-flight checks (rules {RULES_CHECKED}; sources "
           f"checked {SOURCES_CHECKED}):", ""]
    for check in CHECKS:
        out.append(f"  {check['rule']} [{check['severity']}]")
        out.append(f"      {check['basis']}")
    out.append("")
    out.append("Modelled T3010 lines:")
    for number, label in LINE_LABELS.items():
        out.append(f"  {number}  {label}")
    out.append("")
    out.append("Sources:")
    for source in SOURCES:
        out.append(f"  - {source}")
    out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)


class _JsonAwareParser(argparse.ArgumentParser):
    """Argparse errors become {"error": ...} JSON in --json mode."""

    def error(self, message):
        if "--json" in sys.argv:
            print(json.dumps({"error": f"argument error: {message}"}))
        else:
            print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonAwareParser(
        prog="t3010_check",
        description="Pre-flight checks for a charity's own T3010 data: "
                    "completeness, internal consistency and filing "
                    "math. Not a CRA product; not tax advice.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser(
        "check", help="check a T3010 data file (.json or .csv)")
    p_check.add_argument("file", help="the data file to check")
    p_check.add_argument("--as-of", default=None,
                         help="check date for the deadline status "
                              "(YYYY-MM-DD; default: today)")
    p_check.add_argument("--json", action="store_true",
                         help="print one JSON object")

    p_deadline = sub.add_parser(
        "deadline", help="compute a filing deadline from a fiscal "
                         "year-end")
    p_deadline.add_argument("--year-end", required=True,
                            help="fiscal year-end (YYYY-MM-DD)")
    p_deadline.add_argument("--as-of", default=None,
                            help="optional check date (YYYY-MM-DD)")
    p_deadline.add_argument("--filed", default=None,
                            help="optional date the return was filed "
                                 "(YYYY-MM-DD)")
    p_deadline.add_argument("--json", action="store_true",
                            help="print one JSON object")

    p_rules = sub.add_parser(
        "rules", help="print the encoded checks, modelled lines and "
                      "sources")
    p_rules.add_argument("--json", action="store_true",
                         help="print one JSON object")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            as_of = parse_date(args.as_of, "--as-of") if args.as_of \
                else date.today()
            model = normalize(load_return(Path(args.file)))
            result = run_checks(model, as_of)
            result["rules_checked"] = RULES_CHECKED
            result["sources"] = SOURCES
            result["sources_checked"] = SOURCES_CHECKED
            result["disclaimer"] = DISCLAIMER
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(render_text(result, args.file))
            return 1 if result["summary"]["errors"] else 0
        if args.command == "deadline":
            year_end = parse_date(args.year_end, "--year-end")
            as_of = parse_date(args.as_of, "--as-of") if args.as_of \
                else None
            filed = parse_date(args.filed, "--filed") if args.filed \
                else None
            result = compute_deadline(year_end, as_of, filed)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                lines = [
                    f"Filing deadline for fiscal year-end "
                    f"{result['fiscal_year_end']}:",
                    f"  {result['fiscal_year_end']} + 6 months = due "
                    f"{result['due_date']}",
                    f"  Rule: {result['rule']}",
                ]
                if "days_remaining" in result:
                    lines.append(
                        f"  As of {result['as_of']}: "
                        f"{result['days_remaining']} day(s) remaining")
                if "status" in result:
                    lines.append(f"  Status: {result['status']}")
                lines.append("")
                lines.append(DISCLAIMER)
                print("\n".join(lines))
            return 0
        if args.command == "rules":
            print(render_rules(args.json))
            return 0
        parser.error(f"unknown command {args.command!r}")
        return 2
    except ToolError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
