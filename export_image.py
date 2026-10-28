import bpy
import os
import sys

# sample usage:
# Perspective cameras -> EEVEE
# Fisheye / panoramic cameras -> Cycles

# blender -b three_people.blend --python render_cameras.py -- ./images/three_people 

def parse_args():
    # Retrieve arguments after '--'
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
    else:
        args = []
        
    output_dir = args[0] if len(args) > 0 else "./images/temp"
    output_dir = os.path.abspath(output_dir)
    print(f"[*] Output directory: {output_dir}")
    
    return output_dir

def configure_engine(scene, engine):
    # Setup rendering engine parameters
    if engine == "CYCLES":
        scene.render.engine = 'CYCLES'
        gpu_configured = False
        
        # Configure Cycles GPU acceleration
        try:
            prefs = bpy.context.preferences
            cprefs = prefs.addons['cycles'].preferences
            cprefs.get_devices()
            
            # Prefer OptiX or CUDA for NVIDIA GPUs
            for device_type in ('OPTIX', 'CUDA', 'METAL', 'OPENCL'):
                try:
                    cprefs.compute_device_type = device_type
                    cprefs.get_devices()

                    # find all available GPU devices
                    gpu_devices = [d for d in cprefs.devices if d.type == device_type and d.type != 'CPU']

                    if gpu_devices:
                        # Activate all available GPU devices 
                        for d in cprefs.devices:
                            d.use = (d in gpu_devices)

                        activated_names = [d.name for d in gpu_devices]
                        print(f"[*] Cycles compute device set to: {device_type}")
                        print(f"[*] Activated GPUs: {', '.join(activated_names)}")
                        gpu_configured = True
                        break
                        
                except Exception:
                    continue

            if not gpu_configured:
                raise RuntimeError("No compatible GPU devices found or activated.")
              
            scene.cycles.device = 'GPU'

        except Exception as e:
            print(f"[WARN] Failed to configure GPU for Cycles, falling back: {e}")
            scene.cycles.device = 'CPU'
            print("[*] Proceeding with CPU rendering...")

        # ---------------------------------------------------------
        # Cycles Sampling Settings (算圖快一點)
        # ---------------------------------------------------------
        scene.render.use_persistent_data = True

        # Adaptive sampling:
        # Easy pixels stop early, difficult pixels get more samples.
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.samples = 10
        scene.cycles.adaptive_min_samples = 4
        scene.cycles.adaptive_threshold = 0.08

        # Denoising
        scene.cycles.use_denoising = True

        # Preview only
        scene.cycles.preview_samples = 8
        

        # Light Paths / Max Bounces (光線反彈次數，降低可減少運算負擔)
        scene.cycles.max_bounces = 4
        scene.cycles.diffuse_bounces = 2
        scene.cycles.glossy_bounces = 1
        scene.cycles.transmission_bounces = 2
        scene.cycles.transparent_max_bounces = 4
        scene.cycles.volume_bounces = 0
        
        print("[*] Cycles sampling and bounce optimization parameters applied.")
            
    else:
        # EEVEE uses GPU by default
        # Compatible with Blender 4.x / 5.x EEVEE Next and Blender 3.x EEVEE

        try:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        except Exception:
            scene.render.engine = 'BLENDER_EEVEE'
            
        print("[*] Render engine set to EEVEE (Real-time GPU Rasterization).")

def get_engine_for_camera(cam):
    # Perspective cameras use EEVEE.
    if cam.data.type == 'PERSP':
        return "EEVEE"

    # Blender fisheye cameras are panoramic cameras and require Cycles.
    if cam.data.type == 'PANO':
        return "CYCLES"

    # Use EEVEE for other camera types unless explicitly changed.
    return "EEVEE"

def main():
    output_base_dir = parse_args()
    scene = bpy.context.scene
    
    # Output image format settings
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    
    # Detect and sort all camera objects
    cameras = sorted(
        [
            obj for obj in scene.objects if obj.type == 'CAMERA' and not obj.hide_render
        ], 
        key=lambda x: x.name
    )
    
    if not cameras:
        print("[ERROR] No camera objects found in the scene!")
        sys.exit(1)
        
    print(f"[*] Found {len(cameras)} cameras: {[cam.name for cam in cameras]}")
    print(f"[*] Target frame range: {scene.frame_start} ~ {scene.frame_end}")
    
    # Render sequence for each camera
    for cam_idx, cam in enumerate(cameras):
        # Setup engine configurations
        engine = get_engine_for_camera(cam)
        configure_engine(scene, engine)

        # Format folder name: Cam_0, Cam_1, etc.
        cam_tag = f"Cam_{cam_idx}"
        cam_output_folder = os.path.join(output_base_dir, cam_tag)
        os.makedirs(cam_output_folder, exist_ok=True)
        
        # Switch active camera (inherits camera rotation, location, and FOV)
        scene.camera = cam
        
        # Set file prefix: images/Cam_0/0001.png
        scene.render.filepath = os.path.join(cam_output_folder, "")
        
        print(f"\n==========================================")
        print(f"[*] Rendering camera [{cam_idx + 1}/{len(cameras)}]: '{cam.name}' -> {cam_output_folder}")
        print(f"[*] Camera type: {cam.data.type} | Render engine: {engine}")
        print(f"==========================================")
        
        # Render the full animation sequence
        bpy.ops.render.render(animation=True)
        
    print(f"\n[SUCCESS] All {len(cameras)} camera sequences rendered to '{output_base_dir}'.")

if __name__ == "__main__":
    main()