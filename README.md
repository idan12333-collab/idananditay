# AI Photo Album — local MVP

Turn thousands of personal photos into a meaningful album. Current state: **Milestones 0–1**
(library ingestion, metadata, thumbnails, duplicates, quality signals, local UI).

## Run (Windows)
Double-click **`start.bat`**. First run creates a Python 3.12 environment in
`%USERPROFILE%\.ai-photo-album\venv` and installs dependencies; then the app opens at
http://127.0.0.1:8765.

Run tests: double-click **`run_tests.bat`**.

Developer mode: double-click **`start_dev.bat`** (instead of `start.bat` and the dashboard .bat).
It runs the app (8765) and the project dashboard (8790) and restarts them automatically when a
code file changes; the open page reloads itself (ADR-020). Close any normal app window first.

Manual:
```
py -3.12 -m venv %USERPROFILE%\.ai-photo-album\venv
%USERPROFILE%\.ai-photo-album\venv\Scripts\python -m pip install -r requirements-dev.txt
%USERPROFILE%\.ai-photo-album\venv\Scripts\python -m app serve            # web UI
%USERPROFILE%\.ai-photo-album\venv\Scripts\python -m app scan "D:\Photos" # CLI index + JSON summary
%USERPROFILE%\.ai-photo-album\venv\Scripts\python -m pytest -p no:cacheprovider
```
Demo/benchmark library (synthetic, no personal data):
`python scripts/make_sample_library.py OUT_DIR --count 1000`

## New machine setup (e.g. a second developer)
Windows 10/11. About 15 minutes, most of it downloads.
1. Install **Git for Windows** (https://git-scm.com/download/win) and **Python 3.12** from
   https://www.python.org/downloads/ (tick "Add python.exe to PATH"; the `py` launcher is included).
2. Get write access to the GitHub repo `idan12333-collab/idananditay` (the owner invites you).
3. Clone it to a folder **outside OneDrive/Dropbox**, e.g. `C:\dev\idananditay`:
   `git clone https://github.com/idan12333-collab/idananditay.git C:\dev\idananditay`
4. Set your own git identity once: `git config --global user.name "..."` and `user.email "..."`.
5. Double-click **`start.bat`** — the first run creates the Python environment and installs
   everything, then opens http://127.0.0.1:8765. Close it, then double-click **`run_tests.bat`**
   (all tests should pass on Windows).
6. Optional: `start_project_manager.bat` (dashboard on 8790) or `start_dev.bat` (both, auto-reload).
   The dashboard starts empty on a new machine (no `project_management/state.json`, no old
   Claude transcripts) until the Project Manager session writes its state.
7. No secrets are needed today. `.env` is optional — copy `.env.example` only to change defaults.
8. Test with a **copy** of a photo folder (a few hundred photos). Derived data is created in
   `%USERPROFILE%\.ai-photo-album\data`, never in the repo.
9. Install Claude Code and start the Project Manager as described in `HANDOFF_TO_ITAY.md`.

## Benchmarking
The 1,000-photo benchmark (M1: ~51 s to index 1,000 × 12 MP JPEGs) was useful, but **generating**
those 1,000 synthetic 12 MP photos took ~25 minutes — far longer than the scan itself.
For future benchmarks:
- **Reuse a persistent dataset** instead of regenerating: keep it outside the repo and outside OneDrive,
  e.g. `%USERPROFILE%\.ai-photo-album\benchmarks\sample_1000`, and generate it only if it is missing.
- Point the app at a **separate data dir** (`APP_DATA_DIR`) so benchmark results don't mix with real data.
  Re-index from scratch by deleting that data dir, not the dataset.
- If a new dataset is needed, prefer a cheaper setup: smaller images when resolution doesn't matter,
  or generate a few hundred base images and derive the rest (copies, resizes, crops).
- Record results (photos, resolution, workers, seconds per 1,000) in `MEMORY.md`.

## Where data lives
`%USERPROFILE%\.ai-photo-album\data` (SQLite `library.sqlite3`, `thumbnails/`, `logs/`).
Override with `APP_DATA_DIR`. Originals are **never modified**. "מחיקת נתוני אינדקס" in the UI
(`DELETE /api/libraries/{id}`) removes all derived data for a library. No image data leaves the computer.

## Layout
```
app/
  core/        config, structured logging
  db/          SQLite schema + repository (all SQL lives here)
  ingest/      scanner, metadata (EXIF/GPS/dates), hashing, imaging, analyzer (per file), duplicates, pipeline
  vision/      provider interfaces (embeddings, faces, aesthetics, captions, quality) + quality/classical.py
  retrieval/   VectorStore interface (Milestone 2)
  rendering/   AlbumRenderer + PrintProvider interfaces (Milestones 6–9)
  services/    background JobManager
  api/         FastAPI routes
  web/static/  local UI (HTML/JS/CSS, no build step)
tests/         pytest suite + synthetic fixture generator
scripts/       start.ps1, make_sample_library.py
```

## API (summary)
`GET /api/health` · `GET|POST /api/libraries` · `POST /api/libraries/{id}/scan` ·
`DELETE /api/libraries/{id}` · `GET /api/libraries/{id}/stats` · `GET /api/libraries/{id}/duplicates` ·
`GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` · `GET /api/photos?library_id&filter&year&sort&offset&limit` ·
`GET /api/photos/{id}` · `/thumbnail` · `/preview` · `POST /api/system/pick-folder`.
Interactive docs: http://127.0.0.1:8765/docs
