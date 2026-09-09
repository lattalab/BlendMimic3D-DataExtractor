import bpy

# For each blend scene, find all armatures and their associated actions.
for obj in bpy.data.objects:
    if obj.type == 'ARMATURE' and obj.animation_data and obj.animation_data.action:
        armature_name = obj.name  # EX: Armature.001 (as show at blender)
        full_action_name = obj.animation_data.action.name  # EX: 'Armature|walking2 Retarget' (bind with action name)
        # print(f"[*] Found Armature: '{armature_name}' with Action: '{full_action_name}'")
        
        # Remove the prefix (EX: Armature|) and suffix (EX: Retarget)
        clean_action_name = full_action_name.split('|')[-1].replace('Retarget', '')
        # If same action name has multiple suffixes (EX: .001, .002), remove them as well
        # Armature|walking2 Retarget.001 -> walking2 .001 -> walking2__001 -> walking2_001
        # 'Armature|walking2 Retarget' -> walking2_ -> 'walking2'
        clean_action_name = clean_action_name.replace(' ', '_').replace('.', '_').replace('__', '_').strip('_')
        
        # Later used in scripts
        # print to console to verify the action name
        print(f"TARGET:{armature_name}:{clean_action_name}")