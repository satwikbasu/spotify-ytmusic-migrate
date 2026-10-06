---
name: migration-context
description: >-
  Load FIRST before writing or changing any code, spec, extension, or UI in the
  spotify-ytmusic-migrate repo. Grounds the work in the product's goal (seamless
  two-login background migration of up to 50k tracks for non-technical users,
  local-only), the DECIDED architecture (extension + Native Messaging for YouTube
  Music; Spotify BYO-Client-ID-PKCE wizard preferred with web-session-capture
  fallback; shard at 5k; real resume; background survival), the invariants that
  must not break, and the context-loss review rubric. Use whenever the task
  touches auth, the extension/bridge, the Flet UI, the engine (fetch/search/
  match/migrate), rate limiting, packaging, or the migration flow.
---

# migration-context

You are working on **spotify-ytmusic-migrate**: a local desktop app that migrates
a non-technical user's Spotify library to YouTube Music, up to ~50k tracks,
passively in the background over hours, on the user's own machine.

## Before you write anything, read these three files in full

1. `docs/CONTEXT_CONTRACT.md` — the single source of truth: goal, user persona,
   platform reality, DECIDED architecture (with evidence), what already exists,
   the invariants, and the review rubric. **This overrides your assumptions.**
2. `CLAUDE.md` — repo conventions and architecture layers.
3. `HANDOFF.md` — the proven "dead ends." Treat them as settled; never re-attempt.

## The non-negotiables (full list in CONTEXT_CONTRACT.md §6)

- Optimise for **UX seamlessness**, not code reuse. When a choice adds a user
  step to save code, the user wins. The target feel: click Login with Spotify →
  Connect YouTube Music → select playlists → Start → walk away.
- The user is non-technical: **no typed tokens, no JSON edits, no DevTools, no
  terminal steps** may appear in any user-facing flow.
- Branch `prototype/extension-bridge`. `flet` pinned to 0.28. Every API call
  through `RateLimiter`. Local-only, no credential custody, encrypt at rest.
  Tests under `tests/`. No model identifier in committed artifacts.
- YouTube Music = extension cookie capture via Native Messaging (no OAuth, no
  "without extension"). Spotify = BYO Client ID + PKCE wizard (default) /
  in-page web-session capture (opt-in fallback).
- Desktop only (Win/mac/Linux). No native mobile engine.

## Before you hand back

Self-check against the review rubric in `docs/CONTEXT_CONTRACT.md §7`. If your
deliverable trips any item, fix it before handing back. State explicitly which
contract sections your work advances and confirm you did not trip the rubric.
Add/adjust tests under `tests/` for any code you changed. If you changed a
decision, update `docs/CONTEXT_CONTRACT.md` first with the reason.
