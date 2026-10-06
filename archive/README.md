# Archive — historical material, NOT current

⚠️ **Do not treat anything in this directory as accurate or actionable.**
It is preserved only for history. For current context read `HANDOFF.md` and
`CLAUDE.md` at the repo root.

## `troubleshooting-notes/`

Notes written by the original developer during the YouTube-auth debugging.
**Several are now known to be wrong.** In particular, every note describing an
OAuth fix (the "TVs and Limited Input devices" client, the "rewrite complete"
claims, the ACTION_REQUIRED credential steps) describes an approach that was
later proven dead: YouTube Music's internal API rejects OAuth tokens from custom
Google Cloud clients with HTTP 400, regardless of client type. The working auth
path is browser cookies — see `bridge/` and `HANDOFF.md`.

## `scratch-scripts/`

Ad-hoc probe scripts from that same debugging (`test_*.py`, `debug_*.py`,
`diagnose_*.py`). They are **not** part of the test suite — the real tests live
under `tests/`. Kept for reference only; do not extend them.
