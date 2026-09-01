import numpy as np
import cv2
import os
import argparse  

# sample usage
# python3 visualize_2d_video_v3.py --cam Cam_0 --img_folder images/side_view --output Cam0_visualization.avi

# --- Define Skeleton Connections (using Joint Indices) ---
# Format: (Start_Node_Index, End_Node_Index)
SKELETON_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5),   # 脊椎與頭部: Hips -> Spine -> Spine1 -> Spine2 -> Head -> HeadTop_End
    (0, 6), (6, 7), (7, 8),                   # 左腿: Hips -> LeftUpLeg -> LeftLeg -> LeftFoot
    (0, 9), (9, 10), (10, 11),                # 右腿: Hips -> RightUpLeg -> RightLeg -> RightFoot
    (3, 12), (12, 13), (13, 14), (14, 15),    # 左手: Spine2 -> LeftShoulder -> LeftArm -> LeftForeArm -> LeftHand
    (3, 16), (16, 17), (17, 18), (18, 19)     # 右手: Spine2 -> RightShoulder -> RightArm -> RightForeArm -> RightHand
]

def main():
    # --- 1. Setup Command Line Arguments ---
    parser = argparse.ArgumentParser(description="Visualize 2D poses on rendered images.")
    
    # Set up the argument value
    # 2D npz file location
    parser.add_argument("--npz", type=str, nargs='+', default=["../../BlendMimic3D/S1/D2_Positions/Walking2/2D_positions.npz"], help="Path to the 2D coordinates NPZ file.")
    # Occlusion arguments
    parser.add_argument("--occ_npz", type=str, nargs='+', default=["../../BlendMimic3D/S1/Occlusions/Walking2/occluded_kpt.npz"], help="(Optional) Path to the occlusion NPZ file (e.g., occluded_kpt.npz).")
    parser.add_argument("--hide_occluded", action="store_true", help="(Optional) If set, occluded points will NOT be drawn. Otherwise, they will be drawn in red.")
    # select camera
    parser.add_argument("--cam", type=str, required=True, help="Target Camera name EX: Cam_0 OR Cam_1")
    # image folder to be processed
    parser.add_argument("--img_folder", type=str, required=True, help="Path to the folder containing rendered images.")
    # output filename
    parser.add_argument("--output", type=str, default="pose_visualization.avi", help="Output video filename.")
    
    args = parser.parse_args()

    # Store the argument
    npz_path = args.npz
    occ_npz_path = args.occ_npz
    hide_occluded = args.hide_occluded
    cam_name = args.cam
    img_folder = args.img_folder
    output_video_path = args.output
    
    # --- 2. Load the 2D poses ---
    num_people = len(args.npz)
    poses_2d_list = []
    visibilities_list = []
    max_frames = 0

    print(f"[*] Detected {num_people} subjects. Loading data...")

    for p_idx in range(num_people):
        # load the 2D coordinates from the NPZ file
        data = np.load(npz_path[p_idx], allow_pickle=True)
    
        # Error detection: avoid retrieve unknown camera
        if cam_name not in data:
            print(f"ERROR: Cannot find the camera inside NPZ file '{cam_name}'!")
            print(f"Current available camera in NPZ: {list(data.keys())}")
            return
        
        # read from specific camera
        poses_2d = data[cam_name]   # shape: (frames, 17, 2)
        poses_2d_list.append(poses_2d)
        # getting total num of frame for this person
        current_frames = poses_2d.shape[0]
        max_frames = max(max_frames, poses_2d.shape[0])
        print(f"[*] Loaded 2D poses for subject {p_idx + 1}: {current_frames} frames.")

        # --- 3. Load Occlusion Data (with Error Handling) ---
        visibilities = None     # shape: (frames, 20) or (frames, 17) depending on the occlusion data
        if occ_npz_path:
            if not os.path.exists(occ_npz_path[p_idx]):
                print(f"[WARN] Occlusion file not found at {occ_npz_path[p_idx]}. Proceeding without occlusion effects.")
            else:
                occ_data = np.load(occ_npz_path[p_idx], allow_pickle=True)
                if cam_name not in occ_data:
                    print(f"[WARN] Camera '{cam_name}' not found in Occlusion NPZ. Proceeding without occlusion effects.")
                else:
                    visibilities = occ_data[cam_name]
                    
                    # Sanity check: Ensure frame counts match
                    if visibilities.shape[0] != current_frames:
                        print(f"[WARN] Frame count mismatch! 2D: {current_frames}, Occ: {visibilities.shape[0]}. Disabling occlusion.")
                        visibilities = None
                    else:
                        print(f"[*] Successfully loaded occlusion data for subject {p_idx + 1}. Mode: {'HIDE' if hide_occluded else 'RED DOTS'}")

        visibilities_list.append(visibilities)

    # --- 4. Setup Image Sequence & Video Writer ---
    # Assume the images are stored with `png` file extenstion
    # the filename is like <name><frame_number>.png, e.g., test0001.png, test0002.png, ...
    image_files = sorted([f for f in os.listdir(img_folder) if f.endswith('.png')])

    if not image_files:
        print(f"[ERROR] Cannot find any PNG images in folder: {img_folder}")
        return

    # Retrieve video resolution from the first frame
    total_render_frames = min(len(image_files), max_frames)

    first_img_name = image_files[0]
    first_img_path = os.path.join(img_folder, first_img_name)
    first_img = cv2.imread(first_img_path)
    
    if first_img is None:
        print(f"[ERROR] Cannot find the reference image for resolution: {first_img_path}")
        return
        
    height, width, layers = first_img.shape
    size = (width, height)
    
    # Initialize OpenCV VideoWriter (Codec: XVID, FPS: 30.0)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_video_path, fourcc, 30.0, size)
    
    print(f"[*] Initializing rendering for {cam_name}...")
    print(f"[*] Output path: {output_video_path}")
    
    # --- 5. Iterate through each frame ---
    for i in range(total_render_frames):
        img_name = image_files[i]
        img_path = os.path.join(img_folder, img_name)
        
        # Read the image
        img = cv2.imread(img_path)
        if img is None:
            print(f"[WARN] Image {img_path} not found. Skipping frame {i + 1}.")
            continue

        # draw for each person
        for p_idx in range(num_people):
            # Extract the joints for the current frame
            poses = poses_2d_list[p_idx]

            # ignore the frame if the current person's pose is shorter than the total frames
            if i >= poses.shape[0]:
                continue
            current_pose = poses[i]

            # If occlusion data is available, load current frame's visibility (1.0 = visible, 0.0 = occluded)
            # If not available, create a dummy array filled with 1.0 (everything is visible)
            visibilities = visibilities_list[p_idx]
            current_vis = visibilities[i] if visibilities is not None else np.ones(current_pose.shape[0])
        
            # --- 5-1. Draw Skeleton Lines ---
            for connection in SKELETON_CONNECTIONS:
                idx1, idx2 = connection
                
                # Boundary check to prevent index out of range errors
                if idx1 < len(current_pose) and idx2 < len(current_pose):
                    # Check visibility for both ends of the bone
                    vis1 = current_vis[idx1]
                    vis2 = current_vis[idx2]
                
                    # If 'hide_occluded' is enabled and ANY of the two joints are occluded, skip drawing this line
                    if hide_occluded and (vis1 == 0 or vis2 == 0):
                        continue

                    pt1 = (int(current_pose[idx1][0]), int(current_pose[idx1][1]))
                    pt2 = (int(current_pose[idx2][0]), int(current_pose[idx2][1]))
                    
                    # Sanity check: Avoid drawing lines to the origin (0,0) which indicates missing data
                    if (pt1[0] > 0 or pt1[1] > 0) and (pt2[0] > 0 or pt2[1] > 0):
                        # Determine line color: Black if both visible, Red if any part is occluded
                        line_color = (0, 255, 0) if (vis1 == 1 and vis2 == 1) else (0, 0, 255)
                        cv2.line(img, pt1, pt2, color=line_color, thickness=3)
        
            # --- 5-2. Draw Joint Points ---
            for idx, joint in enumerate(current_pose):
                x, y = int(joint[0]), int(joint[1])
                is_visible = current_vis[idx]

                # If 'hide_occluded' is enabled and the joint is occluded, skip drawing this point
                if hide_occluded and is_visible == 0:
                    continue
                
                # Sanity check: Avoid rendering the origin (0,0)
                if x > 0 or y > 0:
                    # Determine dot color: Black if visible, Red if occluded
                    dot_color = (0, 255, 0) if is_visible == 1 else (0, 0, 255)
                    cv2.circle(img, (x, y), radius=7, color=(255, 255, 255), thickness=-1) # White border for better visibility
                    cv2.circle(img, (x, y), radius=5, color=dot_color, thickness=-1)       # Inner dot color based on visibility
                
        # 6. Write the processed frame to the video file
        out.write(img)
        
        if (i + 1) % 10 == 0:
            print(f"    - Processed frame {i + 1}/{total_render_frames}")
            
    # 7. Cleanup Resources
    out.release()
    print(f"[SUCCESS] Video saved successfully to {output_video_path}")
    
if __name__ == "__main__":
    main()
