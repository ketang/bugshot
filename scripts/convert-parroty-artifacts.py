#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BUGSHOT_MANIFEST = "bugshot-unit.json"
BUGSHOT_METADATA = "bugshot-metadata.json"
KNOWN_ASSET_ORDER = [
    "source-crop.png",
    "final.svg",
    "input-minus-svg.png",
    "svg-minus-input.png",
    "difference-overlay.png",
]
RECOGNIZED_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ansi"}


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_clean_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Output path exists and is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"Output directory must be empty: {path}")
    else:
        path.mkdir(parents=True)


def symlink_file(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    destination.symlink_to(source.resolve())


def link_root_passthrough_files(source_root: Path, output_root: Path) -> None:
    for name in ["batch-report.json", "index.html"]:
        source = source_root / name
        if source.is_file():
            symlink_file(source, output_root / name)


def batch_items_by_unit(source_root: Path) -> dict[str, dict]:
    batch_report = source_root / "batch-report.json"
    if not batch_report.is_file():
        return {}

    payload = read_json(batch_report)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    result = {}
    for item in items:
        artifacts = item.get("artifacts")
        if not isinstance(artifacts, str):
            continue
        result[Path(artifacts).name] = item
    return result


def supported_asset_names(unit_dir: Path) -> list[str]:
    names = []
    for child in sorted(unit_dir.iterdir()):
        if not child.is_file():
            continue
        if child.name in {BUGSHOT_MANIFEST, BUGSHOT_METADATA}:
            continue
        if child.suffix.lower() in RECOGNIZED_ASSET_EXTENSIONS:
            names.append(child.name)
    return names


def ordered_assets(unit_dir: Path) -> list[str]:
    available = set(supported_asset_names(unit_dir))
    ordered = [name for name in KNOWN_ASSET_ORDER if name in available]
    ordered.extend(sorted(name for name in available if name not in ordered))
    return ordered


def simplify_selected(report: dict) -> dict:
    selected = report.get("selected", {})
    keys = [
        "name",
        "backend",
        "visual_error",
        "rgb_error",
        "alpha_error",
        "mask_error",
        "edge_error",
        "sdf_error",
        "shape_error",
        "topology_error",
        "bytes",
        "elements",
        "path_commands",
        "cubic_segments",
        "line_segments",
        "text_strategy",
        "text_elements",
        "text_regions",
    ]
    return {key: selected[key] for key in keys if key in selected}


def simplify_detected_text(report: dict) -> list[dict]:
    items = report.get("detected_text_regions", [])
    simplified = []
    if not isinstance(items, list):
        return simplified
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = {}
        if "text" in item:
            entry["text"] = item["text"]
        if "confidence" in item:
            entry["confidence"] = item["confidence"]
        if entry:
            simplified.append(entry)
    return simplified


def build_bugshot_metadata(
    report: dict,
    batch_item: dict | None,
    *,
    has_preview_page: bool,
) -> dict:
    selected = simplify_selected(report)
    detected_text = simplify_detected_text(report)
    original_size = report.get("original_size") or []
    trimmed_size = report.get("trimmed_size") or []
    crop_box = report.get("crop_box") or []
    batch_selected = batch_item.get("selected", {}) if isinstance(batch_item, dict) else {}

    metadata = {
        "schema": "bugshot.logo2svg-metadata/v1",
        "input_name": Path(report.get("input", "")).name,
        "output_name": Path(report.get("output", "")).name,
        "mode": report.get("mode"),
        "text_mode": report.get("text_mode"),
        "comparison_scale": report.get("comparison_scale"),
        "mask_method": report.get("mask_method"),
        "original_width": original_size[0] if len(original_size) > 0 else None,
        "original_height": original_size[1] if len(original_size) > 1 else None,
        "trimmed_width": trimmed_size[0] if len(trimmed_size) > 0 else None,
        "trimmed_height": trimmed_size[1] if len(trimmed_size) > 1 else None,
        "crop_left": crop_box[0] if len(crop_box) > 0 else None,
        "crop_top": crop_box[1] if len(crop_box) > 1 else None,
        "crop_right": crop_box[2] if len(crop_box) > 2 else None,
        "crop_bottom": crop_box[3] if len(crop_box) > 3 else None,
        "warnings": report.get("warnings", []),
        "warnings_count": len(report.get("warnings", [])),
        "detected_text": detected_text,
        "detected_text_count": len(detected_text),
        "selected_name": selected.get("name"),
        "selected_backend": selected.get("backend"),
        "selected_visual_error": selected.get("visual_error"),
        "selected_rgb_error": selected.get("rgb_error"),
        "selected_alpha_error": selected.get("alpha_error"),
        "selected_mask_error": selected.get("mask_error"),
        "selected_edge_error": selected.get("edge_error"),
        "selected_sdf_error": selected.get("sdf_error"),
        "selected_shape_error": selected.get("shape_error"),
        "selected_topology_error": selected.get("topology_error"),
        "selected_bytes": selected.get("bytes"),
        "selected_elements": selected.get("elements"),
        "selected_path_commands": selected.get("path_commands"),
        "selected_cubic_segments": selected.get("cubic_segments"),
        "selected_line_segments": selected.get("line_segments"),
        "selected_text_strategy": selected.get("text_strategy"),
        "selected_text_elements": selected.get("text_elements"),
        "selected_text_regions": selected.get("text_regions"),
        "raw_report_file": "report.json",
    }
    if has_preview_page:
        metadata["preview_page_file"] = "index.html"
    if batch_item:
        metadata["batch_input_name"] = Path(batch_item.get("input", "")).name
        metadata["batch_output_name"] = Path(batch_item.get("output", "")).name
        metadata["batch_selected_backend"] = batch_selected.get("backend")
        metadata["batch_selected_bytes"] = batch_selected.get("bytes")
        metadata["batch_selected_visual_error"] = batch_selected.get("visual_error")
    return {key: value for key, value in metadata.items() if value is not None}


def derive_label(unit_name: str, report: dict, batch_item: dict | None) -> str:
    if batch_item and isinstance(batch_item.get("input"), str):
        return Path(batch_item["input"]).name
    if isinstance(report.get("input"), str) and report["input"]:
        return Path(report["input"]).name
    return unit_name


def convert_unit(source_unit_dir: Path, output_unit_dir: Path, batch_item: dict | None) -> None:
    output_unit_dir.mkdir(parents=True, exist_ok=True)

    for child in sorted(source_unit_dir.iterdir()):
        if child.is_file():
            symlink_file(child, output_unit_dir / child.name)

    report_path = source_unit_dir / "report.json"
    if not report_path.is_file():
        raise ValueError(f"Missing report.json for unit: {source_unit_dir.name}")

    report = read_json(report_path)
    manifest = {
        "label": derive_label(source_unit_dir.name, report, batch_item),
        "assets": ordered_assets(source_unit_dir),
        "reference_asset": "source-crop.png" if (source_unit_dir / "source-crop.png").is_file() else None,
        "metadata": [BUGSHOT_METADATA],
    }
    metadata = build_bugshot_metadata(
        report,
        batch_item,
        has_preview_page=(source_unit_dir / "index.html").is_file(),
    )

    write_json(
        output_unit_dir / BUGSHOT_MANIFEST,
        {key: value for key, value in manifest.items() if value is not None},
    )
    write_json(output_unit_dir / BUGSHOT_METADATA, metadata)


def convert_root(source_root: Path, output_root: Path) -> None:
    if not source_root.is_dir():
        raise ValueError(f"Source root is not a directory: {source_root}")

    ensure_clean_output(output_root)
    batch_map = batch_items_by_unit(source_root)
    link_root_passthrough_files(source_root, output_root)

    for child in sorted(source_root.iterdir()):
        if not child.is_dir():
            continue
        convert_unit(child, output_root / child.name, batch_map.get(child.name))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a parroty logo2svg artifacts root into a Bugshot review root"
    )
    parser.add_argument("source_root", help="Path to the parroty artifacts root")
    parser.add_argument("output_root", help="Path to write the Bugshot review root")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        convert_root(Path(args.source_root), Path(args.output_root))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
