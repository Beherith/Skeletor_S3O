#!BPY
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

bl_info = {
	"name": "SuperSkeletor",
	"author": "Beherith  <mysterme@gmail.com> (Blender 5.1 compatibility and SuperSkeletor batch export by Grok)",
	"version": (1, 0, 0),
	"blender": (2, 80, 0),
	"location": "3D View > Side panel (SuperSkeletor)",
	"description": "Create a Skeleton and batch-export BOS/LUS for SpringRTS / Recoil / Beyond All Reason. Compatible with Blender 2.80 – 5.1+",
	"warning": "I have no idea what im doing (now with 5.x slotted-actions support)",
	"wiki_url": "https://github.com/Beherith/Skeletor_S3O",
	"tracker_url": "https://github.com/Beherith/Skeletor_S3O",
	"support": "COMMUNITY",
	"category": "Rigging",
}
import bpy
from math import pi, degrees, radians
from mathutils import Vector, Euler, Matrix

from bpy.props import (StringProperty,
					   BoolProperty,
					   IntProperty,
					   FloatProperty,
					   FloatVectorProperty,
					   EnumProperty,
					   PointerProperty,
					   CollectionProperty,
					   )
from bpy.types import (Panel,
					   Operator,
					   AddonPreferences,
					   PropertyGroup,
					   )

# S3O and engine-canonical GLTF models share the same BOS Euler convention.
OMITDELTAOUTPUT = True # <= Hide the -- delta comments at the ends of the lines, to reduce fileSize
ROTATION_MODE = "YXZ"
FullDebug = False


import logging
import time
from pathlib import Path

try:
	from .bos_animation import render_bos_animation, validate_action_name
except ImportError:  # Blender can install/run this add-on as loose source files.
	from bos_animation import render_bos_animation, validate_action_name

# Create a logger instance
logger = logging.getLogger('skeletor_logger')
logger.setLevel(logging.DEBUG)
 
# Create a formatter to define the log message format
formatter = logging.Formatter('%(levelname)s: %(message)s')

# Create a file handler to write logs to a file
file_handler = logging.FileHandler(f'{Path.home()}/skeletorscript_log_{time.strftime("%Y%m%d-%H%M%S")}.txt')
file_handler.setFormatter(formatter)

# Create a stream handler to write logs to the standard output (console)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

# Add both handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logger.info(f'The Skeletor Scripts current Rotation Mode is set to {ROTATION_MODE} for S3O and engine-canonical GLTF models')
logger.info(f'Running on Blender {bpy.app.version_string} (API compatibility shim active for 5.0+ slotted actions)')


def get_action_fcurves(arm_or_obj):
	"""
	Return an iterable of F-Curves for the given armature/object's action.
	Compatible with Blender <= 4.5 (legacy action.fcurves) and Blender 5.0+
	(slotted / layered actions via channelbags).
	"""
	if arm_or_obj is None:
		return []
	anim_data = getattr(arm_or_obj, "animation_data", None)
	if anim_data is None or anim_data.action is None:
		return []

	action = anim_data.action

	# Legacy path (Blender < 5.0)
	if hasattr(action, "fcurves"):
		return action.fcurves

	# Blender 5.0+ slotted actions
	try:
		from bpy_extras import anim_utils
	except ImportError:
		logger.error("bpy_extras.anim_utils not available – cannot read F-Curves on Blender 5+")
		return []

	slot = getattr(anim_data, "action_slot", None)
	if slot is None:
		# Fallback: first available slot
		if hasattr(action, "slots") and len(action.slots) > 0:
			slot = action.slots[0]
		else:
			logger.warning("No action_slot found on animation_data and action has no slots")
			return []

	channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
	if channelbag is None:
		# Try ensuring one exists (rare for read-only use, but safe)
		try:
			channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
		except Exception as e:
			logger.warning(f"Could not get/ensure channelbag: {e}")
			return []

	if channelbag is None:
		return []
	return channelbag.fcurves


INVALID_ACTION_CHARS = '\\/:*?"<>|'


def action_name_is_valid(name):
	try:
		validate_action_name(name)
	except ValueError:
		return False
	return True


def anim_action_poll(self, action):
	if action is None or not action_name_is_valid(action.name):
		return False
	scene = getattr(bpy.context, "scene", None)
	settings = getattr(scene, "super_skeletor", None) if scene else None
	if settings is None:
		return True
	for item in settings.anim_exports:
		if item != self and item.action == action:
			return False
	return True


def has_valid_anim_export(context):
	settings = getattr(context.scene, "super_skeletor", None)
	if settings is None:
		return False
	return any(item.action is not None for item in settings.anim_exports)


def sanitize_subfolder(raw):
	if not raw:
		return None
	text = raw.strip().replace("\\", "/")
	parts = []
	for part in text.split("/"):
		part = part.strip()
		if not part or part in (".", ".."):
			continue
		cleaned = "".join(ch for ch in part if ch not in INVALID_ACTION_CHARS)
		if cleaned:
			parts.append(cleaned)
	if not parts:
		return None
	return Path(*parts)


def build_export_filepath(action_name, suffix):
	filename = "%s_%s%s" % ("untitled", action_name, suffix)
	blend_path = bpy.data.filepath
	if blend_path:
		blend = Path(blend_path)
		filename = "%s_%s%s" % (blend.stem, action_name, suffix)
		out_dir = blend.parent
	else:
		out_dir = Path(".")

	settings = getattr(getattr(bpy.context, "scene", None), "super_skeletor", None)
	if settings is not None and getattr(settings, "export_to_subfolder", False):
		sub = sanitize_subfolder(getattr(settings, "export_subfolder", ""))
		if sub is not None:
			out_dir = out_dir / sub
	out_dir.mkdir(parents=True, exist_ok=True)
	return str(out_dir / filename)


def assign_action_to_arm(arm, action):
	if arm.animation_data is None:
		arm.animation_data_create()
	arm.animation_data.action = action
	if hasattr(arm.animation_data, "action_slot") and hasattr(action, "slots") and len(action.slots) > 0:
		try:
			arm.animation_data.action_slot = action.slots[0]
		except Exception:
			pass


def find_export_armature(context):
	if "Armature" in context.scene.objects:
		return context.scene.objects["Armature"], ""
	arm = None
	prefix = ""
	for o in context.scene.objects:
		if o.type == "ARMATURE":
			arm = o
			prefix = o.name + "_"
			break
	return arm, prefix


def pose_piece_name(bone_name):
	if bone_name.endswith('.R') or bone_name.endswith('.L'):
		return bone_name[:-2]
	return bone_name


def get_ik_chain_bone_names(arm):
	names = set()
	if arm is None:
		return names
	for bone in arm.pose.bones:
		if 'IK' not in bone.constraints or bone.constraints['IK'].mute:
			continue
		chain_length = bone.constraints['IK'].chain_count
		p = bone
		if chain_length == 0:
			while p is not None:
				names.add(p.name)
				p = p.parent
		else:
			while p is not None and chain_length > 0:
				names.add(p.name)
				p = p.parent
				chain_length -= 1
	return names


def pose_export_euler(matrix):
	return matrix.to_euler(ROTATION_MODE)


def pose_basis_euler(pose_bone):
	"""Export euler of the pose channel (what Blender keys). Does not include rest/roll."""
	return pose_export_euler(pose_bone.matrix_basis)


def pose_solved_euler(pose_bone):
	"""Equivalent YXZ euler after constraints, with rest/roll removed.

	Used only for IK-solved bones, where matrix_basis is stale.
	Translation from this matrix is NOT exported: Recoil already applies
	parent turns, so dumping recovered local translation double-transforms
	and detaches limbs.
	"""
	conversion_args = {}
	if pose_bone.parent is not None:
		conversion_args["parent_matrix"] = pose_bone.parent.matrix
		conversion_args["parent_matrix_local"] = pose_bone.parent.bone.matrix_local
	offset = pose_bone.bone.convert_local_to_pose(
		pose_bone.matrix,
		pose_bone.bone.matrix_local,
		invert=True,
		**conversion_args,
	)
	return pose_export_euler(offset)


def collect_full_piece_transforms(arm):
	"""rot0/1/2 in degrees and location0/1/2 for every deform bone."""
	pose = {}
	if arm is None:
		return pose
	ik_names = get_ik_chain_bone_names(arm)
	for bone in arm.pose.bones:
		if not bone.bone.use_deform:
			continue
		if 'iktarget' in bone.name:
			continue
		name = pose_piece_name(bone.name)
		if name.startswith('PC_'):
			continue
		# Always the location channel. Never recovered visual translation.
		loc = bone.location
		if bone.name in ik_names:
			rot = pose_solved_euler(bone)
		else:
			rot = pose_basis_euler(bone)
		entry = pose.setdefault(name, {})
		entry['location0'] = float(loc.x)
		entry['location1'] = float(loc.y)
		entry['location2'] = float(loc.z)
		entry['rot0'] = degrees(rot.x)
		entry['rot1'] = degrees(rot.y)
		entry['rot2'] = degrees(rot.z)
	return pose


def gltf_non_identity_animated_rest_frames(arm):
	"""Return animated objects/bones whose local rest frame rotates script axes."""
	animated_names = set()
	animated_object = False
	path_prefix = 'pose.bones["'
	for curve in get_action_fcurves(arm):
		data_path = getattr(curve, "data_path", "")
		if data_path.startswith(("location", "rotation_")):
			animated_object = True
		if not data_path.startswith(path_prefix):
			continue
		name_end = data_path.find('"]', len(path_prefix))
		if name_end < 0:
			continue
		channel = data_path[name_end + 2:]
		if channel.startswith((".location", ".rotation_")):
			animated_names.add(data_path[len(path_prefix):name_end])

	# Constraint-driven bones can move even when only their IK target is keyed.
	if animated_names:
		animated_names.update(get_ik_chain_bone_names(arm))

	non_identity = []
	if animated_object:
		angle = abs(arm.matrix_local.to_quaternion().angle)
		angle = min(angle, abs(2.0 * pi - angle))
		if angle > radians(0.01):
			non_identity.append(arm.name + " (object)")

	for name in sorted(animated_names):
		pose_bone = arm.pose.bones.get(name)
		if pose_bone is None or not pose_bone.bone.use_deform:
			continue
		rest_matrix = pose_bone.bone.matrix_local.copy()
		if pose_bone.parent is not None:
			rest_matrix = pose_bone.parent.bone.matrix_local.inverted_safe() @ rest_matrix
		angle = abs(rest_matrix.to_quaternion().angle)
		angle = min(angle, abs(2.0 * pi - angle))
		if angle > radians(0.01):
			non_identity.append(name)

	return non_identity


def get_move_scale(context):
	settings = getattr(context.scene, "super_skeletor", None)
	if settings is None or not getattr(settings, "multiply_move_scale", False):
		return 1.0
	try:
		return float(settings.move_scale_multiplier)
	except (TypeError, ValueError):
		return 1.0


def get_anim_flags(operator, context):
	settings = context.scene.super_skeletor
	item = getattr(operator, "current_anim_item", None)
	return {
		"ISWALK": bool(getattr(item, "is_walk", False)),
		"ISDEATH": bool(getattr(item, "is_death", False)),
		"VARIABLESPEED": bool(getattr(item, "varspeed", False)),
		"FIRSTFRAMESTANCE": bool(getattr(item, "firstframestance", True)),
		"ALL_TRANSFORMS_FIRST": bool(getattr(item, "all_transforms_first", False)),
		"VARIABLESCALE": bool(getattr(item, "varscale", False)),
		"VARIABLEAMPLITUDE": bool(getattr(item, "varamplitude", False)),
		"ASSIMP": bool(settings.assimp_workflow),
		"SKINNING": bool(settings.skinning),
		"ACTION": getattr(item, "action", None),
	}


class SuperSkeleAnimItem(PropertyGroup):
	action: PointerProperty(
		name="Action",
		type=bpy.types.Action,
		poll=anim_action_poll,
		description="Action exported by this Anim entry"
	)
	is_walk: BoolProperty(
		name="Is Walk Script",
		description="Whether the animation loops",
		default=False
	)
	varspeed: BoolProperty(
		name="Variable speed walk",
		description="Whether walk anim should be unitspeed dependant",
		default=True
	)
	varscale: BoolProperty(
		name="Variable scale walk",
		description="Whether move commands scale should be customizeable",
		default=False
	)
	varamplitude: BoolProperty(
		name="Variable amplitude walk",
		description="Step lengths are variable (dynamic multipliers on all transforms)",
		default=False
	)
	firstframestance: BoolProperty(
		name="First Keyframe Stance",
		description="The first keyframe contains an idle stance (non zero) that the unit returns to when not walking",
		default=True
	)
	all_transforms_first: BoolProperty(
		name="All Transforms on First Frame",
		description="On the first written animation frame, emit rot XYZ and pos XYZ for every deform bone",
		default=False
	)
	is_death: BoolProperty(
		name="Is Death Script",
		description="Unit dies, move pieces far to explode them",
		default=False
	)


class MySettings(PropertyGroup):
	autoaddik: BoolProperty(
		name="Add IK targets to chains",
		description="Whether IK constraints should be added to the bone chains",
		default=False
	)
	iktargetends: BoolProperty(
		name="IK targets at leafs",
		description="Whether IK targets should be at the leafs of anim chains or one branch above",
		default=False
	)
	disable_auto_suffix: BoolProperty(
		name="Disable automatic suffix",
		description="If checked, bone names match piece/object names exactly (no .L / .R). IK and auxiliary bones still get their prefixes",
		default=True
	)
	assimp_workflow_skeleton: BoolProperty(
		name="Assimp Workflow Skeleton",
		description="Creates bones aligned to local space when building the skeleton",
		default=False
	)
	assimp_workflow: BoolProperty(
		name="Assimp Workflow",
		description="Export with Blender/Assimp axis-rotation system",
		default=False
	)
	gltf_workflow: BoolProperty(
		name="glTF Workflow",
		description="Validate the Recoil GLTF workflow; exported BOS/LUS axes remain identical to S3O",
		default=False
	)
	skinning: BoolProperty(
		name="Export for Skinning",
		description="Don't require bones to be created by SuperSkeletor, useful for skinning export. Use it with the Assimp workflow option",
		default=False
	)
	export_to_subfolder: BoolProperty(
		name="Export to Subfolder",
		description="Write exported files into a folder next to the .blend file",
		default=False
	)
	export_subfolder: StringProperty(
		name="Path",
		description="Folder name created next to the .blend file (example: Anims)",
		default="Anims"
	)
	multiply_move_scale: BoolProperty(
		name="Multiply Movement Scale",
		description="Multiply exported move distances and move speeds by the value below. Turns are not affected",
		default=False
	)
	move_scale_multiplier: FloatProperty(
		name="Move Multiplier",
		description="Factor applied to move targets and move speeds",
		default=1.0,
		soft_min=0.0
	)
	anim_exports: CollectionProperty(type=SuperSkeleAnimItem)


class Skelepanel(bpy.types.Panel):
	bl_label = "SuperSkeletor"
	bl_idname = "PT_SuperSkelepanel"
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_category = "SuperSkeletor"

	def draw(self, context):
		layout = self.layout
		settings = context.scene.super_skeletor
		can_export = has_valid_anim_export(context)

		skel = layout.box()
		skel.label(text="Skeleton")
		skel.prop(settings, "autoaddik", text="Add IK targets to chains")
		skel.prop(settings, "iktargetends", text="IK targets at leafs")
		skel.prop(settings, "disable_auto_suffix", text="Disable automatic suffix")
		skel.prop(settings, "assimp_workflow_skeleton", text="Assimp Workflow Skeleton")
		skel.operator("sskele.createskeleton", text="Create Skeleton")

		layout.separator()

		export_box = layout.box()
		export_box.label(text="Export")
		wf = export_box.box()
		wf.label(text="Workflow Options")
		wf.prop(settings, "assimp_workflow", text="Assimp Workflow")
		wf.prop(settings, "gltf_workflow", text="glTF Workflow")
		wf.prop(settings, "skinning", text="Export for Skinning")

		export_box.prop(settings, "export_to_subfolder", text="Export to Subfolder")
		path_col = export_box.column()
		path_col.enabled = settings.export_to_subfolder
		path_col.prop(settings, "export_subfolder", text="Path")

		export_box.prop(settings, "multiply_move_scale", text="Multiply Movement Scale")
		scale_col = export_box.column()
		scale_col.enabled = settings.multiply_move_scale
		scale_col.prop(settings, "move_scale_multiplier", text="Multiplier")

		row = export_box.row()
		row.enabled = can_export
		row.operator("sskele.createbos", text="Create BOS Includes (.h)")
		export_box.label(text="BOS includes require 30 FPS and unit-owned animation policy", icon="INFO")
		row = export_box.row()
		row.enabled = can_export
		row.operator("sskele.createlus", text="Create LUS")
		row = export_box.row()
		row.enabled = can_export
		row.operator("sskele.createlustween", text="Create LUS Tween")

		layout.separator()

		anims = layout.box()
		header = anims.row()
		header.label(text="Anim Exports")
		header.operator("sskele.anim_add", text="New", icon="ADD")

		for i, item in enumerate(settings.anim_exports):
			sub = anims.box()
			row = sub.row()
			row.label(text="Anim %d" % (i + 1))
			rm = row.operator("sskele.anim_remove", text="", icon="X")
			rm.index = i
			sub.prop(item, "action", text="Action")
			sub.prop(item, "is_walk", text="Is Walk Script")
			walk_opts = sub.column()
			walk_opts.enabled = item.is_walk
			walk_opts.prop(item, "varspeed", text="Variable Speed")
			walk_opts.prop(item, "varscale", text="Variable Scale")
			walk_opts.prop(item, "varamplitude", text="Variable Amplitude")
			sub.prop(item, "firstframestance", text="First Frame Stance")
			sub.prop(item, "all_transforms_first", text="All Transforms on First Frame")
			sub.prop(item, "is_death", text="Is Death Script")


class SSKELE_OT_anim_add(Operator):
	bl_idname = "sskele.anim_add"
	bl_label = "Add Anim Export"
	bl_description = "Add a new Anim export entry"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		context.scene.super_skeletor.anim_exports.add()
		return {'FINISHED'}


class SSKELE_OT_anim_remove(Operator):
	bl_idname = "sskele.anim_remove"
	bl_label = "Remove Anim Export"
	bl_description = "Remove this Anim export entry"
	bl_options = {'REGISTER', 'UNDO'}

	index: IntProperty()

	def execute(self, context):
		exports = context.scene.super_skeletor.anim_exports
		if 0 <= self.index < len(exports):
			exports.remove(self.index)
		return {'FINISHED'}


class S3opiece:
	def __init__(self, name, object, mesh, xoff, yoff, zoff):
		self.name = name
		self.parent = None
		self.children = []
		self.object = object
		self.mesh = mesh
		self.xoff = xoff
		self.yoff = yoff
		self.zoff = zoff
		self.loc = Vector((xoff, yoff, zoff))
		self.bone = None
		self.bonename = ""
		self.meshcopy = None
		self.worldpos = Vector((0, 0, 0))
		self.iktarget = None
		self.ikpole = None
		self.ikpoleangle = 0
		self.isafoot = False
		self.isAimXY = False

	def __repr__(self):
		return ('S3opiece:%s parent = %s children = [%s], offsets = %s object=%s mesh=%s worldpos = %s' % (
			self.name,
			self.parent.name if self.parent is not None else None,
			','.join([child.name for child in self.children]),
			self.loc, self.object, self.mesh, self.worldpos))

	def recursefixworldpos(self, parentpos):  # note: doesnt work
		self.worldpos = self.loc + parentpos
		for child in self.children:
			child.recursefixworldpos(self.worldpos)

	def recurseleftrightbones(self, tag=None):

		def nolrname(n):
			return n.lower().replace("l", "_").replace('r', '_')

		if tag is None:
			for i, child in enumerate(self.children):
				isLR = False
				for k, sibling in enumerate(self.children):
					if i != k and nolrname(child.name) == nolrname(sibling.name):
						isLR = True
						logger.info(f'Found a left-right pairing of bones: {self.name} at { self.worldpos}')
						if self.worldpos[0] > 0:  # LEFT
							child.recurseleftrightbones(tag='.L')
						else:
							child.recurseleftrightbones(tag='.R')
				if not isLR:
					child.recurseleftrightbones()

		else:
			self.bonename = self.name + tag
			for child in self.children:
				child.recurseleftrightbones(tag=tag)

	def getmeshboundingbox(self):
		minz = 1000
		maxz = -1000
		miny = 1000
		maxy = -1000
		minx = 1000
		maxx = -1000
		if self.mesh is not None:
			for vertex in self.mesh.vertices:
				minz = min(minz, vertex.co[2])
				maxz = max(maxz, vertex.co[2])
				miny = min(miny, vertex.co[1])
				maxy = max(maxy, vertex.co[1])
				minx = min(minx, vertex.co[0])
				maxx = max(maxx, vertex.co[0])
		return minx, maxx, miny, maxy, minz, maxz


def getmeshbyname(name):
	for mesh in bpy.data.meshes:
		if mesh.name == name:
			return mesh
	return None


def getS3ORootObject():
	#bpy.ops.outliner.item_activate(deselect_all=True) # God knows why this might be needed, but blender 3.6+ refuses to work without this 
	logger.info(f'Searching for S3O root object.')
	currentCollection = bpy.context.collection
	# Safely ensure we are in Object mode (avoids errors when no active object exists)
	try:
		if bpy.context.object is not None:
			bpy.ops.object.mode_set(mode='OBJECT')
	except Exception:
		pass
	#for obj in bpy.data.objects:
	for obj in currentCollection.all_objects:
		
		logger.info(f'{obj} in currentCollection.all_objects: {obj.name} {obj.parent}')
		logger.info(f'{obj} in currentCollection.all_objects: {obj.name}')
		if 'SpringRadius' in obj.name or 'SpringHeight' in obj.name:
			continue
		if obj.parent is None:
			for child in bpy.data.objects:
				if child.parent and child.parent == obj:
					logger.info(f'Root object found: {obj}')
					return obj, obj.name    # rootObject, rootName
	return None, ""     # I don't think this would ever happen, but who knows


def properrot(bone, MYEULER='YXZ', parentEULER=True):
	# MYEULER = 'YXZ' #'ZXY' #BECAUSE FUCK ME THATS WHY
	bone_matrix = bone.matrix.copy()
	parent_bone_matrix = bone.matrix.copy()
	current_bone = bone
	if current_bone.parent is not None:
		parent_bone_matrix = current_bone.parent.matrix.copy()
		parent_bone_matrix.invert()
		# bone_matrix = bone_matrix @ parent_bone_matrix # OH BOY IS THIS WRONG!
		bone_matrix = parent_bone_matrix @ bone_matrix

		current_bone = current_bone.parent

	if parentEULER:
		rot = bone_matrix.to_euler(MYEULER, parent_bone_matrix.to_euler(MYEULER))
	else:
		rot = bone_matrix.to_euler(MYEULER)  # , parent_bone_matrix.to_euler(MYEULER) )
	rotation_text = '%s %s %i X:%.1f Y:%.1f Z:%.1f' % (
		bone.name, MYEULER, parentEULER, degrees(rot.x), degrees(rot.y), degrees(rot.z))
	return rotation_text


class SkeletorRotator(bpy.types.Operator):
	bl_idname = "sskele.rotate"
	bl_label = "skeletor_rotate"
	bl_description = "Create a skeleton"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		self.s3orotate(context=context)
		return {'FINISHED'}

	@staticmethod
	def s3orotate(context):
		scene = context.scene
		for obj in scene.objects:
			obj.select_set(True)
			obj.rotation_mode = ROTATION_MODE
		bpy.ops.object.select_all(action='DESELECT')

		rootObject, rootName = getS3ORootObject()
		bpy.ops.object.select_all(action='DESELECT')
		rootObject.select_set(True)

		# bpy.ops.transform.rotate(value=-pi/2, orient_axis='Z', orient_type='VIEW', orient_matrix=((0, -1, 0), (0, 0, -1), (-1, 0, 0)), orient_matrix_type='VIEW', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False)
		bpy.context.object.rotation_euler[0] = pi / 2

		bpy.ops.object.select_all(action='DESELECT')
		bpy.ops.object.select_all(action='SELECT')
		bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

		# return
		bpy.ops.object.select_all(action='DESELECT')
		rootObject.select_set(True)
		oldz = bpy.context.object.location[2]
		oldy = bpy.context.object.location[1]
		# bpy.context.object.location[1] = oldz
		# bpy.context.object.location[2] = oldy
		bpy.ops.object.select_all(action='SELECT')

		bpy.ops.transform.translate(value=(0, -10.9483, 13.9935), orient_type='GLOBAL',
									orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL',
									mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH',
									proportional_size=1, use_proportional_connected=False,
									use_proportional_projected=False)

		bpy.ops.object.select_all(action='DESELECT')

		rootObject.select_set(True)
		bpy.ops.object.mode_set(mode='EDIT', toggle=False)
		bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

		bpy.ops.object.select_all(action='DESELECT')


class SkeletorOperator(bpy.types.Operator):
	bl_idname = "sskele.createskeleton"
	bl_label = "skeletize"
	bl_description = "Create a skeleton"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		self.skeletize(context=context)
		return {'FINISHED'}

	@staticmethod
	def skeletize(context):
		logger.info("Creating Skeleton")
		NOTAIL = True
		IKTARGETENDS = context.scene.super_skeletor.iktargetends
		AUTOADDIK = context.scene.super_skeletor.autoaddik
		ASSIMP = context.scene.super_skeletor.assimp_workflow_skeleton
		DISABLE_AUTO_SUFFIX = context.scene.super_skeletor.disable_auto_suffix

		# debug delete all armatures and bones!
		# Need an active object or mode_set() throws in Blender 4/5
		if context.view_layer.objects.active is None:
			for obj in context.scene.objects:
				context.view_layer.objects.active = obj
				break
		if context.view_layer.objects.active is not None and context.mode != 'OBJECT':
			bpy.ops.object.mode_set(mode='OBJECT')
		for obj in list(bpy.context.scene.objects):
			if obj.name == "Armature":
				logger.info(f'Removing existing Armature object: {obj}')
				bpy.data.objects.remove(obj, do_unlink=True)

		pieces = {}  # {"name":s3opiece}
		# collect the data we need:
		# object of each piece
		# root object
		# the offsets of each object
		# the children of each object
		# the amount of geometry each object has.

		# find the object with no parents, but has children (root) - ignore *SpringHeight and *SpringRadius
		# TODO: Pass currentCollection here
		rootObject, rootName = getS3ORootObject()

		# got the root!

		rootPiece = S3opiece(rootObject.name, rootObject, getmeshbyname(rootObject.name), # localPos[0][3], localPos[1][3], localPos[2][3])
							 rootObject.location[0], rootObject.location[1], rootObject.location[2])    # Root is always in world coords

		logger.info(f'The root piece is:{rootPiece}')

		logger.info("====Collecting Pieces====")
		pieces[rootName] = rootPiece
		currentCollection = bpy.context.collection
		# for obj in bpy.data.objects:
		for obj in currentCollection.all_objects:
			if obj.parent is not None:
				localPos = obj.matrix_local  # local x = [0][3], y = [1][3], z = [2][3]
				# x, y, z = obj.matrix_world.to_3x3().col
				#globalCoords = obj.matrix_world.translation
				#localMatrix = obj.matrix_world.inverted() @ obj.matrix_world.translation

				newPiece = S3opiece(obj.name, obj, getmeshbyname(obj.name), # localCoords[0], localCoords[1], localCoords[2])
									localPos[0][3], localPos[1][3], localPos[2][3]) #obj.location[0], [1], [2]
				logger.info("\n")
				logger.info(f'Found a new piece {newPiece}')
				pieces[newPiece.name] = newPiece
		for piece in pieces.values():
			logger.info(f'Each of the found pieces are: {piece}, {piece.object}')
			if piece.object.parent is not None:
				piece.parent = pieces[piece.object.parent.name]
				piece.parent.children.append(piece)
				logger.info(f'Parenting child {piece.name} to parent {piece.parent.name}')

		rootPiece.recursefixworldpos(Vector((0, 0, 0)))

		openNodes = set()  # Set to keep track of visited nodes.
		openNodes.add(rootPiece)
		dfs_piece_order = []  # [rootPiece.name]

		while len(openNodes) > 0:
			nodelist = list(openNodes)
			for node in nodelist:
				dfs_piece_order.append(node.name)
				logger.info(f'Visiting node named {node.name}')
				openNodes.remove(node)
				for child in node.children:
					openNodes.add(child)
		logger.info("\n\n==== Piece Order Defaults ====")
		logger.info(f'depth first search piece order is {dfs_piece_order}')

		logger.info("\n\n==== Reparenting pieces to avoid AimX and AimY (if needed) ====")
		# if the parent of an object is called aimx* or aimy*, then reparent the piece to the parent of aimx or aimy actual parent
		for piece in pieces.values():
			if piece.object.parent is not None and piece.object.parent.name[0:4].lower() in ['aimx', 'aimy']:
				logger.info(f'Re-parenting {piece.name} from {piece.parent.name } to {piece.parent.parent.name}')
				piece.parent.isAimXY = True
				try:
					piece.parent.children.remove(piece)
					piece.parent = pieces[piece.object.parent.parent.name]
					piece.parent.children.append(piece)
				except:
					logger.error(f'Failed to reparent piece {piece} from parent {piece.parent} to grandparent {piece.parent.parent}')
					raise

		# final check that we have all set:
		logger.info("\n\n----------Sanity check:-----------")
		for k, v in pieces.items():
			logger.info(f'{k} {v}')

		# set the cursor to origin:
		bpy.ops.transform.translate(value=(0, 0, 0), orient_type='GLOBAL',
									orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL',
									mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH',
									proportional_size=1, use_proportional_connected=False,
									use_proportional_projected=False, cursor_transform=True, release_confirm=True)

		logger.info("\n\n====Setting rotation modes to Euler YXZ====")
		scene = context.scene
		for obj in scene.objects:
			obj.select_set(False)
			obj.rotation_mode = ROTATION_MODE

		# add an armature!
		logger.info("\n\n====Creating Armature====")
		arm_data = bpy.data.armatures.new("Armature")

		armature_object = bpy.data.objects.new("Armature", arm_data)
		armature_object.location = Vector((0, 0, 0))  # rootpiece.loc
		armature_object.show_in_front = True
		armature_object.data.show_axes = True
		armature_object.data.show_names = True

		armature_object.rotation_mode = ROTATION_MODE

		context.collection.objects.link(armature_object)

		armature_object.select_set(True)

		context.view_layer.objects.active = armature_object

		bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
		bpy.ops.object.mode_set(mode='EDIT', toggle=False)
		#bpy.ops.object.mode_set(mode='EDIT', toggle=False)

		logger.info("\n\n====Looking for mirrorable pieces===")
		# to enable : https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle
		# rootpiece.recurseleftrightbones()
		for name, piece in pieces.items():
			piece.bonename = name
			if not DISABLE_AUTO_SUFFIX:
				for name2, piece2 in pieces.items():
					if name == name2:
						continue
					if name.lower().replace('l', '').replace('r', '') == name2.lower().replace('l', '').replace('r', ''):
						if piece.worldpos[0] > 0:
							piece.bonename = piece.bonename + '.R'
						else:
							piece.bonename = piece.bonename + '.L'

		logger.info("\n\n====Adding Bones=====")
		for name in dfs_piece_order:
			piece = pieces[name]
			if piece.isAimXY:
				continue
			if piece.bonename in arm_data.edit_bones:
				newbone = arm_data.edit_bones[piece.bonename]
			else:
				newbone = arm_data.edit_bones.new(piece.bonename)
			newbone.name = piece.bonename
			newbone.head = piece.worldpos

			if AUTOADDIK:
				if NOTAIL:
					newbone.tail = newbone.head + Vector((0, 5, 0))

				tailpos = piece.loc + Vector((0, 5, 0))  # 0, 0 10
				if len(piece.children) >= 1:
					tailpos = Vector((0, 0, 0))
					for child in piece.children:
						tailpos = tailpos + child.worldpos
					tailpos = tailpos / len(piece.children)
					newbone.tail = tailpos
					if NOTAIL:
						newbone.tail = newbone.head + Vector((0, 5, 0))  # TODO fixme
					# TODO: Something is an arm if it has only nomesh children
					# thus we add a forward pointing IK target to its tailpos
					onlyemptychildren = True
					for child in piece.children:
						if child.mesh is not None:
							onlyemptychildren = False
					if onlyemptychildren and AUTOADDIK:
						logger.info(f"LOOKS LIKE AN ARM: { piece.name}")
						ikbone = arm_data.edit_bones.new('iktarget.' + piece.bonename)
						ikbone.head = newbone.tail
						ikbone.tail = newbone.tail + Vector((0, 5, 0))
						piece.iktarget = ikbone
				else:  # end piece
					# TODO: CHECK FOR GEOMETRY, is it a foot or an arm or a tentacle ?
					# TODO: multiple branches for multiple toes give too many IK targets :/
					if piece.mesh is not None and piece.parent.iktarget is None:
						boundingbox = piece.getmeshboundingbox()

						logger.info(f'LOOKS LIKE A FOOT: { piece.name}  {piece.worldpos} {boundingbox}')
						if piece.worldpos[2] + boundingbox[4] <= 2.0:
							# this looks like a foot
							tailpos = piece.worldpos + Vector((0, boundingbox[3], boundingbox[4]))
							# better add the heel IK thing too XD
							if AUTOADDIK:
								if not IKTARGETENDS:
									heelbone = arm_data.edit_bones.new('iktarget.' + piece.parent.bonename)
									heelbone.head = piece.parent.bone.tail  # newbone.head
									heelbone.tail = newbone.head + Vector((0, boundingbox[4], 0))
									if NOTAIL:
										heelbone.tail = heelbone.head + Vector((0, 5, 0))
									piece.parent.iktarget = heelbone
								else:
									heelbone = arm_data.edit_bones.new('iktarget.' + piece.bonename)
									heelbone.head = newbone.tail  # newbone.head
									heelbone.tail = newbone.head + Vector((0, boundingbox[4], 0))
									if NOTAIL:
										heelbone.tail = heelbone.head + Vector((0, 5, 0))
									piece.iktarget = heelbone
						else:
							# todo this is not a foot
							# guess if it points forward or up or down?
							if boundingbox[5] > boundingbox[3] and boundingbox[5] > -1 * boundingbox[2]:  # points forward
								tailpos = piece.worldpos + Vector((0, boundingbox[5], 0))
							else:
								if boundingbox[3] > -1 * boundingbox[2]:
									tailpos = piece.worldpos + Vector((0, 0, boundingbox[3]))  # up
								else:
									tailpos = piece.worldpos + Vector((0, 0, boundingbox[2]))  # down

					# TODO we are also kind of a foot if we only have children with no meshes.
					else:
						tailpos = piece.worldpos + Vector((0, 5, 0))
				newbone.tail = tailpos

			# TODO: easier rotations like this?
			# This is where the world axis is always assigned to the bones rotations
			if NOTAIL:
				newbone.tail = newbone.head + Vector((0, 5, 0))

			if ASSIMP:
				# x, y, z = newbone.matrix.to_3x3().col
				# # rotation matrix 30 degrees around local x axis thru head
				# R = (Matrix.Translation(newbone.head) @
				# 	 Matrix.Rotation(radians(30), 4, x) @
				# 	 Matrix.Translation(-newbone.head)
				# 	 )
				# # bone.matrix = R @ bone.matrix
				# bone.transform(R)
				old_head = newbone.head.copy()

				# Get local matrix of object
				obj = piece.object
				R = obj.matrix_world
				#pos, rot, scl = R.decompose()

				# That's how you'd apply individual rotations, but that's not needed for our purpose
				# R = (Matrix.Rotation(rot[0], 4, newbone.y_axis.normalized()) @  # newbone.y_axis.normalized()
				# 	 Matrix.Rotation(rot[1], 4, newbone.x_axis.normalized()) @  # newbone.x_axis.normalized()
				# 	 Matrix.Rotation(rot[2], 4, newbone.z_axis.normalized())  # newbone.z_axis.normalized()
				# 	)
				#newbone.transform(R, roll=False)

				newbone.matrix = R
				bpy.context.view_layer.update()

			logger.info("trying to add bone to %s\nat head:%s \ntail:%s" % (piece, newbone.head, newbone.tail))
			piece.bone = newbone
		# return
		logger.info("=====Reparenting Bone-Bones=======")

		for name, piece in pieces.items(): # not getattr(piece.parent, "name", "None") and
			if piece.parent is not None and not piece.isAimXY:
				logger.info("piece " + name + " | parent: " + piece.parent.name)
				piece.bone.parent = piece.parent.bone

		bpy.ops.object.editmode_toggle()  # These are required so that 'armature_object.pose.bones[piece.bonename]' works
		bpy.ops.object.posemode_toggle()

		logger.info("=====Setting IK Targets=======")

		if AUTOADDIK:
			for name, piece in pieces.items():
				if not piece.isAimXY:
					armature_object.pose.bones[piece.bonename].rotation_mode = ROTATION_MODE  # ROTATION_MODE = 'YXZ'  # was: 'ZXY'

				if piece.iktarget is not None and piece.parent is not None:
					chainlength = 1
					chainpos = piece.parent
					while len(chainpos.children) == 1 and chainpos.parent is not None:
						chainlength += 1
						chainpos = chainpos.parent
					logger.info(f'Adding iktarget to { piece.name} chain_length = { chainlength}')
					constraint = armature_object.pose.bones[piece.bonename].constraints.new('IK')
					constraint.target = armature_object
					constraint.subtarget = 'iktarget.' + piece.bonename
					constraint.chain_count = chainlength
					armature_object.pose.bones[piece.bonename].ik_stiffness_z = 0.99  # avoids having to create knee poles
		else:
			for name, piece in pieces.items():
				armature_object.pose.bones[piece.bonename].rotation_mode = ROTATION_MODE  # was: 'ZXY'

		logger.info("=====Parenting meshes to bones=======")
		# getting desperate here: https://blender.stackexchange.com/questions/77465/python-how-to-parent-an-object-to-a-bone-without-transformation
		for name, piece in pieces.items():
			if piece.isAimXY:
				continue
			bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
			ob = piece.object
			bpy.ops.object.select_all(action='DESELECT')
			armature_object.select_set(True)
			bpy.context.view_layer.objects.active = armature_object
			bpy.ops.object.mode_set(mode='EDIT')
			parent_bone = piece.bonename
			armature_object.data.edit_bones.active = armature_object.data.edit_bones[parent_bone]
			bpy.ops.object.mode_set(mode='OBJECT')
			bpy.ops.object.select_all(action='DESELECT')
			ob.select_set(True)
			armature_object.select_set(True)
			bpy.context.view_layer.objects.active = armature_object
			bpy.ops.object.parent_set(type='BONE', keep_transform=True)

		logger.info("\n\n ===== Skeletizing Operation complete!")


class SimpleBoneAnglesPanel(bpy.types.Panel):
	bl_label = "Bone Angles"
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'

	def draw(self, context):
		# print ("DrawSimpleBonesAnglesPanel")
		if 'Armature' not in context.scene.objects:
			return
		arm = context.scene.objects['Armature']
		props = {"location": "move", "rotation_euler": "turn"}

		selectednames = []
		if bpy.context.selected_pose_bones is not None:
			for o in bpy.context.selected_pose_bones:
				selectednames.append(o.name)
		# print (selectednames)
		for bone in arm.pose.bones:
			if not bone.bone.use_deform:
				continue
			if 'iktarget' in bone.name:
				continue

			bone_name = bone.name
			MYEULER = 'YXZ'  # 'ZXY' #BECAUSE FUCK ME THAT'S WHY
			bone_matrix = bone.matrix.copy()

			parent_bone_matrix = bone.matrix.copy()
			current_bone = bone
			if current_bone.parent is not None:
				parent_bone_matrix = current_bone.parent.matrix.copy()
				parent_bone_matrix.invert()
				# bone_matrix = bone_matrix @ parent_bone_matrix # OH BOY IS THIS WRONG!
				bone_matrix = parent_bone_matrix @ bone_matrix
				current_bone = current_bone.parent

			# there seems to be a major difference in IK based rots, and manual rots.
			# the matrix inversion with 'YXZ' euler order seems to be correct for IK targetted bones
			# but its way overkill for manually rotated stuff
			# maybe there are two separate rotations, e.g.
			# bpy.context.object.pose.bones["rdoor.R"].rotation_euler[0] = 0.105584
			# and the parent matrix based one
			# but how to choose between these for IK and FK bones?
			# use the locs  and rots from the fcurves, and then in pass 2 merge on the actual ones?
			# We KNOW which bones have FK fcurves - those are the ones manually set
			# We can also figure out, from the IK constraints and the chain lengths, which bones have IK on them
			# bpy.context.object.pose.bones["rankle.R"].constraints["IK"].mute = False

			rot = bone_matrix.to_euler(MYEULER)  # , parent_bone_matrix.to_euler(MYEULER) )

			row = self.layout.row()
			rotation_text = '%s X:%.1f Y:%.1f Z:%.1f' % (bone_name, degrees(rot.x), degrees(rot.y), degrees(rot.z))
			# print (rotation_text)
			# if bone_name in selectednames:
			#     rotation_text = '  '+rotation_text.upper()
			#     for eulertype in ['XYZ','XZY','YXZ','YZX','ZXY','ZYX']:
			#         for ptype in [False,True]:
			#             row.label(text = properrot(bone,MYEULER = eulertype, parentEULER = ptype))
			#             row = self.layout.row()

			if sum([abs(degrees(rot.x)), abs(degrees(rot.y)), abs(degrees(rot.z))]) > 135:
				rotation_text = '[!] ' + rotation_text
				row.alert = True
			row.label(text=rotation_text)
			row = self.layout.row()
			rotation_text = 'E %s X:%.1f Y:%.1f Z:%.1f' % (bone_name,
														   degrees(arm.pose.bones[bone_name].rotation_euler[0]),
														   degrees(arm.pose.bones[bone_name].rotation_euler[1]),
														   degrees(arm.pose.bones[bone_name].rotation_euler[2])
														   )
			row.label(text=rotation_text)


# row.label(text='X%.1f'%(bone_matrix[0][3]))
# row.label(text='Y%.1f'%(bone_matrix[1][3]))
# row.label(text='Z%.1f'%(bone_matrix[2][3]))


# # This is the base class which all Skeleton-Makers derive from.
# # Override the write_file (and tobos, if needed) methods to add your new export option logic.
class SkeletorBOSMaker(bpy.types.Operator):
	bl_idname = "sskele.createbos"
	bl_label = "Create BOS"
	bl_description = "Export selected Anim entries as include-ready [blend]_[action].h files"
	bl_options = {'REGISTER', 'UNDO'}
	export_suffix = ".h"

	@classmethod
	def poll(cls, context):
		return has_valid_anim_export(context)

	def execute(self, context):
		settings = context.scene.super_skeletor
		fps = float(getattr(context.scene.render, "fps", 30) or 30)
		if fps != 30.0:
			self.report({'ERROR'}, "Modular BOS animation export requires a 30 FPS Blender scene")
			return {'CANCELLED'}
		if settings.gltf_workflow:
			message = "glTF workflow: export GLB with Blender's +Y Up option disabled"
			logger.warning(message)
			self.report({'WARNING'}, message)
			if not bool(context.scene.get("s3ocompat", False)):
				message = "glTF workflow: set the Scene custom property s3ocompat=true for S3O-derived models"
				logger.warning(message)
				self.report({'WARNING'}, message)

		items = [item for item in settings.anim_exports if item.action is not None]
		if not items:
			self.report({'WARNING'}, "No Anim entries with a valid Action")
			return {'CANCELLED'}
		invalid_names = sorted({item.action.name for item in items if not action_name_is_valid(item.action.name)})
		if invalid_names:
			self.report({'ERROR'}, "Invalid BOS Action name(s): " + ", ".join(invalid_names))
			return {'CANCELLED'}
		function_names = ["Start" + item.action.name for item in items]
		if len(function_names) != len(set(function_names)):
			self.report({'ERROR'}, "Duplicate generated BOS function name in selected Anim entries")
			return {'CANCELLED'}

		arm, _prefix = find_export_armature(context)
		if arm is None:
			self.report({'ERROR'}, "No armature found")
			return {'CANCELLED'}

		anim_data = arm.animation_data
		prev_action = anim_data.action if anim_data else None
		prev_slot = getattr(anim_data, "action_slot", None) if anim_data else None
		exported = []
		warned_rest_frames = set()

		try:
			for item in items:
				self.current_anim_item = item
				assign_action_to_arm(arm, item.action)
				if settings.gltf_workflow:
					rest_frames = set(gltf_non_identity_animated_rest_frames(arm)) - warned_rest_frames
					if rest_frames:
						message = "glTF workflow: animated objects/bones have non-identity local rest rotations: " + ", ".join(sorted(rest_frames))
						logger.warning(message)
						self.report({'WARNING'}, message)
						warned_rest_frames.update(rest_frames)
				self.tobos(context=context)
				exported.append(item.action.name)
		finally:
			if arm.animation_data is not None:
				arm.animation_data.action = prev_action
				if prev_slot is not None and hasattr(arm.animation_data, "action_slot"):
					try:
						arm.animation_data.action_slot = prev_slot
					except Exception:
						pass
			self.current_anim_item = None

		self.report({'INFO'}, "Exported: " + ", ".join(exported))
		return {'FINISHED'}

	# Note: Do NOT define a custom __init__ that only takes `self`.
	# Blender 4.x/5.x passes extra arguments when constructing Operators.
	# whichframe is initialized lazily below.

	def tobos(self, context):
		logger.info("MAKING BOS, BOSS")
		# Lazy init (safe across Blender versions)
		if not hasattr(self, "whichframe"):
			self.whichframe = 0
		scene = context.scene
		arm = None
		piecenameprefix = ""
		if 'Armature' not in context.scene.objects:
			logger.warning("Default Armature not in context.scene.objects. Objects Found:")
			for o in context.scene.objects:
				logger.info(f'{o} {o.type}')
				if o.type == "ARMATURE":
					logger.info(f'Found an armature{ o} {o.type}')
					piecenameprefix = o.name + '_'
					arm = o
			if arm is None:
				logger.error("No possible armature type object found, exiting")
				return
		else:
			arm = context.scene.objects['Armature']
		logger.info(f'Starting Frame: {self.whichframe}')
		self.whichframe += 1
		bonesinIKchains = []
		piecehierarchy = {}  # for each bone, list its children.
		animframes = {}  # {frame_number:{bone_name:{axis:value}}}

		def posebone_name_to_piece_name(posebone_name):
			if 'iktarget' in posebone_name:
				return None
			if posebone_name.endswith('.R') or posebone_name.endswith('.L'):
				posebone_name = posebone_name[:-2]
			return posebone_name

		for bone in arm.pose.bones:
			if not bone.bone.use_deform:
				continue
			piecename = posebone_name_to_piece_name(bone.name)
			if piecename is not None:
				if piecename not in piecehierarchy:
					piecehierarchy[piecename] = []
				if bone.parent:
					parentname = posebone_name_to_piece_name(bone.parent.name)
					if parentname is not None:
						if parentname not in piecehierarchy:
							piecehierarchy[parentname] = [piecename]
						else:
							piecehierarchy[parentname].append(piecename)

		for bone in arm.pose.bones:
			if not bone.bone.use_deform:
				continue
			if 'iktarget' in bone.name:
				continue
			if 'IK' in bone.constraints and bone.constraints['IK'].mute == False:
				chainLength = bone.constraints['IK'].chain_count
				p = bone
				if chainLength == 0:
					while p is not None:
						if p.name not in bonesinIKchains:
							bonesinIKchains.append(p.name)
						p = p.parent
				else:
					while p is not None and chainLength > 0:
						if p.name not in bonesinIKchains:
							bonesinIKchains.append(p.name)
						chainLength = chainLength - 1
						p = p.parent

		sample_frames = set()
		invalid_sample_frames = set()
		curves = get_action_fcurves(arm)
		if curves:
			for c in curves:
				data_path = getattr(c, "data_path", "")
				if "location" not in data_path and "rotation" not in data_path:
					continue
				for k in c.keyframe_points:
					raw_frame = float(k.co[0])
					resolved_frame = int(round(raw_frame))
					if abs(raw_frame - resolved_frame) > 0.00001:
						invalid_sample_frames.add(raw_frame)
					sample_frames.add(resolved_frame)
		if invalid_sample_frames:
			message = "BOS keyframes must be on distinct integer Blender frames: " + ", ".join(
				"%.3f" % value for value in sorted(invalid_sample_frames)
			)
			logger.error(message)
			self.report({'ERROR'}, message)
			return

		if sample_frames:
			logger.info(f'Baking evaluated pose on {len(sample_frames)} keyframe(s)')
		else:
			action = arm.animation_data.action if arm.animation_data is not None else None
			if action is not None:
				frame_start = int(round(action.frame_range[0]))
				frame_end = int(round(action.frame_range[1]))
			else:
				frame_start = int(scene.frame_start)
				frame_end = int(scene.frame_end)
			if frame_end < frame_start:
				frame_start, frame_end = frame_end, frame_start
			# Fallback: 3-frame steps at 30fps-style spacing
			sample_frames = set(range(frame_start, frame_end + 1, 3))
			sample_frames.add(frame_end)
			logger.info(f'No loc/rot keys found; baking every 3 frames from {frame_start} to {frame_end}')

		prev_scene_frame = scene.frame_current
		try:
			prev_baked = None
			for frame_time in sorted(sample_frames):
				scene.frame_set(frame_time)
				if hasattr(context, "view_layer"):
					context.view_layer.update()
				baked = collect_full_piece_transforms(arm)
				if prev_baked is not None:
					for bone_name, channels in baked.items():
						prev_ch = prev_baked.get(bone_name)
						if not prev_ch:
							continue
						for axis in range(3):
							key = 'rot' + str(axis)
							if key not in channels or key not in prev_ch:
								continue
							curr = channels[key]
							prev = prev_ch[key]
							while curr - prev > 180.0:
								curr -= 360.0
							while curr - prev < -180.0:
								curr += 360.0
							channels[key] = curr
				animframes[frame_time] = baked
				prev_baked = baked
		finally:
			scene.frame_set(prev_scene_frame)

		logger.info("Baked Animframes: ")
		for k in sorted(list(animframes.keys())):
			logger.info(f'	{k} bones={len(animframes[k])}')
		self.write_file(context=context, animframes=animframes, piecehierarchy=piecehierarchy, piecenameprefix = piecenameprefix)
		logger.info(f'bonesinIKchains: {bonesinIKchains}')

	def write_file(self, context, animframes, piecehierarchy, piecenameprefix = ""):
		fps = float(getattr(context.scene.render, "fps", 30) or 30)
		flags = get_anim_flags(self, context)
		action_name = flags["ACTION"].name if flags["ACTION"] else "Action"
		try:
			content = render_bos_animation(
				animframes,
				action_name,
				is_walk=flags["ISWALK"],
				is_death=flags["ISDEATH"],
				variable_speed=flags["VARIABLESPEED"],
				variable_scale=flags["VARIABLESCALE"],
				variable_amplitude=flags["VARIABLEAMPLITUDE"],
				first_frame_stance=flags["FIRSTFRAMESTANCE"],
				all_transforms_first=flags["ALL_TRANSFORMS_FIRST"],
				assimp=flags["ASSIMP"],
				move_scale=get_move_scale(context),
				piece_name_prefix=piecenameprefix,
				piece_hierarchy=piecehierarchy,
				fps=fps,
			)
		except ValueError as error:
			logger.error(str(error))
			self.report({'ERROR'}, str(error))
			return
		newfile_name = build_export_filepath(action_name, self.export_suffix)
		with open(newfile_name, 'w') as outf:
			outf.write(content)
		logger.info('Done writing include-ready BOS animation: %s', newfile_name)
		return

		# Legacy inline emitter retained temporarily below for source-history context;
		# modular exports return above and never emit declarations or unit callbacks.
		move_turn_miniumum_threshold = 0.0001  # skip only true no-ops; keep gait micro-offsets
		sleepperframe = 1.0 / fps
		# conversion time:
		# output a bos script
		# simplify mini rots and mini moves
		# the first frame can be ignored
		keyframe_times = sorted(animframes.keys())
		explodedpieces = []

		filepath = bpy.data.filepath
		logger.info(f'File path to write to : {filepath}')

		INFOSTRING = "For %s Created by https://github.com/Beherith/Skeletor_S3O V(%s)" % (filepath, bl_info['version'])

		flags = get_anim_flags(self, context)
		ISWALK = flags["ISWALK"]
		ISDEATH = flags["ISDEATH"]
		VARIABLESPEED = flags["VARIABLESPEED"]
		FIRSTFRAMESTANCE = flags["FIRSTFRAMESTANCE"]
		ALL_TRANSFORMS_FIRST = flags["ALL_TRANSFORMS_FIRST"]
		VARIABLESCALE = flags["VARIABLESCALE"]
		VARIABLEAMPLITUDE = flags["VARIABLEAMPLITUDE"]
		ASSIMP = flags["ASSIMP"]
		MOVE_SCALE = get_move_scale(context)

		move_variable = '[%.6f]'
		turn_variable = '<%.6f>'

		if VARIABLESCALE:
			move_variable = "((" + move_variable + " *MOVESCALE)/100)"

		if VARIABLEAMPLITUDE:
			move_variable = "((" + move_variable + " *animAmplitude)/100)"
			turn_variable = "((" + turn_variable + " *animAmplitude)/100)"

		#AXES = 'XZY'
		BOSAXIS = ['x-axis', 'z-axis' if not ASSIMP else 'y-axis', 'y-axis' if not ASSIMP else 'z-axis']
		blender_to_bos_axis_multiplier = {'move': [1.0, 1.0, 1.0], 'turn': [-1.0, -1.0, 1.0]}
		if ASSIMP:
			blender_to_bos_axis_multiplier = {'move': [1.0, 1.0, 1.0], 'turn': [1.0, 1.0, -1.0]} # ok Y axis is surely correct now, X looks ok too, Z too, but surely there isnt a swap here?


		

		#LUSAXIS = ['x_axis', 'z_axis' if not ASSIMP else 'y_axis', 'y_axis' if not ASSIMP else 'z_axis']
		#blender_to_bos_axis_multiplier = {'Move': [1.0, 1.0, 1.0], 'Turn': [-1.0, 1.0, 1.0]}


		def MakeBOSLineString(turn_or_move, bonename, axisindex, targetposition, speed, variablespeed=True, indents=3,
							  delta=0):
			axisname = BOSAXIS[axisindex]
			if turn_or_move == 'move':
				targetposition = float(targetposition) * MOVE_SCALE
				speed = float(speed) * MOVE_SCALE
			targetposition = targetposition * blender_to_bos_axis_multiplier[turn_or_move][axisindex]
			cmdline = '' + '\t' * indents
			cmdline = cmdline + turn_or_move + ' '
			cmdline = cmdline + piecenameprefix + bonename + ' to '
			cmdline = cmdline + axisname + ' '
			if turn_or_move == 'turn':
				cmdline = cmdline + turn_variable % targetposition + ' '
			else:
				cmdline = cmdline + move_variable % targetposition + ' '
			cmdline = cmdline + 'speed '
			if turn_or_move == 'turn':
				cmdline = cmdline + turn_variable % speed + ' '
			else:
				cmdline = cmdline + move_variable % speed + ' '
			if variablespeed:
				cmdline = cmdline + '/ animSpeed'
			cmdline = cmdline + '; '
			if delta != 0 and not OMITDELTAOUTPUT:
				cmdline = cmdline + '//delta=%.2f'%delta
			return cmdline

		action_name = flags["ACTION"].name if flags["ACTION"] else "Action"
		newfile_name = build_export_filepath(action_name, getattr(self, "export_suffix", ".txt"))
		outf = open(newfile_name, 'w')
		# Header attribution line removed by request
		if VARIABLESCALE:
			outf.write("#define MOVESCALE 100 //Higher values are bigger, 100 is default\n")
		if VARIABLEAMPLITUDE:
			outf.write("static-var animAmplitude; //Higher values are bigger, 100 is default\n")
		if ISWALK and VARIABLESPEED:
			outf.write(
				"// this animation uses the static-var animFramesPerKeyframe which contains how many frames each keyframe takes\n")
			outf.write("static-var animSpeed, maxSpeed, animFramesPerKeyframe, isMoving;\n#define SIGNAL_MOVE 1\n")
		elif not ISDEATH:
			outf.write("static-var bAnimate;\n")

		animSpeed = [keyframe_times[i] - keyframe_times[i - 1] for i in range(2, len(keyframe_times))]
		animFPK = 4
		if len(animSpeed) == 0:
			logger.warning("MEGA WARNING: NO DETECTABLE FRAMES!")
			return
		else:
			animFPK = float(sum(animSpeed)) / (len(keyframe_times) - 2)
			if ISWALK and (animFPK - round(animFPK) > 0.00001):
				warn = "//Animframes spacing is %f, THIS SHOULD BE AN INTEGER, SPACE YOUR KEYFRAMES EVENLY!\n" % animFPK
				outf.write(warn)
				logger.warning(warn)

		stopwalking_maxspeed = {}  # dict of bos commands, with max velocity in it to define the stopwalking function
		firstframestance_positions = {}  # dict of bos commands, with the target of the piece as value
		if ISWALK:
			outf.write("Walk() {\n\tset-signal-mask SIGNAL_MOVE;\n")
		elif ISDEATH:
			outf.write(
				"//use call-script DeathAnim(); from Killed()\nDeathAnim() {\n\tsignal SIGNAL_MOVE;\n\tsignal SIGNAL_AIM1;\n\tcall-script StopWalking();\n\tturn aimy1 to y-axis <0> speed <120>;\n\tturn aimx1 to x-axis <0> speed <120>;\n")
		else:
			outf.write("// start-script Animate(); //from RestoreAfterDelay\n")
			outf.write(
				"Animate() {\n\tset-signal-mask SIGNAL_MOVE | SIGNAL_AIM1; //you might need this\n\tsleep 100*RAND(30,256);//sleep between 3 and 25.6 seconds\n\tbAnimate = TRUE;\n")

		firststep = True
		if not ISWALK:
			firststep = False

		arm_for_pose, _prefix = find_export_armature(context)
		first_written_frame = True

		for frame_index, frame_time in enumerate(keyframe_times):
			if frame_index == 0 and not FIRSTFRAMESTANCE:  # skip first piece
				continue

			thisframe = animframes[keyframe_times[frame_index]]
			prevframe = animframes[keyframe_times[frame_index - 1]]

			keyframe_delta = keyframe_times[frame_index] - keyframe_times[frame_index - 1]
			if keyframe_delta == 0:
				keyframe_delta = 1
			sleeptime = sleepperframe * keyframe_delta
			force_all = ALL_TRANSFORMS_FIRST and frame_index > 0 and first_written_frame
			if force_all:
				bpy.context.scene.frame_set(frame_time)
				full_pose = collect_full_piece_transforms(arm_for_pose)
				for bone_name, channels in full_pose.items():
					if bone_name not in thisframe:
						thisframe[bone_name] = {}
					thisframe[bone_name].update(channels)

			if frame_index > 0:
				if firststep:
					outf.write("\tif (isMoving) { //Frame:%i\n" % frame_time)
				else:
					if ISWALK:
						outf.write("\t\tif (isMoving) { //Frame:%i\n" % frame_time)
					elif ISDEATH:
						outf.write("\t\tif (TRUE) { //Frame:%i\n" % frame_time)
					else:
						outf.write("\t\tif (bAnimate) { //Frame:%i\n" % frame_time)

			for bone_name in sorted(thisframe.keys()):
				bone_motions = thisframe[bone_name]
				rotations_sum = 0

				for axis, value in bone_motions.items():
					# find previous value
					# TODO: fix missing keyframes for individual anims and interpolate from last known keyframe for curve!
					# handle separately for idle anims, as they dont require accurate keyframe reinterpolation
					sleeptime = sleepperframe * keyframe_delta
					prevvalue = 0
					prevframe = frame_index - 1
					foundprev = False
					for previous in range(frame_index - 1, -1, -1):
						if bone_name in animframes[keyframe_times[previous]] and axis in \
								animframes[keyframe_times[previous]][bone_name]:
							prevvalue = animframes[keyframe_times[previous]][bone_name][axis]
							foundprev = True
							prevframe = previous
							break
					if not foundprev and frame_index > 0:
						logger.warning(f'Failed to find previous position for bone { bone_name} axis {axis} frame { keyframe_times[frame_index]}')
					else:
						pass
					# sleeptime = sleepperframe * (keyframe_times[i] - keyframe_times[prevframe])

					axis_index = int(axis[-1])
					# blender_to_bos_axis_multiplier = [-1.0, -1.0, 1.0]  # for turns
					if abs(value - prevvalue) < move_turn_miniumum_threshold and not force_all:
						logger.info("%i Ignored %s %s of %.6f delta" % (frame_time, bone_name, axis, value - prevvalue))
						continue
					else:
						if ISDEATH:
							if bone_name not in explodedpieces:
								if axis.startswith('location') and abs(value - prevvalue) > 100:

									def recurseexplodechildren(piece_name):
										BOS = '\t\t\texplode %s type FALL|SMOKE|FIRE|NOHEATCLOUD;\n\t\t\thide %s;\n' % (
											piece_name, piece_name)
										outf.write(BOS)
										explodedpieces.append(piece_name)
										for child in piecehierarchy[piece_name]:
											recurseexplodechildren(child)

									recurseexplodechildren(bone_name)
									continue
							else:  # this piece has already blown up, ignore it
								continue

						# bos_cmd = '\t\t\t%s %s to %s %s speed %s %s; //delta=%.2f '
						turn_or_move = 'turn'
						if axis.startswith('location'):  # Move
							turn_or_move = 'move'
						else:
							if axis not in ['rot0', 'rot1', 'rot2']:
								logger.warning(f'Found an axis name {axis} that is nonstandard for bos in piece {bone_name} at frame {frame_time}')
								continue
						stopwalking_cmd = '%s %s to %s' % (turn_or_move, bone_name, BOSAXIS[axis_index])

						if FIRSTFRAMESTANCE and frame_index == 0:
							firstframestance_positions[stopwalking_cmd] = value * \
																		  blender_to_bos_axis_multiplier[turn_or_move][
																			  axis_index]

						maxvelocity = abs(value - prevvalue) / sleeptime
						if stopwalking_cmd in stopwalking_maxspeed:
							if maxvelocity > stopwalking_maxspeed[stopwalking_cmd]:
								stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
						else:
							stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
						rotations_sum += abs(value - prevvalue)
						if bone_name[0:3] == 'PC_':
							logger.info(f'Skipping fake bone PC_ {bone_name}')
							continue
						speed_delta = abs(value - prevvalue)
						if force_all and speed_delta < 0.1:
							speed_delta = max(abs(value), 0.1)
						BOS = MakeBOSLineString(
							turn_or_move,
							bone_name,
							axis_index,
							value,
							speed_delta * fps if VARIABLESPEED else speed_delta / sleeptime,
							variablespeed=VARIABLESPEED,
							indents=3,
							delta=value - prevvalue
						)

						if rotations_sum > 130:
							gwarn = "WARNING: possible gimbal lock issue detected in frame %i bone %s" % (
								frame_time, bone_name)
							logger.warning(gwarn)
							BOS += '//' + gwarn + '\n'

						if not foundprev:
							BOS += '//' + "Failed to find previous position for bone" + bone_name + 'axis' + axis

						if frame_index > 0:
							outf.write(BOS + '\n')

			if frame_index > 0:
				if force_all:
					first_written_frame = False

				if VARIABLESPEED:
					outf.write('\t\tsleep ((33*animSpeed) -1);\n')
				else:
					outf.write('\t\tsleep %i;\n' % (33 * keyframe_delta - 1))

				if firststep:
					outf.write("\t}\n")
					outf.write("\twhile(isMoving) {\n")
					firststep = False
				else:
					outf.write('\t\t}\n')

		if ISWALK:
			outf.write('\t}\n')

		outf.write('}\n')

		if not ISDEATH:
			if ISWALK:
				outf.write(
					'// Call this from StopMoving()!\nStopWalking() {\n\tanimSpeed = 10; // tune restore speed here, higher values are slower restore speeds\n')
			else:
				outf.write('// Call this from StopMoving()!\nStopAnimation() {\n')
			for restore in sorted(stopwalking_maxspeed.keys()):
				if FIRSTFRAMESTANCE:
					stance_position = 0
					if restore in firstframestance_positions:
						stance_position = firstframestance_positions[restore]
					else:
						logger.warning("Stance key %s not found in %s" % (restore, firstframestance_positions))
					if restore.startswith('turn'):
						outf.write(
							'\t' + restore + ' <%.6f> speed <%.6f> / animSpeed;\n' % (
								stance_position, stopwalking_maxspeed[restore] * 10))
					if restore.startswith('move'):
						if VARIABLESCALE:
							outf.write(
								'\t' + restore + ' ([%.6f]*MOVESCALE)/100 speed (([%.6f]*MOVESCALE)/100) / animSpeed;\n' % (
									stance_position * MOVE_SCALE, stopwalking_maxspeed[restore] * 10 * MOVE_SCALE))
						else:
							outf.write(
								'\t' + restore + ' [%.6f] speed [%.6f] / animSpeed;\n' % (
									stance_position * MOVE_SCALE, stopwalking_maxspeed[restore] * 10 * MOVE_SCALE))
				else:
					if restore.startswith('turn'):
						outf.write(
							'\t' + restore + ' <0> speed <%.6f> / animSpeed;\n' % (stopwalking_maxspeed[restore] * 10))
					if restore.startswith('move'):
						if VARIABLESCALE:
							outf.write('\t' + restore + ' [0] speed [%.6f] / animSpeed;\n' % (
									stopwalking_maxspeed[restore] * 10 * MOVE_SCALE))
						else:
							outf.write('\t' + restore + ' [0] speed (([%.6f]*MOVESCALE)/100) / animSpeed;\n' % (
									stopwalking_maxspeed[restore] * 10 * MOVE_SCALE))

			outf.write('}\n')

		if ISWALK and VARIABLESPEED:
			outf.write('// REMEMBER TO animspeed = %i in Create() !!\n' % animFPK)
			outf.write('UnitSpeed(){\n')
			outf.write('\tmaxSpeed = get MAX_SPEED; // this returns cob units per frame i think\n')
			outf.write(
				'\tanimFramesPerKeyframe = %i; //we need to calc the frames per keyframe value, from the known animtime\n' % animFPK)
			outf.write('\tmaxSpeed = maxSpeed + (maxSpeed /(2*animFramesPerKeyframe)); // add fudge\n')
			outf.write('\twhile(TRUE){\n')
			outf.write('\t\tanimSpeed = (get CURRENT_SPEED);\n')
			outf.write('\t\tif (animSpeed<1) animSpeed=1;\n')
			outf.write('\t\tanimSpeed = (maxSpeed * %i) / animSpeed; \n' % animFPK)
			outf.write(
				'\t\t//get PRINT(maxSpeed, animFramesPerKeyframe, animSpeed); //how to print debug info from bos\n')
			outf.write('\t\tif (animSpeed<%i) animSpeed=%i;\n' % (int(animFPK / 2), int(animFPK / 2)))
			outf.write('\t\tif (animspeed>%i) animSpeed = %i;\n' % (animFPK * 2, animFPK * 2))
			outf.write('\t\tsleep %i;\n' % (33 * animFPK - 1))
			outf.write('\t}\n}\n')
			outf.write('StartMoving(){\n\tsignal SIGNAL_MOVE;\n\tisMoving=TRUE;\n\tstart-script Walk();\n}\n')
			outf.write('StopMoving(){\n\tsignal SIGNAL_MOVE;\n\tisMoving=FALSE;\n\tcall-script StopWalking();\n}\n')

		outf.close()
		logger.info(f'Done writing bos! ISWALK = {ISWALK} Varspeed = {VARIABLESPEED}')


class SkeletorLUSMaker(SkeletorBOSMaker):
	bl_idname = "sskele.createlus"
	bl_label = "Create LUS"
	bl_description = "Export selected Anim entries as [blend]_[action].lua"
	bl_options = {'REGISTER', 'UNDO'}
	export_suffix = ".lua"

	def write_file(self, context, animframes, piecehierarchy, piecenameprefix=""):
		fps = float(getattr(context.scene.render, "fps", 30) or 30)
		move_turn_miniumum_threshold = 0.0001  # skip only true no-ops; keep gait micro-offsets
		sleepperframe = 1.0 / fps
		# conversion time:
		# output a bos script
		# simplify mini rots and mini moves
		# the first frame can be ignored
		keyframe_times = sorted(animframes.keys())
		explodedpieces = []

		filepath = bpy.data.filepath
		logger.info(f'{filepath}')

		INFOSTRING = "For %s Created by https://github.com/Beherith/Skeletor_S3O V(%s)" % (filepath, bl_info['version'])

		flags = get_anim_flags(self, context)
		ISWALK = flags["ISWALK"]
		ISDEATH = flags["ISDEATH"]
		VARIABLESPEED = flags["VARIABLESPEED"]
		FIRSTFRAMESTANCE = flags["FIRSTFRAMESTANCE"]
		ALL_TRANSFORMS_FIRST = flags["ALL_TRANSFORMS_FIRST"]
		VARIABLESCALE = flags["VARIABLESCALE"]
		VARIABLEAMPLITUDE = flags["VARIABLEAMPLITUDE"]
		ASSIMP = flags["ASSIMP"]
		MOVE_SCALE = get_move_scale(context)

		move_variable = '%.6f'
		turn_variable = '%.6f'

		if VARIABLESCALE:
			move_variable = "((" + move_variable + " *MOVESCALE)/100)"

		if VARIABLEAMPLITUDE:
			move_variable = "((" + move_variable + " *animAmplitude)/100)"
			turn_variable = "((" + turn_variable + " *animAmplitude)/100)"

		LUSAXIS = ['x_axis', 'z_axis' if not ASSIMP else 'y_axis', 'y_axis' if not ASSIMP else 'z_axis']
		blender_to_bos_axis_multiplier = {'Move': [1.0, 1.0, 1.0], 'Turn': [-1.0, 1.0, 1.0]}

		def MakeBOSLineString(turn_or_move, bonename, axisindex, targetposition, speed, variablespeed=True, indents=3,
							  delta=0):
			axisname = LUSAXIS[axisindex]
			if turn_or_move == 'Move':
				targetposition = float(targetposition) * MOVE_SCALE
				speed = float(speed) * MOVE_SCALE
			targetposition = targetposition * blender_to_bos_axis_multiplier[turn_or_move][axisindex]
			cmdline = '' + '\t' * indents
			cmdline = cmdline + turn_or_move + '('
			cmdline = cmdline + bonename + ', '
			cmdline = cmdline + axisname + ', '
			if turn_or_move == 'Turn':
				cmdline = cmdline + turn_variable % radians(targetposition) + ', '
			else:
				cmdline = cmdline + move_variable % targetposition + ', '
			if turn_or_move == 'Turn':
				cmdline = cmdline + turn_variable % radians(speed) + ' '
			else:
				cmdline = cmdline + move_variable % speed + ' '
			if variablespeed:
				cmdline = cmdline + '* speedMult'
			cmdline = cmdline + ')'
			if delta != 0 and not OMITDELTAOUTPUT:
				cmdline = cmdline + '-- delta=%.2f'%delta
			return cmdline

		action_name = flags["ACTION"].name if flags["ACTION"] else "Action"
		newfile_name = build_export_filepath(action_name, getattr(self, "export_suffix", ".lua"))
		outf = open(newfile_name, 'w')
		# Header attribution line removed by request
		if VARIABLESCALE:
			outf.write("local MOVESCALE = 100 -- Higher values are bigger, 100 is default\n")
		if VARIABLEAMPLITUDE:
			outf.write("local animAmplitude = 100 -- Higher values are bigger, 100 is default\n")
		if ISWALK and VARIABLESPEED:
			outf.write("local ANIM_FRAMES = %i\n"  % (keyframe_times[1] - keyframe_times[0]))
			outf.write("local SIGNAL_MOVE = 1\n")
			outf.write("""
local walking = false -- prevent script.StartMoving from spamming threads if already walking

local function GetSpeedParams()
\tlocal attMod = (Spring.GetUnitRulesParam(unitID, "totalMoveSpeedChange") or 1)
\tif attMod <= 0 then
\t\treturn 0, 300
\tend
\tlocal sleepFrames = math.floor(ANIM_FRAMES / attMod + 0.5)
\tif sleepFrames < 1 then
\t\tsleepFrames = 1
\tend
\tlocal speedMod = 1 / sleepFrames
\treturn speedMod, 33*sleepFrames
end
""")
		elif ISWALK:
			outf.write("local walking")
		elif not ISDEATH:
			outf.write("local bAnimate\n")

		speedMult = [keyframe_times[i] - keyframe_times[i - 1] for i in range(2, len(keyframe_times))]
		animFPK = 4
		if len(speedMult) == 0:
			logger.warning("MEGA WARNING: NO DETECTABLE FRAMES!")
			return
		else:
			animFPK = float(sum(speedMult)) / (len(keyframe_times) - 2)
			if ISWALK and (animFPK - round(animFPK) > 0.00001):
				warn = "-- Animframes spacing is %f, THIS SHOULD BE AN INTEGER, SPACE YOUR KEYFRAMES EVENLY!\n" % animFPK
				outf.write(warn)
				logger.warning(warn)

		stopwalking_maxspeed = {}  # dict of of bos commands, with max velocity in it to define the stopwalking function
		firstframestance_positions = {}  # dict of bos commands, with the target of the piece as value
		if ISWALK:
			outf.write("""
local function Walk()
\tSignal(SIGNAL_MOVE)
\tSetSignalMask(SIGNAL_MOVE)
\tlocal speedMult, sleepTime = GetSpeedParams()
""")
		elif ISDEATH:
			# TODO for death animations:
			# turn values and speeds probably need to be converted to radians
			outf.write("""
-- use StartThread(DeathAnim) from Killed()
local function DeathAnim() -- %s
\tSignal(SIGNAL_MOVE)
\tSignal(SIGNAL_AIM1)
\tStartThread(StopWalking()
\tTurn(aimy1, y_axis, 0, %d)
\tTurn(aimx1, x_axis, 0, %d)
""" % (INFOSTRING, radians(120), radians(120)))
		# Not-walk scripts
		else:
			outf.write("-- Startthread(Animate) -- from RestoreAfterDelay\n")
			outf.write("""
local function Animate() -- %s
""" % INFOSTRING)
		# \tSetSignalMask(SIGNAL_MOVE + SIGNAL_AIM1) -- you might need this
		# \tSleep(100*math.rand(30,256)) -- sleep between 3 and 25.6 seconds

		firststep = True
		if not ISWALK:
			firststep = False

		arm_for_pose, _prefix = find_export_armature(context)
		first_written_frame = True

		for frame_index, frame_time in enumerate(keyframe_times):
			if frame_index == 0 and not FIRSTFRAMESTANCE:  # skip first piece
				continue

			thisframe = animframes[keyframe_times[frame_index]]
			prevframe = animframes[keyframe_times[frame_index - 1]]

			keyframe_delta = keyframe_times[frame_index] - keyframe_times[frame_index - 1]
			if keyframe_delta == 0:
				keyframe_delta = 1
			sleeptime = sleepperframe * keyframe_delta
			force_all = ALL_TRANSFORMS_FIRST and frame_index > 0 and first_written_frame
			if force_all:
				bpy.context.scene.frame_set(frame_time)
				full_pose = collect_full_piece_transforms(arm_for_pose)
				for bone_name, channels in full_pose.items():
					if bone_name not in thisframe:
						thisframe[bone_name] = {}
					thisframe[bone_name].update(channels)

			if frame_index > 0:
				if firststep:
					outf.write("\n\t-- Frame: %i (first step)\n" % frame_time)
				else:
					if ISWALK:
						outf.write("\t\t-- Frame:%i\n" % frame_time)
					elif ISDEATH:
						outf.write("\t\t-- Frame:%i\n" % frame_time)
					else:
						outf.write("\t-- Frame:%i\n" % frame_time)

			for bone_name in sorted(thisframe.keys()):
				bone_motions = thisframe[bone_name]
				rotations_sum = 0

				for axis, value in bone_motions.items():
					if not axis.startswith(('location', 'rot')):
						logger.warning("Warning: Keyframe for something other than location or rotation")
						continue
					# find previous value
					# TODO: fix missing keyframes for individual anims and interpolate from last known keyframe for curve!
					# handle separately for idle anims, as they dont require accurate keyframe reinterpolation
					sleeptime = sleepperframe * keyframe_delta
					prevvalue = 0
					prevframe = frame_index - 1
					foundprev = False
					for previous in range(frame_index - 1, -1, -1):
						if bone_name in animframes[keyframe_times[previous]] and axis in \
								animframes[keyframe_times[previous]][bone_name]:
							prevvalue = animframes[keyframe_times[previous]][bone_name][axis]
							foundprev = True
							prevframe = previous
							break
					if not foundprev and frame_index > 0:
						logger.warning("Warning: Failed to find previous position for bone", bone_name, 'axis', axis, 'frame',
							  keyframe_times[frame_index])
					else:
						pass
					# sleeptime = sleepperframe * (keyframe_times[i] - keyframe_times[prevframe])

					axis_index = int(axis[-1])	# last char, eg: rotation0 => 0
					# blender_to_bos_axis_multiplier = [-1.0, 1.0, 1.0]  # for turns
					if abs(value - prevvalue) < move_turn_miniumum_threshold and not force_all:
						logger.info("%i Ignored %s %s of %.6f delta" % (frame_time, bone_name, axis, value - prevvalue))
						continue
					else:
						if ISDEATH:
							if bone_name not in explodedpieces:
								if axis.startswith('location') and abs(value - prevvalue) > 100:

									def recurseexplodechildren(piece_name):
										BOS = '\t\t\texplode %s type FALL|SMOKE|FIRE|NOHEATCLOUD;\n\t\t\thide %s;\n' % (
											piece_name, piece_name)
										outf.write(BOS)
										explodedpieces.append(piece_name)
										for child in piecehierarchy[piece_name]:
											recurseexplodechildren(child)

									recurseexplodechildren(bone_name)
									continue
							else:  # this piece has already blown up, ignore it
								continue

						# bos_cmd = '\t\t\t%s %s to %s %s speed %s %s; -- delta=%.2f '
						turn_or_move = 'Turn'
						if axis.startswith('location'):  # Move
							turn_or_move = 'Move'
						stopwalking_cmd = '%s(%s, %s' % (turn_or_move, bone_name, LUSAXIS[axis_index])

						if FIRSTFRAMESTANCE and frame_index == 0:
							firstframestance_positions[stopwalking_cmd] = value * \
																		  blender_to_bos_axis_multiplier[turn_or_move][
																			  axis_index]

						maxvelocity = abs(value - prevvalue) / sleeptime
						if stopwalking_cmd in stopwalking_maxspeed:
							if maxvelocity > stopwalking_maxspeed[stopwalking_cmd]:
								stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
						else:
							stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
						rotations_sum += abs(value - prevvalue)

						# "MakeBOSLineString" is an override, don't refactor / rename it
						speed_delta = abs(value - prevvalue)
						if force_all and speed_delta < 0.1:
							speed_delta = max(abs(value), 0.1)
						LUS = MakeBOSLineString(
							turn_or_move,
							bone_name,
							axis_index,
							value,
							speed_delta * fps if VARIABLESPEED else max(maxvelocity, speed_delta / sleeptime),
							variablespeed=VARIABLESPEED,
							indents=2 if ISWALK and not firststep else 1,
							delta=value - prevvalue
						)

						if rotations_sum > 130:
							gwarn = "WARNING: possible gimbal lock issue detected in frame %i bone %s" % (
								frame_time, bone_name)
							logger.warning(gwarn)
							LUS += '-- ' + gwarn + '\n'

						if not foundprev:
							LUS += '-- ' + "Failed to find previous position for bone" + bone_name + 'axis' + axis

						if frame_index > 0:
							outf.write(LUS + '\n')

			if frame_index > 0:
				if force_all:
					first_written_frame = False

				if VARIABLESPEED:
					indent = '\t' if firststep else '\t\t'
					outf.write(indent + 'Sleep(sleepTime)\n')
				else:
					outf.write('\tSleep(%i)\n' % (33 * keyframe_delta - 1))

				if firststep:
					outf.write("\n\twhile true do\n")
					outf.write("\t\tspeedMult, sleepTime = GetSpeedParams()\n")
					firststep = False

		if ISWALK:
			outf.write('\tend\n')

		outf.write('end\n')

		if not ISDEATH:
			suffix = ' * speedMult)\n' if VARIABLESPEED else ')\n'
			if ISWALK:
				outf.write('\n')
				outf.write("""local function StopWalking()
\tSignal(SIGNAL_MOVE)
\tSetSignalMask(SIGNAL_MOVE)

""")
				if VARIABLESPEED:
					outf.write('\tlocal speedMult = 0.5 * GetSpeedParams() -- slower restore speed for last step\n\n')
			else:
				if VARIABLESPEED:
					outf.write('-- Call this from StopMoving()!\n')
				outf.write('local function StopAnimation()\n')
			for restore in sorted(stopwalking_maxspeed.keys()):
				if FIRSTFRAMESTANCE:
					stance_position = 0
					if restore in firstframestance_positions:
						stance_position = firstframestance_positions[restore]
					else:
						logger.warning("Stance key %s not found in %s" % (restore, firstframestance_positions))
					if restore.startswith('Turn'):
						outf.write(
							'\t' + restore + ', %.6f, %.6f' % (
								radians(stance_position), radians(stopwalking_maxspeed[restore] * 10)) + suffix)
					if restore.startswith('Move'):
						if VARIABLESCALE:
							outf.write(
								'\t' + restore + ', (%.6f * MOVESCALE) / 100, ((%.6f * MOVESCALE)/100)' % (
									stance_position * MOVE_SCALE, stopwalking_maxspeed[restore] * 10 * MOVE_SCALE)  + suffix)
						else:
							outf.write(
								'\t' + restore + ', %.6f, %.6f' % (
									stance_position * MOVE_SCALE, stopwalking_maxspeed[restore] * 10 * MOVE_SCALE)  + suffix)
				else:
					if restore.startswith('Turn'):
						outf.write(
							'\t' + restore + ', 0, %.6f' % (radians(stopwalking_maxspeed[restore]) * 10) + suffix)
					if restore.startswith('Move'):
						if VARIABLESCALE:
							outf.write('\t' + restore + ', 0, ((%.6f * MOVESCALE) / 100)' % (
									stopwalking_maxspeed[restore] * 10 * MOVE_SCALE) + suffix)
						else:
							outf.write('\t' + restore + ', 0, %.6f' % (
									stopwalking_maxspeed[restore] * 10 * MOVE_SCALE) + suffix)

			outf.write('end\n')

		if ISWALK and VARIABLESPEED:
			outf.write("""
function script.StartMoving()
\tif not walking then
\t\twalking = true
\t\tStartThread(Walk)
\tend
end
""")
			outf.write("""
function script.StopMoving()
\twalking = false
\tStartThread(StopWalking)
end
""")

		outf.close()
		logger.info(f'Done writing LUS! ISWALK = {ISWALK} Varspeed = {VARIABLESPEED}')


class SkeletorLUSTweenMaker(SkeletorBOSMaker):
	bl_idname = "sskele.createlustween"
	bl_label = "Create LUS Tween"
	bl_description = "Export selected Anim entries as [blend]_[action]_tween.lua"
	bl_options = {'REGISTER', 'UNDO'}
	export_suffix = "_tween.lua"

	def tobos(self, context):
		logger.info("MAKING LUS TWEEN, LIKE A BOSS!")
		# Lazy init (safe across Blender versions – no custom Operator.__init__)
		if not hasattr(self, "whichframe"):
			self.whichframe = 0
		scene = context.scene
		arma = None
		for obj in bpy.data.objects:
			if obj.type == 'ARMATURE':
				arma = obj
				break
		if arma is None:
			logger.error("ERROR: Armature not found! Quitting.")
			return
		# if 'Armature' not in context.scene.objects:
		# 	print("ERROR: Armature not found! Quitting.")
		# 	return
		# arma = context.scene.objects['Armature']
		if FullDebug:
			logger.debug(f'whichframe: {self.whichframe}')
		self.whichframe += 1
		props = {"location": "move", "rotation_euler": "turn"}
		bonesWithCurves = []
		bonesInIkChains = []
		pieceHierarchy = {}  # for each bone, list its children.
		# things I know:
		# curves contain the needed location data
		# pose bones matrices contain the needed rotation data
		# ignore all rots and pos's of iktargets
		# remove .L and .R monikers

		# required structure:
		# a dict of keyframes indexed by their frame number
		# animframes = {}  # {frame_number:{bone_name:{axis:value}}}
		# the values of which is another dict, of piece names
		# each piece name has a turn and a move op, with xzy coords

		# We use this for the tween exporter, which uses a different system (ie. not all new keys add all bones in motion)
		keysPerBone = {}  # {bone_name:[keyframe_idx:{keyframe_time, axisId, value, delta}]} || eg. keysPerBone[bone_name][keyframe_idx] = keyframeData

		# in each frame, each 'real piece' should have its position and location stored
		curves = get_action_fcurves(arma)
		if curves:
			if FullDebug:
				logger.debug(f'Animdata (compatible fcurves): {arma.animation_data}')
			for c in curves:
				keyframes = c.keyframe_points
				try:
					bone_name = c.data_path.split('"')[1]
				except IndexError:
					logger.warning(f'Unable to parse bone name from: {c} {c.data_path}')
					logger.warning("You probably have objects animated that are not parented to bones (i.e. not part of the model)")
					continue
				if bone_name.startswith('iktarget.'):
					continue
				if bone_name not in bonesWithCurves:
					bonesWithCurves.append(bone_name)
				if bone_name.endswith('.R') or bone_name.endswith('.L'):
					bone_name = bone_name[:-2]

				cTarget = c.data_path.rpartition('.')[2]
				# 'euler' in ctarget or 'quaternion' in ctarget or 'scale' in ctarget
				#if FullDebug:
				if 'euler' not in cTarget and 'location' not in cTarget:
					if FullDebug:
						logger.debug("Skipping: "+cTarget)
						continue
				else:
					if FullDebug:
						logger.debug("Keeping: "+cTarget)

				axis = str(c.array_index)

				# axisId = cTarget + axis. Eg: "rotation_euler0", for x rotation
				for i, k in enumerate(keyframes):
					frame_time = int(k.co[0])
					value = float(k.co[1])
					# if abs(value)<0.1:
					#    continue

					if bone_name not in keysPerBone:     #initialize bone entry if new
						keysPerBone[bone_name] = {}

					if frame_time not in keysPerBone[bone_name]:
						keysPerBone[bone_name][frame_time] = {}
					axisId = cTarget + axis
					keyframeData = { 'value': value }  # 'keyframe_time': frame_time,

					keysPerBone[bone_name][frame_time][axisId] = keyframeData.copy()

		logger.info("\n\n\n\n\n\n### Visibility keys\n")

		SKINNING = get_anim_flags(self, context)["SKINNING"]

		#### Goes through keysPerBone, get all bone.names and, from context.scene.objects[bone.name] get
		#### its meshFromBone.animation_data, search *only* for "hide_viewport" channels
		#### Assign that info to keysPerBone; <<== Not usable for Skinned animations! ==>
		if not SKINNING:
			for bone_name in keysPerBone:
				meshFromBone = context.scene.objects.get(bone_name)  # same name as the bone
				if meshFromBone is None:
					continue
				if meshFromBone.animation_data is None or meshFromBone.animation_data.action is None:
					logger.info("skipping (no visibility anim): "+meshFromBone.name)
					continue
				curves = get_action_fcurves(meshFromBone)
				# logger.info("Visibility Animdata: ", curves, meshFromBone.animation_data)
				for c in curves:
					keyframes = c.keyframe_points
					cTarget = c.data_path.rpartition('.')[2]
					if 'hide_viewport' not in cTarget:
						logger.info("Non-visibility channel being skipped: " + cTarget + " on mesh "+ meshFromBone.name)
						continue
					else:
						logger.info("Animated visibility found for mesh: " + meshFromBone.name)
					for i, k in enumerate(keyframes):
						frame_time = int(k.co[0])
						value = float(k.co[1])
						logger.info("\t\tframe: "+str(frame_time)+", value: "+str(value))
						if i > 0:
							previous_value = float(keyframes[i-1].co[1])
							if previous_value != value:
								logger.info("\t\t\tDelta value found at frame: "+str(frame_time)+" value: "+str(value))
								if frame_time not in keysPerBone[bone_name]:
									keysPerBone[bone_name][frame_time] = {}
								keysPerBone[bone_name][frame_time]["hide_viewport"] = { 'value': value }

		if FullDebug:
			logger.info("\n\n### Keys Per Bone (for the Tween Export)\n")
			logger.info(f'{keysPerBone}')
			logger.info("\n\nGathering piece hierarchy\n")

		def posebone_name_to_piece_name(poseBone_name):
			if 'iktarget' in bone.name:
				return None
			if poseBone_name.endswith('.R') or poseBone_name.endswith('.L'):
				poseBone_name = poseBone_name[:-2]
			return poseBone_name

		for bone in arma.pose.bones:
			pieceName = posebone_name_to_piece_name(bone.name)
			if pieceName is not None:
				if pieceName not in pieceHierarchy:
					pieceHierarchy[pieceName] = []
				if bone.parent:
					parentName = posebone_name_to_piece_name(bone.parent.name)
					if parentName is not None:
						if parentName not in pieceHierarchy:
							pieceHierarchy[parentName] = [pieceName]
						else:
							pieceHierarchy[parentName].append(pieceName)

		if FullDebug:
			logger.debug(f'\n\npiecehierarchy: {pieceHierarchy}\n')

		if FullDebug:
			logger.info("\n\nGathering IK chains\n")
			#
			for bone in arma.pose.bones:
				if 'iktarget' in bone.name:
					continue
				bone_name = bone.name
				if 'IK' in bone.constraints and bone.constraints['IK'].mute == False:
					chainLength = bone.constraints['IK'].chain_count
					if chainLength == 0:  # this means that everything up until the root is in the chain
						logger.info(f'{bone_name} has IK length {chainLength}')
						p = bone
						while p is not None:
							logger.info(f'In Chain: {p.name}')
							if p.name not in bonesInIkChains:
								bonesInIkChains.append(p.name)
							chainLength = chainLength - 1
							p = p.parent
					else:
						logger.info(f'{bone_name} has IK length {chainLength}')
						p = bone
						while chainLength > 0:
							logger.info(f'In Chain: {p.name}')
							if p.name not in bonesInIkChains:
								bonesInIkChains.append(p.name)
							chainLength = chainLength - 1
							p = p.parent

		if FullDebug:
			logger.debug("Gathering animdata")

		#for frame_time in sorted(animframes.keys()):
		for bone in arma.pose.bones:
			if 'iktarget' in bone.name:
				continue
			bone_name = bone.name
			if bone_name.endswith('.R') or bone_name.endswith('.L'):
				bone_name = bone_name[:-2]

			if bone_name not in keysPerBone:
				continue

			for frame_time in keysPerBone[bone_name]:    # sorted(keysPerBone[bone_name].keys()):
				if FullDebug:
					logger.debug("SETTING FRAMETIME", frame_time)
				bpy.context.scene.frame_set(frame_time)

				bone_matrix = bone.matrix.copy()

				MYEULER = 'YXZ'  # 'ZXY'
				current_bone = bone
				parent_bone_matrix = bone.matrix.copy()
				if current_bone.parent is not None:
					parent_bone_matrix = current_bone.parent.matrix.copy()
					parent_bone_matrix.invert()

					bone_matrix = parent_bone_matrix @ bone_matrix
					current_bone = current_bone.parent

				rot = bone_matrix.to_euler(MYEULER)  # , parent_bone_matrix.to_euler(MYEULER) )
				rotation_text = '%s X:%.1f Y:%.1f Z:%.1f' % (bone_name, degrees(rot.x), degrees(rot.y), degrees(rot.z))
				if FullDebug:
					logger.debug(rotation_text)

				# if frame_time not in keysPerBone[bone_name]:
				# 	keysPerBone[bone_name][frame_time] = {}

				# rot0, rot1 and rot3 will store the original values in angles (rotation_euler0/1/2 in radians)
				if bone_name not in bonesInIkChains:
					for axis in range(3):
						axisId = 'rot' + str(axis)
						value = degrees(arma.pose.bones[bone.name].rotation_euler[axis])
						keysPerBone[bone_name][frame_time][axisId] = { "value": value }
						# keysPerBone[bone_name][frame_time]['rot' + str(axis)] = degrees(
						# 	arma.pose.bones[bone.name].rotation_euler[axis])
				else:
					for axis, value in enumerate(rot[0:3]):
						axisId = 'rot' + str(axis)
						value = degrees(value)
						if FullDebug:
							logger.debug(f'adding{frame_time} {bone_name} rot {axis} {value}')
						keysPerBone[bone_name][frame_time][axisId] = { "value": value }
						# keysPerBone[bone_name][frame_time]['rot' + str(axis)] = degrees(value)

		logger.info("\n\n\nKeyframes Per Bone: ", keysPerBone)
		self.write_file(context=context, keysPerBone=keysPerBone, pieceHierarchy=pieceHierarchy, arma=arma)
		if FullDebug:
			logger.debug("Bones in IKchains: ", bonesInIkChains)
			logger.debug("Bones with curves: ", bonesWithCurves)

	def write_file(self, context, keysPerBone, pieceHierarchy, arma):
		fps = 30.0
		move_turn_minimum_threshold = 0.1  # moves/turns smaller than this will be straight up ignored
		sleepPerFrame = 1.0 / fps
		# conversion time:
		# output a bos script
		# simplify mini rots and mini moves
		# the first frame can be ignored

		# keyframe_times = sorted(keysPerBone.keys())
		explodedpieces = []

		filepath = bpy.data.filepath
		logger.info(f'{filepath}')

		INFOSTRING = "For %s Created by https://github.com/Beherith/Skeletor_S3O V(%s)" % (filepath, bl_info['version'])

		flags = get_anim_flags(self, context)
		ISWALK = flags["ISWALK"]
		ISDEATH = flags["ISDEATH"]
		ASSIMP = flags["ASSIMP"]
		VARIABLESPEED = flags["VARIABLESPEED"]
		FIRSTFRAMESTANCE = flags["FIRSTFRAMESTANCE"]
		VARIABLESCALE = flags["VARIABLESCALE"]
		VARIABLEAMPLITUDE = flags["VARIABLEAMPLITUDE"]
		SCENEFIRSTFRAME = context.scene.frame_start
		SCENELASTFRAME = context.scene.frame_end

		move_variable = '%.6f'
		turn_variable = '%.6f'
		floatFormat = '%.6f'

		if VARIABLESCALE:
			move_variable = "((" + move_variable + " *MOVESCALE)/100)"

		if VARIABLEAMPLITUDE:
			move_variable = "((" + move_variable + " *animAmplitude)/100)"
			turn_variable = "((" + turn_variable + " *animAmplitude)/100)"

		# LUSAXIS = ['x_axis', 'z_axis', 'y_axis']
		LUSAXIS = ['x_axis', 'z_axis' if not ASSIMP else 'y_axis', 'y_axis' if not ASSIMP else 'z_axis']
		blender_to_bos_axis_multiplier = {'move': [-1.0, 1.0, 1.0] if not ASSIMP else [1.0, 1.0, 1.0], 'turn': [-1.0, 1.0, 1.0] if not ASSIMP else [1.0, 1.0, 1.0]}

		def MakeLusTweenLineString(cmdID, boneName, axisIndex, targetValue, firstFrame, lastFrame, variableSpeed=True, indents=7,
		                           delta=0, luaIdx=0):
			cmdLine = '' + '\t' * indents
			if cmdID == "hide_viewport":
				if targetValue == 1:
					cmdLine = cmdLine + '[' + str(luaIdx) + ']={cmd="hide", '
				else:
					cmdLine = cmdLine + '[' + str(luaIdx) + ']={cmd="show", '
				cmdLine = cmdLine + "firstFrame=" + str(firstFrame) + ",},"
				return cmdLine
			axisName = LUSAXIS[axisIndex]
			targetValue = targetValue * blender_to_bos_axis_multiplier[cmdID][axisIndex]
			cmdLine = cmdLine + '[' + str(luaIdx) +']={cmd="' + cmdID + '", '
			cmdLine = cmdLine + 'axis=' + axisName + ', targetValue='
			cmdLine = cmdLine + floatFormat % targetValue + ', '
			# if turnOrMove == 'turn':
			# 	cmdLine = cmdLine + turn_variable % targetValue + ', '  # radians(targetValue)
			# else:
			# 	cmdLine = cmdLine + move_variable % targetValue + ', '

			cmdLine = cmdLine + "firstFrame="+str(firstFrame)+", "
			cmdLine = cmdLine + "lastFrame="+str(lastFrame)+","
			## TODO: variableSpeed; probably multiply start/endFrame by speedMult and round it to Int
			# if variableSpeed:
			# 	cmdLine = cmdLine + '* speedMult'
			cmdLine = cmdLine + '},'
			if delta != 0 and not OMITDELTAOUTPUT:
				cmdLine = cmdLine + ' -- delta=%.2f'%delta
			if cmdID == "turn" and abs(delta) > 3.1399:
				cmdLine = cmdLine + ' -- Possible unwanted rotation, keep deltas < 180 degrees (3.1399 rad)'
			return cmdLine

		def OutputPieceVariables(arma):
			tabs = '\t' * 5
			# arma = context.scene.objects['Armature']
			outputText = ''
			# for bone_name, keys_dic in bones.items():
			for bone in arma.pose.bones:
				bone_name = bone.name
				piece_name = bone_name
				if 'iktarget' in bone_name:
					continue
				if get_anim_flags(self, context)["SKINNING"]:	# SKINNING UI option is enabled
					piece_name = arma.name + "_" + piece_name  # Something like "Armature_root", for "root" bone
				outputText += "local "+bone_name+" = piece '"+piece_name+"'\n"
			outputText += '\nVFS.Include("scripts/include/springtweener.lua")\n\n'
			firstLine = True
			for bone in arma.pose.bones:
				bone_name = bone.name
				if 'iktarget' in bone_name:
					continue
				line: str = "local scriptEnv = { " if firstLine else tabs
				if firstLine:
					firstLine = False
				line = line + bone_name + " = " + bone_name + ",\n"
				outputText += line
			outputText += tabs + "rad = math.rad,\n" \
                    + tabs + "x_axis = x_axis,\n" \
                    + tabs + "y_axis = y_axis,\n" \
                    + tabs + "z_axis = z_axis,\n" \
                    + tabs + "Turn = Turn,\n" \
                    + tabs + "Move = Move,\n" \
                    + tabs + "Sleep = Sleep,\n" \
                    + tabs + "initTween = initTween,\n" \
					+ "}\n\n"
			return outputText

		action_name = flags["ACTION"].name if flags["ACTION"] else "Action"
		newfile_name = build_export_filepath(action_name, getattr(self, "export_suffix", "_tween.lua"))
		outFile = open(newfile_name, 'w')
		# Header attribution line removed by request
		if VARIABLESCALE:
			outFile.write("local MOVESCALE = 100 -- Higher values are bigger, 100 is default\n")
		if VARIABLEAMPLITUDE:
			outFile.write("local animAmplitude = 100 -- Higher values are bigger, 100 is default\n")
		# TODO
		# 		if ISWALK and VARIABLESPEED:
		# 			outFile.write("local ANIM_FRAMES = %i\n"  % (keyframe_times[1] - keyframe_times[0]))
		# 			outFile.write("local SIGNAL_MOVE = 1\n")
		# 			outFile.write("""
		# local walking = false -- prevent script.StartMoving from spamming threads if already walking
		#
		# local function GetSpeedParams()
		# \tlocal attMod = (Spring.GetUnitRulesParam(unitID, "totalMoveSpeedChange") or 1)
		# \tif attMod <= 0 then
		# \t\treturn 0, 300
		# \tend
		# \tlocal sleepFrames = math.floor(ANIM_FRAMES / attMod + 0.5)
		# \tif sleepFrames < 1 then
		# \t\tsleepFrames = 1
		# \tend
		# \tlocal speedMod = 1 / sleepFrames
		# \treturn speedMod, 33*sleepFrames
		# end
		# """)
		elif ISWALK:
			outFile.write("local walking")
		elif not ISDEATH:
			# outFile.write("local bAnimate\n")
			pass

		# TODO
		# speedMult = [keyframe_times[i] - keyframe_times[i - 1] for i in range(2, len(keyframe_times))]
		# animFPK = 4
		# if len(speedMult) == 0:
		# 	print("MEGA WARNING: NO DETECTABLE FRAMES!")
		# 	return
		# else:
		# 	animFPK = float(sum(speedMult)) / (len(keyframe_times) - 2)
		# 	if ISWALK and (animFPK - round(animFPK) > 0.00001):
		# 		warn = "-- Animframes spacing is %f, THIS SHOULD BE AN INTEGER, SPACE YOUR KEYFRAMES EVENLY!\n" % animFPK
		# 		outFile.write(warn)
		# 		print(warn)

		stopwalking_maxspeed = {}  # dict of commands, with max velocity in it to define the stopwalking function
		firstframestance_positions = {}  # dict of bos commands, with the target of the piece as value
		# 		if ISWALK:
		# 			outFile.write("""
		# local function Walk()
		# \tSignal(SIGNAL_MOVE)
		# \tSetSignalMask(SIGNAL_MOVE)
		# \tlocal speedMult, sleepTime = GetSpeedParams()
		# """)
		# 		elif ISDEATH:
		# 			# TODO for death animations:
		# 			# turn values and speeds probably need to be converted to radians
		# 			outFile.write("""
		# -- use StartThread(DeathAnim) from Killed()
		# local function DeathAnim() -- %s
		# \tSignal(SIGNAL_MOVE)
		# \tSignal(SIGNAL_AIM1)
		# \tStartThread(StopWalking()
		# \tTurn(aimy1, y_axis, 0, %d)
		# \tTurn(aimx1, x_axis, 0, %d)
		# """ % (INFOSTRING, radians(120), radians(120)))
		# 		# Not-walk scripts
		# 		else:
		# 			outFile.write("-- Startthread(Animate) -- from RestoreAfterDelay\n")
		# 			outFile.write("""
		# local function Animate() -- %s
		# """ % INFOSTRING)
		# 		# \tSetSignalMask(SIGNAL_MOVE + SIGNAL_AIM1) -- you might need this
		# 		# \tSleep(100*math.rand(30,256)) -- sleep between 3 and 25.6 seconds
		#
		# 		lastFrame = keyframe_times[-1]
		# 		outFile.write("\tlocal FEF = "+str(lastFrame)+"\n")
		#
		# 		firstStep = True
		# 		if not ISWALK:
		# 			firstStep = False

		# keysPerBone = {}   #  {bone_name:[keyframe_idx:{keyframeTime, axisId, value, delta}]} eg. keysPerBone[bone_name][keyframe_idx] = keyframeData

		markers = []		 #	Just a vector with frames
		markerNames = {}	 #	{ frame:name, ... }
		animNames = []		 #	Final list of animation names (since they won't always be marker-names)
		for m in context.scene.timeline_markers:
			markers.append(m.frame)
			markerNames[m.frame] = m.name
		markers.sort()

		if len(markers) == 0 or markers[-1] < SCENELASTFRAME:   # Minor hack so we always have at least one range
			markers.append(SCENELASTFRAME)                      # also to add the last scene frame as a marker
			markerNames[SCENELASTFRAME] = "anim"
		logger.info("\n\n\n\nMarkers' frames:\n")
		logger.info(f'{markers}')

		RANGESTARTFRAME = SCENEFIRSTFRAME
		RANGELASTFRAME = SCENELASTFRAME

		# Creates the piece variables, eg: local left_arm1 = piece 'left_arm1'
		outFile.write(OutputPieceVariables(arma))

		animID = 0		# anim1, anim2, etc

		outFile.write("-- #=#=# Animations: \n\n")
		for i in range(len(markers)):
			if markers[i] == SCENEFIRSTFRAME:			# Skips a marker coincident with the first scene frame
				continue
			RANGELASTFRAME = markers[i]
			if RANGELASTFRAME > SCENELASTFRAME:			# Must respect the final scene frame
				break
			if RANGELASTFRAME < SCENEFIRSTFRAME:		# Respect the first scene frame
				continue

			logger.info("\n\n\nMarker Range: " + str(RANGESTARTFRAME) + " to " + str(RANGELASTFRAME))
			markerName = "anim"+str(animID+1)			# Let's do anim1..n to match lua's indexing
			if markerNames[RANGELASTFRAME] is not None:
				markerName = markerNames[RANGELASTFRAME]
			animNames.append(markerName)
			outFile.write("local function "+markerName+"()\n")
			animID += 1

			#### ACTUAL TWEEN EXPORT
			outFile.write("\tinitTween({veryLastFrame="+str(RANGELASTFRAME - RANGESTARTFRAME)+",\n")
			for bone_name, keys_dic in keysPerBone.items():
				if len(keys_dic.items()) == 0:      # skip bones with no keyframes
					continue
				keys_dic = dict(sorted(keys_dic.items()))
				BONEHEADERLINE = "\t\t\t\t[" + bone_name + "]={\n"
				if FullDebug:
					logger.info(f'\n\nBone: { bone_name} \nKeys_dic:\n {keys_dic}')
				keys_list = list(keys_dic.items())  # Gets a list with the tuples of the dictionary
				keyframe_idx = -1   # this is for every keyframe
				luaIdx = 1          # this is for actually valid/exported keyframes
				for keyframe_time, keyframeData in keys_dic.items():
					keyframe_idx += 1   # Starts from idx=0
					if not (keyframe_time <= RANGELASTFRAME):          # Must respect the final scene frame
						break
					if keyframe_time < RANGESTARTFRAME:                # Respect the first scene frame
						continue
					# "hide_viewport" mesh key support; only one entry allowed per bone/frame
					if "hide_viewport" in keyframeData:
						value = keyframeData["hide_viewport"]["value"]
						BOS = MakeLusTweenLineString(
							'hide_viewport',
							bone_name,
							0,                                  # axisIndex; unused by hide_viewport
							value,
							keyframe_time - RANGESTARTFRAME,    # firstFrame, offset by the first frame in the scene
							keyframe_time,                      # unused by hide_viewport
							variableSpeed=VARIABLESPEED,
							indents=7,
							delta=0,
							luaIdx=luaIdx,
						)
						if luaIdx == 1:     #  Header line is only written before the 1st tween
							outFile.write(BONEHEADERLINE)
						outFile.write(BOS + '\n')
						luaIdx += 1
					if keyframe_idx >= len(keys_dic)-1:               # Only check tweens up to the previous to last key
						break  # continue

					for axisId, data in keyframeData.items():
						# axisId = keyframeData["axisId"]
						value = data["value"]
						delta = 0
						nextValue = value
						cmdID = 'turn' if 'rotation' in axisId else 'move'
						if 'quaternion' in axisId:
							continue
						if not 'location' in axisId and not 'rotation' in axisId:   # skipping "rot0/1/2" as well
							continue
						# Let's go through all next keys and try to find a match for this key type
						foundNextKey = False
						nextKeyframeTime = keyframe_time
						for nextIdx in range(keyframe_idx+1, len(keys_dic), 1):     # range's 2nd param is exclusive
							nextKeyframeData = keys_list[nextIdx][1]    # Gets the value of the next item ([0]=key)
							# # eg: {'rotation_euler0': {'value': 1.5467493534088135}, ... }
							if not axisId in nextKeyframeData.keys():
								continue
							nextKeyframeTime = keys_list[nextIdx][0]    # Gets the key of the next item (== keyframe_number)
							if nextKeyframeTime > RANGELASTFRAME:
								break
							nextValue = nextKeyframeData[axisId]["value"]
							delta = abs(nextValue - value)
							if FullDebug:
								logger.debug(f'AxisId:  {axisId} Frame: {keyframe_time} nextValue found: {nextValue}  delta: {delta}')
							if axisId.startswith('location'):  # Move
								cmdID = 'move'
							foundNextKey = True
							keysPerBone[bone_name][keyframe_time][axisId] = { "value": value, "nextValue": nextValue, "turn_or_move": cmdID, "delta": delta }
							break

						if not foundNextKey:     # and i > 0:
							if FullDebug:
								logger.debug(f'Warning: Failed to find next key value for bone: {bone_name} axis: {axisId} frame {keyframe_time}')
						else:
							if delta < 0.01:
								continue
							#tweenCount += 1
							if luaIdx == 1:     #  Header line is only written before the 1st tween
								outFile.write(BONEHEADERLINE)
							axisIndex = int(axisId[-1])
							BOS = MakeLusTweenLineString(
								cmdID,
								bone_name,
								axisIndex,    #last char in string, eg.: rotation_euler0 => 0
								nextValue,
								keyframe_time - RANGESTARTFRAME, # firstFrame, offset by the first frame in the scene
								(nextKeyframeTime - RANGESTARTFRAME) if (nextKeyframeTime <= RANGELASTFRAME) \
																	else (RANGELASTFRAME - RANGELASTFRAME), #lastFrame
								variableSpeed=VARIABLESPEED,
								indents=7,  # TODO: if ISWALK and not firstStep else 1,
								delta=delta,
								luaIdx=luaIdx,
							)
							luaIdx += 1

							if delta > 179.95 and cmdID == "turn":
								gWarning = "WARNING: possible gimbal lock issue detected in frame %i bone %s" % (
									keyframe_time, bone_name)
								logger.info(gWarning)
								BOS += '-- ' + gWarning + '\n'

							if not foundNextKey:
								BOS += '-- ' + "Failed to find next value for bone " + bone_name + ', axis ' + axisId

							# if frame_index > 0:
							outFile.write(BOS + '\n')
				if luaIdx > 1:      # Write bone's trailer line
					outFile.write('\t\t\t\t\t\t\t},\n')
			outFile.write('\t\t\t})\n')
			outFile.write("end\n")
			RANGESTARTFRAME = RANGELASTFRAME


		# for frame_index, frame_time in enumerate(keyframe_times):
		# 	if frame_index == 0 and not FIRSTFRAMESTANCE:  # skip first piece
		# 		continue
		# 	thisFrame = keysPerBone[keyframe_times[frame_index]]
		# 	for bone_name in sorted(thisFrame.keys()):
		# 		bone_motions = thisFrame[bone_name]
		# 		for axisId, value in bone_motions.items():
		# 			if not axisId.startswith(('location', 'rot')):
		# 				# print("Warning: Keyframe for something other than location or rotation")
		# 				continue
		# 			prevFrame = frame_index - 1
		# 			foundPrev = False
		# 			for previous in range(prevFrame, -1, -1):
		# 				previousAnimFrame = keysPerBone[keyframe_times[previous]]
		# 				previousBoneAnim = previousAnimFrame[bone_name]
		# 				if bone_name in previousAnimFrame and axisId in previousBoneAnim:
		# 					prevValue = previousBoneAnim[axisId]
		# 					delta = abs(prevValue - value)
		# 			if previous == 0 or delta > move_turn_minimum_threshold:
		# 				foundPrev = True
		# 				prevFrame = previous
		# 				break
		# 			# axis_index = int(axisId[-1])
		# 			if abs(value - prevValue) < move_turn_minimum_threshold:  # 0.1 by default
		# 				print("%i Ignored %s %s of %.6f delta" % (frame_time, bone_name, axisId, value - prevValue))
		# 				continue
		# 			turn_or_move = 'turn'
		# 			if axisId.startswith('location'):  # Move
		# 				turn_or_move = 'move'
		# 			keysPerBone[bone_name][frame_time][axis_index] = { value: value, turn_or_move: turn_or_move, delta:delta }  # nextKeyframeTime TODO
		# 			# TODO: Fix. Should be easy to know a bone's nextKeyframe time from this one

		# Goal: 			BOS = MakeLusTweenLineString(
		# 						turn_or_move,
		# 						bone_name,
		# 						axis_index,
		# 						value,
		# 						#abs(value - prevValue) * fps if VARIABLESPEED else maxVelocity,
		# 						frame_time, # firstFrame
		# 						lastFrame, #lastFrame
		# 						variableSpeed=VARIABLESPEED,
		# 						indents=2 if ISWALK and not firstStep else 1,
		# 						delta=value - prevValue
		# 					)

		# # ===================

		# for frame_index, frame_time in enumerate(keyframe_times):
		# 	# if frame_index == 0 and not FIRSTFRAMESTANCE:  # skip first piece
		# 	# 	continue
		#
		# 	thisFrame = keysPerBone[keyframe_times[frame_index]]
		# 	#prevFrame = animframes[keyframe_times[frame_index - 1]]
		# 	#next_keyframe_time = animframes[keyframe_times[frame_index + 1]] if frame_index + 1 < len(keyframe_times) else thisFrame
		#
		# 	keyframe_delta = keyframe_times[frame_index] - keyframe_times[frame_index - 1]
		# 	sleepTime = sleepPerFrame * keyframe_delta
		#
		# 	if frame_index > 0:
		# 		if firstStep:
		# 			outFile.write("\n\t-- Frame: %i (first step)\n" % frame_time)
		# 		else:
		# 			if ISWALK:
		# 				outFile.write("\t\t-- Frame: %i\n" % frame_time)
		# 			elif ISDEATH:
		# 				outFile.write("\t\t-- Frame: %i\n" % frame_time)
		# 			else:
		# 				outFile.write("\t-- Frame: %i\n" % frame_time)
		#
		# 	for bone_name in sorted(thisFrame.keys()):
		# 		bone_motions = thisFrame[bone_name]
		# 		rotations_sum = 0
		#
		# 		for axis, value in bone_motions.items():
		# 			if not axis.startswith(('location', 'rot')):
		# 				print("Warning: Keyframe for something other than location or rotation")
		# 				continue
		# 			# find previous value
		# 			# TODO: fix missing keyframes for individual anims and interpolate from last known keyframe for curve!
		# 			# handle separately for idle anims, as they dont require accurate keyframe reinterpolation
		# 			sleepTime = sleepPerFrame * keyframe_delta
		# 			prevValue = 0
		# 			prevFrame = frame_index - 1
		# 			foundPrev = False
		# 			nextValue = 0
		# 			nextKeyFrame = frame_index
		# 			foundNext = False
		# 			for previous in range(prevFrame, -1, -1):
		# 				previousAnimFrame = keysPerBone[keyframe_times[previous]]
		# 				previousBoneAnim = previousAnimFrame[bone_name]
		# 				if bone_name in previousAnimFrame and axis in previousBoneAnim:
		# 					prevValue = previousBoneAnim[axis]
		# 					delta = abs(prevValue - value)
		# 					if previous == 0 or delta > move_turn_minimum_threshold:
		# 						foundPrev = True
		# 						prevFrame = previous
		# 						break
		# 			if not foundPrev and frame_index > 0:
		# 				print("Warning: Failed to find previous position for bone", bone_name, 'axis', axis, 'frame',
		# 					  keyframe_times[frame_index])
		# 			else:
		# 				pass
		# 			# sleepTime = sleepPerFrame * (keyframe_times[i] - keyframe_times[prevframe])
		#
		# 			axis_index = int(axis[-1])
		# 			# blender_to_bos_axis_multiplier = [-1.0, -1.0, 1.0]  # for turns
		# 			if abs(value - prevValue) < move_turn_minimum_threshold:  # 0.1 by default
		# 				print("%i Ignored %s %s of %.6f delta" % (frame_time, bone_name, axis, value - prevValue))
		# 				continue
		#
		# 			if ISDEATH:
		# 				if bone_name not in explodedpieces:
		# 					if axis.startswith('location') and abs(value - prevValue) > 100:
		#
		# 						def recurseExplodeChildren(piece_name):
		# 							BOS = '\t\t\texplode %s type FALL|SMOKE|FIRE|NOHEATCLOUD;\n\t\t\thide %s;\n' % (
		# 								piece_name, piece_name)
		# 							outFile.write(BOS)
		# 							explodedpieces.append(piece_name)
		# 							for child in pieceHierarchy[piece_name]:
		# 								recurseExplodeChildren(child)
		#
		# 						recurseExplodeChildren(bone_name)
		# 						continue
		# 				else:  # this piece has already blown up, ignore it
		# 					continue
		#
		# 			# bos_cmd = '\t\t\t%s %s to %s %s speed %s %s; -- delta=%.2f '
		# 			turn_or_move = 'turn'
		# 			if axis.startswith('location'):  # Move
		# 				turn_or_move = 'move'
		# 			stopWalking_cmd = '%s(%s, %s' % (turn_or_move, bone_name, BOSAXIS[axis_index])
		#
		# 			if FIRSTFRAMESTANCE and frame_index == 0:
		# 				firstframestance_positions[stopWalking_cmd] = value * \
		# 															  blender_to_bos_axis_multiplier[turn_or_move][
		# 																  axis_index]
		#
		# 			maxVelocity = abs(value - prevValue) / sleepTime
		# 			if stopWalking_cmd in stopwalking_maxspeed:
		# 				if maxVelocity > stopwalking_maxspeed[stopWalking_cmd]:
		# 					stopwalking_maxspeed[stopWalking_cmd] = maxVelocity
		# 			else:
		# 				stopwalking_maxspeed[stopWalking_cmd] = maxVelocity
		# 			rotations_sum += abs(value - prevValue)
		#
		# 			BOS = MakeLusTweenLineString(
		# 				turn_or_move,
		# 				bone_name,
		# 				axis_index,
		# 				value,
		# 				#abs(value - prevValue) * fps if VARIABLESPEED else maxVelocity,
		# 				frame_time, # firstFrame
		# 				lastFrame, #lastFrame
		# 				variableSpeed=VARIABLESPEED,
		# 				indents=2 if ISWALK and not firstStep else 1,
		# 				delta=value - prevValue
		# 			)
		#
		# 			if rotations_sum > 130:
		# 				gWarning = "WARNING: possible gimbal lock issue detected in frame %i bone %s" % (
		# 					frame_time, bone_name)
		# 				print(gWarning)
		# 				BOS += '-- ' + gWarning + '\n'
		#
		# 			if not foundPrev:
		# 				BOS += '-- ' + "Failed to find previous position for bone" + bone_name + 'axis' + axis
		#
		# 			if frame_index > 0:
		# 				outFile.write(BOS + '\n')

			# TODO: Not sure if needed for tweens
			# if frame_index > 0:
			#
			# 	if VARIABLESPEED:
			# 		indent = '\t' if firstStep else '\t\t'
			# 		outFile.write(indent + 'Sleep(sleepTime)\n')
			# 	else:
			# 		outFile.write('\tSleep(%i)\n' % (33 * keyframe_delta - 1))
			#
			# 	if firstStep:
			# 		outFile.write("\n\twhile true do\n")
			# 		outFile.write("\t\tspeedMult, sleepTime = GetSpeedParams()\n")
			# 		firstStep = False

		# TODO / check:
		# if ISWALK:
		# 	outFile.write('\tend\n')

		animsLine = "\nlocal Animations = {"
		for i in range(len(animNames)):
			animName = animNames[i]
			animsLine = animsLine + animName + " = " + animName + ", "
		animsLine += "}\n\nreturn Animations\n"
		outFile.write(animsLine)

		# Animations = {openstd = openstd, closestd = closestd, morphup = morphup, openadv = openadv, closeadv = closeadv}
		# return Animations

		if not ISDEATH:
			suffix = ' * speedMult)\n' if VARIABLESPEED else ')\n'
			if ISWALK:
				outFile.write('\n')
				outFile.write("""local function StopWalking()
\tSignal(SIGNAL_MOVE)
\tSetSignalMask(SIGNAL_MOVE)

""")
				if VARIABLESPEED:
					outFile.write('\tlocal speedMult = 0.5 * GetSpeedParams() -- slower restore speed for last step\n\n')
			else:
				if VARIABLESPEED:
					outFile.write('-- Call this from StopMoving()!\n')
				# outFile.write('local function StopAnimation()\n')		# Temporarily disabled
			for restore in sorted(stopwalking_maxspeed.keys()):
				if FIRSTFRAMESTANCE:
					stance_position = 0
					if restore in firstframestance_positions:
						stance_position = firstframestance_positions[restore]
					else:
						logger.info("Stance key %s not found in %s" % (restore, firstframestance_positions))
					if restore.startswith('Turn'):
						outFile.write(
							'\t' + restore + ', %.6f, %.6f' % (
								radians(stance_position), radians(stopwalking_maxspeed[restore] * 10)) + suffix)
					if restore.startswith('Move'):
						if VARIABLESCALE:
							outFile.write(
								'\t' + restore + ', (%.6f * MOVESCALE) / 100, ((%.6f * MOVESCALE)/100)' % (
									stance_position, stopwalking_maxspeed[restore] * 10)  + suffix)
						else:
							outFile.write(
								'\t' + restore + ', %.6f, %.6f' % (
									stance_position, stopwalking_maxspeed[restore] * 10)  + suffix)
				else:
					if restore.startswith('Turn'):
						outFile.write(
							'\t' + restore + ', 0, %.6f' % (radians(stopwalking_maxspeed[restore]) * 10) + suffix)
					if restore.startswith('Move'):
						if VARIABLESCALE:
							outFile.write('\t' + restore + ', 0, ((%.6f * MOVESCALE) / 100)' % (
									stopwalking_maxspeed[restore] * 10) + suffix)
						else:
							outFile.write('\t' + restore + ', 0, %.6f' % (
									stopwalking_maxspeed[restore] * 10) + suffix)

			# outFile.write('end\n')

		if ISWALK and VARIABLESPEED:
			outFile.write("""
function script.StartMoving()
\tif not walking then
\t\twalking = true
\t\tStartThread(Walk)
\tend
end
""")
			outFile.write("""
function script.StopMoving()
\twalking = false
\tStartThread(StopWalking)
end
""")

		outFile.close()
		logger.info(f'Done writing LUS! ISWALK = {ISWALK} Varspeed = {VARIABLESPEED}')


def register():
	bpy.utils.register_class(SuperSkeleAnimItem)
	bpy.utils.register_class(MySettings)
	bpy.types.Scene.super_skeletor = PointerProperty(type=MySettings)
	bpy.utils.register_class(SSKELE_OT_anim_add)
	bpy.utils.register_class(SSKELE_OT_anim_remove)
	bpy.utils.register_class(SkeletorOperator)
	bpy.utils.register_class(SkeletorRotator)
	bpy.utils.register_class(SkeletorLUSMaker)
	bpy.utils.register_class(SkeletorLUSTweenMaker)
	bpy.utils.register_class(SkeletorBOSMaker)
	bpy.utils.register_class(Skelepanel)
	bpy.utils.register_class(SimpleBoneAnglesPanel)


def unregister():
	bpy.utils.unregister_class(Skelepanel)
	bpy.utils.unregister_class(SimpleBoneAnglesPanel)
	bpy.utils.unregister_class(SkeletorBOSMaker)
	bpy.utils.unregister_class(SkeletorLUSTweenMaker)
	bpy.utils.unregister_class(SkeletorLUSMaker)
	bpy.utils.unregister_class(SkeletorRotator)
	bpy.utils.unregister_class(SkeletorOperator)
	bpy.utils.unregister_class(SSKELE_OT_anim_remove)
	bpy.utils.unregister_class(SSKELE_OT_anim_add)
	del bpy.types.Scene.super_skeletor
	bpy.utils.unregister_class(MySettings)
	bpy.utils.unregister_class(SuperSkeleAnimItem)
	# To close the logger and remove all handlers
	for handler in logger.handlers[:]:  # Make a copy of the list to avoid modification during iteration
		logger.removeHandler(handler)


if __name__ == "__main__":
	register()
