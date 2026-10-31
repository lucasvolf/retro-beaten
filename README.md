# Retro Beaten

**Version 1.0.0** — a personal game shelf for Windows.

*A Collection of Adventures, Not Achievements.*

Display your completed games as a collection of covers. Keep track of what you
are playing, save games to your wishlist, and discover recommendations across
platforms. Built with Python, CustomTkinter, Pillow, and SQLite.

There are no completion percentages, rankings, or mandatory challenges.
Finish an adventure, add it to your shelf, and enjoy your collection.

## Run from source

Use Python 3.13 on Windows. In PowerShell, from the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe .\main.py
```

Set your own `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` in `.env` to enable online
search and recommendations. Manual registration and saved games work offline
without credentials. Do not commit your `.env` file.

The repository contains no personal collection. A new database is created on
first launch. Source runs store the database in `data/`, covers in `assets/`,
and credentials in `.env` at the project root. The app does not print the collection
to the console. Expected errors are displayed in the interface.

## Windows executable

Open `dist/RetroBeaten/RetroBeaten.exe` and keep `_internal` beside it. The
distribution includes Python and the required libraries. See [WINDOWS.md](WINDOWS.md)
for installation, updates, and IGDB configuration.

The executable stores its collection in `%LOCALAPPDATA%\RetroBeaten`, independently
of the program folder. Source runs continue to use the project collection.
These collections are independent; use Backup and restore to transfer changes.

Build the Windows distribution:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m scripts.build_windows
```

`RetroBeaten.spec` configures a console-free executable and includes CustomTkinter
resources. Personal databases, covers, backups, and credentials are not bundled.

For the initial transfer from development to the executable, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_to_windows
```

Migration copies games, covers, valid cached recommendations, and local credentials.
It preserves the source, creates an initial backup, and refuses to overwrite an
existing destination. Use the app's restoration feature for subsequent transfers.

## Using your shelf

- **Beaten:** completed games, grouped by platform, with gold borders.
- **Playing:** games in progress, with blue borders.
- **Wishlist:** games you want to play, with green borders.
- **Dropped:** unfinished games you chose to leave behind, with red borders.
- **Recommended:** suggestions based on your Beaten games, with gray borders.

Covers keep their proportions within a 150 × 200 display area. Rows adapt to the
window width and stay centered. Each shelf can be collapsed or expanded.
Left-click a cover for details; right-click it to change status.

**Search collection** filters saved games and cached recommendations by name,
ignoring case, accents, spaces, and punctuation. Clear restores the full view.

**Search IGDB** uses both game name and platform. Preview the result, choose a
status, and add it to the collection. Available platforms are PlayStation 1,
PlayStation 2, Nintendo DS, Game Boy Advance, PlayStation Portable, and PC.

**Add manually** accepts a name, platform, status, local PNG/JPEG/WebP cover, and
optional description. The original image is copied rather than moved or renamed.

In a saved game's details:

- **Edit game** changes its name and optional description locally. Saving updates
  the details, order, and current search results. Cancelling discards the edits.
  Renaming to another game's name on the same platform is blocked. Failed saves
  keep your text in the form for another attempt.
- **Change cover** previews a local image before saving it. Cancelling keeps the
  current cover. If saving fails, the previous cover remains available.
- **Delete game** asks for confirmation. Only that record and eligible app-managed
  cover copies are removed. Original images, legacy covers, and files referenced
  by another record are preserved. Locked files may remain for later cleanup.

Recommended games must first be added to Wishlist before they can be edited.
Your own names and descriptions are displayed as entered. Game metadata from
IGDB keeps the language supplied by the service. Native file pickers and system
dialogs follow the Windows display language.

## Recommendations

**Refresh recommendations** finds up to 12 games across supported platforms using
genres and similar games from your IGDB-registered Beaten collection. Each source
platform has equal weight. Manual games without an IGDB ID do not contribute to
the recommendation profile.

The selection excludes games already in your collection by ID or normalized name
and prefers new suggestions over the previous batch. Suggestions can repeat if
candidates run out. Variety depends on the games and covers available from IGDB.

Open a recommendation to see its details and why it was suggested. **Add to Wishlist**
saves a permanent copy. Refreshing recommendations never removes saved games.

Requests run in the background. Refreshing requires internet access; the last
successful list remains available offline in `data/recommendations.json`, with
covers in `assets/recommendations/`. Failed requests keep the previous list.

## Backup and restore

Choose **Backup and restore** in the header, then **Create backup** to export a ZIP.
It includes every saved game, status, platform, ID, description, and cover.
Credentials, previews, and recommendations are excluded.

**Restore backup** validates the archive and asks you to confirm replacement.
Collections are not merged. Before replacement, the app creates a backup of the
current collection in `backups/`. That copy can be restored using the same button.
Missing or invalid covers in the current collection must be fixed before this
safety backup can be created. Restoring an empty backup produces an empty shelf.

The interface remains responsive while collection edits and closing the backup
window are disabled. Restoration closes stale forms and reloads the shelf.
Restored covers receive new internal filenames. Previous covers remain on disk,
so repeated restorations can use additional space.

Backups contain `collection.json` (format version 1) and `covers/`. The service
validates records and images, checks cover hashes, and inserts records in one
SQLite transaction. It does not extract arbitrary ZIP paths or replace the
database with an external SQLite file. Limits are 10,000 games, 50 MB per cover,
20 MB of metadata, and 2 GB of uncompressed contents. Existing backup files are
replaced only after a new export completes.

Legacy databases are upgraded automatically. Extending the status constraint for
Wishlist first creates `data/retro_beaten.before_wishlist.db`. This migration copy
contains only the database; use ZIP backups for a complete collection backup.

## Code organization

```text
Retro Beaten/
├── main.py                       # Application entry point
├── RetroBeaten.spec              # Windows packaging configuration
├── retro_beaten/
│   ├── app.py                    # Application state and action coordination
│   ├── paths.py                  # Development and executable data locations
│   ├── platforms.py              # Platform labels and IGDB IDs
│   ├── statuses.py               # Status codes, labels, and border colors
│   ├── library.py                # Name search and legacy cover filenames
│   ├── error_reporting.py        # Unexpected error dialogs and logs
│   ├── diagnostics.py            # Isolated packaged-app self-test
│   ├── ui/                       # Windows, forms, shelf layout, and controls
│   ├── services/                 # Collection, IGDB, recommendations, backups
│   └── storage/database.py       # SQLite schema, migrations, and queries
├── scripts/                      # Build, migration, and API diagnostics
├── tests/                        # Tests using temporary data
├── assets/                       # Local covers and previews (not committed)
├── data/                         # Database and cache (not committed)
├── backups/                      # Automatic backups (not committed)
├── .env.example                  # Empty credentials template
├── requirements.txt              # Runtime dependencies
└── requirements-build.txt        # Packaging dependencies
```

`RetroBeatenApp` coordinates state and callbacks. For example:

```text
CoverWindow → RetroBeatenApp.change_cover
            → services.collection.replace_cover
            → storage.database.update_game_cover
            → refresh details and shelf
```

UI presentation, service rules, and storage queries remain separate.
Imports do not open windows, read credentials, or access the network.

## Tests and diagnostics

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.check_igdb
```

The tests use temporary databases and covers. Some create Tk windows.
The manual IGDB diagnostic queries Tekken 3 and saves a preview without adding
it to the collection. It deliberately prints diagnostic output.

Test the executable without changing your collection:

```powershell
& .\dist\RetroBeaten\RetroBeaten.exe --self-test "$PWD\build\smoke-test.json"
```

The self-test checks the interface, covers, SQLite, and backups using a temporary
collection without network access, then writes a JSON report. Unexpected errors
during normal use appear in a dialog and are saved to `logs/errors.log` in the
active data folder.
