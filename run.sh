#!/bin/bash

# ==========================================
# Default Values
# ==========================================
# [Necessary] modify to your own path
    # Winodws Path
# BLENDER_PATH="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" 
    # WSL Path
BLENDER_PATH="/mnt/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" 
# Using default setting if not specify 
ACTION_NAME=""
JOINT_ID=""
ARMATURE_NAME="Armature"
SUBJECT="S1"
TEMP_FILE="homefile.blend"
BLEND_FILE="animation.blend"


# ==========================================
# 2. If you want to use command line arguments, you can specify them here
# ==========================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -a|--action) ACTION_NAME="$2"; shift ;;
        -s|--subject) SUBJECT="$2"; shift ;;
        -j|--joint-id) JOINT_ID="$2"; shift ;;
        -r|--armature) ARMATURE_NAME="$2"; shift ;;
        -b|--blend-file) BLEND_FILE="$2"; shift ;;
        -h|--help)
            echo "Usage: ./run.sh -a <action_name> [options]"
            echo "options:"
            echo "  -a, --action       action_name (Necessary, EX: walking)"
            echo "  -s, --subject      subject/person (Default: $SUBJECT)"
            echo "  -j, --joint-id     Joint ID (Default: $JOINT_ID)"
            echo "  -r, --armature     Armature name (Default: $ARMATURE_NAME)"
            echo "  -b, --blend-file   Environment file for camera setting (Default: $BLEND_FILE)"
            exit 0
            ;;
        *) echo "[Error] Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ==========================================
# 3. Check required parameters
# ==========================================
# 缺乏必要參數的時候
if [ -z "$ACTION_NAME" ] || [ -z "$ARMATURE_NAME" ]; then
    echo "=========================================="
    echo "[AUTO MODE] Scanning scene: $BLEND_FILE"
    echo "=========================================="

    # Fetch target armatures and actions from the Blender file
    DETECTED_TARGETS=$("$BLENDER_PATH" --background "$BLEND_FILE" --python ActionDetect.py | tr -d '\r' | grep "^TARGET:")

    if [ -z "$DETECTED_TARGETS" ]; then
        echo "[Error] No active Armatures with Actions found in $BLEND_FILE!"
        exit 1
    fi

    SUBJECT_COUNT=1
    for target in $DETECTED_TARGETS; do
        # Parse TARGET:Armature:Action
        DETECTED_ARM=$(echo "$target" | cut -d':' -f2)
        DETECTED_ACT=$(echo "$target" | cut -d':' -f3)

        # If specified subject is empty, assign a default subject name based on the count
        if [ -n "$SUBJECT" ]; then
            TARGET_SUB="$SUBJECT"
        else
            TARGET_SUB="S${SUBJECT_COUNT}"
        fi

        echo -e "\n------------------------------------------"
        echo ">> Auto Dispatch: Subject=$TARGET_SUB | Armature=$DETECTED_ARM | Action=$DETECTED_ACT"
        echo "------------------------------------------"

        # recursively call run.sh with detected parameters
        "$0" -b "$BLEND_FILE" -r "$DETECTED_ARM" -a "$DETECTED_ACT" -s "$TARGET_SUB" -j "$JOINT_ID"

        SUBJECT_COUNT=$((SUBJECT_COUNT + 1))
    done

    echo -e "\n=========================================="
    echo "[AUTO MODE] All detected subjects processed successfully!"
    echo "=========================================="
    exit 0
fi

# ==========================================
# 4. Check if Blender executable exists
# ==========================================
echo "=========================================="
echo "Working on: $ACTION_NAME"
echo "Subject: $SUBJECT | Joint ID: $JOINT_ID | Armature: $ARMATURE_NAME"
echo "Animation file: $BLEND_FILE"
echo "=========================================="

# The following command follow the guideline.
echo -e "\n[1/5] Extracting 3D skeleton data..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python 3D_extraction.py -- --joint-id "$JOINT_ID" --armature-name "$ARMATURE_NAME" --subject "$SUBJECT" --action "$ACTION_NAME"

echo -e "\n[2/5] Extracting camera parameters..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python camParams.py -- "$SUBJECT"

echo -e "\n[3/5] Calculating 2D projection coordinates..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python 2D_extraction.py -- "$SUBJECT" "$ACTION_NAME"

echo -e "\n[4/5] Handling Occlusion ..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python occlusion.py -- --joint-id "$JOINT_ID" --armature-name "$ARMATURE_NAME" --subject "$SUBJECT" --action "$ACTION_NAME"

# homefile.blend
echo -e "\n[5/5] Cleaning up the environment..."
if [ -f "$TEMP_FILE" ]; then
    rm "$TEMP_FILE"
    echo "[-] Deleted temp file: $TEMP_FILE"
fi

# homefile.blend1
if [ -f "${TEMP_FILE}1" ]; then
    rm "${TEMP_FILE}1"
    echo "[-] Deleted backup file: ${TEMP_FILE}1"
fi

echo -e "\n=========================================="
echo "Processing complete! All data has been output to the specified directory."
echo "=========================================="