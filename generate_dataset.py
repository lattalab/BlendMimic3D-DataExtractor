#!/usr/bin/env python3
"""Configuration-driven v0.1 dataset generation controller."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
    import yaml
except ImportError as exc:  # pragma: no cover - user environment dependent
    print(
        f"Missing dependency: {exc.name}. Create the controller environment from environment.yml",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


PROJECT_ROOT = Path(__file__).resolve().parent

ID_PATTERNS = {
    "setup": re.compile(r"^S\d{3}$"),
    "subject": re.compile(r"^P\d{3}$"),
    "replication": re.compile(r"^R\d{3}$"),
    "action": re.compile(r"^A\d{3}$"),
}


class PipelineError(RuntimeError):
    """Expected, user-facing pipeline failure."""


def parse_args() -> argparse.Namespace:
    """Parse one request and optional batch-provided sample selectors."""
    parser = argparse.ArgumentParser(description=__doc__)
    # Select the YAML file describing one multiview generation request.
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--scene-config", type=Path, help="override the selected scene YAML")
    parser.add_argument("--action-config", type=Path, help="override the selected action YAML")
    parser.add_argument("--fbx", type=Path, help="validated PxxxAxxxRxxx.fbx for this one sample")
    parser.add_argument("--run-id", help="unique run record name for this one sample")
    # Preflight configuration and paths without launching Blender or writing files.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate inputs and print the execution plan without creating files",
    )
    return parser.parse_args()


def resolve_path(value: str | Path, base: Path = PROJECT_ROOT) -> Path:
    """Resolve a user path, using the project root for relative paths."""
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    """Require a YAML section to be a dictionary; otherwise fail clearly."""
    if not isinstance(value, dict):
        raise PipelineError(f"'{name}' must be a mapping")
    return value


def load_yaml_mapping(path: Path, name: str) -> dict[str, Any]:
    """Read a required YAML mapping without changing its source file."""
    if not path.is_file():
        raise PipelineError(f"{name} does not exist: {path}")
    try:
        return require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), name)
    except yaml.YAMLError as exc:
        raise PipelineError(f"invalid {name}: {path}: {exc}") from exc


def file_sha256(path: Path) -> str:
    """Compute a SHA-256 content fingerprint for a source asset."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_and_validate_config(
    config_path: Path,
    scene_config: Path | None = None,
    action_config: Path | None = None,
    fbx_file: Path | None = None,
    run_id_override: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one sample-generation request and validate its inputs.

    Args:
        config_path: YAML file defining one setup, subject, action, and take.

    Returns:
        (config, context): Normalized YAML settings and a dictionary holding
        validated IDs plus resolved input, executable, and output paths.
    """
    if not config_path.is_file():
        raise PipelineError(f"config does not exist: {config_path}")

    # The request selects one scene, one action, and one validated FBX take.
    config = load_yaml_mapping(config_path, "config")

    # Require a dataset version for output metadata (not schema selection).
    if not str(config.get("dataset_version", "")).strip():
        raise PipelineError("dataset_version is required")

    if scene_config is not None:
        config["scene_config"] = str(scene_config)
    if action_config is not None:
        config["action_config"] = str(action_config)
    if run_id_override is not None:
        config["run_id"] = run_id_override
    if fbx_file is not None:
        match = re.fullmatch(r"(P\d{3})(A\d{3})(R\d{3})\.fbx", fbx_file.name)
        if match is None:
            raise PipelineError(f"FBX filename must be PxxxAxxxRxxx.fbx: {fbx_file}")
        config["subject"] = {"id": match.group(1)}
        config["replication"] = {"id": match.group(3)}

    scene_path = resolve_path(str(config.get("scene_config", "")))
    action_path = resolve_path(str(config.get("action_config", "")))
    scene = load_yaml_mapping(scene_path, "scene_config")
    action = load_yaml_mapping(action_path, "action_config")
    subject = require_mapping(config.get("subject"), "subject")
    replication = require_mapping(config.get("replication"), "replication")

    ids = {
        "setup": str(scene.get("id", "")),
        "action": str(action.get("id", "")),
        "subject": str(subject.get("id", "")),
        "replication": str(replication.get("id", "")),
    }
    for section, identifier in ids.items():
        if not ID_PATTERNS[section].fullmatch(identifier):
            raise PipelineError(
                f"{section}.id must match {ID_PATTERNS[section].pattern}: {identifier!r}"
            )
    if fbx_file is not None and match.group(2) != ids["action"]:
        raise PipelineError(f"FBX action ID does not match action config: {fbx_file}")

    if "placement" in config or "character_transform" in config:
        raise PipelineError("placement is selected by action.start_points for this scene")
    start_points = require_mapping(action.get("start_points"), "action.start_points")
    placement_name = str(start_points.get(ids["setup"], ""))
    placements = require_mapping(scene.get("placements"), "scene.placements")
    if placement_name not in placements:
        raise PipelineError(f"placement {placement_name!r} is not defined by {scene_path}")
    transform = dict(require_mapping(placements[placement_name], "scene placement"))
    scene_file = resolve_path(str(scene.get("scene_file", "")))
    animated_dir = resolve_path(str(
        require_mapping(action.get("assets"), "action.assets").get("animated_fbx_dir", "")
    ))
    fbx = animated_dir / f"{ids['subject']}{ids['action']}{ids['replication']}.fbx"
    if fbx_file is not None and resolve_path(fbx_file) != fbx.resolve():
        raise PipelineError(f"FBX is outside the selected action assets: {fbx_file}")
    if action.get("actor_count") != 1 or action.get("interaction_type") != "none":
        raise PipelineError("single-sample generation requires a single-actor, non-interaction action")

    # Keep the resolved values in the existing metadata/organizer shape.
    config["setup"] = {"id": ids["setup"], "name": scene.get("name"), "scene_file": str(scene_file)}
    config["action"] = {"id": ids["action"], "name": action.get("name")}
    config["subject"] = {"id": ids["subject"], "animated_fbx": str(fbx)}
    config["replication"] = {"id": ids["replication"]}
    config["character_transform"] = transform
    config["placement_id"] = placement_name

    # Validate the run ID used as a folder name for records and workspace.
    run_id = config.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise PipelineError("run_id may contain only letters, numbers, '_' and '-'")
    if re.fullmatch(r"R\d{3}", run_id):
        raise PipelineError("run_id must identify a unique run, not only a replication")

    # Validate the action name because legacy extractors use it in paths.
    action_name = config["action"].get("name")
    if not isinstance(action_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", action_name) or action_name in (".", ".."):
        raise PipelineError("action.name must be a non-empty path-safe name")

    # Normalize character placement settings before passing them to Blender.
    for field in ("location", "rotation_deg"):
        values = transform.get(field)
        if not isinstance(values, list) or len(values) != 3:
            raise PipelineError(f"character_transform.{field} must contain three numbers")
        try:
            transform[field] = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise PipelineError(f"character_transform.{field} must contain numbers") from exc
    try:
        transform["scale"] = float(transform.get("scale", 1.0))
    except (TypeError, ValueError) as exc:
        raise PipelineError("character_transform.scale must be a number") from exc
    if transform["scale"] <= 0:
        raise PipelineError("character_transform.scale must be greater than zero")

    # Enforce the v0.1 no-overwrite policy and workspace retention option.
    output = require_mapping(config.get("output"), "output")
    if not isinstance(output.get("overwrite", False), bool):
        raise PipelineError("output.overwrite must be true or false")
    if not isinstance(output.get("save_working_blend", False), bool):
        raise PipelineError("output.save_working_blend must be true or false")
    if output.get("overwrite", False):
        raise PipelineError("v0.1 intentionally refuses output.overwrite: true")

    # Validate render settings and apply defaults.
    render = require_mapping(config.get("render", {}), "render")
    for field in ("width", "height", "fps"):
        try:
            render[field] = int(render[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise PipelineError(f"render.{field} must be a positive integer") from exc
        if render[field] <= 0:
            raise PipelineError(f"render.{field} must be a positive integer")
    render.setdefault("enabled", True)
    if not isinstance(render["enabled"], bool):
        raise PipelineError("render.enabled must be true or false")
    if not render["enabled"]:
        raise PipelineError("render.enabled must be true for a complete dataset sample")
    config["render"] = render

    # The annotation shell owns all four stages as one ordered workflow.
    annotations = require_mapping(config.get("annotations", {}), "annotations")
    for name in ("pose3d", "pose2d", "camera_parameters", "visibility"):
        annotations.setdefault(name, True)
        if annotations[name] is not True:
            raise PipelineError(f"annotations.{name} must be true for run_annotations.sh")
    config["annotations"] = annotations

    # Every published sample includes both camera videos.
    videos = require_mapping(config.get("videos", {}), "videos")
    videos.setdefault("enabled", True)
    if not isinstance(videos["enabled"], bool):
        raise PipelineError("videos.enabled must be true or false")
    if not videos["enabled"]:
        raise PipelineError("videos.enabled must be true for a complete dataset sample")
    config["videos"] = videos

    # Run the controller in WSL Bash; Blender may be a Windows .exe.
    pipeline = require_mapping(config.get("pipeline", {}), "pipeline")
    if not str(pipeline.get("armature_name", "GeneratedCharacter")).strip():
        raise PipelineError("pipeline.armature_name must not be empty")
    blender_value = pipeline.get("blender_executable")
    if not blender_value:
        raise PipelineError("pipeline.blender_executable is required")
    bash_value = shutil.which("bash")
    if not bash_value:
        raise PipelineError("WSL Bash is required")
    if "extractor_root" in pipeline and resolve_path(pipeline["extractor_root"]) != PROJECT_ROOT:
        raise PipelineError("pipeline.extractor_root must be the repository root for run_annotations.sh")

    # Resolve paths relative to the project root.
    paths = {
        "config": config_path.resolve(),
        "scene_config": scene_path,
        "action_config": action_path,
        "template": scene_file,
        "fbx": fbx,
        "output_root": resolve_path(output.get("root", "dataset")),
        "runs_root": resolve_path(output.get("runs_root", "runs")),
        "blender": resolve_path(str(blender_value)),
        "bash": Path(bash_value).resolve(),
        "annotation_shell": PROJECT_ROOT / "run_annotations.sh",
        "visualize_shell": PROJECT_ROOT / "run_visualize.sh",
    }

    # Verify required input files exist.
    for label in ("template", "fbx", "blender", "bash", "annotation_shell", "visualize_shell"):
        if not paths[label].is_file():
            raise PipelineError(f"{label} file does not exist: {paths[label]}")
    if not (PROJECT_ROOT / "export_image.py").is_file():
        raise PipelineError("render script does not exist: export_image.py")

    # Build the multiview group ID; return both settings and resolved context.
    ids["group"] = f"{ids['setup']}{ids['subject']}{ids['replication']}{ids['action']}"
    ids["run"] = run_id
    return config, {"ids": ids, "paths": paths}


def log_line(log_path: Path, message: str) -> None:
    """Append a timestamped message to the run log and print it."""
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
    print(message)


def run_command(command: list[str], cwd: Path, log_path: Path, label: str) -> None:
    """Run one external stage synchronously, logging output and exit status.

    Args:
        command: Executable and command-line arguments.
        cwd: Working directory used by the child process.
        log_path: File receiving stage output and start/finish messages.
        label: Human-readable stage name used in logs and errors.
    """
    # Capture combined child-process output to make failures diagnosable.
    log_line(log_path, f"START {label}")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        log_line(log_path, f"FAILED {label}: {exc}")
        raise PipelineError(f"could not start {label}: {exc}") from exc
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(result.stdout)
        if result.stdout and not result.stdout.endswith("\n"):
            handle.write("\n")
    if result.returncode:
        log_line(log_path, f"FAILED {label} exit_code={result.returncode}")
        raise PipelineError(f"{label} failed with exit code {result.returncode}; see {log_path}")
    log_line(log_path, f"DONE {label}")


def blender_path(blender: Path, path: Path) -> str:
    """Translate a WSL path only when passing it into Windows Blender."""
    if blender.suffix.lower() != ".exe":
        return str(path)
    if not shutil.which("wslpath"):
        raise PipelineError("wslpath is required for Windows Blender")
    result = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise PipelineError(f"cannot convert Blender path: {path}: {result.stderr.strip()}")
    return result.stdout.strip()


def blender_command(blender: Path, blend: Path, script: Path, args: list[str]) -> list[str]:
    """Build a Blender command with Windows paths only at the .exe boundary."""
    converted = list(args)
    if blender.suffix.lower() == ".exe":
        for index in range(1, len(converted)):
            if converted[index - 1] in ("--fbx", "--output", "--report"):
                converted[index] = blender_path(blender, Path(converted[index]))
    return [str(blender), "--background", blender_path(blender, blend),
            "--python-exit-code", "1", "--python", blender_path(blender, script),
            "--", *converted]


def split_npz(source: Path, key: str, target: Path, output_key: str) -> None:
    """Extract one camera array from a legacy multi-camera NPZ archive.

    Args:
        source: Source NPZ containing arrays keyed by camera (e.g. Cam_0).
        key: Camera key to read from the source archive.
        target: Output NPZ file path.
        output_key: Array name used inside the new NPZ.
    """
    if not source.is_file():
        raise PipelineError(f"required annotation output is missing: {source}")
    with np.load(source, allow_pickle=True) as archive:
        if key not in archive:
            raise PipelineError(f"{source} does not contain camera key {key}")
        np.savez_compressed(target, **{output_key: archive[key]})


# 把生成的資料整理成規定的資料夾格式
def organize_outputs(
    config: dict[str, Any], context: dict[str, Any], run_dir: Path, work_dir: Path
) -> Path:
    """Convert legacy RGB/annotation outputs into one staged multiview sample.

    Args:
        config: Validated settings controlling requested outputs.
        context: Sample identifiers, paths, and source asset hashes.
        run_dir: Directory containing the prepared-scene report.
        work_dir: Isolated workspace containing raw legacy outputs.

    Returns:
        Path to the staged sample; it is not published to the final output yet.
    """
    # Read the Blender camera inventory produced when preparing this scene.
    ids = context["ids"]
    report = json.loads((run_dir / "scene_report.json").read_text(encoding="utf-8"))
    cameras = report.get("cameras", [])
    if not cameras:
        raise PipelineError("prepared scene contains no enabled cameras")

    # Stage only the required shared files and camera-specific outputs.
    legacy_dir = work_dir / "BlendMimic3D" / ids["subject"]
    stage_sample = work_dir / "canonical" / ids["group"]
    (stage_sample / "shared").mkdir(parents=True)
    shared_sources = {
        "pose3d.npz": legacy_dir / "D3_Positions" / config["action"]["name"] / f"{config['action']['name']}.npz",
        "camera_params.npz": legacy_dir / "Cameras" / f"camera_params_{ids['subject']}.npz",
        "matrices.npz": legacy_dir / "Cameras" / f"matrices_{ids['subject']}.npz",
        "subjects.txt": legacy_dir / "subjects.txt",
    }
    for name, source in shared_sources.items():
        if not source.is_file() or source.stat().st_size == 0:
            raise PipelineError(f"required annotation output is missing: {source}")
        target_dir = stage_sample if name == "subjects.txt" else stage_sample / "shared"
        shutil.copy2(source, target_dir / name)

    # Split existing per-camera arrays; never recompute annotation values.
    pose2d_source = legacy_dir / "D2_Positions" / config["action"]["name"] / "2D_positions.npz"
    visibility_source = legacy_dir / "Occlusions" / config["action"]["name"] / "occluded_kpt.npz"
    for index, camera in enumerate(cameras):
        camera_id = f"C{index + 1:03d}"
        camera_dir = stage_sample / camera_id
        annotation_dir = camera_dir / "annotations"
        rgb_dir = camera_dir / "rgb"
        videos_dir = camera_dir / "videos"
        annotation_dir.mkdir(parents=True)
        rgb_dir.mkdir()
        videos_dir.mkdir()
        split_npz(pose2d_source, f"Cam_{index}", annotation_dir / "pose2d.npz", "positions_2d")
        split_npz(visibility_source, f"Cam_{index}", annotation_dir / "visibility.npz", "visibility")
        source_images = work_dir / "images" / f"Cam_{index}"
        image_files = sorted(path for path in source_images.glob("*.png") if path.is_file())
        if not image_files:
            raise PipelineError(f"no rendered frames found for {camera_id}: {source_images}")
        for image_path in image_files:
            shutil.copy2(image_path, rgb_dir / image_path.name)
        for video_name in ("original.mp4", "annotated.avi"):
            source_video = work_dir / "videos" / f"Cam_{index}" / video_name
            if not source_video.is_file() or source_video.stat().st_size == 0:
                raise PipelineError(f"camera video is missing: {source_video}")
            shutil.copy2(source_video, videos_dir / video_name)

    # Metadata names each camera's legacy key and calibration matrix index.
    metadata = {
        "dataset_version": str(config["dataset_version"]),
        "sample_id": ids["group"],
        "run_id": ids["run"],
        "ids": {name: ids[name] for name in ("setup", "subject", "replication", "action")},
        "source_fbx": str(context["paths"]["fbx"]),
        "placement_id": config["placement_id"],
        "frame_range": {"start": report["frame_range"][0], "end": report["frame_range"][1]},
        "fps": config["render"]["fps"],
        "resolution": {"width": config["render"]["width"], "height": config["render"]["height"]},
        "cameras": [
            {"id": f"C{index + 1:03d}", "blender_name": camera["name"],
             "legacy_key": f"Cam_{index}", "matrix_index": index, "type": camera["type"]}
            for index, camera in enumerate(cameras)
        ],
    }
    (stage_sample / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return stage_sample


def read_scene_report(run_dir: Path) -> dict[str, Any]:
    """Check the prepared scene's frame range and ordered camera inventory."""
    path = run_dir / "scene_report.json"
    if not path.is_file():
        raise PipelineError(f"scene report is missing: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        start, end = report["frame_range"]
        cameras = report["cameras"]
        names = [camera["name"] for camera in cameras]
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            raise ValueError("invalid frame range")
        if not names or names != sorted(set(names)):
            raise ValueError("camera names must be unique and sorted")
        if any(camera["type"] not in ("PERSP", "PANO") for camera in cameras):
            raise ValueError("unsupported camera type")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PipelineError(f"invalid scene report: {path}: {exc}") from exc
    return report


def rgb_frames(folder: Path, start: int, end: int) -> list[Path]:
    """Return the complete numbered PNG sequence for one camera."""
    if not folder.is_dir():
        raise PipelineError(f"RGB directory is missing: {folder}")
    files = [path for path in folder.iterdir() if path.is_file()]
    if any(not re.fullmatch(r"\d+\.png", path.name, re.IGNORECASE) for path in files):
        raise PipelineError(f"RGB directory contains non-numbered PNG files: {folder}")
    frames = sorted(files, key=lambda path: int(path.stem))
    if [int(path.stem) for path in frames] != list(range(start, end + 1)):
        raise PipelineError(f"RGB frame range does not match {start}..{end}: {folder}")
    return frames


def encode_original_videos(work_dir: Path, report: dict[str, Any], render: dict[str, Any]) -> None:
    """Encode each original MP4 from RGB frames already rendered by Blender."""
    start, end = report["frame_range"]
    size = (render["width"], render["height"])
    for index, _camera in enumerate(report["cameras"]):
        frames = rgb_frames(work_dir / "images" / f"Cam_{index}", start, end)
        target = work_dir / "videos" / f"Cam_{index}" / "original.mp4"
        if target.exists():
            raise PipelineError(f"original video already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), render["fps"], size)
        if not writer.isOpened():
            raise PipelineError(f"could not open original video writer: {target}")
        try:
            for frame_path in frames:
                image = cv2.imread(str(frame_path))
                if image is None or (image.shape[1], image.shape[0]) != size:
                    raise PipelineError(f"RGB frame is unreadable or has wrong resolution: {frame_path}")
                writer.write(image)
        finally:
            writer.release()


def validate_video(path: Path, frames: int, fps: int, size: tuple[int, int]) -> None:
    """Decode a completed camera video and check its timing and resolution."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise PipelineError(f"video cannot be decoded: {path}")
    try:
        measured_fps = capture.get(cv2.CAP_PROP_FPS)
        if abs(measured_fps - fps) > 0.1:
            raise PipelineError(f"video FPS mismatch: {path}: {measured_fps} != {fps}")
        count = 0
        while True:
            ok, image = capture.read()
            if not ok:
                break
            if (image.shape[1], image.shape[0]) != size:
                raise PipelineError(f"video resolution mismatch: {path}")
            count += 1
        if count != frames:
            raise PipelineError(f"video frame count mismatch: {path}: {count} != {frames}")
    finally:
        capture.release()


def validate_staged_sample(sample: Path, config: dict[str, Any], report: dict[str, Any]) -> None:
    """Check camera mapping, annotation shapes, RGB and both videos before publish."""
    start, end = report["frame_range"]
    frames = end - start + 1
    cameras = report["cameras"]
    subject = config["subject"]["id"]
    size = (config["render"]["width"], config["render"]["height"])
    metadata = json.loads((sample / "metadata.json").read_text(encoding="utf-8"))
    if metadata["sample_id"] != sample.name or len(metadata["cameras"]) != len(cameras):
        raise PipelineError("sample metadata identity or camera count does not match")
    if (sample / "subjects.txt").read_text(encoding="utf-8").splitlines() != [config["action"]["name"]]:
        raise PipelineError("subjects.txt does not match the requested action")
    try:
        with np.load(sample / "shared" / "pose3d.npz") as data:
            if data["positions_3d"].shape != (frames, 20, 3):
                raise PipelineError("3D pose frame or joint count mismatch")
        with np.load(sample / "shared" / "camera_params.npz", allow_pickle=True) as data:
            if len(data["intrinsic_params"]) != len(cameras):
                raise PipelineError("camera intrinsic count mismatch")
            extrinsic = data["extrinsic_params"].item()
            if len(extrinsic[subject]) != len(cameras):
                raise PipelineError("camera extrinsic count mismatch")
        with np.load(sample / "shared" / "matrices.npz") as data:
            for key in ("K", "RT", "P", "types"):
                if len(data[key]) != len(cameras):
                    raise PipelineError(f"camera matrix count mismatch: {key}")
            for index, camera in enumerate(cameras):
                expected_type = "FISHEYE_EQUISOLID" if camera["type"] == "PANO" and camera.get("panorama_type") == "FISHEYE_EQUISOLID" else "PERSP"
                if str(data["types"][index]) != expected_type:
                    raise PipelineError(f"camera type mismatch at matrix index {index}")
        for index, camera in enumerate(cameras):
            camera_id = f"C{index + 1:03d}"
            mapping = metadata["cameras"][index]
            if mapping["id"] != camera_id or mapping["blender_name"] != camera["name"] or mapping["legacy_key"] != f"Cam_{index}" or mapping["matrix_index"] != index:
                raise PipelineError(f"camera ID mapping mismatch: {camera_id}")
            camera_dir = sample / camera_id
            with np.load(camera_dir / "annotations" / "pose2d.npz") as data:
                if data["positions_2d"].shape != (frames, 20, 2):
                    raise PipelineError(f"2D pose shape mismatch: {camera_id}")
            with np.load(camera_dir / "annotations" / "visibility.npz") as data:
                if data["visibility"].shape != (frames, 20):
                    raise PipelineError(f"visibility shape mismatch: {camera_id}")
            for frame_path in rgb_frames(camera_dir / "rgb", start, end):
                image = cv2.imread(str(frame_path))
                if image is None or (image.shape[1], image.shape[0]) != size:
                    raise PipelineError(f"RGB resolution or decoding failed: {frame_path}")
            for name in ("original.mp4", "annotated.avi"):
                validate_video(camera_dir / "videos" / name, frames, config["render"]["fps"], size)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise PipelineError(f"sample validation failed: {exc}") from exc


def execute(config: dict[str, Any], context: dict[str, Any]) -> Path:
    """Generate, validate, and publish one single-person multiview sample.

    Args:
        config: Validated generation settings, including render/annotation flags.
        context: Sample IDs and resolved paths from load_and_validate_config().

    Returns:
        Path to the published sample directory under the configured output root.

    Note:
        This function executes one sample and stores its isolated workspace
        and logs under its own runs/<run_id>/ directory.
    """
    # Resolve the final sample path and reject conflicting existing outputs.
    ids = context["ids"]
    paths = context["paths"]
    target = paths["output_root"] / ids["group"]
    run_dir = paths["runs_root"] / ids["run"]
    if target.exists():
        raise PipelineError(f"target already exists (no overwrite): {target}")
    if run_dir.exists():
        raise PipelineError(f"run record already exists (choose a new run_id): {run_dir}")

    # Create an isolated run workspace and preserve the original request/log.
    try:
        run_dir.mkdir(parents=True)
    except FileExistsError as exc:
        raise PipelineError(f"run record already exists (choose a new run_id): {run_dir}") from exc
    shutil.copy2(paths["scene_config"], run_dir / "scene_config.yaml")
    shutil.copy2(paths["action_config"], run_dir / "action_config.yaml")
    saved_request = load_yaml_mapping(paths["config"], "config")
    saved_request.update({
        "run_id": ids["run"],
        "scene_config": str(run_dir / "scene_config.yaml"),
        "action_config": str(run_dir / "action_config.yaml"),
        "subject": {"id": ids["subject"]},
        "replication": {"id": ids["replication"]},
    })
    (run_dir / "config.yaml").write_text(
        yaml.safe_dump(saved_request, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    log_path = run_dir / "generation.log"
    log_line(log_path, f"RUN {ids['run']} group={ids['group']}")
    work_dir = run_dir / "work"
    extractor_cwd = work_dir / "preprocessing" / "BlendMimic3D-DataExtractor"
    extractor_cwd.mkdir(parents=True)
    # Legacy scripts mix process-relative paths with bpy.path.abspath("//").
    # The two '..' segments resolve to this run's work/BlendMimic3D tree.
    # The working blend must live in this same cwd for the bpy-relative scripts.
    working_blend = extractor_cwd / "working_scene.blend"
    legacy_dir = (extractor_cwd / ".." / ".." / "BlendMimic3D" / ids["subject"]).resolve()
    expected_legacy_dir = (work_dir / "BlendMimic3D" / ids["subject"]).resolve()
    if legacy_dir != expected_legacy_dir:
        raise PipelineError(f"legacy output escapes run workspace: {legacy_dir}")
    log_line(log_path, f"WORKING_SCENE {working_blend}")
    log_line(log_path, f"LEGACY_OUTPUT {legacy_dir}")
    # Fingerprint source assets; the template is checked again before publish.
    context["template_hash"] = file_sha256(paths["template"])
    context["fbx_hash"] = file_sha256(paths["fbx"])

    # Pass the FBX, placement, and render settings to the Blender-side helper.
    pipeline = config.get("pipeline", {})
    prepare_args = [
        "--fbx", str(paths["fbx"]), "--output", str(working_blend),
        "--report", str(run_dir / "scene_report.json"),
        "--armature-name", str(pipeline.get("armature_name", "GeneratedCharacter")),
        "--location", *[str(value) for value in config["character_transform"]["location"]],
        "--rotation-deg", *[str(value) for value in config["character_transform"]["rotation_deg"]],
        "--scale", str(config["character_transform"]["scale"]),
        "--width", str(config["render"]["width"]),
        "--height", str(config["render"]["height"]),
        "--fps", str(config["render"]["fps"]),
    ]
    # Open the clean template and save a disposable animated working scene.
    run_command(
        blender_command(paths["blender"], paths["template"], Path(__file__).with_name("prepare_scene.py"), prepare_args),
        extractor_cwd, log_path, "prepare working scene",
    )
    if not working_blend.is_file():
        raise PipelineError(f"prepared working scene is missing: {working_blend}")
    report = read_scene_report(run_dir)

    # The annotation shell owns the ordered 3D/camera/2D/occlusion workflow.
    armature = str(pipeline.get("armature_name", "GeneratedCharacter"))
    joint_id = str(pipeline.get("joint_id", ""))
    subject = ids["subject"]
    action_name = str(config["action"]["name"])
    run_command(
        [
            str(paths["bash"]), paths["annotation_shell"].as_posix(),
            "--blend-file", working_blend.as_posix(),
            "--blender", paths["blender"].as_posix(),
            "--action", action_name, "--subject", subject,
            "--joint-id", joint_id, "--armature", armature,
        ],
        extractor_cwd, log_path, "extract annotations",
    )

    # The legacy visualization shell renders RGB once and draws each overlay.
    start, end = report["frame_range"]
    run_command(
        [
            str(paths["bash"]), paths["visualize_shell"].as_posix(),
            "--blend", working_blend.as_posix(),
            "--blender", paths["blender"].as_posix(),
            "--python", Path(sys.executable).as_posix(),
            "--subject", subject,
            "--img-dir", "../../images",
            "--video-dir", "../../videos",
            "--fps", str(config["render"]["fps"]),
            "--frame-start", str(start), "--frame-end", str(end),
            "--width", str(config["render"]["width"]),
            "--height", str(config["render"]["height"]),
            "--strict",
        ],
        extractor_cwd, log_path, "render and visualize cameras",
    )
    log_line(log_path, "START encode original videos")
    encode_original_videos(work_dir, report, config["render"])
    log_line(log_path, "DONE encode original videos")

    # Refuse to publish if generation modified either source asset.
    if file_sha256(paths["template"]) != context["template_hash"]:
        raise PipelineError("template scene changed during generation; refusing to publish output")
    if file_sha256(paths["fbx"]) != context["fbx_hash"]:
        raise PipelineError("animated FBX changed during generation; refusing to publish output")

    # Collect, validate and publish one complete multiview sample.
    stage_sample = organize_outputs(config, context, run_dir, work_dir)
    try:
        validate_staged_sample(stage_sample, config, report)
    except PipelineError as exc:
        (run_dir / "validation.json").write_text(
            json.dumps({"status": "FAIL", "error": str(exc)}, indent=2) + "\n", encoding="utf-8"
        )
        raise
    (run_dir / "validation.json").write_text(
        json.dumps({"status": "PASS", "sample_id": ids["group"]}, indent=2) + "\n", encoding="utf-8"
    )
    paths["output_root"].mkdir(parents=True, exist_ok=True)
    if target.exists():
        log_line(log_path, f"FAILED publish: target appeared during generation: {target}")
        raise PipelineError(f"target appeared during generation (no overwrite): {target}")
    try:
        stage_sample.rename(target)
    except OSError as exc:
        if target.exists():
            log_line(log_path, f"FAILED publish: target appeared during generation: {target}")
            raise PipelineError(f"target appeared during generation (no overwrite): {target}") from exc
        raise
    log_line(log_path, f"PUBLISHED {target}")

    # Remove intermediate files on success unless workspace retention is enabled.
    if not config["output"].get("save_working_blend", False):
        try:
            shutil.rmtree(work_dir)
            log_line(log_path, "Removed temporary work directory")
        except OSError as exc:
            log_line(
                log_path,
                f"WARNING: Dataset published successfully, "
                f"but temporary workspace cleanup failed: {exc}"
            )
            
    return target


def main() -> int:
    """Validate the CLI request, optionally preflight it, or run one sample."""
    # Validate the single-sample request before executing any generation stage.
    args = parse_args()
    try:
        config, context = load_and_validate_config(
            args.config, args.scene_config, args.action_config, args.fbx, args.run_id
        )
        ids = context["ids"]
        paths = context["paths"]
        target = paths["output_root"] / ids["group"]
        print(f"Group ID:       {ids['group']}")
        print(f"Template scene: {paths['template']}")
        print(f"Animated FBX:   {paths['fbx']}")
        print(f"Target output:  {target}")
        run_dir = paths["runs_root"] / ids["run"]
        print(f"Run record:     {run_dir}")
        if target.exists():
            raise PipelineError(f"target already exists (no overwrite): {target}")
        if run_dir.exists():
            raise PipelineError(f"run record already exists (choose a new run_id): {run_dir}")
        # Dry run stops after preflight checks; it does not launch Blender.
        if args.dry_run:
            print("Dry run passed; no files were created.")
            return 0
        result = execute(config, context)
        print(f"Generation complete: {result}")
        return 0
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
