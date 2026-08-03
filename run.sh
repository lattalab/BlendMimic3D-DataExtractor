#!/bin/bash

# ==========================================
# 1. 設定預設變數 (Default Values)
# ==========================================
# [Necessary] modify to your own path
BLENDER_PATH="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" 
# Using default setting if not specify 
ACTION_NAME=""
JOINT_ID=""
ARMATURE_NAME="Armature"
SUBJECT="S1"
TEMP_FILE="homefile.blend"
BLEND_FILE="animation.blend"


# ==========================================
# 2. 解析使用者輸入的參數
# ==========================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -a|--action) ACTION_NAME="$2"; shift ;;
        -s|--subject) SUBJECT="$2"; shift ;;
        -j|--joint-id) JOINT_ID="$2"; shift ;;
        -r|--armature) ARMATURE_NAME="$2"; shift ;;
        -b|--blend-file) BLEND_FILE="$2"; shift ;;
        -h|--help)
            echo "用法: ./run.sh -a <action_name> [其他選項]"
            echo "選項:"
            echo "  -a, --action       動作名稱 (必填，例如: walk_cycle)"
            echo "  -s, --subject      對象/資料夾名稱 (預設: $SUBJECT)"
            echo "  -j, --joint-id     根關節 ID (預設: $JOINT_ID)"
            echo "  -r, --armature     骨架物件名稱 (預設: $ARMATURE_NAME)"
            echo "  -b, --blend-file   基準相機場景檔 (預設: $BLEND_FILE)"
            exit 0
            ;;
        *) echo "[Error] 未知參數: $1"; exit 1 ;;
    esac
    shift
done

# ==========================================
# 3. 檢查必填參數
# ==========================================
if [ -z "$ACTION_NAME" ]; then
    echo "[Error] 缺少必填參數: 動作名稱 (-a 或 --action)！"
    echo "請輸入 ./run.sh -h 查看幫助。"
    exit 1
fi

# ==========================================
# 4. 執行主流程
# ==========================================
echo "=========================================="
echo "開始執行動作: $ACTION_NAME"
echo "對象: $SUBJECT | 關節ID: $JOINT_ID | 骨架: $ARMATURE_NAME"
echo "底檔: $BLEND_FILE"
echo "=========================================="

echo -e "\n[1/4] 正在提取 3D 骨架資料..."
"$BLENDER_PATH" --background --python 3D_extraction.py -- --joint-id "$JOINT_ID" --armature-name "$ARMATURE_NAME" --subject "$SUBJECT"

echo -e "\n[2/4] 正在提取相機參數..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python camParams.py -- "$SUBJECT"

# 2D 提取理論上不需要載入場景，但為了避免載入預設帶有 Cube 的新檔，維持載入底檔
echo -e "\n[3/4] 正在計算 2D 投影座標..."
"$BLENDER_PATH" --background "$BLEND_FILE" --python 2D_extraction.py -- "$SUBJECT" "$ACTION_NAME"

# homefile.blend
echo -e "\n[4/4] 執行環境清理..."
if [ -f "$TEMP_FILE" ]; then
    rm "$TEMP_FILE"
    echo "[-] 已刪除暫存檔: $TEMP_FILE"
fi

# homefile.blend1
if [ -f "${TEMP_FILE}1" ]; then
    rm "${TEMP_FILE}1"
    echo "[-] 已刪除備份檔: ${TEMP_FILE}1"
fi

echo -e "\n=========================================="
echo "處理完畢！所有資料已輸出至指定目錄。"
echo "=========================================="