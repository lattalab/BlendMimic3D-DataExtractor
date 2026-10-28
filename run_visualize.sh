#!/usr/bin/env bash
# Render RGB images with the legacy Blender script, then overlay 2D skeletons.
# This script produces annotated AVI only; generate_dataset.py encodes original.mp4.

set -euo pipefail

# 1. CLI usage and error reporting.
usage() {
    cat <<'EOF'
Usage: run_visualize.sh --blend WORKING.blend --subject P001 --img-dir DIR [options]

Options:
  -b, --blend FILE       Working Blender scene (default: animation.blend).
  -s, --subject NAME     Legacy subject directory (default: S1).
  -i, --img-dir DIR      RGB output directory (default: images/temp).
      --video-dir DIR    Annotated video root; each Cam_* gets annotated.avi.
      --blender FILE     Windows Blender executable; BLENDER_PATH also works.
      --python FILE      WSL Python executable for OpenCV (default: python3).
      --fps FPS          Video FPS (default: 30).
      --frame-start N    First expected frame in strict mode.
      --frame-end N      Last expected frame in strict mode.
      --width N          Expected image width in strict mode.
      --height N         Expected image height in strict mode.
      --strict           Fail on missing or mismatched frames/annotations.
      --skip-render      Reuse existing RGB frames (legacy option).
      --show-subject     Draw the legacy subject label.
      --hide-occluded    Hide occluded joints.
  -h, --help             Show this help.
EOF
}

fail() { printf '[ERROR] %s\n' "$1" >&2; exit 2; }

# 2. Defaults for the working scene, rendering, and visualization.
BLEND_FILE="animation.blend"
SUBJECT="S1"
IMG_DIR="images/temp"
VIDEO_DIR=""
BLENDER_EXECUTABLE="${BLENDER_PATH:-}"
PYTHON_EXECUTABLE="${PYTHON_PATH:-python3}"
FPS="30"
FRAME_START=""
FRAME_END=""
WIDTH=""
HEIGHT=""
STRICT=false
SKIP_RENDER=false
SHOW_SUBJECT=false
HIDE_OCCLUDED=false

# 3. Parse options: values use two arguments; boolean flags use one.
while (($#)); do
    case "$1" in
        -b|--blend|-s|--subject|-i|--img-dir|--video-dir|--blender|--python|--fps|--frame-start|--frame-end|--width|--height)
            (($# >= 2)) || fail "missing value for $1"
            case "$1" in
                -b|--blend) BLEND_FILE="$2" ;;
                -s|--subject) SUBJECT="$2" ;;
                -i|--img-dir) IMG_DIR="$2" ;;
                --video-dir) VIDEO_DIR="$2" ;;
                --blender) BLENDER_EXECUTABLE="$2" ;;
                --python) PYTHON_EXECUTABLE="$2" ;;
                --fps) FPS="$2" ;;
                --frame-start) FRAME_START="$2" ;;
                --frame-end) FRAME_END="$2" ;;
                --width) WIDTH="$2" ;;
                --height) HEIGHT="$2" ;;
            esac
            shift 2 ;;
        --strict) STRICT=true; shift ;;
        --skip-render) SKIP_RENDER=true; shift ;;
        --show-subject) SHOW_SUBJECT=true; shift ;;
        --hide-occluded) HIDE_OCCLUDED=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1" ;;
    esac
done

# 4. Preflight inputs; strict mode also requires expected frame range/size.
[[ "$SUBJECT" =~ ^[A-Za-z0-9_-]+$ ]] || fail "subject must be a path-safe identifier"
[[ -f "$BLEND_FILE" ]] || fail "working blend does not exist: $BLEND_FILE"
[[ -n "$PYTHON_EXECUTABLE" ]] || fail "Python executable is required"
if [[ "$STRICT" == true ]]; then
    [[ -n "$VIDEO_DIR" ]] || fail "--video-dir is required in strict mode"
    for value in "$FRAME_START" "$FRAME_END" "$WIDTH" "$HEIGHT"; do
        [[ "$value" =~ ^[0-9]+$ ]] || fail "strict mode needs numeric frame range and resolution"
    done
    ((FRAME_END >= FRAME_START && WIDTH > 0 && HEIGHT > 0)) || fail "invalid frame range or resolution"
fi

# 5. Resolve paths relative to the working .blend, matching legacy outputs.
# The visualizer reads ../../BlendMimic3D/<subject>/ from this directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BLEND_DIR="$(cd -- "$(dirname -- "$BLEND_FILE")" && pwd -P)"
BLEND_NAME="$(basename -- "$BLEND_FILE")"
cd -- "$BLEND_DIR"
IMG_DIR="$(realpath -m -- "$IMG_DIR")"
if [[ -n "$VIDEO_DIR" ]]; then VIDEO_DIR="$(realpath -m -- "$VIDEO_DIR")"; fi
SCENE_DIR="$(realpath -m -- "../../BlendMimic3D/$SUBJECT")"
[[ -f "$SCRIPT_DIR/export_image.py" && -f "$SCRIPT_DIR/visualize_2d_video_v3.py" ]] || fail "legacy render/visualize scripts are missing"

# Convert WSL paths only for Windows blender.exe; Linux Python keeps Linux paths.
blender_path() {
    if [[ "$BLENDER_EXECUTABLE" == *.exe ]]; then
        command -v wslpath >/dev/null 2>&1 || fail "wslpath is required for Windows Blender"
        wslpath -w "$(realpath -m -- "$1")"
    else
        realpath -m -- "$1"
    fi
}

# 6. RGB rendering: one Blender invocation renders all enabled cameras.
# --skip-render reuses existing Cam_* PNG directories after an interrupted run.
if [[ "$SKIP_RENDER" == false ]]; then
    [[ -n "$BLENDER_EXECUTABLE" && -f "$BLENDER_EXECUTABLE" ]] || fail "Blender executable is required"
    printf '[START] render RGB frames\n'
    if "$BLENDER_EXECUTABLE" --background "$(blender_path "$BLEND_DIR/$BLEND_NAME")" --python-exit-code 1 \
        --python "$(blender_path "$SCRIPT_DIR/export_image.py")" -- "$(blender_path "$IMG_DIR")"; then
        printf '[DONE] render RGB frames\n'
    else
        status=$?
        printf '[ERROR] Blender rendering failed with exit code %s\n' "$status" >&2
        exit "$status"
    fi
fi

# 7. Locate RGB camera folders and the legacy annotation directory.
# subjects.txt is created by run_annotations.sh before visualization.
[[ -s "$SCENE_DIR/subjects.txt" ]] || fail "subjects.txt is missing: $SCENE_DIR"
shopt -s nullglob
CAM_DIRS=("$IMG_DIR"/Cam_*)
((${#CAM_DIRS[@]} > 0)) || fail "no Cam_* RGB directories under $IMG_DIR"

# 8. For each Cam_N, write an annotated video from RGB + pose2D + visibility.
for cam_dir in "${CAM_DIRS[@]}"; do
    [[ -d "$cam_dir" ]] || fail "not a camera directory: $cam_dir"
    cam_name="${cam_dir##*/}"
    [[ "$cam_name" =~ ^Cam_[0-9]+$ ]] || fail "invalid camera directory: $cam_dir"
    # New dataset layout writes Cam_N/annotated.avi; legacy mode writes Cam_N_viz.avi.
    if [[ -n "$VIDEO_DIR" ]]; then
        video_path="$VIDEO_DIR/$cam_name/annotated.avi"
        mkdir -p -- "$(dirname -- "$video_path")"
    else
        video_path="$IMG_DIR/${cam_name}_viz.avi"
    fi
    [[ ! -e "$video_path" ]] || fail "annotated video already exists: $video_path"
    args=(--scene_dir "$SCENE_DIR" --cam "$cam_name"
        --img_folder "$cam_dir" --output "$video_path" --fps "$FPS")
    # Strict checks happen in visualize_2d_video_v3.py (frames, poses, size).
    if [[ "$STRICT" == true ]]; then
        args+=(--strict --frame-start "$FRAME_START" --frame-end "$FRAME_END"
            --width "$WIDTH" --height "$HEIGHT")
    fi
    if [[ "$SHOW_SUBJECT" == true ]]; then args+=(--subject); fi
    if [[ "$HIDE_OCCLUDED" == true ]]; then args+=(--hide_occluded); fi
    printf '[START] visualize %s\n' "$cam_name"
    # Stop on visualization failure; never silently mark a partial video successful.
    if "$PYTHON_EXECUTABLE" "$SCRIPT_DIR/visualize_2d_video_v3.py" "${args[@]}"; then
        printf '[DONE] visualize %s\n' "$cam_name"
    else
        status=$?
        printf '[ERROR] visualization %s failed with exit code %s\n' "$cam_name" "$status" >&2
        exit "$status"
    fi
done
