#!/usr/bin/env bash
# Sequential Scene, Action, and validated FBX batch controller.

# -e: inproper exit code aborts the script
# -u: unset variable aborts the script
# -o: any command in a pipeline fails, the whole pipeline fails
set -euo pipefail

# sample usage (using EOF to print multiple lines)
usage() {
    cat <<'EOF'
Usage: run.sh --config BASE.yaml --scene-config SCENE.yaml --action-config ACTION.yaml [options]

Repeat --scene-config and --action-config to generate their cross product.
Options:
  --python FILE         WSL controller Python (default: PYTHON_PATH or python3).
  --dry-run             Preflight every single-sample request without generating.
  -h, --help            Show this help.
EOF
}

fail() { printf '[ERROR] %s\n' "$1" >&2; exit 2; }


CONFIG=""
PYTHON_EXECUTABLE="${PYTHON_PATH:-python3}"
DRY_RUN=false
# Bash Array
SCENE_CONFIGS=()
ACTION_CONFIGS=()

#   ./run.sh \
#   --config configs/examples/generation_example.yaml \
#   --scene-config configs/scenes/S001_Industrial_Loft.yaml \
#   --action-config configs/actions/A001_walking.yaml \
#   --dry-run
while (($#)); do
    case "$1" in
        # acknowledge valid argument
        --config|--scene-config|--action-config|--python)
            (($# >= 2)) || fail "missing value for $1"
            # record corresponding value
            case "$1" in
                --config) CONFIG="$2" ;;
                --scene-config) SCENE_CONFIGS+=("$2") ;;
                --action-config) ACTION_CONFIGS+=("$2") ;;
                --python) PYTHON_EXECUTABLE="$2" ;;
            esac
            # move to the next argument pair
            shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1" ;;
    esac
done

# if the config are missing, report fail
[[ -n "$CONFIG" && ${#SCENE_CONFIGS[@]} -gt 0 && ${#ACTION_CONFIGS[@]} -gt 0 ]] || fail "base, scene and action configs are required"

# enter the script directory to ensure relative paths are correct
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$SCRIPT_DIR"

# check for required files and executables
[[ -f generate_dataset.py ]] || fail "root generate_dataset.py is missing"
[[ -f "$CONFIG" ]] || fail "base config is missing: $CONFIG"
# bash array expansion to check each config file exists
for path in "${SCENE_CONFIGS[@]}" "${ACTION_CONFIGS[@]}"; do
    [[ -f "$path" ]] || fail "selected config is missing: $path"
done
# check python dependency 
if [[ "$PYTHON_EXECUTABLE" == */* ]]; then
    [[ -f "$PYTHON_EXECUTABLE" ]] || fail "WSL Python is missing: $PYTHON_EXECUTABLE"
else
    command -v "$PYTHON_EXECUTABLE" >/dev/null 2>&1 || fail "WSL Python is missing: $PYTHON_EXECUTABLE"
fi

# create a batch record directory and log file
CONFIG="$(realpath -- "$CONFIG")"
BATCH_ID="BATCH_$(date -u +%Y%m%dT%H%M%S)_$$"
BATCH_DIR="runs/$BATCH_ID"
mkdir -p -- runs
mkdir -- "$BATCH_DIR" || fail "batch record already exists: $BATCH_DIR"
BATCH_LOG="$BATCH_DIR/batch.log"
log() { printf '%s\n' "$*" | tee -a "$BATCH_LOG"; }
log "BATCH $BATCH_ID config=$CONFIG dry_run=$DRY_RUN"

# scan the action config for animated FBX files and validate their names
scan_action_fbxs() {
    "$PYTHON_EXECUTABLE" -c '
import pathlib, re, sys, yaml
root = pathlib.Path(sys.argv[1])
source = pathlib.Path(sys.argv[2])
action = yaml.safe_load(source.read_text(encoding="utf-8"))
action_id = action["id"]
if re.fullmatch(r"A\d{3}", action_id) is None:
    raise ValueError(f"invalid action ID: {action_id}")
folder = pathlib.Path(action["assets"]["animated_fbx_dir"])
folder = folder if folder.is_absolute() else root / folder
if not folder.is_dir():
    raise FileNotFoundError(f"animated FBX directory is missing: {folder}")
for item in sorted(folder.glob("*.fbx")):
    if re.fullmatch(r"P\d{3}" + action_id + r"R\d{3}\.fbx", item.name):
        print(item.resolve().as_posix())
' "$SCRIPT_DIR" "$1"
}

# process each scene and action
success=0
failure=0
declare -A seen_samples=()
# run each scene
for scene in "${SCENE_CONFIGS[@]}"; do
    scene="$(realpath -- "$scene")"
    if scene_id=$("$PYTHON_EXECUTABLE" -c 'import pathlib,re,sys,yaml; value=yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["id"]; assert re.fullmatch(r"S\d{3}",value), "invalid scene ID"; print(value)' "$scene" 2>> "$BATCH_LOG"); then
        :
    else
        log "FAIL scene_config=$scene: cannot read a valid Sxxx ID"
        ((failure += 1))
        continue
    fi
    scene_id="${scene_id%$'\r'}"

    # read action config to get all the animated FBX
    for action in "${ACTION_CONFIGS[@]}"; do
        action="$(realpath -- "$action")"
        if fbx_list=$(scan_action_fbxs "$action" 2>> "$BATCH_LOG"); then
            :
        else
            log "FAIL scene=$scene_id action_config=$action: FBX scan failed"
            ((failure += 1))
            continue
        fi
        if [[ -z "$fbx_list" ]]; then
            log "FAIL scene=$scene_id action_config=$action: no valid animated FBX"
            ((failure += 1))
            continue
        fi

        # process each FBX file
        mapfile -t fbxs <<< "$fbx_list"
        for fbx in "${fbxs[@]}"; do
            
            fbx="${fbx%$'\r'}"
            filename="${fbx##*/}"
            subject="${filename:0:4}"
            action_id="${filename:4:4}"
            replication="${filename:8:4}"
            sample_id="${scene_id}${subject}${replication}${action_id}"
            
            if [[ -n "${seen_samples[$sample_id]:-}" ]]; then
                log "FAIL $sample_id: duplicate selection in this batch"
                ((failure += 1))
                continue
            fi

            seen_samples[$sample_id]=1
            run_id="RUN_${sample_id}_${BATCH_ID}"

            # calling the generate_dataset.py script with the appropriate arguments
            command=("$PYTHON_EXECUTABLE" "$SCRIPT_DIR/generate_dataset.py"
                --config "$CONFIG" --scene-config "$scene" --action-config "$action"
                --fbx "$fbx" --run-id "$run_id")
            if [[ "$DRY_RUN" == true ]]; then command+=(--dry-run); fi
            log "START $sample_id fbx=$fbx run=$run_id"
            if "${command[@]}" >> "$BATCH_LOG" 2>&1; then
                log "PASS $sample_id"
                ((success += 1))
            else
                status=$?
                log "FAIL $sample_id exit_code=$status"
                ((failure += 1))
            fi
        done
    done
done

# summarize the batch results
log "SUMMARY success=$success failure=$failure log=$BATCH_LOG"
((failure == 0 && success > 0))
