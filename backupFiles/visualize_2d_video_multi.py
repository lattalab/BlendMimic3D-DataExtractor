import numpy as np
import cv2
import os
import argparse  

# --- Define Skeleton Connections (using Joint Indices) ---
SKELETON_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5),   
    (0, 6), (6, 7), (7, 8),                   
    (0, 9), (9, 10), (10, 11),                
    (3, 12), (12, 13), (13, 14), (14, 15),    
    (3, 16), (16, 17), (17, 18), (18, 19)     
]

def main():
    # --- 1. Setup Command Line Arguments ---
    parser = argparse.ArgumentParser(description="Visualize 2D poses for MULTIPLE people on rendered images.")
    
    # [關鍵修改]: 使用 nargs='+' 允許傳入多個 npz 檔案路徑
    parser.add_argument("--npz", type=str, nargs='+', required=True, help="List of paths to the 2D coordinates NPZ files (e.g. S1.npz S2.npz).")
    parser.add_argument("--occ_npz", type=str, nargs='*', default=[], help="(Optional) List of paths to the occlusion NPZ files.")
    
    parser.add_argument("--hide_occluded", action="store_true", help="If set, occluded points will NOT be drawn.")
    parser.add_argument("--cam", type=str, required=True, help="Target Camera name EX: Cam_0")
    parser.add_argument("--img_folder", type=str, required=True, help="Path to the folder containing rendered images.")
    parser.add_argument("--output", type=str, default="multi_person_output.avi", help="Output video filename.")
    
    args = parser.parse_args()

    # --- 2. Load Multiple 2D Poses & Occlusions ---
    num_people = len(args.npz)
    poses_2d_list = []
    visibilities_list = []
    max_frames = 0

    print(f"[*] Detected {num_people} subjects. Loading data...")

    for p_idx in range(num_people):
        # 讀取 2D 座標
        data = np.load(args.npz[p_idx], allow_pickle=True)
        if args.cam not in data:
            raise KeyError(f"Camera '{args.cam}' not found in {args.npz[p_idx]}!")
        
        poses = data[args.cam]
        poses_2d_list.append(poses)
        max_frames = max(max_frames, poses.shape[0]) # 追蹤最長的動作幀數
        
        # 讀取遮蔽資料 (如果有對應的檔案)
        vis = None
        if p_idx < len(args.occ_npz) and os.path.exists(args.occ_npz[p_idx]):
            occ_data = np.load(args.occ_npz[p_idx], allow_pickle=True)
            if args.cam in occ_data:
                vis = occ_data[args.cam]
                if vis.shape[0] != poses.shape[0]:
                    print(f"[WARN] Frame count mismatch for subject {p_idx+1}! Disabling occlusion.")
                    vis = None
        visibilities_list.append(vis)

    # --- 3. Setup Image Sequence & Video Writer ---
    image_files = sorted([f for f in os.listdir(args.img_folder) if f.endswith('.png')])
    if not image_files:
        raise FileNotFoundError(f"Cannot find PNG images in: {args.img_folder}")

    # 使用實際圖片數量與預測最大幀數的最小值，避免讀不到圖片
    total_render_frames = min(len(image_files), max_frames)

    first_img = cv2.imread(os.path.join(args.img_folder, image_files[0]))
    height, width, _ = first_img.shape
    
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(args.output, fourcc, 30.0, (width, height))
    
    print(f"[*] Initializing rendering for {args.cam} (Total Frames: {total_render_frames})...")
    
    # --- 4. Iterate through each frame ---
    for i in range(total_render_frames):
        img_path = os.path.join(args.img_folder, image_files[i])
        img = cv2.imread(img_path)
        if img is None: continue
            
        # [關鍵修改]: 在每一幀中，為每個人物畫骨架
        for p_idx in range(num_people):
            poses = poses_2d_list[p_idx]
            
            # [防呆]: 如果這個人的動作比較短 (例如 150 幀)，就不畫後面的幀
            if i >= poses.shape[0]:
                continue
                
            current_pose = poses[i]
            vis = visibilities_list[p_idx]
            current_vis = vis[i] if vis is not None else np.ones(current_pose.shape[0])
            
            # --- 4-1. Draw Skeleton Lines ---
            for connection in SKELETON_CONNECTIONS:
                idx1, idx2 = connection
                if idx1 < len(current_pose) and idx2 < len(current_pose):
                    vis1, vis2 = current_vis[idx1], current_vis[idx2]
                    
                    if args.hide_occluded and (vis1 == 0 or vis2 == 0):
                        continue

                    pt1 = (int(current_pose[idx1][0]), int(current_pose[idx1][1]))
                    pt2 = (int(current_pose[idx2][0]), int(current_pose[idx2][1]))
                    
                    if (pt1[0] > 0 or pt1[1] > 0) and (pt2[0] > 0 or pt2[1] > 0):
                        line_color = (0, 255, 0) if (vis1 == 1 and vis2 == 1) else (0, 0, 255)
                        cv2.line(img, pt1, pt2, color=line_color, thickness=3)
            
            # --- 4-2. Draw Joint Points ---
            for idx, joint in enumerate(current_pose):
                x, y = int(joint[0]), int(joint[1])
                is_visible = current_vis[idx]

                if args.hide_occluded and is_visible == 0: continue
                
                if x > 0 or y > 0:
                    dot_color = (0, 255, 0) if is_visible == 1 else (0, 0, 255)
                    cv2.circle(img, (x, y), radius=7, color=(255, 255, 255), thickness=-1)
                    cv2.circle(img, (x, y), radius=5, color=dot_color, thickness=-1)
            
        out.write(img)
        if (i + 1) % 10 == 0:
            print(f"    - Processed frame {i + 1}/{total_render_frames}")
            
    out.release()
    print(f"[SUCCESS] Video saved to {args.output}")

if __name__ == "__main__":
    main()