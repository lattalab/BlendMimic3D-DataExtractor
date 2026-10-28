# Run Records

This directory stores logs and temporary files created by the `configuration-driven dataset generation pipeline`. **Generated samples are published to `output.root`**, not necessarily to `runs/`.   

- **Batch records:** `run.sh` always writes to this repository's `runs/BATCH_*/` directory.
- **Single-sample records:** `generate_dataset.py` writes to `output.runs_root/<run_id>/` (default: `runs/`).
- **Published dataset:** a validated sample is written to `output.root/<sample_id>/`, where a sample ID follows `SxxxPxxxRxxxAxxx` (for example, `S001P001R001A001`).
    - For example, `configs/examples/generation_simple.yaml` sets `output.root: runs/QA_DATASET`, so `runs/QA_DATASET/` contains test dataset outputs rather than Run records.

## Directory Layout

The following is an example using the default `output.runs_root: runs` and a Batch invocation. Some files appear only after their corresponding stage succeeds.

```text
runs/
├── README.md
├── BATCH_<UTC-timestamp>_<pid>/
│   └── batch.log
├── RUN_<sample_id>_BATCH_<UTC-timestamp>_<pid>/
│   ├── config.yaml
│   ├── scene_config.yaml
│   ├── action_config.yaml
│   ├── generation.log
│   ├── scene_report.json             # After scene preparation
│   ├── validation.json               # After sample validation is reached
│   └── work/                         # Retained on failure or when configured
│       ├── preprocessing/BlendMimic3D-DataExtractor/
│       │   └── working_scene.blend
│       ├── BlendMimic3D/P001/        # Intermediate annotations
│       ├── images/Cam_0/             # Rendered RGB frames
│       ├── videos/Cam_0/             # Intermediate camera videos
│       └── canonical/<sample_id>/    # Staging area before publication
```

A direct call to `generate_dataset.py` uses the `run_id` specified in the request YAML (or supplied with `--run-id`), instead of the Batch-generated Run ID.  

## Batch Logs

`run.sh` creates `runs/BATCH_<UTC-timestamp>_<pid>/batch.log`. It records the selected base config, the FBX and Run ID for each selected sample, `START` / `PASS` / `FAIL` messages, captured single-sample output, and a final `SUMMARY` with success and failure counts.  

Samples are processed sequentially. A failed sample does not stop later samples, but the Batch exits with a nonzero status if any sample fails or no sample succeeds.  

A Batch `--dry-run` **still creates `batch.log`**, but only checks the individual requests; it does not create single-sample Run directories or publish datasets.  

## Single-Sample Records

After preflight succeeds, `generate_dataset.py` creates a separate Run directory containing:  

| File | Description |
| --- | --- |
| `config.yaml` | A copy of the request YAML with the selected Scene, Action, Subject, Replication, and Run ID applied. It is **not** a fully resolved snapshot of every effective setting. |
| `scene_config.yaml` / `action_config.yaml` | Copies of the selected Scene and Action YAML files. |
| `generation.log` | Execution-stage messages, errors, and the final `PUBLISHED <path>` entry if publication succeeds. |
| `scene_report.json` | Frame range and ordered camera information from the prepared Blender scene. |
| `validation.json` | `PASS` or `FAIL` result, written only when final sample validation is reached. |

The isolated `work/` directory holds the temporary Blender scene, legacy annotation outputs, RGB frames, videos, and the staged canonical sample. On successful publication, `work/` is normally deleted. It is kept after a failure, or when `output.save_working_blend: true` (which retains the **entire workspace**, not only the `.blend` file).  

**A validation `PASS` alone does not confirm publication.** Check `generation.log` for `PUBLISHED <path>` and confirm the output directory exists.  

## Dry Run, Existing Outputs, and Reproduction

- Direct `generate_dataset.py --dry-run` performs preflight without creating a Run directory or dataset output. In contrast, Batch `run.sh --dry-run` writes a Batch log.
- Existing published Sample IDs and existing Run IDs are rejected. This version does **not** automatically skip, overwrite, or resume existing samples.
- A failure during preflight creates no single-sample Run record. Failures after Run creation may leave a partial record and `work/` for debugging.
- Reproducing a Run requires the referenced scene template, animated FBX, and matching code version in addition to the saved YAML files. Paths may need to be updated on another machine.

Generated files under `runs/` are intended to remain local; this README is kept in Git for documentation.  