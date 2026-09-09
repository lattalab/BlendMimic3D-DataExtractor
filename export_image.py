import bpy
import os
import sys

# sample usage:
# 1. EEVEE engine (default)
# blender -b three_people.blend --python render_cameras.py -- ./images/three_people EEVEE
# 2. Cycles engine
# blender -b three_people.blend --python render_cameras.py -- ./images/three_people CYCLES

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
    # support for CYCLE and EEVEE engines for this research
    engine = args[1].upper() if len(args) > 1 else "EEVEE"
    
    return output_dir, engine

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

            # ask for user if wants to continue with CPU rendering
            print("[*] Fallback option: CPU rendering.")
            user_input = input(">> GPU is unavailable. Continue rendering with CPU? (Y/N): ").strip().lower()

            if user_input != 'y':
                print("[!] Aborting rendering process as requested by user.")
                sys.exit(0)
                
            print("[*] Proceeding with CPU rendering...")

        # ---------------------------------------------------------
        # Cycles Sampling Settings (仿照 UI 設定，加快算圖速度)
        # ---------------------------------------------------------
        # 1. Render Sampling
        scene.cycles.use_adaptive_sampling = False      # 關閉 Noise Threshold
        scene.cycles.samples = 12                       # Max Samples: 36 (可依需求改為 32)
        scene.cycles.adaptive_min_samples = 0           # Min Samples: 0
        scene.cycles.time_limit = 0                     # Time Limit: 0s (無限制)
        scene.cycles.use_denoising = True               # 啟用降噪 (Denoise)
        
        # 2. Viewport Sampling (預覽時的取樣數)
        scene.cycles.preview_samples = 16

        # 3. Light Paths / Max Bounces (光線反彈次數，降低可減少運算負擔)
        scene.cycles.max_bounces = 2                    # Total
        
        print("[*] Cycles sampling and bounce optimization parameters applied.")
            
    else:
        # EEVEE uses GPU by default
        # Compatible with Blender 4.x / 5.x EEVEE Next and Blender 3.x EEVEE

        if 'BLENDER_EEVEE_NEXT' in bpy.types.RenderEngine.__subclasses__():
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        else:
            scene.render.engine = 'BLENDER_EEVEE'
            
        print("[*] Render engine set to EEVEE (Real-time GPU Rasterization).")

def main():
    output_base_dir, engine = parse_args()
    scene = bpy.context.scene
    
    # 1. Setup engine configurations
    configure_engine(scene, engine)
    
    # 2. Output image format settings
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    
    # 3. Detect and sort all camera objects
    cameras = sorted([obj for obj in bpy.data.objects if obj.type == 'CAMERA'], key=lambda x: x.name)
    
    if not cameras:
        print("[ERROR] No camera objects found in the scene!")
        sys.exit(1)
        
    print(f"[*] Found {len(cameras)} cameras: {[cam.name for cam in cameras]}")
    print(f"[*] Target frame range: {scene.frame_start} ~ {scene.frame_end}")
    
    # 4. Render sequence for each camera
    for cam_idx, cam in enumerate(cameras):
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
        print(f"==========================================")
        
        # Render the full animation sequence
        bpy.ops.render.render(animation=True)
        
    print(f"\n[SUCCESS] All {len(cameras)} camera sequences rendered to '{output_base_dir}'.")

if __name__ == "__main__":
    main()