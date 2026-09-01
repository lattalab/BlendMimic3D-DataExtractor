import bpy
import os
import sys
import json
import shutil
from mathutils import Vector
import numpy as np 

HOME_FILE_PATH = os.path.abspath('homefile.blend')

# This Resolution is for human 3.6
# RESOLUTION = (1000, 1002)
RESOLUTION = (1920, 1080)

#Crucial joints sufficient for visualisation #FIX ME - Add more joints if desirable for MixamRig
# [Modified] according to Rokoko Retargeting List
BASE_JOINT_NAMES = [
                    'Hips', 'Spine', 'Spine1', 'Spine2', 'Head', 'HeadTop_End',
                    'LeftUpLeg', 'LeftLeg', 'LeftFoot', 
                    'RightUpLeg', 'RightLeg', 'RightFoot', 
                    'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
                    'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand'
                    ]
#Source directory where .fbx exist
SRC_DATA_DIR ='regular'

#Ouput directory where .fbx to JSON dict will be stored
OUT_DATA_DIR ='fbx2json'

#Final directory where NPY files will ve stored
#FINAL_DIR_PATH ='json2npy'

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

def fbx2jointDict(joint_names, armature_name, action_name):
    
    # #Remove 'Cube' object if exists in the scene
    # if bpy.data.objects.get('Cube') is not None:
    #     cube = bpy.data.objects['Cube']
    #     bpy.data.objects.remove(cube)
    
    # #Intensify Light Point in the scene
    # if bpy.data.objects.get('Light') is not None:
    #     bpy.data.objects['Light'].data.energy = 2
    #     bpy.data.objects['Light'].data.type = 'POINT'
    
    #Set resolution and it's rendering percentage
    bpy.data.scenes['Scene'].render.resolution_x = RESOLUTION[0]
    bpy.data.scenes['Scene'].render.resolution_y = RESOLUTION[1]
    bpy.data.scenes['Scene'].render.resolution_percentage = 100
    
    # #Base file for blender
    # bpy.ops.wm.save_as_mainfile(filepath=HOME_FILE_PATH)

    armature = bpy.data.objects[armature_name]
    bone_struct = armature.pose.bones

    # Get the action currently playing on this armature
    action = armature.animation_data.action
    start_frame = int(action.frame_range[0])
    end_frame = int(action.frame_range[1])
    print(f"[*] Locked Armature: '{armature.name}' | Action: '{action.name}' (Frames {start_frame}-{end_frame})")

    # Setup directories
    save_dir = os.path.join(OUT_DATA_DIR, action_name, 'jointDict')
    if os.path.exists(save_dir):
        shutil.rmtree(save_dir)
    os.makedirs(save_dir, exist_ok=True)   

    for i in range(start_frame, end_frame + 1):
        
        bpy.context.scene.frame_set(i)
        
        # bone_struct = bpy.data.objects[armature_name].pose.bones
        # armature = bpy.data.objects[armature_name]

        # --- Debug ---
        # if (i == 1):
            # print("Skeleton keys:", bone_struct.keys())

        # store the keypoint coordinate
        out_dict = {'pose_keypoints_3d': []}
    
        for name in joint_names:
            global_location = armature.matrix_world @ bone_struct[name].matrix @ Vector((0, 0, 0))
            l = [global_location[0], global_location[1], global_location[2]]
            out_dict['pose_keypoints_3d'].extend(l)
        
        save_path = os.path.join(save_dir,'%04d_keypoints.json'%i)
        with open(save_path,'w') as f:
            json.dump(out_dict, f)

def jointDict2npy(subject, action_name):
    
    json_dir = OUT_DATA_DIR
    npz_dir = f"../../BlendMimic3D/{subject}/D3_Positions"
    
    if not os.path.exists(npz_dir):
        os.makedirs(npz_dir)

    files_path = os.path.join(json_dir, action_name, 'jointDict')
    frame_files = sorted([f for f in os.listdir(files_path) if f.endswith('.json')])
    
    motion = []
        
    for frame_file in frame_files:
        file_path = os.path.join(files_path,frame_file)
        
        with open(file_path) as f:
            info = json.load(f)
            joint = np.array(info['pose_keypoints_3d']).reshape((-1, 3))
        motion.append(joint[: ,:])
        
    # shape: (N, 3, T)    
    motion = np.stack(motion,axis=2)
    
    save_path = os.path.join(npz_dir, action_name)
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    print('Saving...')
    # change to (T, N, 3)
    positions = motion.transpose(2, 0, 1)
    np.savez_compressed(os.path.join(save_path, action_name + ".npz"), positions_3d=positions)
    
    print('Done.')

    data = motion
    print(data.shape)
    reshaped_data = np.reshape(data, (data.shape[0], -1))
    np.savetxt(save_path+'/'+'data3D.txt', reshaped_data, delimiter=' ') 
    
    ''' 
    cdf_data = data.transpose(2, 0, 1)
    # Define the attributes
    attributes = {
        'Version': '3.3.0',
        'Encoding': 6,
        'Majority': 'Column_major',
        'zVariables': ['Pose'],
        'Copyright': '\nCommon Data Format (CDF)\n(C) Copyright 1990-2009 NASA/GSFC\nSpace Physics Data Facility\nNASA/Goddard Space Flight Center\nGreenbelt, Maryland 20771 USA\n(Internet -- CDFSUPPORT@LISTSERV.GSFC.NASA.GOV)\n',
    }

    # Create a CDF file and open it for writing
    filename = 'data.cdf'
    cdffile = cdflib.CDF(filename, '')

    # Write the data to the CDF file
    cdffile.write(data)

    # Set the CDF attributes
    cdffile.attrs.update(attributes)

    # Close the CDF file
    cdffile.close()
    '''
    
        
if __name__ == '__main__':
    
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
               

    #Number of joints to be used from MixamoRig
    # format: mixamorig:<joint name>
    joint_names = ['mixamorig'+ joint_id +':' + x for x in BASE_JOINT_NAMES]
   
    #Convert .fbx files to JSON dict
    fbx2jointDict(joint_names, armature_name, action_name)
    
    #Convert JSON dict to NPY 
    jointDict2npy(subject, action_name)   

         


