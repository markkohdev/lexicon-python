---
name: lexicon-library-fix-agent
description: >-
  Finds and fixes DJ library metadata issues using the Lexicon CLI (list-tracks,
  search-tracks, bulk-update). Use when the user wants to clean Lexicon library
  metadata, fix missing artists, genres, titles, remix fields, or run an
  agent-driven export → analyze → propose JSON → dry-run → apply workflow.
---

# Lexicon library fix (agent workflow)

## Preconditions

- **Lexicon app / API** reachable (default `localhost:48624`). Set `--host` / `--port` or env if different.
- **CLI** from this repo: `uv run lexicon …` (or `lexicon` if installed on `PATH`).

## Workflow (always)

1. **Export** — Pull JSON so edits can target stable `id` values:

   ```bash
   uv run lexicon list-tracks --json -f title -f artist -f albumTitle -f genre -f remixer -f mix -f comment -f location
   ```

   Add/remove `-f` fields for the task. For large libraries, redirect to a file (e.g. `~/library-export.json`) and read that file instead of re-fetching.

2. **Detect** — Parse JSON; filter or cluster per the user’s goal (empty `artist`, bad titles, genre variants, etc.). Use heuristics, regex, and **web search** when titles are ambiguous.

3. **Propose** — Build a **JSON array** for `bulk-update`: each object has `"id": <int>` plus only the fields to change.

4. **Review** — Run **dry-run** and show the diff:

   ```bash
   uv run lexicon bulk-update --file /path/to/edits.json --dry-run
   ```

5. **Apply** — Only after explicit user approval (unless they already asked to apply):

   ```bash
   uv run lexicon bulk-update --file /path/to/edits.json --continue-on-error
   ```

6. **Verify** — Re-export or `search-tracks` on a sample to confirm.

## Edits file format

```json
[
  {"id": 101, "artist": "Example Artist"},
  {"id": 102, "title": "Clean Title", "remixer": "DJ Name", "mix": "Remix"}
]

```

Field names use **camelCase** (`albumTitle`, not `album`).

## Safety

- Prefer **small batches** (e.g. one issue type or one genre cluster at a time).
- **Never skip dry-run** before the first apply in a session unless the user explicitly waives it.
- If stdout includes build noise before `[`, parse JSON from the first `[` to the matching `]`, or use `2>/dev/null` when appropriate.
- **Low-confidence guesses**: list separately; do not bulk-apply without user sign-off.

## Extended examples and prompts

For task-specific prompts (missing artists, remix standardization, genre taxonomy), see [.cursor/plans/agent-library-cleanup-workflow.md](../../plans/agent-library-cleanup-workflow.md).
