# #!/bin/bash

# ==========================================
# Default Configurations
# ==========================================
# [Necessary] modify to your own path
    # Winodws Path
# BLENDER_PATH="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" 
    # WSL Path
BLENDER_PATH="/mnt/c/Program Files/Blender Foundation/Blender 5.1/blender.exe" 
# Using default setting if not specify 
SUBJECT="S1"
BLEND_FILE="animation.blend"
# the argument for export_image.py
IMG_DIR="images/temp"
ENGINE="EEVEE"
# whether to skip the Blender rendering step and only run the visualization
SKIP_RENDER=false
# optional argument for visualize_2d_video_v3.py
HIDE_OCCLUDED=false
SHOW_SUBJECT=false

# ==========================================
# Parse Arguments
# ==========================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -b|--blend) BLEND_FILE="$2"; shift ;;
        -s|--subject) SUBJECT="$2"; shift ;;
        -i|--img-dir) IMG_DIR="$2"; shift ;;
        -e|--engine) ENGINE="$2"; shift ;;
        --skip-render) SKIP_RENDER=true ;;
        --show-subject) SHOW_SUBJECT=true ;;
        --hide-occluded) HIDE_OCCLUDED=true ;;
        -h|--help)
            echo "Usage: ./render_and_viz.sh -b <blend_file> -s <subject> [options]"
            echo "Options:"
            echo "  -b, --blend        Target .blend file (Default: $BLEND_FILE)"
            echo "  -s, --subject      Subject scene folder (Default: $SUBJECT)"
            echo "  -i, --img-dir      Output directory for images (Default: $IMG_DIR)"
            echo "  -e, --engine       Render engine: EEVEE or CYCLES (Default: $ENGINE)"
            echo "  --show-subject     Draw subject labels (S1, S2, ...) (Default: false)"
            echo "  --hide-occluded    Hide occluded keypoints in visualization (Default: false)"
            echo "  --skip-render      Skip Blender rendering and only run visualization"
            exit 0
            ;;
        *) echo "[Error] Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

OUTPUT_BASE_DIR="../../BlendMimic3D"
SCENE_DIR="${OUTPUT_BASE_DIR}/${SUBJECT}"

# ==========================================
# 1. Blender Rendering (export_image.py)
# ==========================================
if [ "$SKIP_RENDER" = false ]; then
    echo "=========================================="
    echo "[Step 1/2] Rendering images via Blender ($ENGINE)..."
    echo "Scene File: $BLEND_FILE -> Image Folder: $IMG_DIR"
    echo "=========================================="

    "$BLENDER_PATH" -b "$BLEND_FILE" --python export_image.py -- "$IMG_DIR" "$ENGINE"

    if [ $? -ne 0 ]; then
        echo "[ERROR] Blender rendering failed!"
        exit 1
    fi
else
    echo "[*] Skipping Blender render (--skip-render is active)."
fi

# ==========================================
# 2. 2D Pose Visualization (visualize_2d_video_v3.py)
# ==========================================
echo -e "\n=========================================="
echo "[Step 2/2] Generating Multi-Camera Visualizations..."
echo "Scene Directory: $SCENE_DIR"
echo "=========================================="

# 檢查 subjects.txt 是否存在
if [ ! -f "${SCENE_DIR}/subjects.txt" ]; then
    echo "[ERROR] Metadata file not found: ${SCENE_DIR}/subjects.txt"
    echo "Please ensure run.sh has been executed for this subject."
    exit 1
fi

# 根據 export_image.py 產生的 Cam_* 資料夾繪圖
CAM_FOLDERS=$(find "$IMG_DIR" -maxdepth 1 -type d -name "Cam_*" | sort -V)

if [ -z "$CAM_FOLDERS" ]; then
    echo "[ERROR] No Cam_* subfolders found under: $IMG_DIR"
    exit 1
fi

# Check if --hide-occluded flag is set
HIDE_OCCLUDED_ARGS=""
if [ "$HIDE_OCCLUDED" = true ]; then
    HIDE_OCCLUDED_ARGS="--hide_occluded"
fi
# Check if --show-subject flag is set
SHOW_SUBJECT_ARGS=""
if [ "$SHOW_SUBJECT" = true ]; then
    SHOW_SUBJECT_ARGS="--subject"
fi

for cam_dir in $CAM_FOLDERS; do
    CAM_NAME=$(basename "$cam_dir")
    OUTPUT_VIDEO="${IMG_DIR}/${CAM_NAME}_viz.avi"

    echo -e "\n------------------------------------------"
    echo ">> Visualizing Camera: $CAM_NAME"
    echo ">> Target Directory : $cam_dir"
    echo ">> Output Video     : $OUTPUT_VIDEO"
    echo ">> Show Subject     : $SHOW_SUBJECT"
    echo ">> Hide Occluded    : $HIDE_OCCLUDED"
    echo "------------------------------------------"

    python visualize_2d_video_v3.py \
        --scene_dir "$SCENE_DIR" \
        --cam "$CAM_NAME" \
        --img_folder "$cam_dir" \
        --output "$OUTPUT_VIDEO" \
        ${SHOW_SUBJECT_ARGS} \
        ${HIDE_OCCLUDED_ARGS}
done

echo -e "\n=========================================="
echo "[SUCCESS] All camera videos successfully exported to $IMG_DIR!"
echo "=========================================="