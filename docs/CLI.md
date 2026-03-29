# Lexicon CLI

Command-line access to your Lexicon DJ library (query tracks, inspect fields, update metadata). Install with the package:

```bash
pip install lexicon-python
```

## Invocation

```bash
lexicon [OPTIONS] [COMMAND] [COMMAND_OPTIONS]
```

| Global | Description |
|--------|-------------|
| `-v`, `--verbose` | DEBUG logs for the `lexicon` package on stderr (e.g. unparsable API responses as truncated raw JSON). |
| `--host TEXT` | API host (default `localhost`; override with `LEXICON_HOST`). |
| `--port INTEGER` | API port (default `48624`; override with `LEXICON_PORT`). |

API commands (`list-tracks`, `search-tracks`, `update-track`, `bulk-update`) target localhost:48624 unless you set flags or env vars.

```bash
lexicon list-tracks --host 192.168.1.100 --port 48624 -f title -f artist
```

## Commands

| Command | Purpose |
|---------|---------|
| `list-tracks` | List library tracks; interactive field pick if you omit fields. |
| `search-tracks` | Filter/sort via API; same display options as `list-tracks`. |
| `list-fields` | Show fields for `track` / `playlist` / `tag`. |
| `update-track` | Patch one track by id (`--set` or `--edits`). |
| `bulk-update` | Batch edits from JSON or JSONL. |

---

## Shared: track listing output

Used by **`list-tracks`** and **`search-tracks`** (unless noted).

| Option | Description |
|--------|-------------|
| `-f`, `--field TEXT` | Columns (repeat). Without `-f` or `--format`: interactive picker (InquirerPy; otherwise `title`, `artist`, `albumTitle`). `--json` alone still prompts—add `-f` to skip. |
| `--format TEXT` | Line template with `{fieldName}` placeholders; overrides `-f`. |
| `--output-format` | `compact` (default), `table`, `pairs`, or `json`. |
| `--json` | JSON rows; shorthand for `--output-format json`. |

`compact`: `[id] …fields…`. `table`: ASCII columns. `pairs`: one block per track. `json`: array of objects.

---

## list-tracks

```bash
lexicon list-tracks [OPTIONS]
```

Examples:

```bash
lexicon list-tracks
lexicon list-tracks -f title -f artist -f bpm --output-format table
lexicon list-tracks --format "{title} - {artist} [{bpm} BPM]"
lexicon list-tracks --json -f title -f artist -f album -f bpm -f key -f genre
```

---

## search-tracks

```bash
lexicon search-tracks [OPTIONS]
```

Uses the same **track listing output** options as above. Connection: `--host`, `--port`.

| Option | Description |
|--------|-------------|
| `--filter TEXT` | `FIELD=VALUE` (repeat). Only the first `=` splits key/value. Examples: `artist="Daft Punk"`, `bpm=120`, `bpm="120-128"`, `bpm=">=120"`, `dateAdded="2024-01-01"`, `tags="Rock, Chill"` or `tags="~Rock, !Chill"`. |
| `--sort TEXT` | `FIELD:dir` (repeat); `dir` defaults to `asc`. With no `--sort`: `title:asc`. |
| `--source` | `non-archived` (default), `all`, `archived`, or `incoming`. |


### Filter semantics
- **Unknown keys:** Unknown field keys are ignored. 
- **Strings:** case-insensitive substring match (`artist=Punk` can match `Daft Punk`). 
- **Numeric-like fields:** sent as strings; Lexicon parses comparisons/ranges (e.g. `>`, `>=`, `120-128`); see the Lexicon manual for full operator syntax.
- **`location`:** normalized to Lexicon’s unique path form (Unicode- and case-normalized; on macOS often under `/Volumes/...`) before match.
- **Large result sets:** if the API returns 1,000 tracks, the CLI warns that results may be capped—narrow filters.

Examples:

```bash
lexicon search-tracks --filter artist="Daft Punk" --sort title:asc \
  -f title -f artist -f bpm --output-format table
lexicon search-tracks --filter bpm="120-128" -f title -f artist -f bpm
lexicon search-tracks --filter genre="House" --json -f title -f artist -f genre
lexicon search-tracks --source archived --filter title="Acid" -f title -f artist
```

---

## list-fields

```bash
lexicon list-fields [ENTITY_TYPE] [OPTIONS]
```

`ENTITY_TYPE`: `track` (default), `playlist`, or `tag`. `--sortable` limits to sortable fields.

```bash
lexicon list-fields
lexicon list-fields track --sortable
lexicon list-fields playlist
lexicon list-fields tag
```

---

## update-track

```bash
lexicon update-track --id TRACK_ID (--set FIELD=VALUE ... | --edits JSON) [OPTIONS]
```

Provide **either** `--set` (repeat) **or** `--edits` (JSON string), not both.

| Option | Description |
|--------|-------------|
| `--dry-run` | Show diff vs current track; no write. |
| `--output-format` | `pairs` (default), `json`, or `compact`. |

**Editable fields:** `title`, `artist`, `albumTitle`, `label`, `remixer`, `mix`, `composer`, `producer`, `grouping`, `lyricist`, `comment`, `key`, `genre`, `rating`, `color`, `year`, `playCount`, `trackNumber`, `energy`, `danceability`, `popularity`, `happiness`, `extra1`, `extra2`, `tags`, `tempomarkers`, `cuepoints`, `incoming`, `archived`

```bash
lexicon update-track --id 843 --set title="Rinse & The Night" --set genre="Bass House"
lexicon update-track --id 843 --edits '{"title": "Rinse & The Night", "genre": "Bass House"}'
lexicon update-track --id 843 --set title="Rinse & The Night" --dry-run
lexicon update-track --id 843 --set genre="Tech House" --output-format json
```

---

## bulk-update

```bash
lexicon bulk-update --file PATH [OPTIONS]
```

`--file` is required; use `-` for stdin.

| Option | Description |
|--------|-------------|
| `--dry-run` | Validate, fetch currents, print diffs; no writes. |
| `--continue-on-error` | Keep going after a failed row (default: stop on first error). |
| `--output-format` | `summary` (default), `json` (per-id status objects), or `table` (per-track diffs). |

**File:** JSON array or JSONL. Each object needs `id` (int) and at least one field to change:

```json
[
  {"id": 843, "title": "Rinse & The Night", "genre": "Bass House"},
  {"id": 844, "artist": "ZHU ft. 24kGoldn"}
]
```

```bash
lexicon bulk-update --file edits.json --dry-run
lexicon bulk-update --file edits.json
lexicon bulk-update --file edits.json --continue-on-error
cat edits.json | lexicon bulk-update --file -
lexicon bulk-update --file edits.json --output-format json
```

---

## Common track fields

`title`, `artist`, `albumTitle`, `bpm`, `key`, `genre`, `year`, `duration`, `rating`, `comment` — full list: `lexicon list-fields track`.

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| Connection refused | Lexicon running with Local API on; host/port; network if remote. |
| InquirerPy required | `pip install InquirerPy`, or pass `-f` or `--format` to skip the picker (`--json` still prompts unless you add `-f`). |
| Empty results | Library has tracks; correct server; try `lexicon list-fields track`. |
| Unknown field | Typos are case-sensitive; run `list-fields`; confirm Lexicon version. |
