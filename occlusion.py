import bpy
import sys
import os
from mathutils import Vector
from bpy import context
import bpy_extras
import numpy as np
#from bpy_extras import object_utils

#Crucial joints sufficient for visualisation #FIX ME - Add more joints if desirable for MixamRig
BASE_JOINT_NAMES = [
                    'Hips', 'Spine', 'Spine1', 'Spine2', 'Head', 'HeadTop_End',
                    'LeftUpLeg', 'LeftLeg', 'LeftFoot', 
                    'RightUpLeg', 'RightLeg', 'RightFoot', 
                    'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
                    'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand'
                    ]

num_joints = len(BASE_JOINT_NAMES)  # Number of joints to be used from MixamoRig

#Source directory where .fbx exist
SRC_DATA_DIR ='regular'

# get the bone name without numbers
def remove_trailing_numbers(bone_name):
    # Initialize an empty string to hold the result
    result = ""

    # Iterate through each character in the bone_name
    for char in bone_name:
        # Check if the character is a digit (0-9)
        if char.isdigit():
            # If a digit is found, stop the iteration
            break
        # Add the character to the result string
        result += char

    return result                   

# Perspective camera model detection
def is_keypoint_out_of_view(keypoint, keypoint_location, camera, is_fisheye=False):
    scene = bpy.context.scene

    #camera = bpy.context.scene.camera
    
    # Get the 3D location of the keypoint
    #keypoint_location = keypoint.matrix @ bpy.context.object.matrix_world @ keypoint.location

    if is_fisheye:
        # Get the camera view matrix for the current frame
        mat_cam_inv = camera.matrix_world.inverted()
        # Transform to camera sensor space
        p_cam = mat_cam_inv @ keypoint_location

        # Blender camera looks along -Z axis; depth is along the negative Z direction
        z_depth = -p_cam.z
        if z_depth <= 0:
            return True  # The keypoint is behind the camera

        # Calculate incident angle theta from optical axis
        d = np.sqrt(p_cam.x**2 + p_cam.y**2)
        theta = np.arctan2(d, z_depth)

        # Blender fisheye_fov is the full field of view in radians
        fisheye_fov = camera.data.fisheye_fov
        if fisheye_fov is None:
            print(f"[WARN] Cannot read fisheye FOV from camera '{camera.name}'.")
            print("Fallback to 180 degrees.")
            fisheye_fov = np.pi  # 180 degrees in radians

        half_fov = fisheye_fov / 2.0

        # Check if incident angle exceeds 180-degree hemispherical FOV (theta > 90 degrees)
        # fisheye is at most +90 or -90 degrees, so if theta > 90 degrees, it is out of view
        return theta > half_fov
    else:
        # Project the 3D location of the keypoint onto the camera's image plane
        projected_co = bpy_extras.object_utils.world_to_camera_view(scene, camera, keypoint_location)

        # Check if the projected 2D point is outside the image boundaries
        if 0 <= projected_co.x <= 1 and 0 <= projected_co.y <= 1 and projected_co.z > 0:
            # The keypoint is within the camera's viewport
            return False
        else:
            # The keypoint is outside the camera's viewport
            return True

def is_self_mesh(hit_object, armature):
    """
    Determine whether the hit object belongs to the target character (Armature).
    Checks parent hierarchy and Armature modifiers dynamically.
    """
    if hit_object is None or armature is None:
        return False

    # 1. Direct match with the Armature object itself
    if hit_object == armature:
        return True

    # 2. Check if the object is parented to the Armature
    if hit_object.parent == armature:
        return True

    # 3. Check if the object has an Armature modifier referencing this armature
    if hit_object.type == 'MESH':
        for mod in hit_object.modifiers:
            if mod.type == 'ARMATURE' and mod.object == armature:
                return True

    return False

def is_occluded(keypoint, kpt_global_location, camera, armature):
   
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    #camera = bpy.context.scene.camera

    # Define the ray's starting and ending points
    ray_start = camera.matrix_world.translation
    ray_end = kpt_global_location

    # Calculate the direction from the camera to the keypoint
    ray_vector = ray_end - ray_start
    joint_distance = ray_vector.length

    # Avoid invalid zero-length rays
    if joint_distance <= 1e-6:
        return False
    
    # Perform the ray casting
    direction = ray_vector.normalized()
    result, location, normal, index, object, matrix = scene.ray_cast(depsgraph, ray_start, direction, distance=joint_distance)
    # print(keypoint.name)
    # print(object.name) 
    
    # Test the ray hit the object and the object is identical to desired bone name
    # if result and  remove_trailing_numbers(object.name) not in keypoint.name :
    #     #print(keypoint.name)
    #     #print(object.name)    
    #     return True

    if result:  # if ray hit something
        # Check if the ray hit the character's own skin, clothes, or accessories
        if is_self_mesh(object, armature):
            return False
            
        # If the hit object does not belong to this character, it is a genuine external occlusion (e.g. wall, other person)
        return True

    return False

def find_action_by_name(target_name):
    """
    Search for an action by exact match or substring containment.
    Handles Rokoko/Retargeting prefixes and suffixes automatically.
    """
    target = target_name.lower()
    
    # 1. Exact match
    if target_name in bpy.data.actions:
        return bpy.data.actions[target_name]
        
    # 2. Substring match (e.g. 'runleap' matches 'Armature|runleap Retarget')
    # In my example, the action name is '<bpy_struct, Action("Armature|Armature|walking2 Retarget") at 0x00000138CE1D3888>'
    for act in bpy.data.actions:
        # print(act.name.lower())
        if target in act.name.lower():
            return act
            
    return None

if __name__ == '__main__':
    
    start_frame = 0
    end_frame = 0
    argv = sys.argv[sys.argv.index("--") + 1:]  # Get arguments after "--"
    # Parse the command-line arguments
    if argv:
        for i in range(0, len(argv), 2):
            if argv[i] == "--joint-id":
                joint_id = argv[i + 1]
            elif argv[i] == "--armature-name":
                armature_name = argv[i + 1]
            elif argv[i] == "--subject":
                subject = argv[i + 1]
            elif argv[i] == "--action": 
                action_name = argv[i + 1]
            elif argv[i] == "--start_frame":
                start_frame = argv[i + 1]
            elif argv[i] == "--end_frame":
                end_frame = argv[i + 1]
               

    #Number of joints to be used from MixamoRig
    joint_names = ['mixamorig'+ joint_id +':' + x for x in BASE_JOINT_NAMES]
    
    OUT_DATA_DIR = f"../../BlendMimic3D/{subject}/Occlusions"

    # Create the directory to save the NPZ file if it does not exist
    save_dir = os.path.join(OUT_DATA_DIR, action_name)
    #Make save_dir
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # List of camera names
    # [Modified when needed] List of camera names, matching with your blender object name!
    # camera_names = ['Camera_0', 'Camera_1', 'Camera_2', 'Camera_3'] #Same order as H3.6M dataset 
    camera_names = [obj.name for obj in bpy.context.scene.objects if obj.type == 'CAMERA']
    camera_names.sort() 

    # Replace 'Armature' with the actual name of your armature object
    armature = bpy.data.objects[armature_name]
    keypoints = armature.pose.bones
    bone_struct = bpy.data.objects[armature_name].pose.bones
    action = armature.animation_data.action

    start_frame = int(action.frame_range[0])
    end_frame = int(action.frame_range[1])

    # Create a dictionary to store 'prob' vectors for each camera
    occlusions_dict = {}
        
    for cam_idx, cam_name in enumerate(camera_names):
        print("\n--------------------------------------------")
        print("camera name:", cam_name, sep=" ")
        cam = bpy.data.objects.get(cam_name)
        # each frame will have a 'prob' vector of size (20,) indicating visibility of each joint
        prob = np.ones(( end_frame-start_frame+1 , num_joints))
        print("start frame:", start_frame, sep=" ")

        # detect for camera type
        cycles_cam = getattr(cam.data, 'cycles', None)
        is_fisheye = (cam.data.type == 'PANO' and 
                      getattr(cam.data, 'panorama_type', '') == 'FISHEYE_EQUISOLID')
        
        for frame in range(start_frame, end_frame + 1):
            # Set the current frame
            bpy.context.scene.frame_set(frame)

            occluded_keypoints = []
            out_of_view_keypoints = []
            all_occlusions = []

            # Iterate over the keypoints (bones) of the armature
            for idx, name in enumerate(joint_names):
                keypoint = armature.pose.bones[name]
                global_location = armature.matrix_world @ bone_struct[name].matrix @ Vector((0, 0, 0))
                
                # Check if the keypoint is out of the viewport
                if is_keypoint_out_of_view(keypoint, global_location, cam, is_fisheye):
                    out_of_view_keypoints.append(keypoint.name)
                    all_occlusions.append(keypoint.name)
                    prob[frame-start_frame][idx] = 0

                # Check if the keypoint is occluded by any object in the scene
                elif is_occluded(keypoint, global_location, cam, armature):
                    # Keypoint is occluded
                    occluded_keypoints.append(keypoint.name)
                    all_occlusions.append(keypoint.name)
                    prob[frame-start_frame][idx] = 0
                
                
            #if occluded_keypoints:
                #print("Occluded keypoints in frame", frame)
                #for keypoint_name in occluded_keypoints:
                    #print(keypoint_name)
            #else:
                #print("No occluded keypoints in frame", frame)

            #if out_of_view_keypoints:
                #print("Out-of-view keypoints:")
                #for keypoint_name in out_of_view_keypoints:
                    #print(keypoint_name)
            #else:
                #print("All keypoints are within the camera's viewport.")
            '''
            if occluded_keypoints or out_of_view_keypoints:
                print("\n")
                print("Camera", cam_name)
                print("Frame", frame)
                print("List of non visible keypoints: ")
                for keypoint_name in all_occlusions:
                    print(keypoint_name)
                print("---------------------------------------")
                #exit(0)
            '''

        # Save 'prob' vector for this camera to a separate NPZ file
        print("End Frame", frame)
        ''' # Get the absolute path of the script location
        script_path = bpy.path.abspath("//")
        # Create the directory to save the NPZ file if it does not exist
        save_path = os.path.join(script_path, save_dir)
        os.makedirs(save_path, exist_ok=True)
                    
        np.savez_compressed(os.path.join(save_path, f"occluded_kpt_Camera_{cam_idx}.npz"), prob=prob)'''
                
        # Store the 2D positions in the dictionary with camera name as the key
        occlusions_dict[f'Camera_{cam_idx}'] = prob 
            
    # Save 2D positions to another NPZ file
    # Get the absolute path of the script location
    script_path = bpy.path.abspath("//")
    save_path = os.path.join(script_path, save_dir)
    os.makedirs(save_path, exist_ok=True)

    # np.savez_compressed(os.path.join(save_path, "occluded_kpt.npz"), Cam_0=occlusions_dict['Camera_0'],  Cam_1=occlusions_dict['Camera_1'],  Cam_2=occlusions_dict['Camera_2'],  Cam_3=occlusions_dict['Camera_3'])
    
    # [Modify to dynamic judgment]
    # rename the camera name as new key, and store all valid camera
    save_dict = {}
    for key, value in occlusions_dict.items():
        new_key = key.replace('Camera_', 'Cam_')
        save_dict[new_key] = value

    # make use of `**save_dict` , write all camera coordinates to the NPZ file
    np.savez_compressed(os.path.join(save_path, "occluded_kpt.npz"), **save_dict)
    print(f"Successfully stored occlusion data for: {list(save_dict.keys())}")