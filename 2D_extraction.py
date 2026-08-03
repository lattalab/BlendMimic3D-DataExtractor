import numpy as np
from mathutils import Matrix
import os
import sys
import bpy

# Function to compute 2D positions
def compute_2d_positions(motion, K, RT):
    # Convert 3D motion to homogeneous coordinates (4xN)
    motion_homo = np.concatenate((motion, np.ones((1, motion.shape[1]))), axis=0)

    # Project 3D points to 2D using the camera projection matrix (3x4)
    P = K @ RT
    proj_homo = P @ motion_homo

    # Convert homogeneous coordinates to 2D positions (x, y) by dividing by the last element (w)
    proj_2d = proj_homo[:2, :] / proj_homo[2, :]

    return proj_2d

def main():
    # Get command-line arguments
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]  # Get arguments after '--'

    if len(argv) < 2:
        print("Usage: blender --background H3.6M.blend --python 2D_extraction.py -- S1 action_name")
        sys.exit(1)

    subject = argv[0]
    action_name = argv[1]

    
    # Load motion data from NPZ file
    motion_file = f"../../BlendMimic3D/{subject}/D3_Positions/{action_name}/{action_name}.npz"

    motion_data = np.load(motion_file, allow_pickle=True)
    motion = motion_data['positions_3d']

    # Load camera parameters from NPZ file
    cam_params_file = f"../../BlendMimic3D/{subject}/Cameras/matrices_{subject}.npz"
    cam_params = np.load(cam_params_file, allow_pickle=True)

    # Assuming cam_params is a dictionary with 'K' (intrinsic matrix) and 'RT' (extrinsic matrix)
    K_list = cam_params['K']
    RT_list = cam_params['RT']
    
    # Create a dictionary to hold 2D positions for each camera
    positions_2d_dict = {}
    for cam_idx, (K, RT) in enumerate(zip(K_list, RT_list)):
        # Compute 2D positions for each frame
        positions_2d_frames = []
        for motion_frame in motion:
            proj_2d = compute_2d_positions(motion_frame.T, K, RT)
            positions_2d_frames.append(proj_2d.T)
           
        # Convert the list of 2D positions to a NumPy array of shape (N, 17, 2)
        positions_2d_array = np.stack(positions_2d_frames, axis=0)
        # Store the 2D positions in the dictionary with camera name as the key
        positions_2d_dict[f'Camera_{cam_idx}'] = positions_2d_array 
        
       
    # Save 2D positions to another NPZ file
    # Get the absolute path of the script location
    script_path = bpy.path.abspath("//")
    # Create the directory to save the NPZ file if it does not exist
    save_path = os.path.join(script_path, f"../../BlendMimic3D/{subject}/D2_Positions/{action_name}")
    os.makedirs(save_path, exist_ok=True)
    # np.savez_compressed(os.path.join(save_path, "2D_positions.npz"), Cam_0=positions_2d_dict['Camera_0'], Cam_1=positions_2d_dict['Camera_1'], Cam_2=positions_2d_dict['Camera_2'], Cam_3=positions_2d_dict['Camera_3'])
    np.savez_compressed(os.path.join(save_path, "2D_positions.npz"), Cam_0=positions_2d_dict['Camera_0'])

if __name__ == "__main__":
    main()
