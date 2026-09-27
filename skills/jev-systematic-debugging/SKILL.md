---
name: jev-systematic-debugging
description: Use when encountering any bug, test failure, or build error - enforces root-cause investigation using jev-axi triage for build errors and Jev Score for hypothesis ranking
---

# Jev Systematic Debugging: Root-Cause Investigation with Jev Triage

Enforces the Iron Law from `superpowers:systematic-debugging`:
```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

Symptom patches are failures. Every fix must address the verified root cause.

## The Debugging Phases

### Phase 1: Automated Failure Triage (`jev-axi triage`)
When tests or builds fail, do not guess at the error. Resolve the backend using
`jev-using-superpowers`. For TypeSafe/Laya, pipe compiler/test output into `jev-axi triage`:

```bash
cargo test 2>&1 | jev-axi triage
# or: npm test 2>&1 | jev-axi triage
```

`jev-axi triage` classifies the failure domain (syntax, type system, logic regression, flaky timing, environment) and identifies the exact failing boundary.

For **OpenCode Zen**, use a typed domain choice instead, from the retained checkout
(or use its absolute script path). Remove secrets and personal data from logs
before sending state to a cloud backend:

```bash
python3 scripts/jev-systemone.py pick --question "Which domain explains this failure?" \
  --options "syntax,type-system,logic-regression,flaky-timing,environment" \
  --state "<sanitized compiler/test output and relevant context>"
```

Report the live choice, confidence and probabilities. Apply the existing pick
bands in `docs/CONFIDENCE.md`: act at >= 0.80, confirm at 0.50–0.80, stop below
0.50. A domain choice does not identify an exact failing boundary by itself;
investigate the evidence before proposing a fix.

### Phase 2: Hypothesis Generation & Jev Scoring
Generate 2-3 plausible hypotheses for why the root failure occurred. For each hypothesis, score its plausibility given the error trace and recent git diff:

```bash
jev-axi check "Does this stack trace support the hypothesis: <hypothesis>?" --state "<stack trace & diff snippet>"
```

For **OpenCode Zen**, replace that check with:

```bash
python3 scripts/jev-systemone.py noul \
  --question "Does this stack trace support the hypothesis: <hypothesis>?" \
  --state "<sanitized stack trace and diff snippet>"
```

Report the raw live `noul` probability as p, not a fabricated confidence field.
For rubric scoring, use `python3 scripts/jev-systemone.py score --question
"<hypothesis quality>" --criteria "Unclear,Reasonable,Clear" --state "<evidence>"`.
Keep `score`, `confidence`, `legend`, and `probabilities` separate; a high score
does not substitute for p or override the existing hypothesis threshold.

Select the hypothesis with the highest verified probability ($p > 0.70$).
If all p values are below the threshold, collect more evidence; never blind-fix.
Missing Zen credential, HTTP failure, or missing answer: STOP, no silent fallback.
Zen covers typed decisions only; `jev-scout` registry search and `git jev check`
remain separate required tools, not Zen calls.

### Phase 3: Minimal Reproducing Test Case
Write the smallest possible failing test that triggers the bug. Run it to confirm it fails.

### Phase 4: Root-Cause Fix & Green Verification
Implement the fix at the root cause. Run the test suite to confirm green, then run regression checks across all callers.

## Failure Modes
See docs/CONFIDENCE.md for thresholds. When the gate tool is missing, the key is invalid, the registry is offline, or confidence falls below the Stop band: STOP, state which input failed, and never degrade to unverified guessing silently.
