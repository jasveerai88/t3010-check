# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** t3010-check's promise is "clone and
  run". Pull requests that add a third-party dependency will not be
  merged.
- **Local only.** No network calls, no telemetry, no uploads of user
  files. A charity's return data is sensitive; it never leaves the
  machine.
- **The checks are data, and they stay honest.** Every check lives
  in the `CHECKS` table and every modelled line in `LINE_LABELS` in
  `src/t3010_check.py`, and the README, SKILL.md and CHANGELOG state
  the same rules. Any change to a check, a threshold (the $100,000
  Schedule 6 trigger, the $5,000 T1441 test, the compensation-band
  limits) or the line list is a behaviour change: it needs all three
  documents, the changelog and the tests updated together, with the
  CRA source (form, guide or checklist) for the new value named in
  the pull request.
- **A PASS must never be worded as CRA compliance.** The honesty
  lines are load-bearing. Wording changes that soften "satisfies
  the encoded checks" into "the CRA will accept this return" will
  not be merged. The tool is a checking aid, not a CRA product and
  not tax advice — that stays in every output. Judgement calls
  (Schedule 8, T2081, arm's-length prompts) stay WARNINGs; do not
  promote a prompt into a determination.
- **The tool never invents an amount.** Checks reconcile the user's
  own numbers against each other; a check that would require
  estimating what a figure *should* be does not belong here.
- **Boundaries are pinned by hand.** A new or changed threshold
  needs tests at the threshold (passes) and one step past it
  (fails) — e.g. revenue $100,000 vs $100,001 — with expected counts
  derived from the form/guide, not copied from the tool's own
  output. The bundled faulty example's 22 errors / 4 warnings and
  the clean example's totals were computed by hand when the files
  were built; if a change moves them, the recount must be shown.

## Getting started

```bash
git clone https://github.com/jasveerai88/t3010-check
cd t3010-check
python3 -m unittest discover -s tests -v
python3 src/t3010_check.py check examples/clean-return.json --as-of 2026-03-20
python3 src/t3010_check.py check examples/faulty-return.json --as-of 2025-11-15
python3 src/t3010_check.py rules
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if the
   CLI output changes.
