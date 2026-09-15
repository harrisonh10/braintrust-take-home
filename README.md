# Braintrust project export

Braintrust sent you this repository because experiment or dataset export in the web app is not completing for a project. Run the script here on your machine to download the same data (JSON and CSV, all fields) and send the resulting zip back to Braintrust support.

The zip does **not** include your API key.

## What you need

- Python 3.10 or newer
- Read access to the project in Braintrust
- An API key: [Settings → API keys](https://www.braintrust.dev/app/settings?subroute=api-keys)
- The **project name** or **project ID** (UUID). The ID is in the project URL, or in the project Details pane.

If your API key belongs to more than one organization, also note the organization name.

If you are on a self-hosted Braintrust deployment, also note your app URL (Settings → Data plane / the URL you use to open the product). Hosted customers can skip this.

## 1. Get this repo

```bash
git clone https://github.com/harrisonh10/braintrust-take-home.git
cd braintrust-take-home
```

If you were given a zip of the repo instead of the GitHub link, unzip it and `cd` into that folder.

## 2. Install

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Set your API key

```bash
export BRAINTRUST_API_KEY="sk-..."
```

Windows (PowerShell):

```powershell
$env:BRAINTRUST_API_KEY="sk-..."
```

Do not put the key in the script or commit it.

Optional, only if needed:

```bash
export BRAINTRUST_ORG_NAME="your-org-name"
export BRAINTRUST_APP_URL="https://www.braintrust.dev"   # self-hosted: your app URL
```

## 4. Run the export

By project name:

```bash
python export_project.py --project "Your Project Name"
```

By project ID:

```bash
python export_project.py --project-id 00000000-0000-0000-0000-000000000000
```

`--project` accepts either a name or a UUID. To choose the zip path:

```bash
python export_project.py --project "Your Project Name" --output ./braintrust-export.zip
```

The script prints progress as it walks experiments and datasets. When it finishes, you will have a file like:

`braintrust-export-<project>-<timestamp>.zip`

## 5. Send it to Braintrust

Reply to the support thread (or whoever sent you this link) and attach that zip.

If some objects fail, still send the zip. Failures are listed in `manifest.json` and in an `error.json` next to the object that failed.

## What’s in the zip

| Path | What it is |
| --- | --- |
| `project.json` | Project metadata |
| `manifest.json` | Inventory, row counts, any failures |
| `experiments/<name>__<id>/export.json` | Experiment traces, all fields (UI JSON export) |
| `experiments/<name>__<id>/export.csv` | Same rows, flattened columns (UI CSV export) |
| `experiments/<name>__<id>/spans.json` | Every span, not just traces |
| `experiments/<name>__<id>/metadata.json` | Experiment object |
| `experiments/<name>__<id>/summary.json` | Score / metric summary |
| `experiments/<name>__<id>/diagnostics.json` | Size and shape stats for support |
| `datasets/<name>__<id>/export.json` | Dataset records, all fields |
| `datasets/<name>__<id>/export.csv` | Same rows as CSV |
| `datasets/<name>__<id>/metadata.json` | Dataset object |
| `datasets/<name>__<id>/diagnostics.json` | Size and shape stats for support |

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| Prompted for a token / 401 | Create a new API key and export `BRAINTRUST_API_KEY` in the same terminal you run the script. |
| 403 / project not found | Confirm the key is in the same org as the project. Set `BRAINTRUST_ORG_NAME` if you belong to multiple orgs. |
| Self-hosted 404 | Set `BRAINTRUST_APP_URL` to the URL you use to open Braintrust, not `https://www.braintrust.dev`. |
| One object fails, others succeed | Send the zip anyway; check `manifest.json`. |
| Slow | Expected for large experiments. The script pages through data instead of loading everything in the browser. |
