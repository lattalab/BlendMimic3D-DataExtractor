import numpy as np
import cv2
import os

def main():
    # 1. Paths to your data and rendered images
    npz_path = "../../BlendMimic3D/S1/D2_Positions/Walking2/2D_positions.npz"
    img_folder = "video" 
    
    # 這裡改成輸出 .avi 影片檔
    output_video_path = "pose_visualization.avi" 
    
    # 2. Load the 2D poses
    data = np.load(npz_path, allow_pickle=True)
    poses_2d = data['Cam_0'] 
    num_frames = poses_2d.shape[0]
    
    # --- 新增：讀取第一張圖片來取得影片的長寬解析度 ---
    first_img_name = f"test0001.png"
    first_img_path = os.path.join(img_folder, first_img_name)
    first_img = cv2.imread(first_img_path)
    if first_img is None:
        print(f"Cannot find the first image: {first_img_path}")
        return
        
    height, width, layers = first_img.shape
    size = (width, height)
    
    # --- 新增：設定 OpenCV 的 VideoWriter ---
    # 使用 XVID 編碼器存成 .avi，這是 OpenCV 內建最穩定、不需額外安裝套件的格式
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
            
        # 4. Extract the 17 joints for the current frame
        current_pose = poses_2d[i]
        
        # 5. Draw each joint as a circle on the image
        for joint in current_pose:
            x, y = int(joint[0]), int(joint[1])
            # Draw a green circle (BGR: 0, 255, 0)
            cv2.circle(img, (x, y), radius=5, color=(0, 255, 0), thickness=-1)
            
        # 6. 把畫好點的圖片寫入影片中
        out.write(img)
        
        if i % 10 == 0:
            print(f"Processed frame {i}/{num_frames}")
            
    # 7. 釋放資源並關閉影片檔
    out.release()
    print(f"Video saved successfully to {output_video_path}")

if __name__ == "__main__":
    main()