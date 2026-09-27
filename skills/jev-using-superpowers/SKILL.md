---
name: jev-using-superpowers
description: Use when starting any non-trivial engineering conversation - establishes Jev-verified skill invocation, enforcing TypeSafe System One decisions, crate vetting, and completion gates
---

# Jev-Superpowers: Systematic Engineering with TypeSafe Jev

Upgrades the `superpowers` methodology by replacing LLM hallucinations and arbitrary guesswork with 70ms deterministic TypeSafe Jev System One judgments.

<EXTREMELY-IMPORTANT>
If a task involves planning, architecture, library selection, command execution, or debugging:
YOU MUST INVOKE THE CORRESPONDING JEV-SUPERPOWER.
</EXTREMELY-IMPORTANT>

## The Routing Matrix

| Phase | Standard Superpower | Jev-Superpower | Core Jev Enhancement |
|---|---|---|---|
| **Ideation / Architecture** | `brainstorming` | `jev-brainstorming` | OpenCode Zen: `python3 scripts/jev-systemone.py pick`; TypeSafe/Laya only: `jev-axi pick` trade-off convergence with calibrated confidence ($>0.80$) |
| **Implementation Plan** | `writing-plans` | `jev-writing-plans` | `jev-scout` zero-hallucination crate & repository verification |
| **Execution Loop** | `executing-plans` | `jev-executing-plans` | `jev-guard` command safety + `git-jev` pre-commit reflex gate |
| **Root-Cause Debugging** | `systematic-debugging` | `jev-systematic-debugging` | OpenCode Zen: `python3 scripts/jev-systemone.py` typed decisions; TypeSafe/Laya only: `jev-axi triage` error analysis + Jev `Score` hypothesis ranking |
| **Completion Gate** | `verification-before-completion` | `jev-verification` | `limpet` turn stop-hook + `supercov quality` anti-pattern scoring |

## Prerequisites
First resolve the decision backend from the retained **jev-superpowers checkout**:

```bash
python3 scripts/jev-systemone.py --check-backend
```

Use the checkout's absolute script path when working in another project. Installing
skills does not copy the client; keep the checkout available. Missing client: STOP.
The preflight prints only a backend name, never credentials, and makes no HTTP call.
`JEV_BACKEND=opencode-zen|typesafe|laya` wins; otherwise a non-empty
`OPENCODE_API_KEY` or stored OpenCode Console credential selects `opencode-zen`,
then the existing TypeSafe/Laya environment rules apply.

For **OpenCode Zen**, Python 3 and a resolved Console key are valid prerequisites;
no second TypeSafe key is needed. Run `python3 scripts/jev-systemone.py`
(`noul`, `pick`, or `score`) for System One decisions, as shown in the decision
skills. The default model is `jev-1.13-free`; override with `JEV_MODEL`.
Never print credentials or database rows. See `docs/OPENCODE_ZEN.md` for resolution.

Other gates still require their local Jev tooling:
- `jev-scout` on PATH (`cargo install jev-scout`)
- `jev-axi` on PATH for the TypeSafe/Laya decision path (`npm install -g jev-axi`)
- `git-jev` on PATH (`git jev install`)
- `jev-guard` on PATH
- `supercov` on PATH (`npm install -g supercov`)
- TypeSafe: valid `$TYPESAFE_API_KEY` (Free tier from `https://console.typesafe.ai`)
- Laya: local bridge configured via `$TYPESAFE_BASE_URL` or `$TYPESAFE_BACKEND=laya`

If the **selected backend's** credential is missing, its live call fails, or its
answer is missing: **STOP IMMEDIATELY**. For Zen, ask the user to connect OpenCode
Console or securely set `OPENCODE_API_KEY`, not obtain a second TypeSafe key.
Never silently fall back to another backend or unverified LLM guessing.

Zen covers **typed decisions only**. It does not implement `jev-scout` registry
search, `git jev check`, or reconfigure external guard/verification tools. Keep
those gates and their own prerequisites; missing gate tooling still STOPs.
Report live answer fields unchanged and apply `docs/CONFIDENCE.md`; do not invent
a confidence field from a `score` or `noul` value.

## Failure Modes
See docs/CONFIDENCE.md for thresholds. When the gate tool is missing, the key is invalid, the registry is offline, or confidence falls below the Stop band: STOP, state which input failed, and never degrade to unverified guessing silently.
