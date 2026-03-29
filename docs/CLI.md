# Lexicon CLI Documentation

The Lexicon CLI provides command-line access to your Lexicon DJ library. It allows you to query tracks, list available fields, and format results in multiple ways.

## Installation

The CLI is included with the `lexicon-python` package:

```bash
pip install lexicon-python
```

## Usage

The CLI is invoked via the `lexicon` command:

```bash
lexicon [OPTIONS] [COMMAND] [COMMAND_OPTIONS]
```

### Global options

- `--verbose` / `-v` — Write **DEBUG** logs from the `lexicon` package to stderr. Useful when an API call fails in a confusing way: for example, `PATCH /track` responses that the client cannot parse are logged as raw JSON (truncated if very large). Example:

```bash
lexicon --verbose bulk-update --file edits.json
```

### Connecting to the Lexicon API

Commands that talk to the running Lexicon app (`list-tracks`, `update-track`, `bulk-update`) use **localhost** and port **48624** by default. You rarely need to change this unless Lexicon runs elsewhere or uses a different port.

- `--host TEXT` — Hostname or IP for the Lexicon API (default: `localhost`)
- `--port INTEGER` — API port (default: `48624`)

You can also set defaults with environment variables so you do not repeat flags on every command:

- `LEXICON_HOST` — Default API host
- `LEXICON_PORT` — Default API port

```bash
export LEXICON_HOST=192.168.1.100
export LEXICON_PORT=48624
lexicon list-tracks -f title -f artist
```

Remote server in one shot (same flags on any API command):

```bash
lexicon list-tracks --host 192.168.1.100 --port 48624 -f title -f artist
```

### Available Commands

- `list-tracks` — List all tracks in the library with customizable output
- `list-fields` — Display available fields for entities (tracks, playlists, tags)
- `update-track` — Update a single track's fields by ID
- `bulk-update` — Apply batch edits to multiple tracks from a JSON/JSONL file

---

## list-tracks

List all tracks in your Lexicon library with flexible output formatting.

### Syntax

```bash
lexicon list-tracks [OPTIONS]
```

### Options

#### Field Selection

- `-f, --field TEXT` — Field(s) to display (can be used multiple times)
  - Default fields (if not specified and no format string): `title`, `artist`, `albumTitle`
  - Use `lexicon list-fields track` to see all available fields
  - Example: `-f title -f artist -f bpm`

#### Output Formatting

- `--format TEXT` — Format string for output (overrides `--field` option)
  - Use placeholders in curly braces: `{fieldName}`
  - Example: `--format "{title} - {artist} [{bpm} BPM]"`

- `--output-format [compact|table|pairs|json]` — Output format (default: `compact`)
  - `compact` — Simple list with track ID prefix (default)
  - `table` — ASCII table with columns
  - `pairs` — Key-value pairs, one track per block
  - `json` — Machine-readable JSON

- `--json` — Output as JSON (shorthand; overrides `--output-format`)

### Examples

#### List tracks with default fields (interactive selection)

```bash
lexicon list-tracks
```

This prompts you interactively to choose which fields to display.

#### List tracks with specific fields

```bash
lexicon list-tracks -f title -f artist -f bpm
```

#### List tracks in a table

```bash
lexicon list-tracks -f title -f artist -f bpm --output-format table
```

#### List tracks with custom format string

```bash
lexicon list-tracks --format "{title} - {artist} [{bpm} BPM]"
```

#### Export all track data as JSON

```bash
lexicon list-tracks --json -f title -f artist -f album -f bpm -f key -f genre
```

#### Use pairs format for detailed information

```bash
lexicon list-tracks -f title -f artist -f album -f bpm -f key --output-format pairs
```

---

## list-fields

Display available fields for a given entity type (tracks, playlists, or tags).

### Syntax

```bash
lexicon list-fields [ENTITY_TYPE] [OPTIONS]
```

### Arguments

- `ENTITY_TYPE` — Entity type to list fields for: `track`, `playlist`, or `tag` (default: `track`)

### Options

- `--sortable` — Show only fields that support sorting

### Examples

#### List all track fields

```bash
lexicon list-fields
```

or explicitly:

```bash
lexicon list-fields track
```

#### List sortable track fields

```bash
lexicon list-fields track --sortable
```

#### List playlist fields

```bash
lexicon list-fields playlist
```

#### List tag fields

```bash
lexicon list-fields tag
```

---

## update-track

Update a single track's fields by ID.

### Syntax

```bash
lexicon update-track --id TRACK_ID [--set FIELD=VALUE ...] [--edits JSON] [OPTIONS]
```

### Options

#### Edit Input (one required, mutually exclusive)

- `--set TEXT` — Field edits as `FIELD=VALUE` (can be used multiple times)
- `--edits TEXT` — Raw JSON string of edits (e.g. `'{"title": "New Title"}'`)

#### Other Options

- `--dry-run` — Preview changes without applying them (fetches current values and shows a diff)
- `--output-format [pairs|json|compact]` — Output format for the updated track (default: `pairs`)

### Editable Fields

`title`, `artist`, `albumTitle`, `label`, `remixer`, `mix`, `composer`, `producer`, `grouping`, `lyricist`, `comment`, `key`, `genre`, `rating`, `color`, `year`, `playCount`, `trackNumber`, `energy`, `danceability`, `popularity`, `happiness`, `extra1`, `extra2`, `tags`, `tempomarkers`, `cuepoints`, `incoming`, `archived`

### Examples

#### Update fields with --set

```bash
lexicon update-track --id 843 --set title="Rinse & The Night" --set genre="Bass House"
```

#### Update fields with --edits JSON

```bash
lexicon update-track --id 843 --edits '{"title": "Rinse & The Night", "genre": "Bass House"}'
```

#### Preview changes without applying (dry run)

```bash
lexicon update-track --id 843 --set title="Rinse & The Night" --dry-run
```

Output:

```
Track 843:
  title:  'Rinse & The Night [DanFX Mashup]'  →  'Rinse & The Night'

Summary: 1 track, 1 field change(s) (dry run — no changes applied)
```

#### Get JSON output after update

```bash
lexicon update-track --id 843 --set genre="Tech House" --output-format json
```

---

## bulk-update

Apply batch edits to multiple tracks from a JSON or JSONL file, with optional dry-run preview.

### Syntax

```bash
lexicon bulk-update --file PATH [OPTIONS]
```

### Options

#### Input

- `--file PATH` — Path to a JSON array or JSONL edits file, or `-` for stdin (required)

#### Behavior

- `--dry-run` — Parse and validate the file, fetch current values, and display a before/after diff without applying any changes
- `--continue-on-error` — If one update fails, log the error and continue to the next track (default: stop on first failure)
- `--output-format [summary|json|table]` — Output format (default: `summary`)
  - `summary` — Print success/failure counts only
  - `json` — Full results as a JSON array of `{id, status, result_or_error}` objects
  - `table` — Before/after diff view for each track

### Edits File Format

The edits file can be a JSON array or JSONL (one JSON object per line). Each entry must have an `id` (integer) and at least one field to edit:

```json
[
  {"id": 843, "title": "Rinse & The Night", "genre": "Bass House"},
  {"id": 844, "artist": "ZHU ft. 24kGoldn"},
  {"id": 845, "genre": "Tech House", "remixer": ""}
]
```

Or as JSONL:

```
{"id": 843, "title": "Rinse & The Night", "genre": "Bass House"}
{"id": 844, "artist": "ZHU ft. 24kGoldn"}
{"id": 845, "genre": "Tech House", "remixer": ""}
```

### Examples

#### Preview changes without applying (dry run)

```bash
lexicon bulk-update --file edits.json --dry-run
```

Output:

```
Track 843:
  title:  'Rinse & The Night [DanFX Mashup]'  →  'Rinse & The Night'
  genre:  ''  →  'Bass House'

Track 844:
  artist: 'Zhu ft 24kgoldn'  →  'ZHU ft. 24kGoldn'

Summary: 3 track(s), 4 field change(s) (dry run — no changes applied)
```

#### Apply changes

```bash
lexicon bulk-update --file edits.json
```

#### Continue past failures

```bash
lexicon bulk-update --file edits.json --continue-on-error
```

#### Pipe from stdin

```bash
cat edits.json | lexicon bulk-update --file -
```

#### Get detailed JSON output

```bash
lexicon bulk-update --file edits.json --output-format json
```

---

## Output Formats

### Compact (Default)

```
Listing all tracks in the library...
Found 3 track(s):

  [1] Title Track - Artist Name - 120 BPM
  [2] Another Song - Different Artist - 95 BPM
  [3] Third Track - Yet Another Artist - 128 BPM
```

### Table

```
Listing all tracks in the library...
Found 3 track(s):

title           | artist               | bpm
----------------+----------------------+-----
Title Track     | Artist Name          | 120
Another Song    | Different Artist     | 95
Third Track     | Yet Another Artist   | 128
```

### Pairs

```
Listing all tracks in the library...
Found 3 track(s):

Title: Title Track
Artist: Artist Name
BPM: 120

Title: Another Song
Artist: Different Artist
BPM: 95

Title: Third Track
Artist: Yet Another Artist
BPM: 128
```

### JSON

```json
[
  {
    "title": "Title Track",
    "artist": "Artist Name",
    "bpm": 120
  },
  {
    "title": "Another Song",
    "artist": "Different Artist",
    "bpm": 95
  },
  {
    "title": "Third Track",
    "artist": "Yet Another Artist",
    "bpm": 128
  }
]
```

---

## Common Field Names

The most commonly used track fields are:

- `title` — Track title
- `artist` — Artist name(s)
- `albumTitle` — Album name
- `bpm` — Beats per minute (tempo)
- `key` — Musical key
- `genre` — Genre classification
- `year` — Release year
- `duration` — Track length
- `rating` — User rating
- `comments` — Notes or comments

Use `lexicon list-fields track` to see the complete list of available fields.

---

## Troubleshooting

### "Connection refused" error

- Ensure Lexicon DJ is running with the Local API enabled
- Verify host and port match your Lexicon configuration (see [Connecting to the Lexicon API](#connecting-to-the-lexicon-api))
- Check your network connectivity if using a remote server

### "InquirerPy is required" warning

- Install InquirerPy: `pip install InquirerPy`
- Or use explicit field selection with `-f/--field` to skip interactive prompts

### Empty results

- Verify your Lexicon library contains tracks
- Check that you're connected to the correct API server
- Try `lexicon list-fields track` to verify the API is responding

### Field not found errors

- Use `lexicon list-fields track` to see available fields
- Check for typos in field names (they're case-sensitive)
- Ensure the field is available in your Lexicon version
