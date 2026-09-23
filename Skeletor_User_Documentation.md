**By Beherith**

[[https://www.beyondallreason.info/]{.underline}](https://www.beyondallreason.info/)

[[https://github.com/Beherith/Skeletor_S3O]{.underline}](https://github.com/Beherith/Skeletor_S3O)

Table of contents:![](images/media/image6.gif){width="2.34375in"
height="2.34375in"}

[[Requirements]{.underline}](#requirements)

[[Setting up S3O's in
UpSpring]{.underline}](#setting-up-s3os-in-upspring)

[[Skeleton and Inverse
Kinematics]{.underline}](#skeleton-and-inverse-kinematics)

> [[Checking the created bones/inverse
> kinematics]{.underline}](#checking-the-created-bonesinverse-kinematics)
>
> [[Stiffening joints]{.underline}](#stiffening-joints)
>
> [[Choosing Actions to export]{.underline}](#choosing-actions-to-export)

[[Animation]{.underline}](#animation)

> [[Walk Animations]{.underline}](#walk-animations)
>
> [[Example Walk Animation]{.underline}](#example-walk-animation)
>
> [[Useful hotkeys]{.underline}](#useful-hotkeys)
>
> [[General workflow]{.underline}](#general-workflow)
>
> [[Idle animations]{.underline}](#idle-animations)
>
> [[Death animations NEW!]{.underline}](#death-animations-new)
>
> [[Starting position - Power
> Stance!]{.underline}](#starting-position---power-stance)
>
> [[Exporting death animations and
> wrecks]{.underline}](#exporting-death-animations-and-wrecks)

[[Avoiding Gimbal Lock]{.underline}](#avoiding-gimbal-lock)

[[Exporting actions]{.underline}](#exporting-actions)

> [[BOS includes and integration]{.underline}](#bos-includes-and-integration)
>
> [[Other export targets]{.underline}](#other-export-targets)
>
> [[Modern model workflows]{.underline}](#modern-model-workflows)

[[Troubleshooting]{.underline}](#troubleshooting)

> [[BOS export did not produce a header]{.underline}](#bos-export-did-not-produce-a-header)

[[Youtube Sources]{.underline}](#youtube-sources)

# Requirements

1.  The current add-on metadata targets Blender 5.1. SuperSkeletor also
    contains a compatibility path for legacy Actions, but earlier Blender
    releases should be tested with the model pipeline before production use.

2.  The current SuperSkeletor add-on from:
    [[https://github.com/Beherith/Skeletor_S3O]{.underline}](https://github.com/Beherith/Skeletor_S3O)

3.  Enable **SuperSkeletor** in Blender's Add-ons preferences. When
    installing from source, keep `SuperSkeletor.py` and `bos_animation.py`
    together. `skeletorscript.py` is the legacy exporter and is not the
    add-on described in this guide.

4.  Enable `s3o_import.py` too when importing S3O files directly. UpSpring
    remains useful for inspecting or repairing S3O hierarchies, but is not
    required for an already-prepared Blender or GLTF model.

The screenshots in this document come from the previous Skeletor interface.
Use the current control names quoted in the text: the panel is called
**SuperSkeletor**, in the 3D View side panel.

# Setting up S3O's in UpSpring

- The origins of pieces should be at sane positions for each piece.

- Pelvis should be the midpoint of the pelvis object.

- Left and right arms and feet. The origins of these objects should be
  exact mirrors of each other, so the animations can be mirrored too
  (less work, more fun!)

- Aimx1 and Aimy1 points:These should allow for fully animated
  walk+aims, and less duplication on walk/walk+aim animations

  - AimY1 should coincide with the exact pos of the torso, to allow for
    nice torso anims.

  - AimX1 should be at the midpoint between the arms, at shoulder level

  - AimX and AimY should not be direct parents of each other, usually
    add the torso there

- Make note of the max velocity of your unit (elmos/frame). You will
  need to know this to ensure that feet move in sync with the ground.

![](images/media/image7.png){width="6.5in" height="5.520833333333333in"}

# Skeleton and Inverse Kinematics

Familiarize yourself with the way things are set up with the example
corshiva blend file in the repo
([[https://github.com/Beherith/Skeletor_S3O/blob/master/corshiva_anim_v5_bos_out.blend]{.underline}](https://github.com/Beherith/Skeletor_S3O/blob/master/corshiva_anim_v5_bos_out.blend)
)

Enable **SuperSkeletor** in Blender's Add-ons preferences. The old
`skeletorscript.py` add-on mentioned in previous versions of this tutorial
is not used by the current workflow.

**Import the model into blender via the Import Spring ZY S3O menu in
blender.**

~~Select the pelvis (or root piece) of the model.~~

In the Outliner, make the collection containing the complete model hierarchy
the active collection. SuperSkeletor finds the S3O root and pieces in that
collection. Before creating a skeleton, apply the model's rotation and scale
if they have not already been applied.

![](images/media/image22.png){width="3.4479166666666665in"
height="1.6666666666666667in"}

Open the 3D View side panel (`N`) and select the **SuperSkeletor** tab. In
the **Skeleton** section, click **Create Skeleton**. If you want automatic
IK controllers, enable **Add IK targets to chains** first: it is disabled by
default. **IK targets at leafs** selects whether the target is placed on a
leaf or one branch above it.

![](images/media/image1.png){width="6.5in"
height="3.2083333333333335in"}

## Checking the created bones/inverse kinematics

Spend 10 minutes watching these two videos, they give a better rundown
of IK than I ever could.

Basic Bones and rigging:
[[https://www.youtube.com/watch?v=cp1YRaTZBfw]{.underline}](https://www.youtube.com/watch?v=cp1YRaTZBfw)

Basic inverse kinematics:
[[https://www.youtube.com/watch?v=gH5uATTTYB4]{.underline}](https://www.youtube.com/watch?v=gH5uATTTYB4)

![](images/media/image24.png){width="4.302083333333333in"
height="4.458333333333333in"}

Note that we will not use inverse kinematics poles in the animations,
instead I stiffen the Z axis joints, as poles are more problematic to
work with for elbows and knees.

When **Add IK targets to chains** is enabled, the skeleton creator can be a
little bit overzealous in placing inverse-kinematics targets on appendages.
You can disable or edit these in Pose Mode.

You can tune the chain lengths and targets here. **Setting chain lengths
to zero means all pieces up to root will be in IK.**

## ![](images/media/image19.png){width="3.3854166666666665in" height="4.1875in"}

## Stiffening joints

You can also stiffen joints along various axes, setting knees, and
ankles like this is good. Bone properties -\> Inverse Kinematics -\>
Stiffness.

**Another method of keeping the feet always level, and not pointing
everywhere is by setting Bone Constraints -\> IK -\> Rotation checkbox.
THIS IS THE ABSOLUTE EASIEST AND BEST METHOD TO DO ANIMATIONS**

![](images/media/image28.png){width="4.197916666666667in"
height="4.114583333333333in"}

You can also show/hide bone names on the skeleton:
![](images/media/image4.png){width="2.4375in"
height="5.208333333333333in"}

# Choosing Actions to export

SuperSkeletor exports Blender **Actions**, not one implicit timeline. In the
**Anim Exports** section, click **New**, select an **Action**, and set that
entry's options. Add one entry for every Action you want to export; an Action
can only appear once in the list. Clicking an export button processes every
entry with a selected Action and creates one file per Action.

The options belong to the selected Anim Export entry:

- **Is Walk Script** makes the animation loop. Its walk-specific options are
  **Variable Speed**, **Variable Scale**, and **Variable Amplitude**.
- **First Frame Stance** records the first frame as the pose to restore when
  stopping. It is enabled by default.
- **All Transforms on First Frame** explicitly emits every transform on the
  first written animation frame, which is useful when a consumer needs a
  complete initial pose.
- **Is Death Script** enables exploding pieces when their movement crosses
  the death-animation threshold described below.

# Animation

Once satisfied with the skeleton (move/rotate the bones and IK targets
around), you can begin on your animation.

Set Blender to interpolate linear for walk scripts in
Edit-\>Preferences. For death and idle you might want to use some other
to export a high-detail anim.

![](images/media/image27.png){width="6.5in"
height="3.7916666666666665in"}

## Walk Animations

Decide if you want a 6 or 8 or 10 or 12 keyframe walk animation, this is
largely governed by the speed/size of the units.

For large/slow units, you will likely want more keyframes, and for
smaller/faster units you will want less.

Set Blender's render to **30 FPS**, as Recoil animations run at that
rate.

![](images/media/image20.png){width="4.401042213473316in"
height="3.6690791776027996in"}

You want to **space the keyframes evenly**, to allow for sane speeding
up and slowing down animation when the unit isn't traveling at
maxvelocity. Make sure that the unit travels the required distance in
the allotted time

Also remember to set the animation interpolation to LINEAR.

**Tip:**

Use transformation locking in tools to set the rotation of
knees/hips/heels to be locked to the X axis. It will save you time when
doing transformations and setting keyframes as you will not have to tap
G + y, G + z every time you move a piece. Another tip is to use the side
view (NUM3) when animating legs so that you can precisely see the ground
level and all default transformations will be within ZY plane.

![](images/media/image25.png){width="4.780859580052494in"
height="2.425955818022747in"}

## Example Walk Animation

Unit has a maxvelocity of 1.61 elmos/frame. I want 8 keyframes, spaced 3
frames apart.

Each walk cycle will be 24 frames in total. Thus the animation should
traverse forward 24\*1.61 elmos in a cycle.

8 Frame walk cycle, recommend starting from High-Point

[[https://sites.google.com/site/disasterbot0101/game-design/12\-\--animated-walk-cycle\-\--50pts]{.underline}](https://sites.google.com/site/disasterbot0101/game-design/12---animated-walk-cycle---50pts)

![](images/media/image21.png){width="6.5in" height="2.0in"}

![](images/media/image11.png){width="6.5in"
height="1.7638888888888888in"}

[[https://www.youtube.com/watch?time_continue=4&v=GlYTXs0Cyc8&feature=emb_logo]{.underline}](https://www.youtube.com/watch?time_continue=4&v=GlYTXs0Cyc8&feature=emb_logo)

I recommend using the Dope sheet in blender to do your animations:

![](images/media/image23.png){width="6.5in"
height="2.861111111111111in"}

The first keyframe at pos 1 should be the default idle position of the
unit, so the first step is animated nicely. **You can pose your unit on
the first keyframe to its 'idle' stance; it does not have to be all zeros.**
Keep **First Frame Stance** enabled for this Action if you want the generated
stop function to return to that pose; otherwise its fallback is zero.

You do not need blank LocRot keys on a pelvis or another non-IK bone.
SuperSkeletor samples the evaluated pose at the Action's location and
rotation keyframes, so an IK target can drive an exported chain by itself.
For BOS exports, all sample keys must lie on distinct integer Blender frames.

The last keyframe should be identical to the second keyframe (so the
animation loops correctly).

### Useful hotkeys

G - move bone, Alt+G resets movement

R - rotate bone, Alt+R resets rotation

I - Insert keyframe (choose LocRot)

Copy-paste on dopesheet, paste always pastes at cursor, Ctrl+Shift+V
MIRRORS the paste (L-R)

Left-Right keys step the timeline 1 frame at a time

Up-Down keys step to the next keyframe

Shift+Space starts and stops the animation

### General workflow

Start by setting fps to 30, having the timeline and dope sheets open,
kind of like so:

![](images/media/image18.png){width="5.869792213473316in"
height="3.5463320209973754in"}

Turn on recording on the timeline, and set your animation loop times for
easy debugging

![](images/media/image14.png){width="6.5in"
height="0.5555555555555556in"}

![](images/media/image10.png){width="3.8020833333333335in"
height="3.8854166666666665in"}

Start with the pelvis bobbing up and down, and rotating it left and
right, and maybe even side to side.

It is easiest to do this by dragging or keying in values when you have
the bone selected on the Item panel in the 3D view.

You only have to animate the left or right side of the body, you can
mirror a walk cycle to the other half of a skeleton:
[[https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle]{.underline}](https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle)

On the Dope sheet, select all the keyframes of the animation.

To left-right copy an animation from one bone to the other on the dope
sheet, select all of the keyframes in the walk cycle belonging to that
bone on the dope sheet (iktarget.l_foot.L marked yellow here), and
ctrl+c to copy them.

![](images/media/image3.png){width="6.5in"
height="0.7638888888888888in"}

Now to copy them 180\* out of phase and X reversed to the other
iktarget.r_foot.R, put the timeline to the point where you want the copy
to start (30 in this case), select the iktarget.r_foot.R target bone,
and press Ctrl+Shift+V to paste it mirrored:

![](images/media/image26.png){width="6.5in"
height="0.6111111111111112in"}

Select the second half of the keyframes of this bone, and copy-paste
them to the first half of the animation.

## Idle animations![](images/media/image13.png){width="2.3541666666666665in" height="3.0729166666666665in"}

These do not have to have keyframes placed evenly. Disable **Is Walk Script**
for the Action. Walk-only speed options are ignored for idle and death
exports, which use fixed animation timing.

## Death animations **NEW!**

Note that there is no real performance limit on keyframes or anything
for these. Go nuts! Disable **Is Walk Script** and enable **Is Death Script**
for the Action. Walk-only speed settings do not affect death exports.

**To explode pieces off the model, make the respective bone's movement change
by more than 100 units between sampled frames.** This tells the exporter to
hide that piece and make it fly off. All children of that piece will fly off
too.

### Starting position - Power Stance!

It is recommended to start the death animation from the same power
stance (or neutral) pose that's in the walk animation file. Put the
first actual death keyframe about 10-15 frames from the neutral stance,
to give some time so that all animated pieces can achieve that position.
![](images/media/image2.png){width="4.385470253718285in"
height="1.4322922134733158in"}

### Exporting death animations and wrecks![](images/media/image15.png){width="2.3122462817147857in" height="4.984375546806649in"}

To export a wreck model, select all non-exploded off meshes export as
OBJ (using the export settings in the image to the right) , then convert
to s3o with obj2s3o available from **or** by using Upspring, but then
remember to **left-right flip the model**, by scale X=-1, apply.

![](images/media/image5.png){width="3.78125in"
height="4.020833333333333in"}

Checklist: Unit_dead.s3o

- Flip the model left-right (scale X=-1, apply), if needed!

- Set the texture,

- Merge the pieces

- Set model height

- Set model radius

- Set model center

- Edit-\>optimize-\>all objects

- and save as unitname_dead.s3o in Upspring.

- Set the unitdef in \\luarules\\gadgets\\unit_death_animations.lua

When editing the .bos file, ensure that aim pieces also get returned to
neutral during the death animation.

Note that a gadget must be added to your game that prevents dying units
from moving and from being selected.

# Avoiding Gimbal Lock![](images/media/image8.png){width="3.7203412073490814in" height="4.671875546806649in"}

Sometimes, especially due to the use of IK targets, when bones are
rotated \~90 degrees along their major axis, further rotations can be
affected by gimbal lock. The **Bone Angles** panel in the 3D View side panel
alerts
you of possible gimbal lock conditions being present at a given point in
time. Scrub through your animation and watch if any of the bone angles
go red. The recommended mitigation is to move the IK targets around a
little to prevent the joint from going into gimbal lock (as this will
look atrocious in-game). The .BOS output will also contain warnings if
it feels that there may be gimbal lock present.

Gimbal lock is a terrible thing, so it must be avoided at all costs.
Sometimes, changing bone inverse kinematics stiffness solves the issue
for one keyframe, but then makes the rest of the animation look bad.
Luckily, by clicking the diamond next to the stiffness markers, you can
also animate the stiffness properties of a bone. Thus you can set the
desired stiffness to reduce gimbal lock on one frame, and then set it
back to normal for the next and previous
frames!![](images/media/image12.png){width="1.9791666666666667in"
height="1.1770833333333333in"}

# Exporting actions

Save the `.blend` file, add the Actions you want under **Anim Exports**, and
click an export button in the **Export** section. By default, each file is
written beside the blend file as `[blend]_[action]` plus its extension. Enable
**Export to Subfolder** to write them into a named folder beside the blend
file instead.

Action names are converted to safe BOS identifiers and filenames: invalid
characters become underscores, and a leading digit receives an underscore.
For BOS, two Action names that normalize to the same identifier cannot be
exported together.

**Create BOS Includes (.h)** requires an effective scene rate of exactly
30 FPS and writes one include-ready header per Action. It does not write the
old `bos_export.txt` file. A BOS export needs at least two distinct,
integer-frame samples; a looping walk needs a stance/entry frame plus at
least one loop frame.

**Multiply Movement Scale** applies a scene-wide multiplier to exported move
targets and move speeds; turns are unaffected. This is separate from the
per-Action **Variable Scale** option.

## BOS includes and integration

Generated `.h` files are intended to be `#include`d by the owning unit
script. Their functions, variables, and configuration macros are namespaced
by Action name, so headers for several animations can coexist in one unit.
For an Action named `Walk`, the public entry points are `Walk()`,
`STOP_Walk()`, and—when Variable Speed or Variable Amplitude is enabled—
`Walk_INIT()`.

The generated header documents its supported overrides. Examples include
`Walk_SIGNAL_MASK`, `Walk_DEFAULT_ANIM_TIME`, `Walk_STOP_SPEED`, and, when
Variable Scale is enabled, `Walk_MOVESCALE`. Variable Amplitude adds the
speed range and `Walk_BLEND_PERCENT` configuration. Do not add the legacy
global `MOVESCALE`, `SIG_WALK`, or `animSpeed` setup from older Skeletor
exports.

A minimal owning-script setup for a speed-dependent walk looks like this:

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

If neither Variable Speed nor Variable Amplitude is enabled, omit `maxSpeed`
and the `Walk_INIT()` call. The unit script remains responsible for its own
callbacks, aim handling, and signal choices.

## Other export targets

**Create LUS** writes one `[blend]_[action].lua` Lua Unit Script export per
Action. **Create LUS Tween** writes `[blend]_[action]_tween.lua` for the
SpringTweener-style tween workflow. These exporters use the same Anim Export
list and per-Action options as BOS.

## Modern model workflows

Use **Assimp Workflow** when your pipeline needs Blender/Assimp axis
rotation conventions. **Assimp Workflow Skeleton** aligns newly created
bones to local space for that workflow. **Export for Skinning** is intended
for compatible existing deform-bone rigs; an armature with deform bones is
still required for export.

For Recoil GLTF/GLB models, export the GLB with Blender's **+Y Up** option
disabled and set the Scene custom property `s3ocompat=true` for an
S3O-derived model. Enable **glTF Workflow** before export to have
SuperSkeletor check these conditions and warn about animated non-identity
local rest rotations. BOS/LUS axes remain the same as the S3O workflow: do
not add a `#define GLTF` or use deprecated GLTF axis-remapping compiler
flags.

# Troubleshooting

SuperSkeletor writes diagnostic output to Blender's system console and to a
timestamped `skeletorscript_log_*.txt` file in the user's home directory.
There is no panel toggle for debug logging in the current add-on.

## BOS export did not produce a header

Check the following before adding dummy keys:

- At least one **Anim Export** entry has an Action selected.
- The scene's effective FPS (FPS divided by FPS Base) is exactly 30.
- The exporter must obtain at least two distinct integer-frame samples; a
  walk needs at least three. It normally uses location and rotation keys and
  falls back to sampling the Action range every three frames when none exist.
- No key is on a fractional frame, and selected Action names do not collide
  after BOS identifier sanitization.
- An armature with deform bones exists in the scene.

The exporter bakes the evaluated pose of every deform bone at sampled frames.
Keys placed only on IK targets are valid; do not add blank LocRot keys to the
pelvis merely to make an export appear.

# Youtube Sources 

Half an hour of **highly** recommended viewing:

Full Reaminate workflow in Blender on the example of corstorm:

<https://www.youtube.com/watch?v=DaMLNfOR6KU&feature=youtu.be>

walk cycle animation blueprint: a how to guide \[8min\], use \<\> (,.)
keys to view frame by frame :)

[[https://youtu.be/GlYTXs0Cyc8?t=13]{.underline}](https://youtu.be/GlYTXs0Cyc8?t=13)

Basic Bones and rigging:

[[https://www.youtube.com/watch?v=cp1YRaTZBfw]{.underline}](https://www.youtube.com/watch?v=cp1YRaTZBfw)

Basic inverse kinematics:

[[https://www.youtube.com/watch?v=gH5uATTTYB4]{.underline}](https://www.youtube.com/watch?v=gH5uATTTYB4)

Other:

Blender Python Tutorial: An Introduction to Scripting \[Python - bpy\]

[[https://www.youtube.com/watch?v=cyt0O7saU4Q]{.underline}](https://www.youtube.com/watch?v=cyt0O7saU4Q)
