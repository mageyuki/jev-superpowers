---
name: jev-brainstorming
description: Use before any creative architecture, feature design, or stack selection - explores requirements, generates 2-3 approaches, and uses TypeSafe Jev (jev-axi pick) to converge on the optimal technical decision
---

# Jev Brainstorming: Systematic Design with Typed Convergence

Inherits all requirements exploration and collaborative dialogue rules from `superpowers:brainstorming`, but eliminates ungrounded LLM guessing on architectural tradeoffs using TypeSafe Jev System One.

## The Workflow

### 1. Classify Scope
- **Spike**: Quick feasibility question. 2-3 sentences in chat.
- **Bounded**: Modifying an existing, readable flow. Short design in chat.
- **Architectural**: New subsystem, stack choice, or major refactor. Full process with written spec.

### 2. Divergent Exploration
- Ask the 1-2 clarifying questions that matter most.
- Identify the core tension (latency vs simplicity, SQLite vs Postgres, sync vs async).
- Present 2-3 viable technical approaches with honest pros and cons.

### 3. Jev Convergence Gate (MANDATORY)
Before recommending an approach or asking the user to decide, resolve the backend
using `jev-using-superpowers`. For TypeSafe/Laya, run `jev-axi pick`:

```bash
jev-axi pick "<Tradeoff Question>" \
  --options "<opt1>,<opt2>,<opt3>" \
  --text "<Context, constraints, user persona, latency & memory targets>"
```

For **OpenCode Zen**, run the in-repo client instead, from the retained checkout
(or use its absolute script path):

```bash
python3 scripts/jev-systemone.py pick --question "<Tradeoff Question>" \
  --options "<opt1>,<opt2>,<opt3>" \
  --state "<Context, constraints, user persona, latency & memory targets>"
```

Option tokens are the choice IDs. Zen returns live `choice`, `confidence`, and
`probabilities`; report these unchanged, not a guessed or remapped confidence.
Missing credential, HTTP failure, or missing answer: STOP, with no silent fallback.
Zen replaces only this typed decision, not registry search or `git jev check`.

**Evaluation Rules:**
1. **Report Live Jev Output**: State the picked option, its probability distribution, and calibrated confidence score.
2. **Confidence Threshold**:
   - `Confidence >= 0.80` (Band: `act`): Present as the strongly recommended choice.
   - `0.50 <= Confidence < 0.80` (Band: `confirm`): Explain why the tradeoff is close and explicitly ask the human partner to break the tie.
   - `Confidence < 0.50` (Band: `stop`): Gather requirements; do not recommend action. These are the existing bands in `docs/CONFIDENCE.md`.
3. **Ponytail Check**: If one option is standard library or already-installed dependency, bias the context toward Rung 3/5.

### 4. Human Approval Gate
Present the Jev-scored recommendation in chat. Do NOT touch code or write implementation plans until the human partner says "yes" or selects an alternative.

## Failure Modes
See docs/CONFIDENCE.md for thresholds. When the gate tool is missing, the key is invalid, the registry is offline, or confidence falls below the Stop band: STOP, state which input failed, and never degrade to unverified guessing silently.
