---
name: t3010-check
description: Pre-flight check a Canadian charity's T3010 Registered Charity Information Return data before filing — completeness against the CRA's published requirements (required lines, worksheets T1235/T1236/T1441, schedules 1/2/3/4/5, financial statements, signed certification), exact internal-consistency cross-footing (totals vs components, line 4500 vs the receipt-register total, return vs financial-statement totals), and the filing deadline (fiscal year-end + 6 months, Income Tax Act s. 149.1(14)). Use when a charity or preparer has drafted T3010 figures in a spreadsheet or export and wants the mechanical review done before the return is filed. The checks are ENCODED from the T3010 (24) form, the T4033 guide and the CRA's T3010 checklist, checked 2026-11-04 — a PASS means the data satisfies the encoded checks, never that the CRA will accept the return. Not a CRA product, does not file anything, and is not tax or legal advice.
---

# t3010-check — agent skill

## Purpose

Every Canadian registered charity files a T3010 every year, and the
defects that draw CRA attention are mostly mechanical: a required
worksheet missing, director details incomplete on the T1235, totals
that don't cross-foot, financial statements that don't match the
return, a deadline quietly missed. This tool checks a charity's own
T3010 data — entered once into a JSON or CSV file mirroring the
return's key lines and answers — and reports grouped ERROR / WARNING /
INFO findings with the field named and both numbers shown wherever
arithmetic disagrees. Pure Python standard library; local only; no
network code; reads the data file, writes nothing.

**The honesty core of this tool:** the checks are encoded data,
checked 2026-11-04, drawn from the CRA's published T3010 (24) form,
the T4033 guide and the CRA's own T3010 checklist. A PASS means the
data satisfies the checks *encoded in this tool* — never present it
as CRA compliance, CRA acceptance, or tax advice. Schedule triggers
that need judgement (Schedule 8, Form T2081, non-arm's-length
compensation) are WARNING prompts ("appears required because you
answered Y"), never determinations.

## When to use

- A T3010 draft exists as figures (spreadsheet, accounting export, or
  a preparer's worksheet) and someone asks "is this ready to file?"
- Before a board review or a professional review of the return — run
  the mechanical pass first so the human review is spent on judgement.
- To compute or verify a filing deadline from a fiscal year-end.
- After receipt-gate produces the year-end register: its eligible
  total is the `receipts.eligible_total` this tool ties to line 4500.

## Commands

```bash
python3 src/t3010_check.py check RETURN.json [--as-of YYYY-MM-DD] [--json]
python3 src/t3010_check.py check RETURN.csv  [--as-of YYYY-MM-DD] [--json]
python3 src/t3010_check.py deadline --year-end YYYY-MM-DD [--as-of YYYY-MM-DD] [--filed YYYY-MM-DD] [--json]
python3 src/t3010_check.py rules [--json]
```

Exit codes: **0** = no ERROR findings, **1** = at least one ERROR,
**2** = the input could not be read or parsed. `--json` prints exactly
one JSON object; input errors are `{"error": "…"}` (including argparse
errors) and never a traceback.

## The JSON contract

`check --json` returns one object:

- `charity` — name, registration number, designation, fiscal period,
  financial mode, as supplied
- `deadline` — `fiscal_year_end`, `due_date`, `rule`, `as_of`,
  `days_remaining`, `filed_date`, `status` (`filed_on_time`,
  `filed_late`, `overdue`, `not_yet_due`, `computed`)
- `summary` — `{"errors": n, "warnings": n, "info": n}`
- `verdict` — `PASS` when errors = 0, else `FAIL`
- `findings` — list of `{section, field, rule, severity, measured,
  limit, message}`, sorted errors first, then warnings, then info
- `rules_checked`, `sources`, `sources_checked`, `disclaimer`

`rules --json` returns the encoded check table (`checks`, each with
its CRA basis), the `modelled_lines` map, sources and disclaimer.

## Data model (summary)

JSON keys: `charity` (name, registration_number, designation,
fiscal_period_start/end), `financials` (`mode`: `section_d` |
`schedule_6`; `basis`; `issued_receipts`; `schedule_6_required`;
`lines` keyed by T3010 line number, whole dollars only),
`section_c` (the yes/no answers C1–C17 as modelled, plus
`programs_description`), `attachments` (one boolean per part),
`receipts.eligible_total` (may carry cents), `financial_statements`
(its totals + `fiscal_year_end`), `directors` (T1235 rows),
`t1236` (rows), `schedule_3` (line 300, `bands` 305–345, lines
370/380/390), `certification` (`signed`, `signature_date`,
`filed_date`). The CSV format carries the scalar fields and lines
only; worksheet-row checks then report themselves as skipped (INFO),
never as passed. Full field list: README.md.

## Behaviour rules for agents

- Report the verdict and counts exactly as returned; never soften a
  FAIL into "mostly fine" without the error list.
- Quote findings with their field names and both numbers — that is
  the actionable content.
- Keep the disclaimer attached to any summary you relay: not a CRA
  product, a clean run is not compliance, not tax advice, verify
  against current CRA guidance.
- Deadline answers must show the arithmetic (year-end + 6 months =
  due date) and the check date.
