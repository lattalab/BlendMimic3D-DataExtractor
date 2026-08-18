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
# If you want to use command line arguments, you can specify them here
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

# main loop
for fbx_file in regular/*.fbx; do
    # fetch filename without extension
    action_name=$(basename "$fbx_file" .fbx)
    echo ">>> Processed with: $action_name"

    # call single script for current action
    ./run.sh -a "$action_name" -s "$SUBJECT" -j "$JOINT_ID" -r "$ARMATURE_NAME" -b "$BLEND_FILE"
done