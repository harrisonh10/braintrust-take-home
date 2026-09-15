# Braintrust project export (customer script)

Exports **every experiment and dataset** in one project as JSON, using Braintrust's generated Python API SDK (`braintrust-api`) and its `/btql` query endpoint (`SELECT `* / `select: *`). That is the API equivalent of the UI **Export → JSON → all fields** option: native event column names (`input`, `output`, `expected`, `scores`, `metadata`, `metrics`, `span_attributes`, `tags`, `error`, ids, timestamps, and any other stored fields), not a reduced table view.

The UI export can hang in the browser even after the control plane returns 200. This script pages on the **data plane** and streams into a zip so large objects still complete.

## Zip contents


| File                    | What it is                                                                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `full_traces.json`      | Experiment **traces** (`shape => traces`): one JSON object per root trace, nested spans included. Same grain as the experiment table **Traces** view.    |
| `experiment_spans.json` | Experiment **span rows**: root and nested spans as separate objects. Same grain as the **Spans** row type.                                               |
| `dataset_rows.json`     | All dataset events, all columns.                                                                                                                         |
| `manifest.json`         | Per-object row counts, byte sizes, max row size, dotted column names, durations, and errors. Use this to find which objects are unusually large or wide. |


Each JSON data file is a single JSON **array**. Rows keep Braintrust field names. `experiment_id` / `dataset_id` on each event identify which object a row belongs to.

## Prerequisites

- Python 3.10+
- The official `braintrust-api` Python SDK (installed by `requirements.txt`).
- A Braintrust **API key** (Settings → API keys). The key must be able to read the project.
- Your **self-hosted / hybrid data-plane API URL** (Settings → Data plane). Example: `https://xxxxxxxx.cloudfront.net`.
- The **project ID** (UUID). Open the project in the app; copy the id from the URL or from the project Details pane.

Do **not** put the API key in the script. Use an environment variable.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export BRAINTRUST_API_KEY="sk-...."
export BRAINTRUST_API_URL="https://YOUR_DATA_PLANE_API_URL"

python export_project.py --project-id "00000000-0000-0000-0000-000000000000"
```

Optional flags:

```bash
python export_project.py \
  --project-id "00000000-0000-0000-0000-000000000000" \
  --api-url "$BRAINTRUST_API_URL" \
  --output "./braintrust-export.zip"
```

`--api-key` exists but is discouraged (shell history). Prefer `BRAINTRUST_API_KEY`.

When it finishes, send Braintrust the zip (or at least `manifest.json` plus any objects whose `likely_ui_risks` is non-empty).

## After export

```bash
unzip -l braintrust-export-<project-id>.zip
python3 -m json.tool manifest.json | less
```

`manifest.json` → `likely_ui_risks` flags:

- `more_than_1000_rows` — UI downloads are documented as capped / heavy in-memory
- `payload_over_25mb` — likely to stall a browser download
- `single_row_over_1mb` — pathological nested input/output/trace
- `very_wide_schema` — many score/metadata/classifier columns



## Troubleshooting


| Symptom                           | What to check                                                                                                                                       |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Missing API URL / 404             | `BRAINTRUST_API_URL` must be the **data plane** URL, not `https://www.braintrust.dev`. Strip a trailing `/v1` if you copied it from a REST example. |
| 401 / 403                         | New API key; confirm it belongs to the same org as the project.                                                                                     |
| One object errors, others succeed | See that object's `error` in `manifest.json`. The zip still contains the rest.                                                                      |
| Slow                              | Normal for large traces. The script pages 1000 rows at a time and retries 429/5xx.                                                                  |




## SDK usage

The script uses `Braintrust.projects`, `Braintrust.experiments`, and
`Braintrust.datasets` to retrieve the project, discover all objects, and fetch
event pages. The generated SDK does not currently expose `/btql` as a named resource, so the trace-shaped `SELECT *` query is sent through the SDK's generic `client.post()` method; authentication, base URL handling, retries, and HTTP transport still come from the SDK.