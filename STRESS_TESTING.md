# UI stress testing

Run from the project root with the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.stress_ui --games 200
```

The runner creates temporary images and synthetic records, never opens the personal database, and exercises initial rendering, 100 favorite changes, sorting, window resizing, cover sizing, rapid searches, and scrolling to both ends of the shelf. It prints elapsed time, active card counts, and the longest gap between Tk heartbeat callbacks. Measurements include a short settling period. The favorite scenario intentionally changes 100 records without yielding; it is not the latency of one click or a database benchmark.

Use `--games 500` for an extreme single-shelf workload and `--trace` to print diagnostic stacks during long runs. Run benchmarks without the test suite or other heavy workloads concurrently. Timers can be delayed by Tk itself, so an unresponsive run may need to be stopped from its terminal.

## Findings (2026-11-01)

- The 200-card baseline completed all scenarios without callback exceptions. Changing cover size took 10.13 seconds including settling; the largest heartbeat gap was 0.95 seconds in that scenario.
- A 500-card shelf exposed substantial layout stalls. Some runs failed to finish changing cover size in a reasonable time and were stopped. This was the pre-virtualization implementation; see the new results below.
- Changes reuse card widgets when resizing covers, skip unchanged star painting and redundant grid measurements, preserve mapped cards during reorder, and stabilize panel geometry during incremental updates.
- Window-owned timers are cancelled when dialogs close. This includes timers scheduled internally by CustomTkinter, while retaining timers owned by other windows.

These findings led to the viewport-based rendering implementation described below.

## Earlier polishing validation

- The complete suite passed: 97 tests. An intermittent Tcl callback warning still occurred during test teardown; it is not considered fully resolved.
- In the final isolated 200-card run, cover resizing took 7.72 seconds including settling, versus 10.13 seconds in the earlier run. Its largest heartbeat gap dropped from 0.95 to 0.43 seconds. These are local synthetic observations, not guaranteed timings.
- The executable and personal collection were not modified.
- Exporting 200 synthetic covers completed in 3.72 seconds, with a maximum Tk heartbeat gap of 19.5 ms.

## Initial viewport rendering (2026-11-01)

The initial viewport implementation reserved the full shelf height but created widgets only for visible rows
and one extra row above/below. Scrolling releases offscreen cards. Hidden/collapsed
shelves do not keep cards alive. The synchronous renderer remains available for
small isolated rendering tests; the desktop uses the viewport renderer.

Commands for the new stress coverage:

```powershell
.\.venv\Scripts\python.exe -m scripts.stress_ui --games 1000 --unique-covers 1000
```

The isolated run completed every scenario, including assertions that the first and
last sorted records are present at the corresponding scroll positions. No callback
exceptions or phase timeouts occurred. Covers were distinct temporary image files.

| Scenario | Total seconds (includes settling) | Longest heartbeat gap (ms) | Active cards |
| --- | ---: | ---: | ---: |
| Initial display | 2.412 | 445.9 | 30 |
| 100 favorite changes | 0.477 | 72.6 | 30 |
| Sort | 2.119 | 305.8 | 30 |
| Resize window | 0.549 | 333.5 | 16 |
| Change cover size | 1.967 | 302.7 | 30 |
| Rapid consecutive searches | 2.293 | 815.1 | 30 |
| Scroll to bottom | 1.454 | 175.9 | 28 |
| Scroll to top | 1.309 | 162.8 | 30 |

These are local synthetic measurements, not guaranteed timings. Rapid searches can
still briefly block the UI; virtualization bounds widget count, but does not move
image decoding or every Tk operation off the UI thread. Export/statistics continue
to use all records and are independent of viewport visibility.


## Single-surface scrolling correction (2026-11-01)

The initial viewport tests checked positions and active cards but missed a visible
Windows repaint defect: moving native child windows left strips of covers and
headers behind. A window-local capture reproduced the defect during motion even
when the final settled image was correct.

The desktop now draws covers, borders, favorite stars, and headers as items on a
single fixed canvas. Logical section spacers still supply the scroll range. Each
refresh moves all retained cards before yielding; new images are loaded in short
batches. Only nearby rows retain image objects.

The same isolated 1,000-game/1,000-cover stress command completed without callback
exceptions or timeouts after this correction:

| Scenario | Total seconds (includes settling) | Longest heartbeat gap (ms) | Active cards |
| --- | ---: | ---: | ---: |
| Initial display | 2.115 | 360.7 | 30 |
| 100 favorite changes | 0.405 | 11.0 | 30 |
| Sort | 1.712 | 291.2 | 30 |
| Resize window | 0.446 | 282.8 | 16 |
| Change cover size | 1.644 | 293.1 | 30 |
| Rapid consecutive searches | 1.510 | 733.9 | 30 |
| Scroll to bottom | 1.131 | 19.1 | 28 |
| Scroll to top | 0.606 | 25.4 | 30 |

Heartbeat gaps measure event-loop responsiveness, not frame rate. Search bursts
and layout changes can still pause briefly; these results do not imply that every
operation is stall-free.

Run the visual regression on Windows:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_scroll_visual
```

It opens a temporary synthetic library, captures only that test window during
scrolling and after settling, and checks visible cover-border pixels. Captures are
written to the ignored `build/scroll-visual` folder. The final run passed all pixel
checks; visual inspection also confirmed aligned covers and section headers during
motion. It does not access the personal collection.

The complete suite passed 108 tests, including canvas favorite/detail clicks,
mouse-wheel routing, empty searches, collapsed sections, exhibition mode, resizing,
and reaching both ends of tall shelves. The previously observed intermittent Tcl
`after` warning still appeared during suite teardown; it remains a separate issue.
The executable was not rebuilt.


## Release 1.1.0 validation (2026-11-02)

The desktop no longer checks every cover file during a search or sort. It compares
record metadata and validates file signatures for nearby thumbnails when refreshing
the viewport, including replacements made at the same path.

In isolated 1,000-game / 1,000-cover runs, the largest heartbeat gap during the
rapid-search burst fell from 659.2 ms to 214.1 ms; sorting fell from 299.0 ms to
26.7 ms. Scroll-to-end gaps stayed below 19 ms. These are local measurements;
initial layout and size changes can still pause for several hundred milliseconds.

A separate full-application runner creates temporary SQLite records and distinct
cover files, switches shelves repeatedly, tests search, favorites, sidebar sizing,
exhibition, dialog cleanup, PNG export, backup, and restoration:

```powershell
.\.venv\Scripts\python.exe -m scripts.stress_app --games 1000 --cycles 15
```

The final run completed without callback errors, timeouts, or resource-growth
assertion failures. All 1,000 records, cover files, and the changed favorite were
preserved by the backup/restore round trip. Reports are written under ignored
`build/`. The harness does not read the personal collection or contact IGDB.

| Operation | Seconds (includes settling) | Longest heartbeat gap (ms) |
| --- | ---: | ---: |
| startup | 1.398 | 785.9 |
| favorite | 1.837 | 436.7 |
| search | 0.787 | 133.7 |
| sidebar | 0.568 | 388.7 |
| large covers | 1.225 | 516.3 |
| scroll bottom | 1.939 | 172.5 |
| scroll top | 0.748 | 22.4 |
| export | 11.537 | 11.1 |
| backup | 5.047 | 16.9 |
| restore | 17.335 | 22.4 |
| reload restored | 1.737 | 50.8 |

After warm-up and 15 navigation cycles, private memory changed from 73.2
to 72.6 MB. Tcl image count remained 48, command count
1020, and pending timer count 3. This is a bounded regression
check, not proof that every possible usage pattern is leak-free. Opening ten
detail dialogs in sequence also completed without delayed callback errors.

The release regression suite passed all 131 tests. Scroll and sidebar visual
checks passed, including moving cover-border checks. The 1.1.0 PyInstaller
distribution passed its own `--self-test`: backup, restore, sidebar, favorites,
exhibition, details, native file-drop support, and process-based PNG export.
The self-test used temporary data; the personal collection was not modified.
