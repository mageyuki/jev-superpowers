# OpenCode Zen System One

Use the OpenCode Console connection you already have for typed Jev decisions.
No additional TypeSafe key is needed. Python 3 (standard library only) is required.

From this fork's checkout:

```bash
export JEV_BACKEND=opencode-zen
python3 scripts/jev-systemone.py --check-backend
bash install.sh
python3 scripts/jev-systemone.py pick --question "Which backend is already connected?" \
  --options "opencode-zen,typesafe,laya" --state "OpenCode Console is connected."
```

On PowerShell, set `$env:JEV_BACKEND = 'opencode-zen'` and run `./install.ps1`.
The installers validate credentials before copying skills, without an HTTP call.
They do not persist backend selection: keep the environment in the agent session.
Keep the checkout available; installed skills refer to its client. From another
project, use the absolute path to `scripts/jev-systemone.py`.

## Selection and credentials

1. Explicit `JEV_BACKEND` wins: `opencode-zen`, `typesafe`, or `laya`.
2. Otherwise, a resolvable OpenCode Console credential selects Zen.
3. Otherwise, `TYPESAFE_BASE_URL` or `TYPESAFE_BACKEND=laya` selects the existing
   local path; the remaining default is TypeSafe with `TYPESAFE_API_KEY`.

Zen uses a non-empty `OPENCODE_API_KEY` first. Otherwise it reads, **read-only**,
the `key` field from the SQLite `credential.value` JSON for
`integration_id='opencode'`. Database path order:

- `JEV_OPENCODE_DB`, when set (an explicit empty store prevents real-store discovery);
- `opencode debug paths db`, when it prints an absolute path;
- `$XDG_DATA_HOME/opencode/opencode.db`, or `~/.local/share/opencode/opencode.db`.

Never print, copy into reports, or commit credentials. An absent/unreadable store
or missing key fails the explicitly selected Zen backend; it does not silently
switch to TypeSafe or guessing. `--check-backend` prints only the backend name;
it checks configuration, not remote key validity.

## Wire contract and commands

Zen calls `POST https://opencode.ai/zen/v1/systemone` with a Bearer Console key and
`User-Agent: opencode/jev-superpowers`. The default model is `jev-1.13-free`;
`JEV_MODEL=jev-1.13` overrides it. Redirects are refused to avoid forwarding keys.

```bash
python3 scripts/jev-systemone.py noul --question "Is the evidence sufficient?" --state "<sanitized evidence>"
python3 scripts/jev-systemone.py pick --question "Choose an approach" --options "a,b,c" --state "<constraints>"
python3 scripts/jev-systemone.py score --question "Rate clarity" --criteria "Unclear,Reasonable,Clear" --state "<proposal>"
```

Pick tokens are choice IDs. Score criteria become ordered numeric labels starting
at zero. The request contains `model`, `state`, and a single typed question with
`instructions` and, for pick/score, `criteria`.

Stdout contains only the selected answer JSON, retaining raw fields:
`{"type":"noul","noul":0.72}`, a choice with confidence/probabilities, or a score
with its separate confidence/legend/probabilities. There is no second confidence
mapping. Follow [the existing confidence bands](CONFIDENCE.md), and do not treat
a score as confidence. Missing credential, HTTP error, or missing answer returns
nonzero; errors omit server bodies and credentials. Sanitize state before cloud calls.

## Boundaries and offline verification

Zen covers **typed decisions only**. It does not replace `jev-scout` registry
searches, `git jev check`, or configure external guard/verification tools. Those
tools keep their own requirements. TypeSafe and [local Laya](FOSS_LAYA.md) remain
available; explicitly select `JEV_BACKEND=laya` to keep decisions local even when
Console is connected.

Run `bash scripts/test.sh`. Its installer negative check and Python contract tests
use temporary homes and isolated credential stores; they never rely on your real
key. `python3 scripts/test-systemone.py` runs the focused offline tests directly.
Live-network checks are deliberately not part of the committed test suite.
