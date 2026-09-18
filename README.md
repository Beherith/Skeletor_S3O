# Usage Guide:
READ THE TUTORIAL / DOCUMENTATION HERE: https://docs.google.com/document/d/1-oMLkWHBhfN6a3a5aEZU6X02lY4aZE52nZRtrvIe4cM/edit?usp=sharing

Video Tutorial:

https://www.youtube.com/watch?v=DaMLNfOR6KU

# Skeletor_S3O
A blender script that automatically generates a skeleton for an s3o imported model for SpringRTS and Recoil Engine animation

Usage:

1. Register the script with any version of blender from 2.80 up to 4.3 LTS

2. Select the collection where the root piece (pelvis/base) of the model is. Make sure it's within a collection.

3. Hit Tab, type "Apply Rotation", and select Object > Apply > Rotation & Scale

4. Press the "Create Skeleton" button

5. You can now go into Pose mode and flail the appendages around. 

        ATTENTION: Spring/Recoil engine doesn't properly support rotations greater than 130 degrees, which might lead to undesired
        "flips" during animation playback. When that's required and to avoid some gimbal lock issues, you might need to add
        intermediary empty object parts, with the same pivot, and apply smaller rotations to each part (Eg: 90 degrees to the
        parent and child, instead of 180 degrees to a single bone).

7. If you keep enabled "Add IK targets to chains", the addon will setup up inverse kinematics automagically for you, so you can rotate chains from a controller at its tip. If that fails for some reason, I recommend watching this video, in 5 minutes it will explain things better than letters ever could:

https://www.youtube.com/watch?v=gH5uATTTYB4

7. If you select the "Assimp Workflow" button before creating the skeleton, bones will point to their children, effectively aligning them to the source meshes local rotation. Additionally, activate "Export for Skinning" to use third-party generated skeletons, usually from other industry-standard DCC animation packages, on export.

8. The "Export for DAE (vs s3o)" option will export the coordinates system according to the DAE file format. 

        IMPORTANT: With that option, have the models point towards the Negative Y direction, instead of Positive Y.

8. Export to BOS, LUS (Lua Unit Script) or [LUS Tween format](https://github.com/FluidPlay/TAP/blob/main/scripts/include/springtweener.lua) by clicking the bottom buttons. The script will be created right next to where the current blender file is saved.
   - For videos showcasing the entire production workflow from a blender model, to animating it, exporting and integrating it in SpringRTS (with the SpringTweener library), check the three videos which start here: https://www.youtube.com/watch?v=W1U3WAbjXss

8. Enjoy!

## Recoil GLTF/GLB workflow

For a model imported through the S3O Blender workflow, export GLB with Blender's
`+Y up` option disabled and add the Scene custom property `s3ocompat=true`.
SuperSkeletor exports the same `YXZ` BOS/LUS axes for S3O and GLTF models because
current RecoilEngine versions convert GLTF piece data into engine coordinates
while loading. Compile the generated BOS normally: do not add `#define GLTF` or
use BARScriptCompiler's deprecated GLTF axis-remapping flags.

Enable **glTF Workflow** before exporting scripts to validate these settings. It
also warns when an animated object or bone has a non-identity local rest rotation;
that rest frame is intentionally preserved by Recoil and rotates the affected
piece's local animation axes.


![example](cormort.gif)
