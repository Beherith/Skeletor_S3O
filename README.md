# Usage Guide:
READ THE TUTORIAL / DOCUMENTATION HERE: https://docs.google.com/document/d/1-oMLkWHBhfN6a3a5aEZU6X02lY4aZE52nZRtrvIe4cM/edit?usp=sharing

Video Tutorial:

https://www.youtube.com/watch?v=DaMLNfOR6KU

# Skeletor_S3O
A blender script that automatically generates a skeleton for an s3o imported model for SpringRTS animation

Usage:

1. Register the script with any version of blender from 2.80 up to 4.3 LTS

2. Select the collection where the root piece (pelvis/base) of the model is. Make sure it's within a collection.

3. Hit Tab, type "Apply Rotation", and select Object > Apply > Rotation & Scale

4. Press the "Create Skeleton" button

5. You can now go into Pose mode and flail the appendages around. 

6. If you keep enabled "Add IK targets to chains", the addon will setup up inverse kinematics automagically for you, so you can rotate chains from a controller at its tip. If that fails for some reason, I recommend watching this video, in 5 minutes it will explain things better than I ever could:

https://www.youtube.com/watch?v=gH5uATTTYB4

7. Export to BOS, LUS (Lua Unit Script) or [LUS Tween format](https://github.com/FluidPlay/TAP/blob/main/scripts/include/springtweener.lua) by clicking the bottom buttons. The script will be created right next to where the current blender file is saved.
   - For videos showcasing the entire production workflow from a blender model, to animating it, exporting and integrating it in SpringRTS (with the SpringTweener library), check the three videos which start here: https://www.youtube.com/watch?v=W1U3WAbjXss

8. Enjoy!

## Include-ready BOS animation export

**Create BOS Includes (.h)** writes one header per selected Blender Action. Action
names are converted to BOS identifiers one character at a time: invalid characters
become underscores and a leading digit receives an underscore prefix. An empty
name becomes `Walk`. The same normalized name is used in the output filename.
The Blender scene must run at 30 FPS.

Every generated macro, local variable, and function is namespaced with the Action
name, so several generated headers can be included by one unit. For an Action named
`Walk`, the public entry points are `Walk()`, `STOP_Walk()`, and, when unit-speed
modulation is enabled, `Walk_INIT()`.

Walking animations can sample `CURRENT_SPEED` before every keyframe. The generated
calculation splits speed correction between cadence and absolute transform
amplitude while carrying fractional milliseconds forward. Idle and death
animations instead use a fixed-time calculation and never read unit speed; their
speed remains configurable through `<Action>_DEFAULT_ANIM_TIME`. Stop-animation
speed is configurable through `<Action>_STOP_SPEED`.

A complete owning-script setup looks like this:

```bos
#include "constants.h"

piece pelvis, thigh;
static-var isMoving, maxSpeed;

#define Walk_MAX_SPEED_PERCENT 175
#define Walk_SIGNAL_MASK SIGNAL_MOVE
#include "myunit_Walk.h"

Create()
{
	Walk_INIT();
}

StartMoving(reversing)
{
	signal SIGNAL_MOVE;
	isMoving = TRUE;
	start-script Walk();
}

StopMoving()
{
	signal SIGNAL_MOVE;
	isMoving = FALSE;
	call-script STOP_Walk();
}
```

The generated header documents every supported override next to its default. BOS
headers contain animation code and namespaced configuration only; unit callbacks
such as `Create`, `StartMoving`, and `StopMoving` remain owned by the including
script.

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
