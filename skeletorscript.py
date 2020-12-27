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
    "name": "Skeletor_S3O SpringRTS (.s3o)",
    "author": "Beherith  <mysterme@gmail.com>",
    "version": (0, 3, 6),
    "blender": (2, 80, 0),
    "location": "3D View > Side panel",
    "description": "Create a Skeleton and a BOS for a SpringRTS",
    "warning": "I have no idea what im doing",
    "wiki_url": "https://github.com/Beherith/Skeletor_S3O",
    "tracker_url": "http://springrts.com",
    "support": "COMMUNITY",
    "category": "Rigging",
}
import bpy
from math import pi, degrees, radians
from mathutils import Vector, Euler, Matrix
import os
import sys

from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       FloatVectorProperty,
                       EnumProperty,
                       PointerProperty,
                       )
from bpy.types import (Panel,
                       Operator,
                       AddonPreferences,
                       PropertyGroup,
                       )


class MySettings(PropertyGroup):
    is_walk: BoolProperty(
        name="Is Walk Script",
        description="Whether the animation loops",
        default=True
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
    iktargetends: BoolProperty(
        name="Where to place IK targets",
        description="Whether IK targets should be at the leafs of anim chains or one branch above",
        default=True
    )
    firstframestance: BoolProperty(
        name="First Keyframe Stance",
        description="The first keyframe contains an idle stance (non zero) that the unit returns to when not walking",
        default=True
    )
    is_death: BoolProperty(
        name="Is Death Script",
        description="Unit dies, move pieces far to explode them",
        default=False
    )


class Skelepanel(bpy.types.Panel):
    bl_label = "Skeletor S30"
    bl_idname = "PT_Skelepanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SkeletorS30"
    
    def draw(self, context):
        layout = self.layout
        
        scene = context.scene
        mytool = scene.my_tool
        
        # row = layout.row()
        # row.operator("skele.skeletorrotator", text='1. Correctly rotate S3O')
        
        layout.prop(mytool, "iktargetends", text="IK targets at leafs")
        row = layout.row()
        row.operator('skele.skeletoroperator', text='1. Create Skeleton')
        layout.prop(mytool, "is_walk", text="Is Walk Script")
        layout.prop(mytool, "varspeed", text="Variable speed")
        layout.prop(mytool, "varscale", text="Variable scale")
        layout.prop(mytool, "varamplitude", text="Variable amplitude")
        layout.prop(mytool, "firstframestance", text="First Frame Stance")
        layout.prop(mytool, "is_death", text="Is Death Script")
        row = layout.row()
        row.operator('skele.skeletorbosmaker', text='2. Create BOS')
        row = layout.row()
        row.operator('skele.skeletorlusmaker', text='2b. Create LUS')


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
                        print(self.name, self.worldpos)
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
        return (minx, maxx, miny, maxy, minz, maxz)


def getmeshbyname(name):
    for mesh in bpy.data.meshes:
        if mesh.name == name:
            return mesh
    return None


def getS3ORootObject():
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    rootobject = None
    rootname = ""
    for object in bpy.data.objects:
        if object.parent is None:
            for child in bpy.data.objects:
                if child.parent and child.parent == object:
                    print("We have a root!", object)
                    rootobject = object
                    rootname = object.name
                    return rootobject, rootname
                    break


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
    bl_idname = "skele.skeletorrotator"
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
            obj.rotation_mode = 'ZXY'
        bpy.ops.object.select_all(action='DESELECT')
        
        rootobject, rootname = getS3ORootObject()
        bpy.ops.object.select_all(action='DESELECT')
        rootobject.select_set(True)
        
        # bpy.ops.transform.rotate(value=-pi/2, orient_axis='Z', orient_type='VIEW', orient_matrix=((0, -1, 0), (0, 0, -1), (-1, 0, 0)), orient_matrix_type='VIEW', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False)
        bpy.context.object.rotation_euler[0] = pi / 2
        
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        
        # return
        bpy.ops.object.select_all(action='DESELECT')
        rootobject.select_set(True)
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
        
        rootobject.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        
        bpy.ops.object.select_all(action='DESELECT')


class SkeletorOperator(bpy.types.Operator):
    bl_idname = "skele.skeletoroperator"
    bl_label = "skeletize"
    bl_description = "Create a skeleton"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        self.skeletize(context=context)
        return {'FINISHED'}
    
    @staticmethod
    def skeletize(context):
        print("skeletizing, very happy")
        NOTAIL = True
        IKTARGETENDS = context.scene.my_tool.iktargetends
        
        # debug delete all armatures and bones!
        # bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        for object in bpy.context.scene.objects:
            if object.name == "Armature":
                print(object)
                bpy.data.objects['Armature'].select_set(True)
                bpy.ops.object.delete({"selected_objects": [object]})
        
        pieces = {}  # {"name":s3opiece}
        # collect the data we need:
        # object of each piece
        # root object
        # the offsets of each object
        # the children of each object
        # the amount of geometry each object has.
        
        # find the object with no parents, but has children (root)
        rootobject, rootname = getS3ORootObject()
        
        # got the root!
        rootpiece = S3opiece(rootobject.name, rootobject, getmeshbyname(rootobject.name), rootobject.location[0],
                             rootobject.location[1], rootobject.location[2])
        
        print(rootpiece)
        
        print("====Collecting Pieces====")
        pieces[rootname] = rootpiece
        for object in bpy.data.objects:
            if object.parent is not None:
                newpiece = S3opiece(object.name, object, getmeshbyname(object.name), object.location[0],
                                    object.location[1], object.location[2])
                print(newpiece)
                
                pieces[newpiece.name] = newpiece
        for piece in pieces.values():
            print(piece)
            print(piece.object)
            if piece.object.parent is not None:
                piece.parent = pieces[piece.object.parent.name]
                piece.parent.children.append(piece)
                print(piece.name, '->', piece.parent.name)
        
        rootpiece.recursefixworldpos(Vector((0, 0, 0)))
        
        opennodes = set()  # Set to keep track of visited nodes.
        opennodes.add(rootpiece)
        dfs_piece_order = [rootpiece.name]
        
        while (len(opennodes) > 0):
            nodelist = list(opennodes)
            for node in nodelist:
                dfs_piece_order.append(node.name)
                print('nodename', node.name)
                opennodes.remove(node)
                for child in node.children:
                    opennodes.add(child)
        print(dfs_piece_order)
        
        print("====Reparenting pieces to avoid AimX and AimY====")
        # if the parent of an object is called aimx* or aimy*, then reparent the piece to the parent of aimx or aimy actual parent
        for piece in pieces.values():
            if piece.object.parent is not None and piece.object.parent.name[0:4].lower() in ['aimx', 'aimy']:
                print("Reparenting ", piece.name, "from", piece.parent.name, 'to', piece.parent.parent.name)
                piece.parent.isAimXY = True
                try:
                    piece.parent.children.remove(piece)
                    piece.parent = pieces[piece.object.parent.parent.name]
                    piece.parent.children.append(piece)
                
                except:
                    print("piece", piece)
                    print("parent", piece.parent)
                    print("GP", piece.parent.parent)
                    raise
        
        # final check that we have all set:
        print("----------Sanity check:-----------")
        for k, v in pieces.items():
            print(k, v)
        
        # set the cursor to origin:
        bpy.ops.transform.translate(value=(0, 0, 0), orient_type='GLOBAL',
                                    orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL',
                                    mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH',
                                    proportional_size=1, use_proportional_connected=False,
                                    use_proportional_projected=False, cursor_transform=True, release_confirm=True)
        
        print("====Setting rotation modes to Euler YXZ====")
        scene = context.scene
        for obj in scene.objects:
            obj.select_set(False)
            obj.rotation_mode = 'YXZ'  # was: 'ZXY', but that is prolly wrong
        
        # add an armature!
        print("====Creating Armature====")
        arm_data = bpy.data.armatures.new("Armature")
        
        armature_object = bpy.data.objects.new("Armature", arm_data)
        armature_object.location = Vector((0, 0, 0))  # rootpiece.loc
        armature_object.show_in_front = True
        armature_object.data.show_axes = True
        armature_object.data.show_names = True
        
        armature_object.rotation_mode = 'YXZ'  # was: 'ZXY', but that is prolly wrong
        
        context.collection.objects.link(armature_object)
        
        armature_object.select_set(True)
        
        context.view_layer.objects.active = armature_object
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        print("====Looking for mirrorable pieces===")
        # to enable : https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle
        # rootpiece.recurseleftrightbones()
        for name, piece in pieces.items():
            piece.bonename = name
            for name2, piece2 in pieces.items():
                if name == name2:
                    continue
                if name.lower().replace('l', '').replace('r', '') == name2.lower().replace('l', '').replace('r', ''):
                    if piece.worldpos[0] > 0:
                        piece.bonename = piece.bonename + '.R'
                    else:
                        piece.bonename = piece.bonename + '.L'
        
        print("====Adding Bones=====")
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
            if NOTAIL:
                newbone.tail = newbone.head + Vector((0, 5, 0))
            
            tailpos = piece.loc + Vector((0, 0, 10))
            if len(piece.children) >= 1:
                tailpos = Vector((0, 0, 0))
                for child in piece.children:
                    tailpos = tailpos + child.worldpos
                tailpos = tailpos / len(piece.children)
                newbone.tail = tailpos
                if NOTAIL:
                    newbone.tail = newbone.head + Vector((0, 5, 0))  # TODO fixeme
                # TODO: Something is an arm if it has only nomesh children
                # thus we add a forward pointing IK target to its tailpos
                onlyemptychildren = True
                for child in piece.children:
                    if child.mesh is not None:
                        onlyemptychildren = False
                if onlyemptychildren:
                    print("LOOKS LIKE AN ARM:", piece.name)
                    ikbone = arm_data.edit_bones.new('iktarget.' + piece.bonename)
                    ikbone.head = newbone.tail
                    ikbone.tail = newbone.tail + Vector((0, 5, 0))
                    piece.iktarget = ikbone
            
            else:  # end piece
                # TODO: CHECK FOR GEOMETRY, is it a foot or an arm or a tentacle ?
                # TODO: multiple branches for multiple toes give too many IK targets :/
                if piece.mesh is not None and piece.parent.iktarget is None:
                    boundingbox = piece.getmeshboundingbox()
                    
                    print("LOOKS LIKE A FOOT:", piece.name, piece.worldpos, boundingbox)
                    if piece.worldpos[2] + boundingbox[4] <= 2.0:
                        # this looks like a foot
                        tailpos = piece.worldpos + Vector((0, boundingbox[3], boundingbox[4]))
                        # better add the heel IK thing too XD
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
                        if (boundingbox[5] > boundingbox[3] and boundingbox[5] > -1 * boundingbox[2]):  # points forward
                            tailpos = piece.worldpos + Vector((0, boundingbox[5], 0))
                        else:
                            if (boundingbox[3] > -1 * boundingbox[2]):
                                tailpos = piece.worldpos + Vector((0, 0, boundingbox[3]))  # up
                            else:
                                tailpos = piece.worldpos + Vector((0, 0, boundingbox[2]))  # down
                
                # TODO we are also kind of a foot if we only have children with no meshes.
                else:
                    tailpos = piece.worldpos + Vector((0, 5, 0))
            newbone.tail = tailpos
            # TODO: easier rotations like this?
            if NOTAIL:
                newbone.tail = newbone.head + Vector((0, 5, 0))
            
            print("trying to add bone to %s\nat head:%s \ntail:%s" % (piece, newbone.head, newbone.tail))
            piece.bone = newbone
        # return
        print("=====Reparenting Bone-Bones=======")
        
        for name, piece in pieces.items():
            
            if piece.parent is not None and not piece.isAimXY:
                piece.bone.parent = piece.parent.bone
        
        bpy.ops.object.editmode_toggle()  # i have no idea what im doing
        bpy.ops.object.posemode_toggle()
        
        print("=====Setting IK Targets=======")
        
        for name, piece in pieces.items():
            if not piece.isAimXY:
                armature_object.pose.bones[piece.bonename].rotation_mode = 'YXZ'  # was: 'ZXY', but that is prolly wrong
            
            if piece.iktarget is not None:
                chainlength = 1
                chainpos = piece.parent
                while (len(chainpos.children) == 1 and chainpos.parent is not None):
                    chainlength += 1
                    chainpos = chainpos.parent
                print('Adding iktarget to ', piece.name, 'chain_length = ', chainlength)
                constraint = armature_object.pose.bones[piece.bonename].constraints.new('IK')
                constraint.target = armature_object
                constraint.subtarget = 'iktarget.' + piece.bonename
                constraint.chain_count = chainlength
                armature_object.pose.bones[piece.bonename].ik_stiffness_z = 0.99  # avoids having to create knee poles
        
        print("=====Parenting meshes to bones=======")
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
        
        print("done")


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
            
            if 'iktarget' in bone.name:
                continue
            
            bone_name = bone.name
            MYEULER = 'YXZ'  # 'ZXY' #BECAUSE FUCK ME THATS WHY
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
            # We can also fiogure out, from the IK constraints and the chain lengths, which bones have IK on them
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


class SkeletorBOSMaker(bpy.types.Operator):
    bl_idname = "skele.skeletorbosmaker"
    bl_label = "skeletor_bosmaker"
    bl_description = "Writes *_bos_export.txt next to .blend file"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        self.tobos(context=context)
        return {'FINISHED'}
    
    def __init__(self):
        super().__init__()
        print("SkeletorBOSMaker.init")
        self.whichframe = 0
    
    # @staticmethod
    def tobos(self, context):
        print("MAKING BOS, BOSS")
        scene = context.scene
        if 'Armature' not in context.scene.objects:
            return
        arm = context.scene.objects['Armature']
        print("whichframe", self.whichframe)
        self.whichframe += 1
        props = {"location": "move", "rotation_euler": "turn"}
        boneswithcurves = []
        bonesinIKchains = []
        explodedpieces = []
        piecehierarchy = {}  # for each bone, list its children.
        ISWALK = context.scene.my_tool.is_walk
        ISDEATH = context.scene.my_tool.is_death
        VARIABLESPEED = context.scene.my_tool.varspeed
        FIRSTFRAMESTANCE = context.scene.my_tool.firstframestance
        VARIABLESCALE = context.scene.my_tool.varscale
        VARIABLEAMPLITUDE = context.scene.my_tool.varamplitude
        
        move_variable = '%.6f'
        turn_variable = '%.6f'
        
        if VARIABLESCALE:
            move_variable = "((" + move_variable + " *MOVESCALE) / 100)"
        
        if VARIABLEAMPLITUDE:
            move_variable = "((" + move_variable + " * animAmplitude) / 100)"
            turn_variable = "((" + turn_variable + " * animAmplitude) / 100)"
        # things I know:
        # curves contain the needed location data
        # pose bones matrices contain the needed rotation data
        # ignore all rots and pos's of iktargets
        # remove .L and .R monikers
        
        # required structure:
        # a dict of keyframes indexed by their frame number
        animframes = {}  # {frame_number:{bone_name:{axis:value}}}
        # the values of which is another dict, of piece names
        # each piece name has a turn and a move op, with xzy coords
        
        # in each frame, each 'real piece' should have its position and location stored
        if arm.animation_data is not None:
            if arm.animation_data.action is not None:
                curves = arm.animation_data.action.fcurves
                print("Animdata:", curves, arm.animation_data)
                for c in curves:
                    keyframes = c.keyframe_points
                    try:
                        bone_name = c.data_path.split('"')[1]
                    except IndexError:
                        print("Unable to parse bone name from:", c, c.data_path)
                        print(
                            "You probably have objects animated that are not parented to bones (i.e. not part of the model)")
                        continue
                    if bone_name.startswith('iktarget.'):
                        continue
                    if bone_name not in boneswithcurves:
                        boneswithcurves.append(bone_name)
                    
                    if bone_name.endswith('.R') or bone_name.endswith('.L'):
                        bone_name = bone_name[:-2]
                    
                    ctarget = c.data_path.rpartition('.')[2]
                    if (
                            'euler' in ctarget or 'quaternion' in ctarget or 'scale' in ctarget) and 'location' not in ctarget:
                        continue
                    
                    axis = str(c.array_index)
                    
                    for i, k in enumerate(keyframes):
                        
                        frame_time = int(k.co[0])
                        value = float(k.co[1])
                        # if abs(value)<0.1:
                        #    continue
                        
                        if frame_time not in animframes:
                            animframes[frame_time] = {}
                        if bone_name not in animframes[frame_time]:
                            animframes[frame_time][bone_name] = {}
                        
                        animframes[frame_time][bone_name][ctarget + axis] = value
        
        print(animframes)
        
        print("Gathering piece hierarchy")
        
        def posebone_name_to_piece_name(posebone_name):
            if 'iktarget' in bone.name:
                return None
            if posebone_name.endswith('.R') or posebone_name.endswith('.L'):
                posebone_name = posebone_name[:-2]
            return posebone_name
        
        for bone in arm.pose.bones:
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
        print('piecehierarchy', piecehierarchy)
        
        print("Gathering IK chains")
        
        for bone in arm.pose.bones:
            if 'iktarget' in bone.name:
                continue
            bone_name = bone.name
            if 'IK' in bone.constraints and bone.constraints['IK'].mute == False:
                chainlength = bone.constraints['IK'].chain_count
                if chainlength == 0:  # this means that everything up until the root is in the chain
                    print(bone.name, 'has ik length', chainlength)
                    p = bone
                    while p is not None:
                        print("inchain", p.name)
                        if p.name not in bonesinIKchains:
                            bonesinIKchains.append(p.name)
                        chainlength = chainlength - 1
                        p = p.parent
                
                else:
                    print(bone.name, 'has ik length', chainlength)
                    p = bone
                    while chainlength > 0:
                        print("inchain", p.name)
                        if p.name not in bonesinIKchains:
                            bonesinIKchains.append(p.name)
                        chainlength = chainlength - 1
                        p = p.parent
        
        print("Gathering animdata")
        
        for frame_time in sorted(animframes.keys()):
            print("SETTING FRAMETIME", frame_time)
            bpy.context.scene.frame_set(frame_time)
            for bone in arm.pose.bones:
                if 'iktarget' in bone.name:
                    continue
                bone_name = bone.name
                
                if bone_name.endswith('.R') or bone_name.endswith('.L'):
                    bone_name = bone_name[:-2]
                bone_matrix = bone.matrix.copy()
                
                MYEULER = 'YXZ'  # 'ZXY' #LORD HAVE MERCY
                current_bone = bone
                parent_bone_matrix = bone.matrix.copy()
                if current_bone.parent is not None:
                    parent_bone_matrix = current_bone.parent.matrix.copy()
                    parent_bone_matrix.invert()
                    
                    # bone_matrix = bone_matrix @ parent_bone_matrix # OH BOY IS THIS WRONG!
                    bone_matrix = parent_bone_matrix @ bone_matrix
                    current_bone = current_bone.parent
                
                # rot = bone_matrix.to_euler(MYEULER, parent_bone_matrix.to_euler(MYEULER) )
                rot = bone_matrix.to_euler(MYEULER)  # , parent_bone_matrix.to_euler(MYEULER) )
                rotation_text = '%s X:%.1f Y:%.1f Z:%.1f' % (bone_name, degrees(rot.x), degrees(rot.y), degrees(rot.z))
                print(rotation_text)
                
                if bone.name not in bonesinIKchains:
                    for axis in range(3):
                        if frame_time not in animframes:
                            animframes[frame_time] = {}
                        if bone_name not in animframes[frame_time]:
                            animframes[frame_time][bone_name] = {}
                        animframes[frame_time][bone_name]['rot' + str(axis)] = degrees(
                            arm.pose.bones[bone.name].rotation_euler[axis])
                
                else:
                    for axis, value in enumerate(rot[0:3]):
                        if frame_time not in animframes:
                            animframes[frame_time] = {}
                        if bone_name not in animframes[frame_time]:
                            animframes[frame_time][bone_name] = {}
                        print('adding', frame_time, bone_name, 'rot' + str(axis), value)
                        animframes[frame_time][bone_name]['rot' + str(axis)] = degrees(value)
        
        print("Animframes:", animframes)
        fps = 30.0
        move_turn_miniumum_threshold = 0.1  # moves/turns smaller than this will be straight up ignored
        sleepperframe = 1.0 / fps
        # conversion time:
        # output a bos script
        # simplify mini rots and mini moves
        # the first frame can be ignored
        keyframe_times = sorted(animframes.keys())
        
        filepath = bpy.data.filepath
        print(filepath)
        
        INFOSTRING = "For %s Created by https://github.com/Beherith/Skeletor_S3O V(%s)" % (filepath, bl_info['version'])
        
        AXES = 'XZY'
        BOSAXIS = ['x_axis', 'z_axis', 'y_axis']
        blender_to_bos_axis_multiplier = {'Move': [1.0, 1.0, 1.0], 'Turn': [-1.0, -1.0, 1.0]}
        
        def MakeBOSLineString(turn_or_move, bonename, axisindex, targetposition, speed, variablespeed=True, indents=3,
                              delta=0):
            axisname = BOSAXIS[axisindex]
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
                cmdline = cmdline + '/ animSpeed'
            cmdline = cmdline + ') '
            if delta != 0:
                cmdline = cmdline + '-- delta=%.2f'%delta
            return cmdline
        
        newfile_name = filepath + ".lua_export.lua"
        outf = open(newfile_name, 'w')
        outf.write("-- " + INFOSTRING + '\n')
        if VARIABLESCALE:
            outf.write("local MOVESCALE = 100 -- Higher values are bigger, 100 is default\n")
        if VARIABLEAMPLITUDE:
            outf.write("local animAmplitude = 100 -- Higher values are bigger, 100 is default\n")
        if ISWALK and VARIABLESPEED:
            outf.write(
                "-- this animation uses the var animFramesPerKeyframe which contains how many frames each keyframe takes\n")
            outf.write("local animSpeed, maxSpeed, animFramesPerKeyframe, walking\nlocal SIG_WALK = 4\n")
        elif ISWALK:
            outf.write("local walking")
        elif not ISDEATH:
            outf.write("local bAnimate\n")
        
        animSpeed = [keyframe_times[i] - keyframe_times[i - 1] for i in range(2, len(keyframe_times))]
        animFPK = 4
        if len(animSpeed) == 0:
            print("MEGA WARNING: NO DETECTABLE FRAMES!")
            return
        else:
            animFPK = float(sum(animSpeed)) / (len(keyframe_times) - 2)
            if ISWALK and (animFPK - round(animFPK) > 0.00001):
                warn = "-- Animframes spacing is %f, THIS SHOULD BE AN INTEGER, SPACE YOUR KEYFRAMES EVENLY!\n" % animFPK
                outf.write(warn)
                print(warn)
        
        stopwalking_maxspeed = {}  # dict of of bos commands, with max velocity in it to define the stopwalking function
        firstframestance_positions = {}  # dict of bos commands, with the target of the piece as value
        if ISWALK:
            outf.write("local function Walk()-- %s \n\tSignal(SIG_WALK)\n\tSetSignalMask(SIG_WALK)\n" % (INFOSTRING))
        elif ISDEATH:
            # TODO for death animations:
            # turn values and speeds probably need to be converted to radians
            outf.write(
                "-- use call-script DeathAnim(); from Killed()\nDeathAnim() {--  %s \n\tsignal SIG_WALK;\n\tsignal SIG_AIM;\n\tcall-script StopWalking();\n\tturn aimy1 to y-axis <0> speed <120>;\n\tturn aimx1 to x-axis <0> speed <120>;\n" % (
                    INFOSTRING))
        else:
            outf.write("-- start-script Animate(); -- from RestoreAfterDelay\n")
            # TODO not walk scripts
            outf.write(
                "Animate() -- %s \n\tset-signal-mask SIG_WALK | SIG_AIM; -- you might need this\n\tSleep(100*RAND(30,256)) -- sleep between 3 and 25.6 seconds\n\tbAnimate = TRUE;\n" % (
                    INFOSTRING))
        
        firststep = True
        if not ISWALK:
            firststep = False
        
        for frame_index, frame_time in enumerate(keyframe_times):
            if frame_index == 0 and not FIRSTFRAMESTANCE:  # skip first piece
                continue
            
            thisframe = animframes[keyframe_times[frame_index]]
            prevframe = animframes[keyframe_times[frame_index - 1]]
            
            keyframe_delta = keyframe_times[frame_index] - keyframe_times[frame_index - 1]
            sleeptime = sleepperframe * keyframe_delta
            
            if frame_index > 0:
                if firststep:
                    # can remove
                    outf.write("\tif walking then\n\t\t-- Frame:%i\n" % frame_time)
                else:
                    if ISWALK:
                        outf.write("\t\t-- Frame:%i\n" % frame_time)
                    elif ISDEATH:
                        outf.write("\t\t-- Frame:%i\n" % frame_time)
                    else:
                        outf.write("\tif bAnimate then -- Frame:%i\n" % frame_time)
            
            for bone_name in sorted(thisframe.keys()):
                bone_motions = thisframe[bone_name]
                rotations_sum = 0

                for axis, value in bone_motions.items():
                    if not axis.startswith(('location', 'rot')):
                        print("Warning: Keyframe for something other than location or rotation")
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
                        print("Warning: Failed to find previous position for bone", bone_name, 'axis', axis, 'frame',
                              keyframe_times[frame_index])
                    else:
                        pass
                    # sleeptime = sleepperframe * (keyframe_times[i] - keyframe_times[prevframe])
                    
                    axis_index = int(axis[-1])
                    # blender_to_bos_axis_multiplier = [-1.0, -1.0, 1.0]  # for turns
                    if abs(value - prevvalue) < 0.1:
                        print("%i Ignored %s %s of %.6f delta" % (frame_time, bone_name, axis, value - prevvalue))
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
                        stopwalking_cmd = '%s(%s, %s' % (turn_or_move, bone_name, BOSAXIS[axis_index])
                        
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
                        
                        BOS = MakeBOSLineString(
                            turn_or_move,
                            bone_name,
                            axis_index,
                            value,
                            abs(value - prevvalue) * fps if VARIABLESPEED else maxvelocity,
                            variablespeed=VARIABLESPEED,
                            indents=2,
                            delta=value - prevvalue
                        )
                        
                        if rotations_sum > 130:
                            gwarn = "WARNING: possible gimbal lock issue detected in frame %i bone %s" % (
                                frame_time, bone_name)
                            print(gwarn)
                            BOS += '-- ' + gwarn + '\n'
                        
                        if not foundprev:
                            BOS += '-- ' + "Failed to find previous position for bone" + bone_name + 'axis' + axis
                        
                        if frame_index > 0:
                            outf.write(BOS + '\n')
            
            if frame_index > 0:
                
                if VARIABLESPEED:
                    outf.write('\t\tSleep((33 * animSpeed) -1)\n')
                else:
                    outf.write('\t\tSleep(%i)\n' % (33 * keyframe_delta - 1))
                
                if firststep:
                    outf.write("\tend\n")
                    outf.write("\twhile true do\n")
                    outf.write("\t\tanimSpeed = GetSpeedMod()\n")
                    firststep = False
        
        if ISWALK:
            outf.write('\tend\n')
        
        outf.write('end\n')
        
        if not ISDEATH:
            suffix = ' / animSpeed)\n' if VARIABLESPEED else ')\n'
            if ISWALK:
                if VARIABLESPEED:
                    outf.write('\n-- Call this from MotionControl()!')
                outf.write('\n')
                outf.write("""
local function StopWalking()
	Signal(SIG_WALK)
	SetSignalMask(SIG_WALK)

""")
                if VARIABLESPEED:
                    outf.write('\tanimSpeed = 10; -- tune restore speed here, higher values are slower restore speeds\n')
            else:
                if VARIABLESPEED:
                    outf.write('-- Call this from MotionControl()!\n')
                outf.write('local function StopAnimation()')
            for restore in sorted(stopwalking_maxspeed.keys()):
                if FIRSTFRAMESTANCE:
                    stance_position = 0
                    if restore in firstframestance_positions:
                        stance_position = firstframestance_positions[restore]
                    else:
                        print("Stance key %s not found in %s" % (restore, firstframestance_positions))
                    if restore.startswith('Turn'):
                        outf.write(
                            '\t' + restore + ', %.6f, %.6f' % (
                                radians(stance_position), radians(stopwalking_maxspeed[restore] * 10)) + suffix)
                    if restore.startswith('Move'):
                        if VARIABLESCALE:
                            outf.write(
                                '\t' + restore + ', (%.6f * MOVESCALE) / 100, ((%.6f * MOVESCALE)/100)' % (
                                    stance_position, stopwalking_maxspeed[restore] * 10)  + suffix)
                        else:
                            outf.write(
                                '\t' + restore + ', %.6f, %.6f' % (
                                    stance_position, stopwalking_maxspeed[restore] * 10)  + suffix)
                else:
                    if restore.startswith('Turn'):
                        outf.write(
                            '\t' + restore + ', 0, %.6f' % (radians(stopwalking_maxspeed[restore]) * 10) + suffix)
                    if restore.startswith('Move'):
                        if VARIABLESCALE:
                            outf.write('\t' + restore + ', 0, ((%.6f * MOVESCALE) / 100)' % (
                                    stopwalking_maxspeed[restore] * 10) + suffix)
                        else:
                            outf.write('\t' + restore + ', 0, %.6f' % (
                                    stopwalking_maxspeed[restore] * 10) + suffix)
            
            outf.write('end\n')
        
        if ISWALK and VARIABLESPEED:
            outf.write('--  REMEMBER TO animspeed = %i in Create() !!\n' % animFPK)
            outf.write('local function UnitSpeed()\n')
            outf.write('\tmaxSpeed = GetUnitValue(COB.MAX_SPEED); --  this returns cob units per frame i think\n')
            outf.write(
                '\tanimFramesPerKeyframe = %i; -- we need to calc the frames per keyframe value, from the known animtime\n' % animFPK)
            outf.write('\tmaxSpeed = maxSpeed + (maxSpeed /(2*animFramesPerKeyframe)); --  add fudge\n')
            outf.write('\twhile true do\n')
            outf.write('\t\tanimSpeed = GetUnitValue(COB.CURRENT_SPEED)\n')
            outf.write('\t\tif (animSpeed < 1) then animSpeed = 1 end\n')
            outf.write('\t\tanimSpeed = (maxSpeed * %i) / animSpeed \n' % animFPK)
            outf.write(
                '\t\t-- get PRINT(maxSpeed, animFramesPerKeyframe, animSpeed); -- how to print debug info from bos\n')
            outf.write('\t\tif (animSpeed < %i) then animSpeed=%i end\n' % (int(animFPK / 2), int(animFPK / 2)))
            outf.write('\t\tif (animspeed > %i) then animSpeed = %i end\n' % (animFPK * 2, animFPK * 2))
            outf.write('\t\tsleep(%i)\n' % (33 * animFPK - 1))
            outf.write('\tend\nend\n')
            outf.write("""
function script.StartMoving()
	if not walking then
		walking = true
		StartThread(Walk)
	end
end
""")
            outf.write("""
function script.StopMoving()
    walking = false
    StopWalking()
end
""")
        
        outf.close()
        print("Done writing bos!", " ISWALK = ", ISWALK, "Varspeed = ", VARIABLESPEED)
        print("bonesinIKchains:", bonesinIKchains)
        print("boneswithcurves:", boneswithcurves)



class SkeletorLUSMaker(SkeletorBOSMaker):
    bl_idname = "skele.skeletorlusmaker"
    bl_label = "skeletor_lusmaker"
    bl_description = "Writes *_lua_export.lua next to .blend file"
    bl_options = {'REGISTER', 'UNDO'}


def register():
    bpy.utils.register_class(MySettings)
    bpy.types.Scene.my_tool = PointerProperty(type=MySettings)
    bpy.utils.register_class(SkeletorOperator)
    bpy.utils.register_class(SkeletorRotator)
    bpy.utils.register_class(SkeletorBOSMaker)
    bpy.utils.register_class(SkeletorLUSMaker)
    bpy.utils.register_class(Skelepanel)
    bpy.utils.register_class(SimpleBoneAnglesPanel)


def unregister():
    bpy.utils.unregister_class(SkeletorOperator)
    bpy.utils.unregister_class(MySettings)
    bpy.utils.unregister_class(SkeletorRotator)
    bpy.utils.unregister_class(SkeletorBOSMaker)
    bpy.utils.unregister_class(SkeletorLUSMaker)
    bpy.utils.unregister_class(Skelepanel)
    bpy.utils.unregister_class(SimpleBoneAnglesPanel)
    del bpy.types.Scene.my_tool


if __name__ == "__main__":
    register()
