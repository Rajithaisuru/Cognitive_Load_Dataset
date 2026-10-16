# Cognitive Load Data Collection System - Project Handover

Last reviewed: 2026-10-17

## 1. Project overview

This final-year research project collects anonymous behavioral data while learners watch educational videos. Its eventual goal is to train and evaluate a cognitive-load classifier, but the current participant interface is intended for real-data collection rather than live model inference.

- Project title: Cognitive Load Prediction System for Online Learning Using Behavioral Patterns
- Group ID: R26-SE-004
- Researcher: Subasinghe M.H.R.I. (IT22089786)
- Institution: Sri Lanka Institute of Information Technology
- Current stage: deployed data collection plus a locally implemented model-evaluation workflow awaiting deployment

## 2. Technology and architecture

- Frontend: one standalone HTML/CSS/JavaScript file, `data_collection.html`
- Backend: Python FastAPI application under `app/`
- Validation: Pydantic request models
- Database: MySQL through `mysql-connector-python`
- Data processing: pandas and scikit-learn are retained for legacy prediction/training code
- Video delivery: public Cloudinary video URLs loaded directly by the browser
- Local data copy: append-only CSV files under `data_backups/`
- Model format: Joblib `.pkl`, retained for later work and legacy endpoints

Current request flow:

```text
Participant browser
  -> consent and anonymous session creation
  -> Cloudinary video playback
  -> browser-side interaction counters
  -> two-minute feature-window API request
  -> Paas rating API request
  -> Aiven MySQL plus local CSV copies
  -> joined training dataset/export
```

Cloudinary serves video directly to each participant, so the application server does not carry the video-streaming bandwidth.

## 3. Important files and directories

- `data_collection.html`: participant UI, consent, lesson selection, video tracking, Paas prompt, and API calls
- `app/main.py`: FastAPI application, CORS middleware, and router registration
- `app/api/routes.py`: HTTP endpoints
- `app/core/database.py`: `.env` loading and MySQL connections
- `app/core/model_loader.py`: loads the Joblib model when imported
- `app/schemas/`: Pydantic request schemas
- `app/services/db_service.py`: MySQL inserts, queries, joins, and dataset population
- `app/services/csv_backup_service.py`: append-only CSV copies
- `app/services/paas_service.py`: Paas-to-cognitive-load mapping
- `app/services/raw_feature_service.py`: feature extraction from stored raw events
- `app/services/prediction_service.py`: legacy inference and prediction logging
- `scripts/train_cognitive_load_model.py`: six-feature Random Forest training script
- `sql/mysql_schema.sql`: full database schema
- `sql/feature_windows_6_columns_migration.sql`: removes five old feature columns
- `model/training_report.txt`: report from a previous model experiment
- `.env.example`: environment-variable template
- `.gitignore`: excludes credentials, environments, local data exports, and model binaries
- `README.md`: currently contains only `"Hello"`

## 4. Implemented participant experience

1. A participant-consent modal opens on page load.
2. Consent must be checked before a participant code can be generated.
3. The API generates a code consisting of `P` plus five uppercase letters/digits and a millisecond-based session ID.
4. The participant chooses L101 or L102. Changing the lesson before starting clears an already generated code.
5. Starting the session locks the participant, lesson, and consent controls.
6. The first video play starts a 120-second wall-clock feature window.
7. The browser counts pauses, navigation, backward navigation/rewatch, playback-rate changes, idle duration, and time on content.
8. No interaction for 30 seconds starts idle time; the duration is added when activity resumes or the window ends.
9. At the end of the window, the video pauses and the Paas 1-9 panel appears.
10. Submitting a rating sends the feature window first and the Paas record second.
11. The next window starts and the video resumes.

The `minute_index` values advance as `1, 3, 5, 7, ...`, representing UI ranges `1-2`, `3-4`, `5-6`, and so on.

Navigation counting uses browser `seeking`/`seeked`, pointer/click fallbacks, and a `timeupdate` jump fallback. Movement under one second is ignored, and an 800 ms guard prevents repeated counts. A pause caused by seeking is intended to be suppressed.

## 5. Lessons and external video URLs

- L101 - Enterprise Applications
  - `https://res.cloudinary.com/zg8dorc2/video/upload/v1786546595/Enterprise_Applications.mp4`
- L102 - Event-Driven Microservices
  - `https://res.cloudinary.com/zg8dorc2/video/upload/v1786546159/event_driven_microservice.mp4`

These are public delivery URLs. The browser does not need a Cloudinary API key or secret for playback.

## 6. API endpoints

| Method | Endpoint | Current purpose |
| --- | --- | --- |
| GET | `/` | Basic API-running message |
| GET | `/health` | Reports data-collection mode and prediction disabled |
| POST | `/participants/create` | Generates and stores an anonymous participant/session |
| POST | `/events/raw` | Stores one raw interaction event; not a batch endpoint |
| POST | `/feature-windows` | Stores one feature window and attempts combined-dataset insertion |
| POST | `/paas-ratings` | Stores one Paas rating and attempts combined-dataset insertion |
| GET | `/dataset/export` | Downloads a direct feature/Paas join as CSV |
| POST | `/predict` | Legacy prediction endpoint; not used by the collection UI |
| POST | `/predict/from-raw` | Legacy raw-window prediction endpoint |
| GET | `/xai/data` | Reads legacy prediction CSV logs |

The frontend uses `API_BASE_URL = "/api"`. Production therefore requires a reverse proxy that maps `/api` to FastAPI.

## 7. Database schema and relationships

Database name used by the schema: `CL_Data_Collection`.

### `participant_sessions`

Stores `student_id`, `lesson_id`, `session_id`, `session_start_time`, and `created_at`. Participant code and session ID have unique indexes. New sessions send a UTC start time; historical rows may remain `NULL`.

### `raw_interaction_events`

Stores optional event-level data: event type/time, video time, positions, values, question fields, and session identity. The current HTML interface does not post every event here.

### `feature_windows`

Stores six behavioral features:

- `pause_frequency`
- `navigation_count_video`
- `rewatch_segments`
- `playback_rate_change`
- `idle_duration_video`
- `time_on_content`

### `paas_ratings`

Stores the Paas rating and derived target:

| Paas rating | Cognitive load | Label |
| --- | --- | --- |
| 1-2 | 1 | Very Low |
| 3-4 | 2 | Low |
| 5 | 3 | Medium |
| 6-7 | 4 | High |
| 8-9 | 5 | Very High |

### `model_experiment_dataset`

Stores a combined feature-and-label row after matching feature and Paas records are available. Its intended identity is:

```text
participant_id + lesson_id + session_id + minute_index
```

The SQL schema declares this as a unique key. The runtime `CREATE TABLE IF NOT EXISTS` in `save_model_experiment_dataset_row()` omits that unique key, although its insert uses a `NOT EXISTS` guard.

### `prediction_logs`

Legacy prediction table. Its optional `feature_window_id` is the schema's only declared foreign key and references `feature_windows.id` with `ON DELETE SET NULL`.

Other tables are associated by participant, lesson, session, and window fields rather than declared foreign keys.

## 8. Dataset creation and CSV behavior

When a feature window arrives, the backend stores it and attempts to populate `model_experiment_dataset`. This normally inserts zero rows because the rating has not arrived. After the Paas request is stored, the operation runs again and can insert the matched combined row.

`GET /dataset/export` does not read `model_experiment_dataset`; it directly joins `feature_windows` and `paas_ratings` on student, lesson, nullable session, and minute index.

The backend writes local CSV copies for sessions, raw events, feature windows, and ratings even when MySQL succeeds. These are parallel append-only copies, not failure-only fallbacks.

## 9. Model and training status

Normal application startup and the participant UI do not import `model_loader.py`, so the model is not loaded for collection. `/health` reports:

```json
{
  "status": "ok",
  "mode": "data_collection",
  "model_loaded": false,
  "prediction_enabled": false
}
```

The legacy `/predict`, `/predict/from-raw`, and `/xai/data` paths import `prediction_service.py` only when called. That service imports `model_loader.py`, which immediately loads `model/cognitive_load_model.pkl`.

The training script expects `training_video_features_6_from_previous_dataset.csv`, trains a calibrated Random Forest using the six features, and writes a model and report. The expected training CSV is not currently in the project. The existing report describes an older 4,500-row experiment and is not validation of newly collected real data.

## 10. Environment variables

Create a private `.env` file using placeholders like these:

```text
MYSQL_HOST=<AIVEN_MYSQL_HOST>
MYSQL_PORT=<AIVEN_MYSQL_PORT>
MYSQL_USER=<AIVEN_MYSQL_USER>
MYSQL_PASSWORD=<AIVEN_MYSQL_PASSWORD>
MYSQL_DATABASE=CL_Data_Collection
MYSQL_SSL_DISABLED=false
```

Optional `MYSQL_SSL_CA` is supported. Never place real credentials, tokens, participant data, or private exports in documentation.

## 11. Local installation and running

Python 3.10 or newer is recommended because the code uses `str | None` syntax.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

FastAPI does not serve `data_collection.html`, and the HTML uses `/api`. A complete local browser test needs a local web server/reverse proxy forwarding `/api` to port 8000, or a temporary local API-base adjustment.

## 12. Testing and verification

`tests/test_evaluation.py` checks the evaluation model metadata, real inference, the explicit Moderate-to-Medium comparison mapping, prediction hiding, and post-rating result reveal. Run it with:

```powershell
python -m unittest discover -s tests -v
```

The broader collection workflow still requires these manual checks:

1. Start the backend and check `/health` and `/docs`.
2. Verify consent blocks code generation until checked.
3. Generate a participant and confirm the UI reports `MySQL: true`.
4. Check new participant start times:

```sql
SELECT id, student_id, lesson_id, session_id, session_start_time, created_at
FROM participant_sessions
ORDER BY id DESC
LIMIT 10;
```

5. Test pause, timeline click, drag seek, backward seek, playback-rate change, and idle tracking.
6. Complete a two-minute window and submit one Paas rating.
7. Confirm matching identity values in `feature_windows`, `paas_ratings`, and `model_experiment_dataset`.
8. Download `/api/dataset/export` and inspect headers, labels, nulls, duplicates, and row count.
9. Perform a controlled multi-browser test before formal collection.

## 13. Reported production hosting

The deployment described during development is:

- Site: `https://www.cognitive-load.site`
- Compute: Azure VM with 2 vCPU and 4 GB RAM
- Backend service: systemd unit `cognitive-load-api`
- Intended worker count: two
- Database: Aiven MySQL
- Video delivery: Cloudinary
- HTTPS/reverse proxy: maps `/api` to FastAPI

The repository does not contain the systemd unit, reverse-proxy, DNS, TLS, or infrastructure configuration. Their exact current production contents could not be verified from this workspace.

Useful server checks are:

```bash
sudo systemctl restart cognitive-load-api
sudo systemctl status cognitive-load-api
journalctl -u cognitive-load-api -n 100 --no-pager
```

## 14. Recent completed changes

- Added a consent modal that opens on page load.
- Moved the required consent checkbox into the modal.
- Added database-backed anonymous participant-code generation.
- Reset generated identity when the lesson changes before session start.
- Added Cloudinary-hosted L101 and L102 videos.
- Added pause suppression during navigation and multiple seek-detection fallbacks.
- Added two-minute feature-window and Paas capture.
- Added automatic combined-row insertion into `model_experiment_dataset`.
- Kept CSV export as a direct feature/Paas join.
- Added `session_start_time` to participant creation, CSV fields, and SQL schema.
- Avoided model loading on normal collection startup through route-level imports.

## 15. Known limitations and unfinished work

- The requested 10-15 second raw-event batching architecture is not implemented. `/events/raw` accepts one event, while the current UI sends aggregated window data.
- Browser counters exist only for the active window. Refresh, tab closure, network failure, or device failure before submission can lose that window.
- Feature and Paas requests are separate and not one database transaction. One can succeed while the other fails.
- The UI has no retry queue or idempotency key.
- Source `feature_windows` and `paas_ratings` have no uniqueness constraints. Duplicate rows can produce a many-to-many join and inflate export row counts.
- The runtime and SQL definitions of `model_experiment_dataset` differ because the runtime definition omits the unique key.
- Participant-code uniqueness is checked in MySQL. If MySQL is unavailable but CSV writing succeeds, partial success lacks database-backed uniqueness.
- Local CSV files have no documented off-machine backup or retention policy.
- CORS permits every origin.
- Legacy prediction endpoints remain callable and can load the model.
- Paas buttons are not disabled while submission is in progress, so repeated clicks are possible.
- The two-minute timer is wall-clock based and does not pause during a manual video pause.
- Navigation behavior still needs testing across actual participant browsers/devices.
- The evaluation core has unit tests, but database integration, full browser, load, and recovery tests are not automated.
- `README.md` is still a placeholder.

## 16. Recommended next steps

1. Add uniqueness constraints or idempotent upserts for feature and Paas rows.
2. Add a retry-safe browser queue for completed windows.
3. Decide whether raw events are required; if so, add a true batch endpoint and 10-15 second browser buffer.
4. Reconcile the runtime and SQL definitions of `model_experiment_dataset`.
5. Add tests for identity isolation, Paas mapping, export joins, duplicate prevention, and database failure behavior.
6. Run a staged concurrency test before the 60-student session.
7. Define database and local-CSV backup/retention procedures.
8. Restrict or remove legacy prediction endpoints during formal collection.
9. Replace the placeholder README with operator documentation.

## 17. Prompt for continuing from another account

```text
I am continuing the cognitive-load data collection project in this workspace. Read PROJECT_HANDOVER.md completely, then inspect the current source code before making changes. Treat the code as the source of truth if the handover is outdated. The active phase is anonymous real-data collection: do not enable model prediction unless I explicitly request it. Preserve participant/session/window isolation, two-minute feature windows, Paas 1-9 labels, Aiven MySQL storage, local CSV copies, Cloudinary video delivery, and the Azure deployment. Never expose credentials or participant data. Begin by summarizing the current state, known risks, and files relevant to my next request.
```

## 18. Model evaluation page

`model_evaluation.html` is a separate participant workflow linked from the navigation in both HTML pages. It preserves the existing Paas 1-9 data-collection page and uses separate `evaluation_sessions` and `evaluation_records` tables.

The evaluation page:

- reuses the same 120-second tracking window and six behavioral features;
- loads `scripts/cognitive_load_model.pkl` lazily on the backend;
- validates the exact feature order and five model classes before inference;
- saves a prediction without returning its value to the browser;
- requires a five-point self-reported mental-effort selection with no default;
- reveals the stored prediction only after the rating is saved;
- prevents duplicate segment rows and duplicate rating updates;
- records the model version, SHA-256 hash, timestamps, and mapping version;
- exports records through `GET /evaluation/export`.

The participant scale uses `Moderate` for option 3 while the model class is `Medium`. Both original labels are preserved. Agreement uses the documented mapping `self-report-5-to-model-classes-v1`, which maps rating 3 (`Moderate`) to model class `Medium` and otherwise compares the same named levels.

The inspected model bundle contains its feature list, class order, scikit-learn version, preprocessing pipeline, and classifier, but it does not contain provenance documenting how the original training labels were obtained. Do not describe the evaluation as validation against an original Paas scale without separate research documentation.
