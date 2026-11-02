# Retro Beaten 1.1.0 for Windows

Double-click `RetroBeaten.exe`. Keep the `_internal` folder beside it: it contains
Python, the required libraries, and their resources. You do not need to install
Python to use this distribution.

You can move the whole application folder and create a shortcut to the EXE.
To update, close the app and replace the entire application folder.

## Your collection

The executable stores data in `%LOCALAPPDATA%\RetroBeaten`. Paste that path into
the File Explorer address bar to open it.

- `data`: game database and recommendations cache.
- `assets`: covers and previews.
- `backups`: safety copies created before restoration and the initial migration backup.
- `.env`: local IGDB credentials.
- `logs/errors.log`: unexpected error diagnostics, when available.

Updating the program folder does not replace your collection. To move your shelf
to another computer, use **Backup and restore** and transfer the ZIP. IGDB
credentials are not included in collection backups or this distribution.

To configure online search on a new installation, create `.env` in the data
folder above and fill in your own credentials:

```dotenv
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
```

Restart the app after configuring the file. Saved games and manual registration
work offline without credentials.

The application interface is in English. Game names and descriptions keep their
original language. Native file pickers and system dialogs follow your Windows
display language.

## Development

Running `main.py` uses the project collection. Running the EXE uses the collection
in `%LOCALAPPDATA%\RetroBeaten`. They are independent; use Backup and restore to
transfer changes between them.

The optional command `RetroBeaten.exe --self-test path-to-report.json` tests the
package using temporary data, without contacting IGDB or changing your collection.
