import json
import os
import subprocess


def test_converter_emits_bugshot_review_root(repo_root, parroty_artifacts_dir, tmp_path):
    output_dir = tmp_path / "bugshot-review-root"

    subprocess.run(
        [
            "python3",
            f"{repo_root}/scripts/convert-parroty-artifacts.py",
            parroty_artifacts_dir,
            str(output_dir),
        ],
        check=True,
        cwd=repo_root,
    )

    unit_dir = output_dir / "logo-sample"
    manifest = json.loads((unit_dir / "bugshot-unit.json").read_text(encoding="utf-8"))
    metadata = json.loads(
        (unit_dir / "bugshot-metadata.json").read_text(encoding="utf-8")
    )

    assert manifest == {
        "label": "logo-sample.png",
        "assets": [
            "source-crop.png",
            "final.svg",
            "input-minus-svg.png",
            "svg-minus-input.png",
            "difference-overlay.png",
        ],
        "reference_asset": "source-crop.png",
        "metadata": ["bugshot-metadata.json"],
    }

    assert metadata["schema"] == "bugshot.logo2svg-metadata/v1"
    assert metadata["input_name"] == "logo-sample.png"
    assert metadata["output_name"] == "logo-sample.svg"
    assert metadata["original_width"] == 243
    assert metadata["original_height"] == 234
    assert metadata["trimmed_width"] == 209
    assert metadata["trimmed_height"] == 213
    assert metadata["selected_backend"] == "boundary-smoothed-bezier-contours"
    assert metadata["selected_visual_error"] == 0.048742581435797294
    assert metadata["selected_bytes"] == 3886
    assert metadata["batch_selected_backend"] == "boundary-smoothed-bezier-contours"
    assert metadata["batch_selected_visual_error"] == 0.048742581435797294
    assert metadata["detected_text"] == [{"text": "COLLEGE", "confidence": 0.98}]
    assert metadata["detected_text_count"] == 1
    assert metadata["raw_report_file"] == "report.json"
    assert "selected" not in metadata
    assert "batch" not in metadata

    assert os.path.islink(unit_dir / "final.svg")
    assert os.path.islink(unit_dir / "report.json")
    assert os.path.islink(output_dir / "batch-report.json")
