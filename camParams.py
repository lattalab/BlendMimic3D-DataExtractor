import bpy
from mathutils import Matrix, Vector, Quaternion
import numpy as np
import sys
import os

#---------------------------------------------------------------
# 3x4 P matrix from Blender camera
#---------------------------------------------------------------

# BKE_camera_sensor_size
def get_sensor_size(sensor_fit, sensor_x, sensor_y):
    if sensor_fit == 'VERTICAL':
        return sensor_y
    return sensor_x

# BKE_camera_sensor_fit
def get_sensor_fit(sensor_fit, size_x, size_y):
    if sensor_fit == 'AUTO':
        if size_x >= size_y:
            return 'HORIZONTAL'
        else:
            return 'VERTICAL'
    return sensor_fit

# Build intrinsic camera parameters from Blender camera data
#
# See notes on this in 
# blender.stackexchange.com/questions/15102/what-is-blenders-camera-projection-matrix-model
# as well as
# https://blender.stackexchange.com/a/120063/3581
def get_calibration_matrix_K_from_blender(camd):
    # support:
    # perspective cameras in EEVEE engine or CYCLE engine.
    # panoramic cameras (fisheye Equisolid) in cycles engine.
    if camd.type not in ('PERSP', 'PANO'):
        raise ValueError(f"Unsupported camera type: {camd.type}")
    
    scene = bpy.context.scene
    # f_in_mm = camd.lens # focal length 焦距

    if camd.type == 'PANO':
        # check cycle engine and fisheye camera lens
        f_in_mm = getattr(camd, 'fisheye_lens', camd.lens)
    else:
        # perspective camera
        f_in_mm = camd.lens  

    # render image in resolution
    scale = scene.render.resolution_percentage / 100
    resolution_x_in_px = scale * scene.render.resolution_x
    resolution_y_in_px = scale * scene.render.resolution_y

    sensor_size_in_mm = get_sensor_size(camd.sensor_fit, camd.sensor_width, camd.sensor_height)
    sensor_fit = get_sensor_fit(
        camd.sensor_fit,
        scene.render.pixel_aspect_x * resolution_x_in_px,
        scene.render.pixel_aspect_y * resolution_y_in_px
    )
    pixel_aspect_ratio = scene.render.pixel_aspect_y / scene.render.pixel_aspect_x
    if sensor_fit == 'HORIZONTAL':
        view_fac_in_px = resolution_x_in_px
    else:
        view_fac_in_px = pixel_aspect_ratio * resolution_y_in_px
    pixel_size_mm_per_px = sensor_size_in_mm / f_in_mm / view_fac_in_px
    s_u = 1 / pixel_size_mm_per_px
    s_v = 1 / pixel_size_mm_per_px / pixel_aspect_ratio

    # Parameters of intrinsic calibration matrix K
    u_0 = resolution_x_in_px / 2 - camd.shift_x * view_fac_in_px
    v_0 = resolution_y_in_px / 2 + camd.shift_y * view_fac_in_px / pixel_aspect_ratio
    skew = 0 # only use rectangular pixels

    K = Matrix(
        ((s_u, skew, u_0),
        (   0,  s_v, v_0),
        (   0,    0,   1)))
    return K

# Returns camera rotation and translation matrices from Blender.
# 
# There are 3 coordinate systems involved:
#    1. The World coordinates: "world"
#       - right-handed
#    2. The Blender camera coordinates: "bcam"
#       - x is horizontal
#       - y is up
#       - right-handed: negative z look-at direction
#    3. The desired computer vision camera coordinates: "cv"
#       - x is horizontal
#       - y is down (to align to the actual pixel coordinates 
#         used in digital images)
#       - right-handed: positive z look-at direction
def get_3x4_RT_matrix_from_blender(cam):
    # bcam stands for blender camera
    R_bcam2cv = Matrix(
        ((1, 0,  0),
        (0, -1, 0),
        (0, 0, -1)))

    # Transpose since the rotation is object rotation, 
    # and we want coordinate rotation
    # R_world2bcam = cam.rotation_euler.to_matrix().transposed()
    # T_world2bcam = -1*R_world2bcam @ location
    #
    # Use matrix_world instead to account for all constraints
    location, rotation = cam.matrix_world.decompose()[0:2]
    R_world2bcam = rotation.to_matrix().transposed()

    # Convert camera location to translation vector used in coordinate changes
    # T_world2bcam = -1*R_world2bcam @ cam.location
    # Use location from matrix_world to account for constraints:     
    T_world2bcam = -1*R_world2bcam @ location

    # Build the coordinate transform matrix from world to computer vision camera
    R_world2cv = R_bcam2cv@R_world2bcam
    T_world2cv = R_bcam2cv@T_world2bcam

    # put into 3x4 matrix
    RT = Matrix((
        R_world2cv[0][:] + (T_world2cv[0],),
        R_world2cv[1][:] + (T_world2cv[1],),
        R_world2cv[2][:] + (T_world2cv[2],)
        ))
    return RT

def get_3x4_P_matrix_from_blender(cam):
    K = get_calibration_matrix_K_from_blender(cam.data)
    RT = get_3x4_RT_matrix_from_blender(cam)
    return K@RT, K, RT


# Function to save intrinsic parameters into a dictionary
def save_intrinsic_params_to_dict(cam):
    K = get_calibration_matrix_K_from_blender(cam.data)
    P, _, _ = get_3x4_P_matrix_from_blender(cam)
    
    intrinsic_params = {
        'id': cam.name,
        'center': [K[0][2], K[1][2]],
        'focal_length': [K[0][0], K[1][1]],
        'radial_distortion': [0, 0, 0],  # Placeholder values as radial distortion is not computed in the existing code
        'tangential_distortion': [0, 0],  # Placeholder values as tangential distortion is not computed in the existing code
        'res_w': bpy.context.scene.render.resolution_x,
        'res_h': bpy.context.scene.render.resolution_y,
        'azimuth': 0,  # Placeholder value for azimuth as it is not computed in the existing code
    }
    return intrinsic_params

# Function to save extrinsic parameters into a dictionary
def save_extrinsic_params_to_dict(RT):
    # Extract the 3x3 rotation matrix from the extrinsic parameters matrix
    R_world2cv = Matrix(((RT[0][0], RT[0][1], RT[0][2]),
                         (RT[1][0], RT[1][1], RT[1][2]),
                         (RT[2][0], RT[2][1], RT[2][2])))
                         

    # Convert the rotation matrix to a quaternion
    orientation_quaternion = convert_matrix_to_quaternion(R_world2cv)

    # Get the translation vector from the last column of the extrinsic parameters matrix
    translation =  Vector((RT[0][3], RT[1][3], RT[2][3]))
    
    
    extrinsic_params = {
        'orientation': [ orientation_quaternion.w, orientation_quaternion.x, orientation_quaternion.y, orientation_quaternion.z],
        'translation': [translation[0], translation[1], translation[2]],
    }
    
    return extrinsic_params



def convert_matrix_to_quaternion(R_world2cv):
    # Convert the rotation matrix to a quaternion representation
    quat_orientation = R_world2cv.to_quaternion()
    return quat_orientation

# ----------------------------------------------------------
if __name__ == "__main__":
     # Get command-line arguments
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]  # Get arguments after '--'

    if len(argv) < 1:
        print("Usage: blender --background H3.6M.blend --python camParamsV2.py -- S1")
        sys.exit(1)

    subject = argv[0]

    # --- [Safe Coding] If the folder is not created, automatically invent one ---
    save_dir = f"../../BlendMimic3D/{subject}/Cameras"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    # ---------------------------
    
    # [Modified when needed] List of camera names, matching with your blender object name!
    # camera_names = ['Camera_0', 'Camera_1', 'Camera_2', 'Camera_3'] #Same order as H3.6M dataset 
    #camera_names = ['Camera_0'] #Same order as H3.6M dataset 

    # --- Dynamic fetch all camera objects ---
    camera_names = [obj.name for obj in bpy.context.scene.objects if obj.type == 'CAMERA']
    camera_names.sort() 
    print(f"Detected Cameras in Blender: {camera_names}")

    intrinsic_params_list = []
    extrinsic_params_list = []  # List to hold individual camera extrinsic parameter dictionaries for each subject
    K_list = []
    RT_list = []
    P_list = []
    camera_types_list = []  # Record the camera types for each camera
    extrinsic_params_dict = {}
    i=0
    
    for cam_name in camera_names:
        
        cam = bpy.data.objects.get(cam_name)
        P, K, RT = get_3x4_P_matrix_from_blender(cam)
        
        print(K)
        print(RT)

        # [ADD] record camera type for each camera
        if cam.data.type == 'PANO' and getattr(cam.data, 'panorama_type', '') == 'FISHEYE_EQUISOLID':
            cam_type = 'FISHEYE_EQUISOLID'
        else:
            cam_type = 'PERSP'
        camera_types_list.append(cam_type)
           
        nP = np.matrix(P)
        np.savetxt(f"../../BlendMimic3D/{subject}/Cameras/CamView{i}_P3x4.txt", nP)  # to select precision, use e.g. fmt='%.2f'

        #Create a list to hold intrinsic parameter dictionaries for all cameras
        intrinsic_params = save_intrinsic_params_to_dict(cam)
        intrinsic_params_list.append(intrinsic_params)
       
        # Create a dictionary to hold extrinsic parameter dictionaries for each subject
        extrinsic_params = save_extrinsic_params_to_dict(RT)
        extrinsic_params_list.append(extrinsic_params)
        
        # Append matrices K, RT, and P to their respective lists
        K_list.append(K)
        RT_list.append(RT)
        P_list.append(P)
       
        #h36m_cameras_extrinsic_params = {
         #   subject : [save_extrinsic_params_to_dict(RT)],
        #}
        #print(h36m_cameras_extrinsic_params)
       
        
        #orientation= h36m_cameras_extrinsic_params[subject][0]['orientation']
        #translation = h36m_cameras_extrinsic_params[subject][0]['translation']
         
        i = i+1
        
    extrinsic_params_dict = {
        subject: extrinsic_params_list
    }
    
    print(intrinsic_params_list)
    print(extrinsic_params_dict)
    print(K_list)
    print(camera_types_list)
    # Save intrinsic and extrinsic parameters to npz file
    np.savez(f"../../BlendMimic3D/{subject}/Cameras/camera_params_{subject}.npz", intrinsic_params=intrinsic_params_list, extrinsic_params=extrinsic_params_dict)
     # Save matrices K, RT, and P to another npz file
    np.savez(f"../../BlendMimic3D/{subject}/Cameras/matrices_{subject}.npz", K=K_list, RT=RT_list, P=P_list, types=camera_types_list)

    print("Data saved successfully.")
    
   