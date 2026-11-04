# t3010-check — T3010 Pre-Flight Checker

Canada's ~86,000 registered charities file a **T3010 Registered Charity
Information Return** every year, and mistakes are dangerous: late or
defective returns can lead to penalties and revocation of registration.
A Canadian charity-law practice reports finding mistakes in *"probably
over 95% of the drafts we review."* The CRA's own T3010 checklist names
the recurring ones — incomplete director details on the T1235, financial
statements that are missing or don't match the return, returns filed
late. There is no cheap local pre-flight check: preparers eyeball a
long form, or pay professional fees.

**t3010-check is that pre-flight check.** Enter the return's key lines
and answers once into a small data file (JSON or CSV), and it runs the
checks a careful reviewer runs — completeness, internal consistency,
and the filing deadline — locally, offline, in seconds.

> **Honesty first:** this tool is **not** a CRA product. A clean run
> means the data satisfies the checks encoded here (drawn from the
> T3010 (24) form, the T4033 guide, and the CRA's own T3010 checklist,
> checked 2026-11-04) — it does **not** mean the return complies with
> the Income Tax Act. It is not tax or legal advice. Verify every
> figure against your records and current CRA guidance before filing.

## What it checks

**Completeness** — the parts the CRA itself requires for *this* return:

- Section A: charity name, registration number (format-checked:
  9 digits + `RR` + 4 digits), designation, fiscal period
- Section C: every question answered; C2 program description present
  (describing fundraising there is a named CRA error)
- Financial lines: 4200, 4350, 4700, 4950, 5000, 5010, 5100 — plus
  line 4500 when receipts were issued (4490 = yes), line 5045 when
  grants were made (C16 = yes), line 5050 when gifts to qualified
  donees were made (C3 = yes), line 4880 on Schedule 6 when the
  charity had compensation expenses (C9 = yes)
- Attachments: financial statements (always), Form T1235 (always),
  Schedule 1 (foundations), Schedule 2 (C4), Schedule 3 (C9),
  Schedule 4 (C7 / C10), Schedule 5 (C11), Form T1236 (C3),
  Form T1441 (a grantee over $5,000)
- Schedule 6 instead of Section D when total revenue exceeds
  $100,000 (checked at the boundary: $100,000 passes, $100,001 fires)
- Section E: the return is certified and signed, with a date
- T1235 rows: every director's name, position, start date, date of
  birth, arm's-length status and postal code (the CRA checklist names
  exactly these)

**Internal consistency** — exact arithmetic, both numbers always shown:

- Revenue components = line 4700; expenditure components = line 4950;
  the breakdown (lines 5000–5040) = line 4950;
  4950 + 5045 + 5050 = line 5100
- On Schedule 6: assets = line 4200, liabilities = line 4350,
  government revenue 4540 + 4550 + 4560 = line 4570,
  Schedule 3 line 390 = Schedule 6 line 4880
- Line 4500 vs. the receipt-register eligible total you supply
  (receipt-gate's register total drops straight in)
- Return totals vs. your financial-statement totals (4700, 5100, 4200,
  4350) and the statements' fiscal year-end vs. the return's
- T1236 qualified-donee rows = line 5050; Schedule 3 band counts ≤ 10
  and ≤ line 300; memo lines (4505, 4520, 4525) never exceed their
  parent lines; line 4166 entered as a negative

**Filing math** — the return is due **within six months after the
fiscal year-end** (Income Tax Act s. 149.1(14)). The tool computes the
deadline from your dates and shows the arithmetic, following the CRA's
own examples (Dec 31 → Jun 30, Mar 31 → Sep 30, Jun 30 → Dec 31 —
month-end year-ends land on the target month's last day). A filed date
after the deadline is an ERROR; an unfiled return past its deadline is
a WARNING. The CRA does not grant extensions — verify against current
CRA guidance.

**Prompts, never determinations** — some things can only be flagged:
Schedule 8 (C17 answered yes) and Form T2081 (private foundations) are
WARNINGs that say "appears required because you answered Y — check."
A non-arm's-length director on the T1235 while C8 is answered "no" is
the same kind of prompt.

Findings are grouped **ERROR / WARNING / INFO** with the field named.
Exit codes: **0** no errors, **1** at least one ERROR, **2** the input
itself could not be read (clean message, JSON in `--json` mode, never
a traceback).

## Input format

### JSON (full model)

```json
{
  "charity": {
    "name": "Exampleton Community Food Bank",
    "registration_number": "123456789RR0001",
    "designation": "charitable organization",
    "fiscal_period_start": "2025-01-01",
    "fiscal_period_end": "2025-12-31"
  },
  "financials": {
    "mode": "section_d",
    "basis": "accrual",
    "issued_receipts": true,
    "lines": {"4500": 48250, "4700": 74700}
  },
  "section_c": {"active": true, "gifts_to_qualified_donees": true},
  "attachments": {"financial_statements_included": true,
                  "t1235_included": true, "t1236_included": true},
  "receipts": {"eligible_total": "48250.00"},
  "directors": [{"name": "…", "position": "Chair",
                 "start_date": "2023-05-01",
                 "date_of_birth": "1980-04-12",
                 "arms_length": true, "postal_code": "V1Y 1A1"}],
  "certification": {"signed": true, "signature_date": "2026-03-15",
                    "filed_date": "2026-03-20"}
}
```

- `financials.mode` is `"section_d"` or `"schedule_6"`; `lines` is
  keyed by T3010 line number. Amounts are **whole dollars** (the T3010
  reports to the nearest dollar, no cents — the tool refuses cents
  rather than rounding silently). `receipts.eligible_total` is the one
  exception: it may carry cents, because a receipt register does.
- `directors` mirrors Form T1235; `t1236` mirrors Form T1236
  (`organization_name`, `registration_number`, `is_qualified_donee`,
  `total_gifts`); `schedule_3` mirrors Schedule 3 (`full_time_positions`
  = line 300, `bands` keyed by lines 305–345, `total_compensation` =
  line 390); `financial_statements` carries the statements' own totals
  and year-end for the tie-out.
- Unknown line numbers and malformed values are input errors (exit 2),
  never guesses.

### CSV (quick path)

A two-column `field,value` file: `charity.*`, `financials.*`,
`line.<number>`, `section_c.*`, `attachments.*`, `receipts.*`,
`financial_statements.*`, `certification.*`. The CSV format carries
scalar fields and lines only — director/donee row checks need JSON.
When a worksheet is marked included but its rows aren't in the file,
the tool says so (an INFO note: *skipped, not passed*) instead of
silently passing it. See `examples/clean-return.csv`.

## Usage

```bash
# Pre-flight a draft return (JSON or CSV)
python3 src/t3010_check.py check examples/clean-return.json --as-of 2026-03-20

# Just the deadline for a fiscal year-end
python3 src/t3010_check.py deadline --year-end 2025-03-31 --filed 2025-11-15

# The encoded checks, modelled lines and sources
python3 src/t3010_check.py rules
```

`--as-of` pins the check date for the deadline status (default: today).
No installation, no dependencies — Python 3.10+ standard library only.

### For agents and scripts

Every command accepts `--json` and prints exactly one JSON object.
Findings carry `section`, `field`, `rule`, `severity`, `measured`,
`limit` and `message`; the check result carries a `deadline` object
(`fiscal_year_end`, `due_date`, `status`) and a `summary` count.
Errors in `--json` mode are `{"error": "…"}` with exit code 2.
`SKILL.md` describes the agent contract.

## Real runs (verbatim)

Clean return — exit 0:

```console
$ python3 src/t3010_check.py check examples/clean-return.json --as-of 2026-03-20
T3010 pre-flight check — Exampleton Community Food Bank
Source file: examples/clean-return.json
Rules checked: 2026-11 (sources checked 2026-11-04)
Designation: charitable organization · fiscal period 2025-01-01 to 2025-12-31 · financials: section_d

Verdict: PASS — no errors (0 warning(s), 1 note(s))

NOTES (1):
  [filing_deadline] filing_deadline: Filing deadline: fiscal year-end 2025-12-31 + 6 months = due 2026-06-30 (Income Tax Act s. 149.1(14); CRA grants no extensions — verify against current CRA guidance). Filed 2026-03-20, 102 days before the deadline.

Pre-flight checks only. This tool is not a CRA product, a clean run does not mean the return complies with the Income Tax Act, and this is not tax or legal advice. Verify every figure against your records and check the current T3010 form, the T4033 guide and CRA guidance before filing.
```

Faulty return (fictional, one planted fault per rule) — exit 1,
**22 errors, 4 warnings**:

```console
$ python3 src/t3010_check.py check examples/faulty-return.json --as-of 2025-11-15
T3010 pre-flight check — Northwind Example Community Kitchen
Source file: examples/faulty-return.json
Rules checked: 2026-11 (sources checked 2026-11-04)
Designation: private foundation · fiscal period 2024-04-01 to 2025-03-31 · financials: schedule_6

Verdict: FAIL — 22 error(s), 4 warning(s), 0 note(s)

ERRORS (22):
  [registration_number_format] charity.registration_number: Registration number '12345678RR001' is not in the CRA format: the 9-digit business number, then RR, then a 4-digit reference number (e.g. 123456789RR0001).
  [programs_missing] section_c.programs_description: Question C2 is blank. The return must describe the charity's charitable programs in its own words (or, if it was inactive, explain why). Describing fundraising activities here instead is a named CRA error.
  [subtotal_mismatch] line 4570: Government revenue: line 4570 shows $25,000 but lines 4540 + 4550 + 4560 add to $30,000.
  [total_mismatch] line 4700: Total revenue: line 4700 shows $147,500 but its components add to $147,800 (4500 $95,000 + 4510 $8,000 + 4530 $1,500 + 4540 $20,000 + 4550 $10,000 + 4560 $0 + 4571 $0 + 4575 $500 + 4580 $2,200 + 4590 $0 + 4600 $0 + 4620 $800 + 4630 $6,000 + 4640 $3,500 + 4650 $300). Difference: $-300.
  [total_mismatch] line 4950: Expenditures breakdown (lines 5000-5040 must equal line 4950): line 4950 shows $152,000 but its components add to $151,900 (5000 $131,000 + 5010 $12,400 + 5020 $7,100 + 5030 $0 + 5040 $1,400). Difference: $100.
  [required_missing] line 5045: Line 5045 (total grants to non-qualified donees) is blank, but question C16 says the charity made grants to grantees. Report the total (and see Form T1441).
  [total_mismatch] line 5100: Total expenditures: line 5100 shows $158,300 but line 4950 ($152,000) + line 5045 ($0) + line 5050 ($9,000) add to $161,000.
  [receipts_mismatch] line 4500: Line 4500 shows $95,000 of tax-receipted gifts, but the receipt register total supplied is $94,000.00. Difference: $1,000.00. Every receipted gift on the return must be in the register, and every eligible receipt in the register must be on line 4500.
  [statements_mismatch] financial_statements.total_assets: The financial statements show total assets of $210,000, but line 4200 of the return shows $410,000. Difference: $-200,000.
  [statements_mismatch] financial_statements.total_revenue: The financial statements show total revenue of $147,800, but line 4700 of the return shows $147,500. Difference: $300.
  [required_missing] directors[2].date_of_birth: T1235: Marta Chen has no date of birth. The CRA checklist requires dates of birth for all directors/trustees/like officials.
  [required_missing] directors[2].postal_code: T1235: Marta Chen has no postal code. The CRA checklist requires the worksheet to include each director's postal code.
  [director_dates] directors[4].start_date: T1235: Elena Brooks shows a start date (2025-06-01) after the fiscal period end (2025-03-31) — they did not serve during this return's period.
  [financial_statements_missing] attachments.financial_statements_included: The financial statements are not marked as included. A complete T3010 return always includes the charity's financial statements, with the same fiscal year-end as the return (T4033; CRA checklist).
  [schedule_missing] attachments.schedule_1_included: Schedule 1 (Foundations) appears required because the designation is 'private foundation', and it is not marked as included.
  [schedule_missing] attachments.schedule_2_included: Schedule 2 (Outside Canada) appears required because question C4 (activities outside Canada) is answered yes, and it is not marked as included.
  [schedule_missing] attachments.schedule_3_included: Schedule 3 (Compensation) appears required because question C9 (compensation expenses) is answered yes, and it is not marked as included.
  [schedule_missing] attachments.schedule_5_included: Schedule 5 (Non-cash gifts) appears required because question C11 (non-cash gifts for which receipts were issued) is answered yes, and it is not marked as included.
  [worksheet_missing] attachments.t1236_included: Form T1236 (Qualified Donees / Amounts Provided to Other Organizations Worksheet) appears required because question C3 (gifts to qualified donees or other organizations) is answered yes, and it is not marked as included.
  [worksheet_missing] attachments.t1441_included: Form T1441 (Qualifying Disbursements — Grants to Grantees Worksheet) appears required because a grantee received more than $5,000, and it is not marked as included.
  [certification_unsigned] certification.signed: The return is not marked as certified and signed. Section E of the T3010 must be signed by a director, trustee or like official of the charity.
  [late_filing] certification.filed_date: The return was filed 2025-11-15, 46 days after the deadline 2025-09-30 (fiscal year-end 2025-03-31 + 6 months). The CRA does not grant extensions; a return that is not filed on time can lead to revocation of registration.

WARNINGS (4):
  [memo_exceeds] line 4520: Line 4520 (Specified gifts (included in line 4510)) shows $9,000, more than line 4510 ($8,000) — but line 4520 is a part of line 4510, not in addition to it.
  [nal_director_prompt] directors.arms_length: T1235 lists 1 director(s) who are not at arm's length (Elena Brooks), and question C8 (compensation to directors or non-arm's length persons) is answered no. If any of them — or any other non-arm's length person — was compensated, C8 must be yes. A prompt to check, not a determination.
  [director_not_serving] directors[3].end_date: T1235: Omar Haddad's term ended 2023-06-30, before this fiscal period began (2024-04-01). The worksheet lists directors who served during the period — check whether they belong on this return.
  [schedule_trigger] attachments.schedule_8_included: Schedule 8 (Calculation of Quota) appears required because question C17 (the disbursement-quota property threshold) is answered yes, and it is not marked as included. Check whether it applies — this is a prompt, not a determination.
```

Deadline only — exit 0:

```console
$ python3 src/t3010_check.py deadline --year-end 2025-03-31 --filed 2025-11-15
Filing deadline for fiscal year-end 2025-03-31:
  2025-03-31 + 6 months = due 2025-09-30
  Rule: Income Tax Act s. 149.1(14): the T3010 is due within six months after the fiscal year-end. CRA examples: Dec 31 -> Jun 30, Mar 31 -> Sep 30, Jun 30 -> Dec 31. The CRA does not grant extensions. Verify against current CRA guidance.
  Status: filed_late
```

## Modelled fields and their sources

Modelled from the **T3010 (24)** form, the **T4033** guide and the
**CRA's T3010 checklist** (canada.ca, checked 2026-11-04):

- **Section A** — name, registration number, designation, fiscal
  period (lines 1510/1600 answers modelled as Section C fields)
- **Section B/C answers** — C1 active, C2 programs, C3 gifts to
  qualified donees (line 2000), C4 outside Canada (line 2100), C7 paid
  external fundraisers, C8 director / non-arm's-length compensation,
  C9 employee compensation, C10 non-resident donations ≥ $10,000,
  C11 non-cash gifts receipted, C16 grants to grantees (line 5840,
  incl. the over-$5,000 test at line 5843), C17 disbursement-quota
  property (line 5850)
- **Section D** — lines 4020 (basis), 4050, 4200, 4350, 4400, 4490 and
  the revenue / expenditure / breakdown lines listed above
- **Schedule 6** — lines 4100–4180 (assets; line 4180 is detail, not
  part of the 4200 total, which adds lines 4100 to 4170), 4300–4350,
  4500–4700 (incl. memo lines 4505/4520/4525), 4800–4950; the other
  Schedule 6 conditions (property not used in charitable activities
  over $25,000 — lines 5900/5910 territory — or permission to
  accumulate funds) are carried by the `financials.schedule_6_required`
  flag the preparer sets
- **Schedule 3** — lines 300, 305–345, 370, 380, 390
- **Forms T1235, T1236, T1441, T2081; Schedules 1, 2, 3, 4, 5, 8** —
  presence and row-level checks as described above
- **Section E** — certification and signature

Not modelled: the C6 fundraising-method checkboxes, Schedule 2/5/8
internal detail, disbursement-quota computation, and anything that
would require the tool to judge an amount rather than reconcile the
charity's own numbers. The current form governs — line labels are
summarized from the sources above.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

39 tests. Every rule fires in both directions; every total and
deadline in the fixtures was computed by hand (the arithmetic is in
the test file's header comments) and is pinned, including the
$100,000 Schedule 6 boundary, the compensation-band limits, and all
three CRA deadline examples plus leap-year February. Error paths
assert exit code 2 with no traceback.

## Who it's for

Treasurers, bookkeepers and charity-law/accounting preparers who draft
the T3010 from a charity's own records and want the mechanical review
done before the return goes to the board or to CRA — the same audience
that runs receipt-gate on the donation side. Works for any of Canada's
~86,000 registered charities; the examples use fictional charities.

## Known limits

- The tool checks the data you give it. It cannot see the actual
  return, the financial statements, or the books — a wrong number
  entered consistently everywhere will pass.
- Completeness is judged against the CRA's published requirements as
  encoded here (checked 2026-11-04). Form versions change (T3010 (24)
  covers fiscal periods ending on or after December 31, 2023); check
  the current form.
- Schedule triggers that depend on judgement (Schedule 8, T2081, the
  non-arm's-length prompt) are warnings by design.
- It does not file anything, compute tax, or assess the disbursement
  quota — pre-flight only.

## Privacy

Local only. No network code (the test suite greps for it), no
telemetry, no uploads. A charity's return data never leaves the
machine it runs on.

## Support

If t3010-check saves your charity or your practice time, you can
sponsor its development on GitHub Sponsors — see
`.github/FUNDING.yml`. Issues and pull requests are welcome; see
`CONTRIBUTING.md`.

## Licence

MIT — see `LICENSE`.
