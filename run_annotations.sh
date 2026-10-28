#!/usr/bin/env bash
# Run the existing Blender annotation scripts in one isolated working scene.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: run_annotations.sh --blend-file WORKING.blend --blender BLENDER.exe [options]

Options:
  -a, --action NAME       Legacy action output name; omit to detect scene targets.
  -s, --subject NAME      Legacy subject output folder (default: S1).
  -j, --joint-id ID       Mixamo joint prefix (default: empty).
  -r, --armature NAME     Armature object name (default: Armature).
  -b, --blend-file FILE   Working .blend; its directory is the process cwd.
      --blender FILE      Windows Blender executable; BLENDER_PATH also works.
  -h, --help              Show this help.
EOF
}

fail() {
    printf '[ERROR] %s\n' "$1" >&2
    exit 2
}

ACTION_NAME=""
JOINT_ID=""
ARMATURE_NAME="Armature"
SUBJECT="S1"
BLEND_FILE="animation.blend"
BLENDER_EXECUTABLE="${BLENDER_PATH:-}"

while (($#)); do
    case "$1" in
        -a|--action|-s|--subject|-j|--joint-id|-r|--armature|-b|--blend-file|--blender)
            (($# >= 2)) || fail "missing value for $1"
            case "$1" in
                -a|--action) ACTION_NAME="$2" ;;
                -s|--subject) SUBJECT="$2" ;;
                -j|--joint-id) JOINT_ID="$2" ;;
                -r|--armature) ARMATURE_NAME="$2" ;;
                -b|--blend-file) BLEND_FILE="$2" ;;
                --blender) BLENDER_EXECUTABLE="$2" ;;
            esac
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1" ;;
    esac
done

# Keep the working blend and process cwd together for both legacy path styles.
[[ "$SUBJECT" =~ ^[A-Za-z0-9_-]+$ ]] || fail "subject must be a path-safe identifier"
[[ -n "$ARMATURE_NAME" ]] || fail "armature name must not be empty"
[[ -n "$BLENDER_EXECUTABLE" ]] || fail "set --blender or BLENDER_PATH"
if [[ "$BLENDER_EXECUTABLE" == */* ]]; then
    [[ -f "$BLENDER_EXECUTABLE" ]] || fail "Blender executable does not exist: $BLENDER_EXECUTABLE"
else
    command -v "$BLENDER_EXECUTABLE" >/dev/null 2>&1 || fail "Blender executable not found: $BLENDER_EXECUTABLE"
fi
[[ -f "$BLEND_FILE" ]] || fail "working blend does not exist: $BLEND_FILE"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BLEND_DIR="$(cd -- "$(dirname -- "$BLEND_FILE")" && pwd -P)"
BLEND_NAME="$(basename -- "$BLEND_FILE")"
cd -- "$BLEND_DIR"
LEGACY_DIR="../../BlendMimic3D/$SUBJECT"
SUBJECTS_FILE="$LEGACY_DIR/subjects.txt"

# Only Windows Blender needs Windows paths; WSL Bash keeps Linux paths.
blender_path() {
    if [[ "$BLENDER_EXECUTABLE" == *.exe ]]; then
        command -v wslpath >/dev/null 2>&1 || fail "wslpath is required for Windows Blender"
        wslpath -w "$(realpath -m -- "$1")"
    else
        realpath -m -- "$1"
    fi
}
BLEND_FOR_BLENDER="$(blender_path "$BLEND_DIR/$BLEND_NAME")"

for script in ActionDetect.py 3D_extraction.py camParams.py 2D_extraction.py occlusion.py; do
    [[ -f "$SCRIPT_DIR/$script" ]] || fail "research script does not exist: $SCRIPT_DIR/$script"
done

run_stage() {
    local label="$1" script="$2" status
    shift 2
    printf '[START] %s\n' "$label"
    if "$BLENDER_EXECUTABLE" --background "$BLEND_FOR_BLENDER" --python-exit-code 1 \
        --python "$(blender_path "$SCRIPT_DIR/$script")" -- "$@"; then
        printf '[DONE] %s\n' "$label"
    else
        status=$?
        printf '[ERROR] %s failed with exit code %s\n' "$label" "$status" >&2
        return "$status"
    fi
}

require_output() {
    [[ -s "$1" ]] || { printf '[ERROR] expected annotation output is missing: %s\n' "$1" >&2; return 1; }
}

run_one() {
    local action="$1" armature="$2"
    [[ "$action" =~ ^[A-Za-z0-9_.-]+$ && "$action" != "." && "$action" != ".." ]] || \
        fail "action must be a path-safe name"

    run_stage "3D pose" 3D_extraction.py \
        --joint-id "$JOINT_ID" --armature-name "$armature" --subject "$SUBJECT" --action "$action"
    require_output "$LEGACY_DIR/D3_Positions/$action/$action.npz"

    run_stage "camera parameters" camParams.py "$SUBJECT"
    require_output "$LEGACY_DIR/Cameras/camera_params_$SUBJECT.npz"
    require_output "$LEGACY_DIR/Cameras/matrices_$SUBJECT.npz"

    run_stage "2D pose" 2D_extraction.py "$SUBJECT" "$action"
    require_output "$LEGACY_DIR/D2_Positions/$action/2D_positions.npz"

    run_stage "visibility" occlusion.py \
        --joint-id "$JOINT_ID" --armature-name "$armature" --subject "$SUBJECT" --action "$action"
    require_output "$LEGACY_DIR/Occlusions/$action/occluded_kpt.npz"
}

# Explicit mode handles one validated character; legacy detection stays available.
if [[ -n "$ACTION_NAME" ]]; then
    run_one "$ACTION_NAME" "$ARMATURE_NAME"
    mkdir -p -- "$LEGACY_DIR"
    printf '%s\n' "$ACTION_NAME" > "$SUBJECTS_FILE"
else
    printf '[START] detect armatures and actions\n'
    if DETECTED_OUTPUT=$("$BLENDER_EXECUTABLE" --background "$BLEND_FOR_BLENDER" --python-exit-code 1 \
        --python "$(blender_path "$SCRIPT_DIR/ActionDetect.py")" 2>&1); then
        printf '%s\n' "$DETECTED_OUTPUT"
    else
        status=$?
        printf '[ERROR] target detection failed with exit code %s\n%s\n' "$status" "$DETECTED_OUTPUT" >&2
        exit "$status"
    fi

    DETECTED_ACTIONS=()
    DETECTED_ARMATURES=()
    while IFS= read -r line; do
        line="${line%$'\r'}"
        [[ "$line" == TARGET:* ]] || continue
        target="${line#TARGET:}"
        [[ "$target" == *:* ]] || fail "invalid ActionDetect target: $line"
        DETECTED_ARMATURES+=("${target%%:*}")
        DETECTED_ACTIONS+=("${target#*:}")
    done <<< "$DETECTED_OUTPUT"
    ((${#DETECTED_ACTIONS[@]} > 0)) || fail "ActionDetect found no active armatures with actions"

    for ((index = 0; index < ${#DETECTED_ACTIONS[@]}; index++)); do
        run_one "${DETECTED_ACTIONS[index]}" "${DETECTED_ARMATURES[index]}"
    done
    mkdir -p -- "$LEGACY_DIR"
    printf '%s\n' "${DETECTED_ACTIONS[@]}" > "$SUBJECTS_FILE"
fi

printf '[DONE] annotations and subjects.txt: %s\n' "$(realpath -m -- "$SUBJECTS_FILE")"
