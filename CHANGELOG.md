# Changelog

## v0.1.0 — 2026-11-04

First release. `t3010-check` is the local, offline pre-flight check
for a Canadian charity's T3010 (Registered Charity Information
Return) data — the mechanical review (completeness, internal
consistency, filing deadline) done before the return is filed,
built from the T3010 (24) form, the T4033 guide and the CRA's own
T3010 checklist (sources checked 2026-11-04).

- `check RETURN.json|RETURN.csv [--as-of YYYY-MM-DD] [--json]` with
  grouped ERROR / WARNING / INFO findings and exit codes 0/1/2:
  - **Completeness** — Section A fields and registration-number
    format (9 digits + RR + 4 digits); Section C answers and the C2
    program description; required lines (4200, 4350, 4700, 4950,
    5000, 5010, 5100) plus conditional lines 4500 (receipts issued),
    5045 (grants made), 5050 (gifts to qualified donees), 4880
    (Schedule 6 compensation); always-required financial statements
    and Form T1235; answer-driven parts — Schedule 1 (foundations),
    Schedule 2 (C4), Schedule 3 (C9), Schedule 4 (C7/C10),
    Schedule 5 (C11), Form T1236 (C3), Form T1441 (grantee over
    $5,000); Schedule 6 required instead of Section D when revenue
    exceeds $100,000 or the preparer's Schedule-6 flag is set;
    Section E certification signed and dated; T1235 director rows
    complete (name, position, start date, date of birth, arm's
    length status, postal code).
  - **Internal consistency** — exact cross-footing with both numbers
    shown: revenue/expenditure components vs lines 4700/4950, the
    5000–5040 breakdown vs 4950, 4950 + 5045 + 5050 vs 5100; on
    Schedule 6 the asset (4200) and liability (4350) sums and the
    government subtotal (4540 + 4550 + 4560 = 4570); Schedule 3
    line 390 vs Schedule 6 line 4880; line 4500 vs the supplied
    receipt-register eligible total; return totals vs the supplied
    financial-statement totals and year-end; T1236 donee rows vs
    line 5050; Schedule 3 band counts (≤ 10, ≤ line 300); memo lines
    (4505/4520/4525) vs their parents; line 4166 sign; answers that
    contradict the figures.
  - **Filing math** — deadline = fiscal year-end + 6 months
    (Income Tax Act s. 149.1(14)), computed with the CRA's own
    examples (month-end year-ends land on the target month's last
    day); filed-late is an ERROR with the day count, overdue-unfiled
    a WARNING.
  - **Prompts, not determinations** — Schedule 8 (C17) and Form
    T2081 (private foundations) as WARNINGs; a non-arm's-length
    director with C8 answered "no" as a WARNING.
- `deadline --year-end YYYY-MM-DD [--as-of] [--filed] [--json]` —
  the deadline arithmetic on its own.
- `rules [--json]` — the encoded check table with the CRA basis for
  every check, the modelled-lines map, sources and check date.
- `--json` on every command: one JSON object, `{"error": …}` input
  errors with exit 2, no tracebacks anywhere.
- Examples: a clean fictional return (JSON + CSV) and a faulty
  fictional return with one planted fault per rule — 22 errors and
  4 warnings, every count and total computed by hand in the test
  file. 39 tests, all passing, boundaries pinned both directions.
- Not a CRA product; a clean run is not compliance; not tax advice.
  The disclaimer ships in the README, SKILL.md and every output.
