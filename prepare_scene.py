#!/usr/bin/env python3
"""Blender-side helper: import one animated FBX into a template copy."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy


def arguments() -> argparse.Namespace:
    """Parse scene preparation arguments passed by the controller."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--fbx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--armature-name", required=True)
    parser.add_argument("--location", nargs=3, required=True, type=float)
    parser.add_argument("--rotation-deg", nargs=3, required=True, type=float)
    parser.add_argument("--scale", required=True, type=float)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--fps", required=True, type=int)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def main() -> None:
    """
    Import one animated FBX into a Blender scene template.

    The function identifies the imported armature, applies a shared
    character transform, configures scene settings, and saves a
    temporary working scene with a JSON preparation report.

    Returns:
        None. Outputs are written to the configured .blend and JSON paths.
    """

    # Import the animated FBX and identify newly created Blender objects.
    args = arguments()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(args.fbx.resolve()))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        raise RuntimeError("FBX import created no objects")
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"expected exactly one imported armature, found {len(armatures)}")
    if args.armature_name in bpy.data.objects and bpy.data.objects[args.armature_name] is not armatures[0]:
        raise RuntimeError(f"template already contains object named {args.armature_name!r}")

    # Validate the single imported armature and its active animation.
    armature = armatures[0]
    armature.name = args.armature_name
    armature.data.name = f"{args.armature_name}_Data"
    if armature.animation_data is None or armature.animation_data.action is None:
        raise RuntimeError("imported armature has no active animation action")

    # Create a parent Empty to transform the entire character without
    # changing the internal hierarchy of imported FBX objects.
    root = bpy.data.objects.new("GeneratedCharacterRoot", None)
    bpy.context.scene.collection.objects.link(root)
    imported_set = set(imported)
    imported_roots = [obj for obj in imported if obj.parent not in imported_set]
    for obj in imported_roots:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world

    # Apply character placement and configure render resolution and FPS.
    root.location = args.location
    root.rotation_euler = [math.radians(value) for value in args.rotation_deg]
    root.scale = (args.scale, args.scale, args.scale)

    scene = bpy.context.scene
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps

    # Use the imported animation's frame range and discover enabled cameras.
    action = armature.animation_data.action
    scene.frame_start = math.floor(action.frame_range[0])
    scene.frame_end = math.ceil(action.frame_range[1])
    cameras = sorted(
        (obj for obj in scene.objects if obj.type == "CAMERA" and not obj.hide_render),
        key=lambda obj: obj.name,
    )
    if not cameras:
        raise RuntimeError("template contains no enabled cameras")
    if len(cameras) != sum(obj.type == "CAMERA" for obj in scene.objects):
        raise RuntimeError("hidden cameras would misalign legacy camera indices")

    # Save the disposable working scene for subsequent rendering and extraction.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), check_existing=False)
    report = {
        "working_blend": str(args.output.resolve()),
        "armature": armature.name,
        "action": action.name,
        "imported_action_frame_range": [float(action.frame_range[0]), float(action.frame_range[1])],
        "frame_range": [scene.frame_start, scene.frame_end],
        "cameras": [
            {
                "name": camera.name,
                "type": camera.data.type,
                "panorama_type": getattr(camera.data, "panorama_type", None),
            }
            for camera in cameras
        ],
        "imported_object_count": len(imported),
    }

    # Write a preparation report for the dataset controller.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {args.output} with {len(cameras)} cameras and armature {armature.name}")


if __name__ == "__main__":
    main()
