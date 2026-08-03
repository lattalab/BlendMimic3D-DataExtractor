import numpy as np
import cv2
import os

def main():
    # 1. Paths to your data and rendered images
    # Replace these paths with your actual paths!
    npz_path = "../../BlendMimic3D/S1/D2_Positions/Walking/2D_positions.npz"
    img_folder = "../video" 
    
    # 2. Load the 2D poses
    data = np.load(npz_path, allow_pickle=True)
    # Extract the array for Camera_0. Shape should be (Frames, 17, 2)
    poses_2d = data['Cam_0'] 
    
    # 3. Iterate through each frame
    num_frames = poses_2d.shape[0]
    
    for i in range(num_frames):
        # Blender default output names are 1-indexed and zero-padded (e.g., 0001.png)
        img_name = f"test{i + 1:04d}.png" 
        img_path = os.path.join(img_folder, img_name)
        
        # Read the image
        img = cv2.imread(img_path)
        if img is None:
            print(f"Cannot find image: {img_path}")
            continue
            
        # 4. Extract the 17 joints for the current frame
        current_pose = poses_2d[i]
        
        # 5. Draw each joint as a circle on the image
        for joint in current_pose:
            # OpenCV requires integer coordinates for drawing
            x, y = int(joint[0]), int(joint[1])
            
            # Draw a green circle (BGR: 0, 255, 0) with radius 5
            cv2.circle(img, (x, y), radius=5, color=(0, 255, 0), thickness=-1)
            
        # 6. Display the image
        cv2.imshow('2D Pose Visualization', img)
        
        # Wait 30ms before showing the next frame (Press 'q' to quit)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()