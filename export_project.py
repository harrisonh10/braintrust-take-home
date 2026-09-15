#!/usr/bin/env python3
"""Export every experiment and dataset in a Braintrust project.

Produces a zip whose per-object CSV/JSON matches the control-plane UI
"download all fields" export (one row per table row: traces for experiments,
records for datasets). Extra metadata and diagnostics are included so the
Braintrust team can inspect objects that fail to finish exporting in the UI.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import UUID

import braintrust
from braintrust.logger import Attachment, ReadonlyAttachment, api_conn
from braintrust.version import VERSION

PAGE_SIZE = 100
JSON_SEPARATORS = (",", ":")

EXPERIMENT_CSV_LEAD = (
    "id",
    "created",
    "input",
    "output",
    "expected",
    "error",
    "scores",
    "metrics",
    "metadata",
    "tags",
    "span_id",
    "root_span_id",
    "span_parents",
    "span_attributes",
    "is_root",
    "project_id",
    "experiment_id",
    "_xact_id",
    "origin",
    "comments",
    "facets",
    "classifications",
    "context",
    "audit_data",
    "_pagination_key",
)

DATASET_CSV_LEAD = (
    "id",
    "created",
    "input",
    "expected",
    "metadata",
    "tags",
    "span_id",
    "root_span_id",
    "is_root",
    "project_id",
    "dataset_id",
    "_xact_id",
    "origin",
    "comments",
    "facets",
    "classifications",
    "audit_data",
    "_pagination_key",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export all experiments and datasets for a Braintrust project."
    )
    parser.add_argument(
        "--project",
        help="Project name, or a project UUID. You can also pass --project-id.",
    )
    parser.add_argument(
        "--project-id",
        dest="project_id",
        help="Project UUID. Takes precedence over --project when both are set.",
    )
    parser.add_argument(
        "--project-name",
        dest="project_name",
        help="Project name. Optional when --project-id is set.",
    )
    parser.add_argument(
        "--output",
        help="Path for the zip file. Defaults to ./braintrust-export-<project>-<timestamp>.zip",
    )
    parser.add_argument(
        "--org-name",
        dest="org_name",
        default=os.environ.get("BRAINTRUST_ORG_NAME"),
        help="Organization name if the API key belongs to multiple orgs. "
        "Defaults to BRAINTRUST_ORG_NAME.",
    )
    parser.add_argument(
        "--app-url",
        dest="app_url",
        default=os.environ.get("BRAINTRUST_APP_URL"),
        help="Control-plane URL for self-hosted setups. Defaults to BRAINTRUST_APP_URL "
        "or https://www.braintrust.dev.",
    )
    return parser.parse_args()


def is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def login(*, api_key: str | None, org_name: str | None, app_url: str | None) -> None:
    kwargs: dict[str, Any] = {"force_login": True}
    if api_key:
        kwargs["api_key"] = api_key
    if org_name:
        kwargs["org_name"] = org_name
    if app_url:
        kwargs["app_url"] = app_url
    braintrust.login(**kwargs)


def list_objects(path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    conn = api_conn()
    query = dict(params or {})
    query.setdefault("limit", PAGE_SIZE)
    objects: list[dict[str, Any]] = []
    while True:
        page = conn.get_json(path, query)
        batch = list(page.get("objects") or [])
        objects.extend(batch)
        if len(batch) < int(query["limit"]):
            break
        query["starting_after"] = batch[-1]["id"]
    return objects


def resolve_project(project: str | None, project_id: str | None, project_name: str | None) -> dict[str, Any]:
    if project and not project_id and not project_name:
        if is_uuid(project):
            project_id = project
        else:
            project_name = project

    if not project_id and not project_name:
        raise SystemExit("Provide a project name or project id via --project, --project-name, or --project-id.")

    params: dict[str, Any] = {}
    if project_id:
        params["ids"] = project_id
    if project_name:
        params["project_name"] = project_name

    matches = list_objects("v1/project", params)
    if project_id:
        matches = [p for p in matches if p.get("id") == project_id]
    if project_name:
        matches = [p for p in matches if p.get("name") == project_name]

    if not matches:
        raise SystemExit("No project matched the provided name/id. Check the identifier and org.")
    if len(matches) > 1:
        ids = ", ".join(p["id"] for p in matches)
        raise SystemExit(f"Multiple projects matched; pass --project-id. Candidates: {ids}")
    return matches[0]


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "").strip("._")
    return (cleaned or fallback)[:80]


def is_attachment(value: Any) -> bool:
    return isinstance(value, (ReadonlyAttachment, Attachment))


def to_jsonable(value: Any) -> Any:
    """Convert SDK rows to JSON, keeping attachment *references* (not file bytes)."""
    if is_attachment(value):
        return dict(value.reference)
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def is_root_trace(event: Mapping[str, Any]) -> bool:
    if event.get("is_root") is True:
        return True
    if event.get("is_root") is False:
        return False
    span_id = event.get("span_id")
    root_span_id = event.get("root_span_id")
    if span_id and root_span_id:
        return span_id == root_span_id
    return True


def flatten_record(record: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested objects the way the UI 'all fields' CSV does (dot paths)."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        column = f"{prefix}.{key}" if prefix else str(key)
        if is_attachment(value):
            flat[column] = json.dumps(to_jsonable(value), ensure_ascii=False, separators=JSON_SEPARATORS)
        elif isinstance(value, Mapping):
            if value:
                flat.update(flatten_record(value, column))
            else:
                flat[column] = "{}"
        elif isinstance(value, list):
            flat[column] = json.dumps(to_jsonable(value), ensure_ascii=False, separators=JSON_SEPARATORS)
        elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            flat[column] = ""
        elif value is None:
            flat[column] = ""
        elif isinstance(value, bool):
            flat[column] = "true" if value else "false"
        elif isinstance(value, (int, float, str)):
            flat[column] = value
        else:
            flat[column] = json.dumps(to_jsonable(value), ensure_ascii=False, separators=JSON_SEPARATORS)
    return flat


def add_derived_metrics(record: dict[str, Any]) -> dict[str, Any]:
    """Mirror the UI duration column derived from metrics.start / metrics.end."""
    metrics = record.get("metrics")
    if isinstance(metrics, Mapping):
        start = metrics.get("start")
        end = metrics.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and "duration" not in metrics:
            record = dict(record)
            record["metrics"] = {**metrics, "duration": end - start}
    return record


def ordered_columns(rows: list[dict[str, Any]], lead: Iterable[str]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row.keys())
    ordered: list[str] = []
    seen: set[str] = set()
    for prefix in lead:
        group = sorted(k for k in keys if k == prefix or k.startswith(prefix + "."))
        for key in group:
            if key not in seen:
                ordered.append(key)
                seen.add(key)
    for key in sorted(keys - seen):
        ordered.append(key)
    return ordered


def write_json(path: Path, payload: Any) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def write_csv(path: Path, rows: list[dict[str, Any]], lead: Iterable[str]) -> tuple[int, list[str]]:
    columns = ordered_columns(rows, lead)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return path.stat().st_size, columns


def walk_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)


def diagnostics(raw_events: list[Mapping[str, Any]], json_events: list[Any], csv_rows: list[dict[str, Any]]) -> dict[str, Any]:
    attachment_count = 0
    attachment_types: Counter[str] = Counter()
    for event in raw_events:
        for value in walk_values(event):
            if is_attachment(value):
                attachment_count += 1
                attachment_types[str(value.reference.get("type"))] += 1
            elif isinstance(value, Mapping) and value.get("type") in {"braintrust_attachment", "external_attachment"}:
                attachment_count += 1
                attachment_types[str(value.get("type"))] += 1

    row_sizes = [len(json.dumps(row, ensure_ascii=False, default=str)) for row in json_events]
    column_counts = [len(row) for row in csv_rows]
    return {
        "event_count": len(raw_events),
        "exported_row_count": len(json_events),
        "csv_column_count": max(column_counts, default=0),
        "max_csv_columns_on_a_row": max(column_counts, default=0),
        "approx_max_row_json_bytes": max(row_sizes, default=0),
        "approx_total_json_bytes": sum(row_sizes),
        "attachment_reference_count": attachment_count,
        "attachment_types": dict(attachment_types),
        "trace_count": sum(1 for event in raw_events if is_root_trace(event)),
        "span_count": len(raw_events),
    }


def export_table(
    dest: Path,
    events: list[Mapping[str, Any]],
    *,
    lead: Iterable[str],
    traces_only: bool,
) -> dict[str, Any]:
    dest.mkdir(parents=True, exist_ok=True)
    selected = [event for event in events if is_root_trace(event)] if traces_only else list(events)
    json_rows = [to_jsonable(add_derived_metrics(dict(event))) for event in selected]
    csv_rows = [flatten_record(row) for row in json_rows]

    json_bytes = write_json(dest / "export.json", json_rows)
    csv_bytes, columns = write_csv(dest / "export.csv", csv_rows, lead)
    diag = diagnostics(selected, json_rows, csv_rows)
    diag.update(
        {
            "export_json_bytes": json_bytes,
            "export_csv_bytes": csv_bytes,
            "csv_columns": columns,
            "row_shape": "traces" if traces_only else "records",
        }
    )
    write_json(dest / "diagnostics.json", diag)
    return diag


def fetch_summary(experiment_id: str) -> dict[str, Any] | None:
    try:
        return dict(api_conn().get_json(f"v1/experiment/{experiment_id}/summarize"))
    except Exception as exc:  # noqa: BLE001 - keep the rest of the export moving
        return {"error": str(exc)}


def export_experiment(
    project: Mapping[str, Any],
    experiment: Mapping[str, Any],
    dest: Path,
) -> dict[str, Any]:
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "metadata.json", experiment)
    write_json(dest / "summary.json", fetch_summary(experiment["id"]))

    handle = braintrust.init(
        project=project.get("name"),
        project_id=project["id"],
        experiment=experiment["name"],
        open=True,
        set_current=False,
    )
    events = [dict(row) for row in handle.fetch()]
    write_json(dest / "spans.json", [to_jsonable(event) for event in events])
    diag = export_table(dest, events, lead=EXPERIMENT_CSV_LEAD, traces_only=True)
    diag["name"] = experiment.get("name")
    diag["id"] = experiment.get("id")
    return diag


def export_dataset(
    project: Mapping[str, Any],
    dataset: Mapping[str, Any],
    dest: Path,
) -> dict[str, Any]:
    dest.mkdir(parents=True, exist_ok=True)
    write_json(dest / "metadata.json", dataset)

    handle = braintrust.init_dataset(
        project=project.get("name"),
        project_id=project["id"],
        name=dataset["name"],
        use_output=False,
    )
    events = [dict(row) for row in handle.fetch()]
    diag = export_table(dest, events, lead=DATASET_CSV_LEAD, traces_only=False)
    diag["name"] = dataset.get("name")
    diag["id"] = dataset.get("id")
    return diag


def zip_directory(source: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(source))


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("BRAINTRUST_API_KEY")
    if not api_key and not os.environ.get("BRAINTRUST_API_TOKEN"):
        print(
            "Set BRAINTRUST_API_KEY to a personal or service API key "
            "(Settings → API keys). The script will otherwise prompt if stdin is a TTY.",
            file=sys.stderr,
        )

    login(api_key=api_key or os.environ.get("BRAINTRUST_API_TOKEN"), org_name=args.org_name, app_url=args.app_url)
    project = resolve_project(args.project, args.project_id, args.project_name)
    print(f"Exporting project {project['name']!r} ({project['id']})", file=sys.stderr)

    experiments = list_objects("v1/experiment", {"project_id": project["id"]})
    datasets = list_objects("v1/dataset", {"project_id": project["id"]})
    print(f"Found {len(experiments)} experiment(s) and {len(datasets)} dataset(s)", file=sys.stderr)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = safe_name(project["name"], project["id"])
    zip_path = Path(args.output) if args.output else Path(f"braintrust-export-{slug}-{stamp}.zip")
    workdir = zip_path.with_suffix("").with_name(zip_path.stem + "-work")
    if workdir.exists():
        raise SystemExit(f"Working directory already exists: {workdir}")
    workdir.mkdir(parents=True)

    write_json(workdir / "project.json", project)
    manifest: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "sdk_version": VERSION,
        "project": {"id": project["id"], "name": project["name"]},
        "row_shape": {
            "experiments": "traces (root spans), all fields — same as the experiment UI export",
            "datasets": "dataset records, all fields — same as the dataset UI export",
        },
        "experiments": [],
        "datasets": [],
        "failures": [],
    }

    for experiment in experiments:
        folder = workdir / "experiments" / f"{safe_name(experiment['name'], experiment['id'])}__{experiment['id']}"
        print(f"  experiment {experiment['name']!r}", file=sys.stderr)
        try:
            diag = export_experiment(project, experiment, folder)
            manifest["experiments"].append(diag)
        except Exception as exc:  # noqa: BLE001
            failure = {"type": "experiment", "id": experiment.get("id"), "name": experiment.get("name"), "error": str(exc)}
            manifest["failures"].append(failure)
            write_json(folder / "error.json", failure)
            print(f"    failed: {exc}", file=sys.stderr)

    for dataset in datasets:
        folder = workdir / "datasets" / f"{safe_name(dataset['name'], dataset['id'])}__{dataset['id']}"
        print(f"  dataset {dataset['name']!r}", file=sys.stderr)
        try:
            diag = export_dataset(project, dataset, folder)
            manifest["datasets"].append(diag)
        except Exception as exc:  # noqa: BLE001
            failure = {"type": "dataset", "id": dataset.get("id"), "name": dataset.get("name"), "error": str(exc)}
            manifest["failures"].append(failure)
            write_json(folder / "error.json", failure)
            print(f"    failed: {exc}", file=sys.stderr)

    write_json(workdir / "manifest.json", manifest)
    (workdir / "README.txt").write_text(
        "Braintrust project export for support review.\n\n"
        "experiments/<name>__<id>/export.csv and export.json\n"
        "  UI-equivalent experiment download (all fields, one row per trace).\n"
        "experiments/<name>__<id>/spans.json\n"
        "  Every span in the experiment, for objects whose nested traces are huge.\n"
        "datasets/<name>__<id>/export.csv and export.json\n"
        "  UI-equivalent dataset download (all fields).\n"
        "*/metadata.json, summary.json, diagnostics.json, project.json, manifest.json\n"
        "  Object metadata and size/shape signals useful for export failures.\n",
        encoding="utf-8",
    )

    zip_directory(workdir, zip_path)
    print(f"Wrote {zip_path.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
