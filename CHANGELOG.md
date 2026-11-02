# Changelog

## 1.1.0 — 2026-11-02

- Avoid checking every cover file during searches and sorting; validate visible thumbnails on refresh.
- Extend packaged diagnostics to sidebar navigation, favorites, native file drops, and process-based PNG export.

- Replace the top action toolbar with a persistent collapsible sidebar and an icon rail.
- Add direct shelf navigation with counts, keeping search above the library.
- Adopt graphite neutrals throughout the interface and exports while preserving status colors.
- Restore the selected shelf and sidebar layout after exhibition mode; keep sidebar scrolling independent.

- Match recommendations to individual favorite Beaten games using genres, themes, keywords, and perspective.
- Require meaningful shared evidence and filter weak matches before balancing platforms; return up to 20 without padding.
- Rotate close matches on refresh without placing novelty above substantially stronger affinity.
- Explain each recommendation with its closest favorite and actual shared metadata.
- Fetch related candidates separately and invalidate the old genre-only recommendation cache.

- Paint the visible shelves on one canvas to fix sliced covers and duplicated headers during Windows scrolling.
- Move retained covers together before yielding, preserving favorite clicks, menus, and wheel scrolling.
- Add window-local visual regression captures with cover-border pixel checks.

- Virtualize the desktop shelves: render only visible rows and a one-row scrolling margin.
- Release offscreen cards while preserving all collection records, actions, and exports.
- Extend stress checks with unique covers, active-card counts, and end-to-end scrolling.

- Reuse cover cards when changing cover size and avoid redundant favorite repainting.
- Stabilize panel geometry during batched updates and skip redundant grid measurements.
- Cancel window-owned timers on close, including delayed CustomTkinter callbacks.
- Add a synthetic UI stress runner using temporary data.

- Support PlayStation 3, Nintendo 3DS, and Nintendo Switch across the collection and IGDB search.
- Keep shelves accessible when covers are missing or damaged, using replaceable placeholders.

- PNG exports run in an isolated process with progress, cancellation, and atomic saving.
- Downsample covers before RGB conversion and use faster lossless PNG compression.
- Large shelves build in cancellable time slices to keep processing UI events.
- Skip wallpaper redraws when dimensions and darkness are unchanged.

- Favorite clicks update only the star and statistics, without rebuilding personal shelves.
- Sorting and collection edits reuse unchanged cover widgets within each section.
- Responsive layout callbacks are replaced and cancelled when a shelf changes.

- Collection overview with status totals, favorites, and platform bars filterable by status.

- Persistent gray/gold favorite stars on personal collection covers.
- Recommendations now use only favorite Beaten games linked to IGDB.
- Favorite-aware recommendation cache and stale-request protection.
- Backup format 2 preserves favorites and still imports version 1 archives.

- Unified dark collector theme, compact header, neutral controls, and gold primary actions.
- Original console line icons and subtle shelf dividers.
- Lightweight status-border highlights and delayed cover-name tooltips.
- Two-column game details with prominent artwork and clearer action hierarchy.

- Up to 20 recommendations balanced across platforms.
- Local wallpaper with adjustable darkness and persistent section ordering.
- Native cover file drops into the manual registration form.
- Random Wishlist picks without changing game status.
- Background PNG shelf exports for Beaten games or the entire collection.

- Reuse unchanged shelves and defer collapsed cover loading until expansion.
- Bound thumbnail memory with a 128-entry cache that detects changed cover files.

- Small, Medium, and Large covers with responsive centered rows.
- Persistent cover size, sorting, and expanded/collapsed shelf preferences.
- Sort each shelf by name or most recent addition.
- Exhibition mode with hidden tools; exit using the button or Escape.
- Correct the remaining status menu labels to English.

## 1.0.0 — 2026-10-30

First Windows desktop release of Retro Beaten.

- Visual game shelf with responsive, centered covers and collapsible sections.
- Platform sections and Beaten, Playing, Wishlist, and Dropped statuses.
- IGDB and manual registration, local search, and offline details.
- Name and description editing, cover replacement, and confirmed deletion.
- Recommendations across platforms based on completed games.
- SQLite storage and local covers.
- Collection backup and restoration in ZIP format.
- Windows executable with personal data stored outside the program folder.
- English interface, messages, comments, and documentation.
