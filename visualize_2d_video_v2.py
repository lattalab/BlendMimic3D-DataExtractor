import numpy as np
import cv2
import os

# --- 新增：定義 19 個關節的連線規則 (使用索引值) ---
# 基於你的 BASE_JOINT_NAMES 對應順序
SKELETON_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5),   # 脊椎與頭部: Hips -> Spine -> Spine1 -> Spine2 -> Head -> HeadTop_End
    (0, 6), (6, 7), (7, 8),                   # 左腿: Hips -> LeftUpLeg -> LeftLeg -> LeftFoot
    (0, 9), (9, 10), (10, 11),                # 右腿: Hips -> RightUpLeg -> RightLeg -> RightFoot
    (3, 12), (12, 13), (13, 14), (14, 15),    # 左手: Spine2 -> LeftShoulder -> LeftArm -> LeftForeArm -> LeftHand
    (3, 16), (16, 17), (17, 18), (18, 19)     # 右手: Spine2 -> RightShoulder -> RightArm -> RightForeArm -> RightHand
]

def main():
    # 1. Paths to your data and rendered images
    npz_path = "../../BlendMimic3D/S1/D2_Positions/Walking2/2D_positions.npz"
    img_folder = "video" 
    
    output_video_path = "pose_visualization.avi" 
    
    # 2. Load the 2D poses
    data = np.load(npz_path, allow_pickle=True)
    poses_2d = data['Cam_0'] 
    num_frames = poses_2d.shape[0]
    
    # 取得影片的長寬解析度
    first_img_name = f"test0001.png"
    first_img_path = os.path.join(img_folder, first_img_name)
    first_img = cv2.imread(first_img_path)
    if first_img is None:
        print(f"Cannot find the first image: {first_img_path}")
        return
        
    height, width, layers = first_img.shape
    size = (width, height)
    
    # 設定 OpenCV 的 VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_video_path, fourcc, 30.0, size)
    
    print("Saving video... This might take a moment.")
    
    # 3. Iterate through each frame
    for i in range(num_frames):
        img_name = f"test{i + 1:04d}.png" 
        img_path = os.path.join(img_folder, img_name)
        
        # Read the image
        img = cv2.imread(img_path)
        if img is None:
            continue
            
        # 4. Extract the joints for the current frame
        current_pose = poses_2d[i]
        
        # --- 5-1. 新增：先畫骨架連線 (畫在底層) ---
        for connection in SKELETON_CONNECTIONS:
            idx1, idx2 = connection
            
            # 確保資料量足夠，不會發生 index out of range 的報錯
            if idx1 < len(current_pose) and idx2 < len(current_pose):
                pt1 = (int(current_pose[idx1][0]), int(current_pose[idx1][1]))
                pt2 = (int(current_pose[idx2][0]), int(current_pose[idx2][1]))
                
                # 安全機制：如果任一端點是 (0,0)，代表資料遺失，跳過不畫這條線
                if (pt1[0] > 0 or pt1[1] > 0) and (pt2[0] > 0 or pt2[1] > 0):
                    # 畫藍色的線 (BGR: 255, 0, 0)，粗細為 2
                    cv2.line(img, pt1, pt2, color=(255, 0, 0), thickness=2)
        
        # --- 5-2. 修改：再畫每個關節點 (畫在線的上面，視覺比較清楚) ---
        for joint in current_pose:
            x, y = int(joint[0]), int(joint[1])
            
            # 同樣的安全機制：跳過 (0,0) 的錯誤座標
            if x > 0 or y > 0:
                # 畫綠色實心圓 (BGR: 0, 255, 0)
                cv2.circle(img, (x, y), radius=5, color=(0, 255, 0), thickness=-1)
            
        # 6. 把畫好點與線的圖片寫入影片中
        out.write(img)
        
        if i % 10 == 0:
            print(f"Processed frame {i}/{num_frames}")
            
    # 7. 釋放資源並關閉影片檔
    out.release()
    print(f"Video saved successfully to {output_video_path}")

if __name__ == "__main__":
    main()