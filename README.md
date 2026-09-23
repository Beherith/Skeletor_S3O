# SuperSkeletor for S3O

SuperSkeletor creates a Blender armature for an S3O-style piece hierarchy and
exports Blender Actions as BOS includes, Lua Unit Scripts (LUS), or LUS Tween
files for SpringRTS, Recoil, and Beyond All Reason.

For the complete rigging, animation, and export guide, see
[Skeletor User Documentation](Skeletor_User_Documentation.md). The legacy
`skeletorscript.py` exporter is not the add-on documented here.

## Quick start

1. Enable **SuperSkeletor** in Blender's Add-ons preferences. If installing
   from source, keep `SuperSkeletor.py` and `bos_animation.py` together.
   The current add-on metadata targets Blender 5.1; the code also contains a
   compatibility path for legacy Actions.
2. Import an S3O model with `s3o_import.py`, if needed. Make the collection
   containing the complete piece hierarchy active in the Outliner, then apply
   the model's rotation and scale.
3. In the 3D View side panel (`N`), open the **SuperSkeletor** tab and click
   **Create Skeleton**. Enable **Add IK targets to chains** first if you want
   automatic IK controllers; it is disabled by default.
4. Create one or more Blender Actions. Under **Anim Exports**, click **New**,
   choose an Action, and configure its per-Action options. An Action can occur
   only once in the export list.
5. Choose **Create BOS Includes (.h)**, **Create LUS**, or **Create LUS
   Tween**. One file is written for each selected Action, beside the saved
   blend file by default or in the configured export subfolder.

For an overview of the end-to-end workflow, start with this
[video tutorial](https://www.youtube.com/watch?v=DaMLNfOR6KU).

## Export formats

| Export | Output | Notes |
| --- | --- | --- |
| BOS | `[blend]_[action].h` | Include-ready header; requires an effective Blender frame rate of exactly 30 FPS. |
| LUS | `[blend]_[action].lua` | Lua Unit Script export. |
| LUS Tween | `[blend]_[action]_tween.lua` | SpringTweener-style tween export. |

Action names are converted to safe BOS identifiers and filenames. Invalid
characters become underscores, and a leading digit receives an underscore.

## BOS includes

BOS exports are include-ready headers, not the old `bos_export.txt` output.
The generated functions and configuration macros are namespaced by Action, so
several animations can be included by one unit script. For an Action named
`Walk`, the public functions are `Walk()`, `STOP_Walk()`, and—when Variable
Speed or Variable Amplitude is enabled—`Walk_INIT()`.

For a speed-dependent walk, the owning unit script needs `isMoving` and
`maxSpeed` static variables and initializes the generated animation:

```bos
#include "constants.h"

piece pelvis, thigh;
static-var isMoving, maxSpeed;

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

The generated header documents its Action-namespaced configuration macros,
such as `Walk_SIGNAL_MASK`, `Walk_DEFAULT_ANIM_TIME`, `Walk_STOP_SPEED`, and
`Walk_MOVESCALE` when Variable Scale is enabled. Do not use the legacy global
`MOVESCALE`, `SIG_WALK`, or `animSpeed` setup.

## Recoil GLTF/GLB workflow

For an S3O-derived GLTF/GLB model, export GLB with Blender's **+Y Up** option
disabled and set the Scene custom property `s3ocompat=true`. Enable **glTF
Workflow** before export to validate those settings and warn about animated
non-identity local rest rotations. SuperSkeletor uses the same BOS/LUS axes
for S3O and GLTF models; do not add `#define GLTF` or use deprecated GLTF
axis-remapping compiler flags.

![Example animation](cormort.gif)
