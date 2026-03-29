# Lexicon library fix (agent)

Use the **lexicon-library-fix-agent** skill and follow `.cursor/plans/agent-library-cleanup-workflow.md` for detailed prompts and examples.

## Goal

Describe the metadata issue to fix (or pick one): missing or placeholder artists, garbage title suffixes, genre/tag cleanup, remixer and mix fields, inconsistent artist spellings, etc.

## What to do

1. Read the **lexicon-library-fix-agent** skill (`.cursor/skills/lexicon-library-fix-agent/SKILL.md`).
2. If the users instructions are not clear, ask for clarification.
3. Run from the **lexicon-python** repo root with `uv run lexicon` (or `lexicon` if on PATH). Ensure the Lexicon API is running unless the user says otherwise.
4. **Export** library JSON with fields relevant to the issue (`list-tracks --json` and `-f …`). For big libraries, write to a file under the user’s home or project and read it.
5. **Analyze** the export; propose fixes with evidence (title, album, remixer, web lookup). Separate high-confidence vs uncertain rows.
6. Write proposed edits to a JSON file and run:

   `uv run lexicon bulk-update --file <path> --dry-run`

6. Summarize the diff for the user. **Apply** only if they confirm:

   `uv run lexicon bulk-update --file <path> --continue-on-error`

7. **Verify** with a targeted `search-tracks` or small re-export.

## Constraints

- Use **bulk-update** JSON shape: `[{"id": <int>, "<field>": "value", …}, …]`.
- Prefer incremental batches; do not mix unrelated cleanup types in one file without asking.
- When filenames look like `NN - Title` only, do not assume the prefix is an artist.
