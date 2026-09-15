# Export experiments and datasets (customer script)

This script downloads every experiment and dataset in one Braintrust project using the official Python SDK (v0.33.0). The per-object `export.csv` / `export.json` files match the web UI **Download as CSV / JSON** with **all fields**:

- Experiments: one row per **trace** (root span), including inputs, outputs, expected values, scores, metrics (with UI `duration`), metadata, tags, and the other event fields the table export includes.
- Datasets: one row per record, including `input`, `expected`, `metadata`, `tags`, and the other dataset fields.

The zip also includes object metadata, experiment summaries, full experiment spans, and size/shape diagnostics so Braintrust can inspect objects whose UI export never finishes.

## Requirements

- Python 3.10+
- A Braintrust API key with read access to the project (Settings → API keys)
- Network access to your Braintrust control plane and data plane



## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins `braintrust==0.33.0`.

## Credentials

The SDK reads `BRAINTRUST_API_KEY`. If your key belongs to more than one organization, also set `BRAINTRUST_ORG_NAME`.

Self-hosted / non-default control plane:

```bash
export BRAINTRUST_APP_URL="https://www.braintrust.dev"   # or your control-plane URL
```

The SDK resolves the correct regional API URL after login. You do not need to hard-code `https://api.braintrust.dev`.

```bash
export BRAINTRUST_API_KEY="sk-..."
# optional
export BRAINTRUST_ORG_NAME="your-org"
```



## Run

By project name:

```bash
python export_project.py --project "Your Project Name"
```

By project id:

```bash
python export_project.py --project-id 00000000-0000-0000-0000-000000000000
```

`--project` accepts either a name or a UUID. Optional `--output path/to/export.zip` sets the zip location.

The script prints progress to stderr and writes a zip next to your current directory, named like:

`braintrust-export-<project>-<timestamp>.zip`

Send that zip to the Braintrust team. It does not include your API key.

## What’s in the zip


| Path                                        | Contents                                                               |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| `project.json`                              | Project metadata                                                       |
| `manifest.json`                             | Inventory, row counts, failures                                        |
| `experiments/<name>__<id>/export.json`      | UI-equivalent JSON (all fields, traces)                                |
| `experiments/<name>__<id>/export.csv`       | UI-equivalent CSV (flattened `scores.*`, `metrics.*`, `metadata.*`, …) |
| `experiments/<name>__<id>/spans.json`       | Every span, not just traces                                            |
| `experiments/<name>__<id>/metadata.json`    | Experiment object                                                      |
| `experiments/<name>__<id>/summary.json`     | Score/metric summary                                                   |
| `experiments/<name>__<id>/diagnostics.json` | Row/column/byte/attachment counts                                      |
| `datasets/<name>__<id>/export.json`         | UI-equivalent JSON                                                     |
| `datasets/<name>__<id>/export.csv`          | UI-equivalent CSV                                                      |
| `datasets/<name>__<id>/metadata.json`       | Dataset object                                                         |
| `datasets/<name>__<id>/diagnostics.json`    | Row/column/byte/attachment counts                                      |


If one object fails, the script continues and records the error in `manifest.json` and `error.json` for that object.

