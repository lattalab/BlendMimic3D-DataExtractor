# BlendMimic3D-DataExtractor: Blender Data Extraction Tool

## Overview

The BlendMimic3D-DataExtractor is designed to convert .fbx files to .npy format, specifically for human motion analysis. It was instrumental in generating [BlendMimic3D](https://github.com/FilipaLino/BlendMimic3D) dataset from our project. For more detailed information about to our project please visit our [project webpage](https://blendmimic3d.github.io/BlendMimic3D/).

This repository contains scripts that require Blender to run.
<p align="left">
  <img src="https://github.com/FilipaLino/BlendMimic3D-DataExtractor/assets/102179022/822a0ad3-0944-40a4-b720-27f116984e42" width="30%" height="30%">
</p>


Blender can be downloaded from the [official website](https://www.blender.org/download/).

## Dependencies
- Blender
- Python

### Reference Environment
- Blender 5.1.2
- Python 3.13.11
- WSL
```bash
$ wsl --install -d Ubuntu-24.04
$ sudo apt update
```
- Anaconda or other Virtual Environment (Not Necessary)

## Contents

### Annotation Parts
- `run.sh`: Automated pipeline script coordinating all extraction stages in a single command, featuring an auto-detection `fallback` mode.
- `ActionDetect.py`: Blender helper script to inspect armatures and animations within a `.blend` scene file.
- `3D_extraction.py`: Converts .fbx files to .npz files containing 3D joint data. 
- `camParams.py`: Extracts camera parameters used in the animations.
- `2D_extraction.py`: Extracts 2D joint data by projecting the 3D joint data onto 2D space using camera parameters.
- `occlusion.py`: Determines the presence of occlusions in the dataset.
- `fbx2jason/`: Intended for storing .fbx files converted to JSON.
- `regular/`: Default directory for placing sample .fbx files.
   > [Refactor] By running `run.sh`, it may not be a necessary step.  

### Visualized Parts
- `run_visualize.sh`: Unified pipeline script to batch `render camera frames` and `generate skeletal visualization videos`.
- `export_image.py`: Blender background rendering script to export multi-camera frame sequences.
   > Also, you can render your image with your Blender interface.
- `visualize_2d_video_v3.py`: OpenCV script to generate visualized video from specific render image folder.  
features:  
   - overlay projected 2D skeletons
   - joint visibility indicators (with occlusion distinction)
   - subject tags on rendered frames.
- `images/`: Default staging directory for rendered camera frames  

## Setup
1. Clone or download this repository to your local machine.
2. Ensure Blender is installed and added to your system PATH.

### Directory Structure
The scripts rely on relative paths (e.g., `../../BlendMimic3D/{subject}/...`) to locate and store motion capture annotations, camera calibration files, and dataset metadata.   
It is recommended to organize your workspace as follows:  

<pre>
BlendMimic3D/                         # Workspace root
├── BlendMimic3D/                     # Generated dataset output directory
│   └── &lt;scenes&gt;/                     # e.g., S1, S2
│       ├── subjects.txt
│       ├── Cameras/
│       ├── D3_Positions/
│       ├── D2_Positions/
│       └── Occlusions/
└── preprocessing/
    └── BlendMimic3D-DataExtractor/   # This repository
        ├── run.sh
        ├── run_visualize.sh
        ├── ...
</pre>

## Quick Start

It is assumed that `animation.blend` is provided and prepared by the user.   
It may contains:  
- Target Armatures (animated character rigs)
- Scene obstacles / environment geometry
- Cameras

For most use cases, the entire extraction pipeline (3D joints, camera calibration, 2D projections, occlusion) can be executed automatically via `run.sh`:   

```bash
# Ensure the execution premission
% chmod +x run.sh
# It will call `ActionDetect.py`, and take turns do the annotation with all animations.  
% ./run.sh -b animation.blend -s S1
```

Once annotations are extracted, render the camera viewpoints and generate skeleton overlay videos via `run_visualized.sh`:  

```bash
# Ensure the execution premission
% chmod +x run_visualize.sh
# `export_image.py` will render image and save to `images/S1`
# Parse the directory (e.g: images/S1/cam0) to produced corresponding visualized videos.
% ./run_visualize.sh -b animation.blend -s S1 -i images/S1 --show-subject
```

Below are samples of the extracted 2D pose overlays and occlusion indicators across multiple camera viewpoints:  

| Cam_0 (Perspective Front) | Cam_1 (Perspective Side) | Cam_2 (Perspective Side) |
| :---: | :---: | :---: |
| <img src="assets/four_people.gif" width="100%"> | <img src="assets/four_people_cam1.gif" width="100%"> | <img src="assets/four_people_cam2.gif" width="100%"> |
| *Green: Visible / Red: Occluded* | *Green: Visible / Red: Occluded* | *Green: Visible / Red: Occluded* |

## Usage Instructions

### General Usage
Before running the scripts, download a sample .fbx file from your Blender animation ([link](https://www.immersivelimit.com/tutorials/export-animations-from-blender-to-unreal-engine)) and place it into the `regular` folder.

### 3D Data Extraction
1. Move the .fbx file to the `regular` folder.
2. Open a command prompt with administrator permissions.
3. Change to the directory containing `3D_extraction.py`.
4. Execute the script with the following command:
   ```
   blender --background -P 3D_extraction.py -- --joint-id "" --armature-name Armature --subject S1 --action <action_name>
   ```

### Camera Parameters Extraction
1. Change to the directory containing `camParams.py`.
2. Execute the script with the following command:
   ```
   blender --background animation.blend --python camParams.py -- S1
   ```

### 2D Data Conversion
1. Change to the directory containing `2D_extraction.py`.
2. Execute the script with the following command:
   ```
   blender --background animation.blend --python 2D_extraction.py -- S1 <action_name>
   ```

### Occlusion Handling
1. Change to the directory containing `occlusion.py`.
2. Execute the script with the following command:
   ```
   blender --background animation.blend --python occlusion.py -- --joint-id "" --armature-name Armature --subject S1 --action <action_name>
   ```

### Multi-Camera Image Rendering
1. Change to the directory containing `export_image.py`.
2. Execute the script with the following command:
   ```bash
   # fisheye cannot support EEVEE engine, you should change to CYCLE
   blender --background animation.blend --python export_image.py -- ./images/S1 EEVEE
   ```

### Video with Skeleton Annotation
1. Change to the directory containing `visualize_2d_video.py`.
2. Execute the script with the following command:
   ```bash
   python visualize_2d_video_v3.py \
   --scene_dir ../../BlendMimic3D/S1 \
   --cam Cam_0 \
   --img_folder images/S1/Cam_0 \
   --output Cam_0_viz.avi \
   --subject
   ```

## Contributing
Contributions are welcome. Please open an issue or submit a pull request with your suggested changes.

## Citation
If you use our code in your research, please cite our paper: 
```
@inproceedings{lino20243d,
  title={3D Human Pose Estimation with Occlusions: Introducing BlendMimic3D Dataset and GCN Refinement},
  author={Lino, Filipa and Santiago, Carlos and Marques, Manuel},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition},
  pages={4646--4656},
  year={2024}
}
```

## Aknowledgements
This work was supported by LARSyS funding (DOI: 10.54499/LA/P/0083/2020, 10.54499/UIDP/50009/2020, and 10.54499/UIDB/50009/2020) and 10.54499/2022.07849.CEECIND/CP1713/CT0001, through Fundação para a Ciência e a Tecnologia, and by the SmartRetail project [PRR - C645440011-00000062], through IAPMEI - Agência para a Competitividade e Inovação.
<p align="center">
  <img src="https://github.com/FilipaLino/BlendMimic3D/assets/102179022/670897d0-1f7d-43e8-b63b-b2b961242730" width="50%" height="50%">
</p>

