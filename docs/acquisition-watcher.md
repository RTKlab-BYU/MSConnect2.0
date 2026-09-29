# Acquisition-computer watcher

The production acquisition mode is `staged-direct-upload`. Install one copy of
the repository on each Windows MS computer and run one scheduled task. The
vendor software writes to the approved acquisition root; MSConnect never
deletes or modifies that source tree.

## Server-side setup

Create an `AcquisitionAgent` in Django admin (or through `/api/acquisition-agents/`):

- `name`: the computer name, for example `ms01`
- `token_label`: the matching label in `MSCONNECT_WATCHER_TOKENS`
- `source_root`: the approved path on that computer, for example `C:\\MSData\\VendorOutput`

Add an `AcquisitionRoute` for each simultaneous project or experiment. A route
contains the project, a relative `source_prefix`, and a relative `spool_folder`.
Use `mode=worklist` with a worklist for filename matching, or `mode=adhoc`
with an experiment and optional processing pipeline. For example:

```text
agent: ms01
project: 12
name: project-12
source_prefix: LabA\Project12
spool_folder: project-12
mode: worklist
worklist: 7
```

The watcher creates missing nested source-prefix and spool directories. To
change a computer's source root, use `propose-source-root`, verify the path on
the computer, then use `approve-source-root`. The watcher reports its local
validation but cannot approve a root by itself.

## Windows installation

Run PowerShell as Administrator on the acquisition computer:

```powershell
winget install --id=astral-sh.uv -e
uv python install 3.12
New-Item -ItemType Directory -Force C:\MSConnect2
git clone https://github.com/RTKlab-BYU/MSConnect2.0.git C:\MSConnect2
Set-Location C:\MSConnect2
uv venv --python 3.12
uv pip install --python C:\MSConnect2\.venv\Scripts\python.exe -r requirements.txt
```

Create `C:\MSConnect2\.env`:

```text
DJANGO_SECRET_KEY=local-only-secret
DJANGO_DEBUG=0
SQLITE_PATH=C:\MSConnect2\data\agent.sqlite3
MSCONNECT_API_BASE_URL=http://10.55.69.67:8083/api
MSCONNECT_AGENT_NAME=ms01
MSCONNECT_AGENT_TOKEN=the-token-for-ms01
MSCONNECT_ACQUISITION_SOURCE_ROOT=C:\MSData\VendorOutput
MSCONNECT_ALLOWED_SOURCE_ROOTS=C:\MSData,D:\InstrumentData
MSCONNECT_SPOOL_ROOT=C:\MSConnect2\spool
MSCONNECT_AGENT_STATE_DB=C:\MSConnect2\data\upload-state.sqlite3
MSCONNECT_CONFIG_REFRESH_SECONDS=60
MSCONNECT_UPLOAD_CHUNK_SIZE_BYTES=8388608
MSCONNECT_DELETE_SPOOL_AFTER_UPLOAD=1
WATCHER_INTERVAL_SECONDS=60
WATCHER_STABILITY_CHECKS=2
MSCONNECT_AGENT_HEALTH_DIR=C:\ProgramData\MSConnect\health
MSCONNECT_RELEASE_VERSION=0663117c54fb12249fa0350f06bcc802ea18b914
MSCONNECT_IMAGE=python-native
```

The local source root is only a fallback until the server has an approved
root. The server route configuration supplies the project and nested source
prefixes; no project ID needs to be edited into the computer `.env` for each
new project.

## Test before enabling background operation

```powershell
Test-NetConnection 10.55.69.67 -Port 8083
Invoke-WebRequest http://10.55.69.67:8083/healthz/
Set-Location C:\MSConnect2
uv run --no-project --env-file C:\MSConnect2\.env --python C:\MSConnect2\.venv\Scripts\python.exe -- manage.py run_staged_upload_agent --once --stability-checks 1
```

Place one completed test acquisition under the route's source prefix before
running the one-shot command. Confirm the file remains in the vendor folder,
the server has the same SHA-256 and size, and the route spool copy is gone
after a successful upload. A failed upload leaves the spool copy and a receipt
in `C:\MSConnect2\data\upload-state.sqlite3` for retry.

## Enable continuous operation

```powershell
Set-ExecutionPolicy -Scope Process Bypass
Set-Location C:\MSConnect2
.\ops\install-msconnect-watcher.ps1 `
  -ProjectDir C:\MSConnect2 `
  -EnvFile C:\MSConnect2\.env `
  -PythonExe C:\MSConnect2\.venv\Scripts\python.exe `
  -Mode staged-direct-upload `
  -TaskName "MSConnect2 Staged Uploader ms01"
```

Check task state and logs:

```powershell
Get-ScheduledTask -TaskName "MSConnect2 Staged Uploader ms01" | Get-ScheduledTaskInfo
Get-ChildItem C:\ProgramData\MSConnect\logs
```

Each route is independent, so several project uploads can run on one computer
at the same time. Worklist routes match expected filenames. Ad-hoc routes
create a sample/run for each uploaded file under the selected experiment and
queue the selected processing pipeline immediately; the route's quiet period
is operational metadata for deciding when acquisition has gone quiet, while a
future UI can add an explicit Finish action for closing the batch.
