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
    "version": (0, 1, 6),
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
from math import pi, degrees
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

piecehierarchy = None

class MySettings(PropertyGroup):

    is_walk : BoolProperty(
        name="Is Walk Script",
        description="Whether the animation loops",
        default = True
        )
        
    varspeed : BoolProperty(
        name="Variable speed walk",
        description="Whether walk anim should be unitspeed dependant",
        default = True
        )    
    iktargetends : BoolProperty(
        name="Where to place IK targets",
        description="Whether IK targets should be at the leafs of anim chains or one branch above",
        default = True
        )    
    firstframestance : BoolProperty(
        name="First Keyframe Stance",
        description="The first keyframe contains an idle stance (non zero) that the unit returns to when not walking",
        default = True
        )

class Skelepanel(bpy.types.Panel):
    bl_label = "Skeletor S30"
    bl_idname = "PT_Skelepanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SkeletorS30"
    
    def draw(self,context):
        layout = self.layout
        
        scene = context.scene
        mytool = scene.my_tool

        row = layout.row()
        row.operator("skele.skeletorrotator",text = '1. Correctly rotate S3O')

        layout.prop(mytool, "iktargetends", text="IK targets at leafs")
        row = layout.row()
        row.operator('skele.skeletoroperator',text = '2. Create Skeleton')
        layout.prop(mytool, "is_walk", text="Is Walk Script")
        layout.prop(mytool, "varspeed", text="Variable speed")
        layout.prop(mytool, "firstframestance", text="First Frame Stance")
        row = layout.row()
        row.operator('skele.skeletorbosmaker',text = '3. Create BOS')
        
class S3opiece:
    def __init__(self, name, object, mesh, xoff,yoff,zoff):
        self.name = name
        self.parent = None
        self.children = []
        self.object = object
        self.mesh = mesh
        self.xoff = xoff
        self.yoff = yoff
        self.zoff = zoff
        self.loc = Vector((xoff,yoff,zoff))
        self.bone = None
        self.bonename = ""
        self.meshcopy = None
        self.worldpos = Vector((0,0,0))
        self.iktarget = None
        self.ikpole = None
        self.ikpoleangle = 0
        self.isafoot = False
        self.isAimXY = False
        
    def __repr__(self):
        return ('S3opiece:%s parent = %s children = [%s], offsets = %s object=%s mesh=%s worldpos = %s'%(
            self.name, 
            self.parent.name if self.parent is not None else None, 
            ','.join([child.name for child in self.children]), 
            self.loc, self.object,self.mesh, self.worldpos))
    
    def recursefixworldpos(self,parentpos): #note: doesnt work
        self.worldpos = self.loc+parentpos
        for child in self.children:
            child.recursefixworldpos(self.worldpos)
            
    def recurseleftrightbones(self,tag = None):
        
        def nolrname(n):
            return n.lower().replace("l","_").replace('r','_')
        
        if tag is None:
            for i,child in enumerate(self.children):  
                isLR = False
                for k, sibling in enumerate(self.children):
                    if i!=k and nolrname(child.name)==nolrname(sibling.name):
                        isLR = True
                        print (self.name, self.worldpos)
                        if self.worldpos[0]>0 : #LEFT
                            child.recurseleftrightbones(tag = '.L')
                        else:
                            child.recurseleftrightbones(tag = '.R')
                if not isLR:
                    child.recurseleftrightbones()
                        
        else:
            self.bonename = self.name+tag
            for child in self.children:
                child.recurseleftrightbones(tag = tag)
    
    def getmeshboundingbox(self):
        minz = 1000
        maxz = -1000
        miny = 1000
        maxy = -1000
        minx = 1000
        maxx = -1000
        if self.mesh is not None:
            for vertex in self.mesh.vertices:
                minz = min(minz,vertex.co[2])
                maxz = max(maxz,vertex.co[2])
                miny = min(miny,vertex.co[1])
                maxy = max(maxy,vertex.co[1])
                minx = min(minx,vertex.co[0])
                maxx = max(maxx,vertex.co[0])
        return (minx,maxx,miny,maxy,minz,maxz)
    
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
                    print ("We have a root!", object)
                    rootobject = object
                    rootname = object.name
                    return rootobject,rootname
                    break
                
def properrot(bone, MYEULER = 'YXZ',parentEULER = True):
    #MYEULER = 'YXZ' #'ZXY' #BECAUSE FUCK ME THATS WHY
    mat = bone.matrix.copy()
    pmat = bone.matrix.copy()
    currbone = bone
    if currbone.parent is not None:         
        pmat = currbone.parent.matrix.copy()
        pmat.invert()
        #mat = mat @ pmat # OH BOY IS THIS WRONG!
        mat = pmat @ mat


        currbone = currbone.parent

    if parentEULER:
        rot = mat.to_euler(MYEULER, pmat.to_euler(MYEULER) )
    else:
        rot = mat.to_euler(MYEULER)#, pmat.to_euler(MYEULER) )
    rottext = '%s %s %i X:%.1f Y:%.1f Z:%.1f'%(bone.name,MYEULER,parentEULER,degrees(rot.x),degrees(rot.y),degrees(rot.z))
    return rottext

class SkeletorRotator(bpy.types.Operator):
    bl_idname = "skele.skeletorrotator"
    bl_label = "skeletor_rotate"
    bl_description = "Create a skeleton"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self,context):
        self.s3orotate(context = context)
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
        
        #bpy.ops.transform.rotate(value=-pi/2, orient_axis='Z', orient_type='VIEW', orient_matrix=((0, -1, 0), (0, 0, -1), (-1, 0, 0)), orient_matrix_type='VIEW', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False)
        bpy.context.object.rotation_euler[0] = pi/2

        
        
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        
        #return 
        bpy.ops.object.select_all(action='DESELECT')
        rootobject.select_set(True)
        oldz = bpy.context.object.location[2] 
        oldy = bpy.context.object.location[1] 
        #bpy.context.object.location[1] = oldz 
        #bpy.context.object.location[2] = oldy
        bpy.ops.object.select_all(action='SELECT')
        
        bpy.ops.transform.translate(value=(0, -10.9483, 13.9935), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False)
        
        bpy.ops.object.select_all(action='DESELECT')
        
        rootobject.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        
        
        bpy.ops.object.select_all(action='DESELECT')

class SkeletorOperator(bpy.types.Operator):
    bl_idname = "skele.skeletoroperator"
    bl_label = "skeletize"
    bl_description = "Create a skeleton"
    bl_options = {'REGISTER','UNDO'}

    def execute(self,context):
        piecehierarchy = self.skeletize(context = context)
        return {'FINISHED'}
        
    @staticmethod
    def skeletize(context):
        print ("skeletizing, very happy")
        NOTAIL = True
        IKTARGETENDS = context.scene.my_tool.iktargetends

        #debug delete all armatures and bones!
        #bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        for object in bpy.context.scene.objects:
            if object.name == "Armature":
                print (object)
                bpy.data.objects['Armature'].select_set(True)
                bpy.ops.object.delete({"selected_objects":[object]})
        
        
        pieces = {} #"name":s3opiece
        
        # collect the data we need:
        # object of each piece
        # root object
        # the offsets of each object
        # the children of each object
        # the amount of geometry each object has. 

        #find the object with no parents, but has children (root)
        rootobject,rootname = getS3ORootObject()

        #got the root!
        rootpiece = S3opiece(rootobject.name,rootobject, getmeshbyname(rootobject.name), rootobject.location[0], rootobject.location[1], rootobject.location[2]) 

        print (rootpiece)

        print ("====Collecting Pieces====")
        pieces[rootname] = rootpiece
        for object in bpy.data.objects:
            if object.parent is not None:
                newpiece = S3opiece(object.name, object, getmeshbyname(object.name), object.location[0], object.location[1], object.location[2])
                print (newpiece)

                pieces[newpiece.name] = newpiece
        for piece in pieces.values():
            print (piece)
            print (piece.object)
            if piece.object.parent is not None:
                piece.parent = pieces[piece.object.parent.name]
                piece.parent.children.append(piece)
                print (piece.name,'->', piece.parent.name)
        
        rootpiece.recursefixworldpos(Vector((0,0,0)))

        opennodes = set() # Set to keep track of visited nodes.
        opennodes.add(rootpiece)
        dfs_piece_order = [rootpiece.name]
        
        while(len(opennodes)>0):
            nodelist = list(opennodes)
            for node in nodelist:
                dfs_piece_order.append(node.name)
                print ('nodename', node.name)
                opennodes.remove(node)
                for child in node.children:
                    opennodes.add(child)
        print (dfs_piece_order)    

        print ("====Reparenting pieces to avoid AimX and AimY====")
        # if the parent of an object is called aimx* or aimy*, then reparent the piece to the parent of aimx or aimy actual parent
        for piece in pieces.values():
            if piece.object.parent is not None and piece.object.parent.name[0:4].lower() in ['aimx','aimy']:
                print("Reparenting ",piece.name, "from", piece.parent.name,'to', piece.parent.parent.name)
                piece.parent.isAimXY = True
                try:
                    piece.parent.children.remove(piece)
                    piece.parent = pieces[piece.object.parent.parent.name]
                    piece.parent.children.append(piece)

                except:
                    print ("piece", piece)
                    print ("parent", piece.parent)
                    print ("GP", piece.parent.parent)
                    raise

        #final check that we have all set:
        print ("----------Sanity check:-----------")
        for k,v in pieces.items():
            print (k,v)
        
        #set the cursor to origin:
        bpy.ops.transform.translate(value=(0, 0, 0), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False, cursor_transform=True, release_confirm=True)

        print ("====Setting rotation modes to Euler ZXY====")
        scene = context.scene
        for obj in scene.objects:
            obj.select_set(False)
            obj.rotation_mode = 'YXZ' # was: 'ZXY', but that is prolly wrong
        
        #add an armature!
        print ("====Creating Armature====")
        arm_data = bpy.data.armatures.new("Armature")
        
        armature_object =  bpy.data.objects.new("Armature", arm_data)
        armature_object.location=Vector((0,0,0)) #rootpiece.loc
        armature_object.show_in_front = True
        armature_object.data.show_axes = True
        armature_object.data.show_names = True

        armature_object.rotation_mode = 'YXZ' # was: 'ZXY', but that is prolly wrong
        
        context.collection.objects.link(armature_object)
        
        armature_object.select_set(True)
        
        context.view_layer.objects.active = armature_object
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        print ("====Looking for mirrorable pieces===")
        #to enable : https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle
        #rootpiece.recurseleftrightbones()
        for name, piece in pieces.items():
            piece.bonename = name
            for name2, piece2 in pieces.items():
                if name == name2:
                    continue
                if name.lower().replace('l','').replace('r','') == name2.lower().replace('l','').replace('r',''):
                    if piece.worldpos[0]>0:
                        piece.bonename = piece.bonename + '.R'
                    else:
                        piece.bonename = piece.bonename + '.L'

        print ("====Adding Bones=====")
        for name in dfs_piece_order:
            piece = pieces[name]
            if piece.isAimXY:
                continue
            if piece.bonename in arm_data.edit_bones:
                newbone = arm_data.edit_bones[piece.bonename]
            else:
                newbone = arm_data.edit_bones.new(piece.bonename)
            newbone.name = piece.bonename
            
            #TODO CHANGE TO POSE MODE TO SET THESE!
            #newbone.rotation_mode = 'ZXY'
            
            newbone.head = piece.worldpos 
            if NOTAIL:
                newbone.tail = newbone.head + Vector((0,5,0)) 
            
            tailpos =  piece.loc+Vector((0,0,10))
            if len(piece.children)>=1:
                tailpos = Vector((0,0,0))
                for child in piece.children:
                    tailpos = tailpos + child.worldpos
                tailpos = tailpos /len(piece.children)
                newbone.tail = tailpos
                if NOTAIL:
                    newbone.tail = newbone.head + Vector((0,5,0)) #TODO fixeme
                #TODO: Something is an arm if it has only nomesh children
                #thus we add a forward pointing IK target to its tailpos
                onlyemptychildren = True
                for child in piece.children:
                    if child.mesh is not None:
                        onlyemptychildren = False
                if onlyemptychildren:
                    print ("LOOKS LIKE AN ARM:",piece.name)
                    ikbone = arm_data.edit_bones.new('iktarget.'+piece.bonename)
                    ikbone.head = newbone.tail
                    ikbone.tail = newbone.tail + Vector((0,5,2))
                    piece.iktarget = ikbone   
                
            else: #end piece
                #TODO: CHECK FOR GEOMETRY, is it a foot or an arm or a tentacle ? 
                #TODO: multiple branches for multiple toes give too many IK targets :/
                if piece.mesh is not None and piece.parent.iktarget is None:
                    boundingbox = piece.getmeshboundingbox()
                    
                    print ("LOOKS LIKE A FOOT:", piece.name,piece.worldpos,  boundingbox)
                    if piece.worldpos[2] + boundingbox[4] <= 2.0: 
                        #this looks like a foot
                        tailpos = piece.worldpos + Vector((0, boundingbox[3], boundingbox[4]))
                        #better add the heel IK thing too XD
                        if not IKTARGETENDS:
                            heelbone = arm_data.edit_bones.new('iktarget.'+piece.parent.bonename)
                            heelbone.head = piece.parent.bone.tail #newbone.head
                            heelbone.tail = newbone.head + Vector((0,boundingbox[4],0))
                            if NOTAIL:
                                heelbone.tail =  heelbone.head + Vector((0,5,2))
                            piece.parent.iktarget = heelbone
                        else:
                            heelbone = arm_data.edit_bones.new('iktarget.'+piece.bonename)
                            heelbone.head = newbone.tail #newbone.head
                            heelbone.tail = newbone.head + Vector((0,boundingbox[4],0))
                            if NOTAIL:
                                heelbone.tail =  heelbone.head + Vector((0,5,2))
                            piece.iktarget = heelbone
                    else:
                        #todo this is not a foot
                        #guess if it points forward or up or down?
                        if (boundingbox[5] > boundingbox[3] and boundingbox[5]> -1*boundingbox[2]): # points forward
                            tailpos = piece.worldpos + Vector((0, boundingbox[5], 0))
                        else:
                            if (boundingbox[3] > -1*boundingbox[2]):
                                tailpos = piece.worldpos + Vector((0, 0, boundingbox[3])) #up
                            else:
                                tailpos = piece.worldpos + Vector((0, 0, boundingbox[2])) #down
                                
                    # TODO we are also kind of a foot if we only have children with no meshes.
                else:
                    tailpos =  piece.worldpos+Vector((0,5,0))
            newbone.tail = tailpos 
            #TODO: easier rotations like this?
            if NOTAIL:
                newbone.tail = newbone.head + Vector((0,5,0))
            
            
            print ("trying to add bone to %s\nat head:%s \ntail:%s"%(piece,newbone.head,newbone.tail))
            piece.bone = newbone
        #return
        print ("=====Reparenting Bone-Bones=======")
        
        for name,piece in pieces.items():
            
            if piece.parent is not None and not piece.isAimXY:
                piece.bone.parent = piece.parent.bone      
  
        bpy.ops.object.editmode_toggle() # i have no idea what im doing
        bpy.ops.object.posemode_toggle()

        print ("=====Setting IK Targets=======")
        
        for name,piece in pieces.items():
            if not piece.isAimXY:
                armature_object.pose.bones[piece.bonename].rotation_mode = 'YXZ' # was: 'ZXY', but that is prolly wrong

            if piece.iktarget is not None:
                chainlength = 1
                chainpos = piece.parent
                while(len(chainpos.children) ==1  and chainpos.parent is not None):
                    chainlength +=1
                    chainpos = chainpos.parent
                print ('Adding iktarget to ',piece.name,'chain_length = ',chainlength)
                constraint = armature_object.pose.bones[piece.bonename].constraints.new('IK')
                constraint.target = armature_object
                constraint.subtarget = 'iktarget.'+piece.bonename
                constraint.chain_count = chainlength
                armature_object.pose.bones[piece.bonename].ik_stiffness_z = 0.99 #avoids having to create knee poles

        print ("=====Parenting meshes to bones=======")
        #getting desperate here: https://blender.stackexchange.com/questions/77465/python-how-to-parent-an-object-to-a-bone-without-transformation
        for name,piece in pieces.items():
            if piece.isAimXY:
                continue
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
            ob = piece.object
            bpy.ops.object.select_all(action = 'DESELECT')
            armature_object.select_set(True)
            bpy.context.view_layer.objects.active = armature_object
            bpy.ops.object.mode_set(mode='EDIT')
            parent_bone = piece.bonename
            armature_object.data.edit_bones.active = armature_object.data.edit_bones[parent_bone]
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action = 'DESELECT')
            ob.select_set(True)
            armature_object.select_set(True)
            bpy.context.view_layer.objects.active = armature_object
            bpy.ops.object.parent_set(type = 'BONE', keep_transform = True)
            
        print ("done")  
        
class SimpleBoneAnglesPanel(bpy.types.Panel):
    bl_label = "Bone Angles"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        #print ("DrawSimpleBonesAnglesPanel")
        if 'Armature' not in context.scene.objects:
            return
        arm = context.scene.objects['Armature']
        props = {"location":"move", "rotation_euler":"turn"} 
        
        selectednames = []
        if bpy.context.selected_pose_bones is not None:
            for o in bpy.context.selected_pose_bones:
                selectednames.append(o.name)
        #print (selectednames)
        for bone in arm.pose.bones:
            
            if 'iktarget' in bone.name:
                continue
            #row = self.layout.row()
            #row.label(text = bone.name)
            bname = bone.name
            MYEULER = 'YXZ' #'ZXY' #BECAUSE FUCK ME THATS WHY
            mat = bone.matrix.copy()
            
            pmat = bone.matrix.copy()
            currbone = bone
            if currbone.parent is not None:         
                pmat = currbone.parent.matrix.copy()
                pmat.invert()
                #mat = mat @ pmat # OH BOY IS THIS WRONG!
                mat = pmat @ mat
                currbone = currbone.parent

            #there seems to be a major difference in IK based rots, and manual rots. 
            #the matrix inversion with 'YXZ' euler order seems to be correct for IK targetted bones
            #but its way overkill for manually rotated stuff
            #maybe there are two separate rotations, e.g. 
            #bpy.context.object.pose.bones["rdoor.R"].rotation_euler[0] = 0.105584
            #and the parent matrix based one
            #but how to choose between these for IK and FK bones?
            #wierd as fuck....
            #use the locs  and rots from the fcurves, and then in pass 2 merge on the actual ones?
            #We KNOW which bones have FK fcurves - those are the ones manually set
            #We can also fiogure out, from the IK constraints and the chain lengths, which bones have IK on them
            #bpy.context.object.pose.bones["rankle.R"].constraints["IK"].mute = False

            rot = mat.to_euler(MYEULER)#, pmat.to_euler(MYEULER) )
            
            row = self.layout.row()
            rottext = '%s X:%.1f Y:%.1f Z:%.1f'%(bname,degrees(rot.x),degrees(rot.y),degrees(rot.z))
            #print (rottext)
            if bname in selectednames:
                rottext = '  '+rottext.upper()
                for eulertype in ['XYZ','XZY','YXZ','YZX','ZXY','ZYX']:
                    for ptype in [False,True]:
                        row.label(text = properrot(bone,MYEULER = eulertype, parentEULER = ptype))
                        row = self.layout.row()
                
            if sum([abs(degrees(rot.x)),abs(degrees(rot.y)),abs(degrees(rot.z))])> 135:
                rottext = '[!] '+rottext
                row.alert = True
            row.label(text=rottext)
            row = self.layout.row()
            rottext = 'E %s X:%.1f Y:%.1f Z:%.1f'%(bname,
                degrees(arm.pose.bones[bname].rotation_euler[0]),
                degrees(arm.pose.bones[bname].rotation_euler[1]),
                degrees(arm.pose.bones[bname].rotation_euler[2])
                )
            row.label(text = rottext)
            #row.label(text='X%.1f'%(mat[0][3]))
            #row.label(text='Y%.1f'%(mat[1][3]))
            #row.label(text='Z%.1f'%(mat[2][3]))


class SkeletorBOSMaker(bpy.types.Operator):
    bl_idname = "skele.skeletorbosmaker"
    bl_label = "skeletor_bosmaker"
    bl_description = "Writes .bos to console"
    bl_options = {'REGISTER','UNDO'}
    
    def execute(self,context):
        self.tobos(context = context)
        return {'FINISHED'}
    
    def __init__(self):
        super().__init__()
        print ("SkeletorBOSMaker.init")
        self.whichframe = 0
        
    #@staticmethod
    def tobos(self,context):
        print ("MAKING BOS, BOSS")
        scene = context.scene
        if 'Armature' not in context.scene.objects:
            return
        arm = context.scene.objects['Armature']
        print ("whichframe",self.whichframe)
        self.whichframe +=1
        props = {"location":"move", "rotation_euler":"turn"} 
        boneswithcurves = []
        bonesinIKchains = []
        
        ISWALK = context.scene.my_tool.is_walk
        VARIABLESPEED = context.scene.my_tool.varspeed
        FIRSTFRAMESTANCE = context.scene.my_tool.firstframestance
        # for a sane firstframestance:
        # some pieces may be moved in a stance that are not present in the walk
        # when setting stance, make sure of the following:
        
        #things I know:
        # curves contain the needed location data
        # pose bones matrices contain the needed rotation data
        # ignore all rots and pos's of iktargets
        # remove .L and .R monikers
        
        #required structure:
        # a dict of keyframes indexed by their frame number
        animframes = {}
        #the values of which is another dict, of piece names
        #each piece name has a turn and a move op, with xzy coords
        
        #in each frame, each 'real piece' should have its position and location stored
        if arm.animation_data is not None:
            if arm.animation_data.action is not None:
                curves = arm.animation_data.action.fcurves;
                print ("Animdata:",curves, arm.animation_data)
                for c in curves:
                    keyframes = c.keyframe_points
                    bname = c.data_path.split('"')[1]
                    if bname.startswith('iktarget.'):
                        continue
                    if bname not in boneswithcurves:
                        boneswithcurves.append(bname)
                        
                    if bname.endswith('.R') or bname.endswith('.L'):
                        bname = bname[:-2]
                    
                    ctarget = c.data_path.rpartition('.')[2]
                    if ('euler' in ctarget or 'quaternion' in ctarget or 'scale' in ctarget) and 'location' not in ctarget:
                        continue
                    
                    axis = str(c.array_index)

                    for i,k in enumerate(keyframes):    
                        
                        frameidx = int(k.co[0])
                        value = float(k.co[1])
                        #if abs(value)<0.1:
                        #    continue
                        
                        if frameidx not in animframes:
                            animframes[frameidx] = {}
                        if bname not in animframes[frameidx]:
                            animframes[frameidx][bname] = {}
                            
                        animframes[frameidx][bname][ctarget+axis] = value
        
        print (animframes)

        for frameidx in sorted(animframes.keys()):
            print ("SETTING FRAMETIME",frameidx)
            bpy.context.scene.frame_set(frameidx)
            #return (None)
            for bone in arm.pose.bones:
                
                if 'iktarget' in bone.name:
                    continue
                #row = self.layout.row()
                #row.label(text = bone.name)
                bname = bone.name
                if 'IK' in bone.constraints and bone.constraints['IK'].mute == False:
                    chainlength = bone.constraints['IK'].chain_count
                    if chainlength == 0: #this means that everything up until the root is in the chain
                        print (bone.name, 'has ik length',chainlength)
                        p = bone
                        while p is not None:
                            print ("inchain",p.name)
                            if p.name not in bonesinIKchains:
                                bonesinIKchains.append(p.name)
                            chainlength = chainlength -1
                            p = p.parent
                        
                    else:
                        print (bone.name, 'has ik length',chainlength)
                        p = bone
                        while chainlength > 0:
                            print ("inchain",p.name)
                            if p.name not in bonesinIKchains:
                                bonesinIKchains.append(p.name)
                            chainlength = chainlength -1
                            p = p.parent
                            
                
                if bname.endswith('.R') or bname.endswith('.L'):
                    bname = bname[:-2]
                mat = bone.matrix.copy()
                
                MYEULER = 'YXZ' #'ZXY' #LORD HAVE MERCY
                currbone = bone
                pmat = bone.matrix.copy()
                if currbone.parent is not None:  
                    pmat = currbone.parent.matrix.copy()
                    pmat.invert()

                    #mat = mat @ pmat # OH BOY IS THIS WRONG!
                    mat = pmat @ mat
                    currbone = currbone.parent
                
                #rot = mat.to_euler(MYEULER, pmat.to_euler(MYEULER) )
                rot = mat.to_euler(MYEULER)#, pmat.to_euler(MYEULER) )
                rottext = '%s X:%.1f Y:%.1f Z:%.1f'%(bname,degrees(rot.x),degrees(rot.y),degrees(rot.z))
                print (rottext)
                 
                if bone.name not in bonesinIKchains:
                    for axis in range(3):
                        if frameidx not in animframes:
                            animframes[frameidx] = {}
                        if bname not in animframes[frameidx]:
                            animframes[frameidx][bname] = {}
                        animframes[frameidx][bname]['rot'+str(axis)] = degrees(arm.pose.bones[bone.name].rotation_euler[axis])

                else:
                    for axis,value  in enumerate(rot[0:3]):                        
                        if frameidx not in animframes:
                            animframes[frameidx] = {}
                        if bname not in animframes[frameidx]:
                            animframes[frameidx][bname] = {}
                        print ('adding',frameidx,bname,'rot'+str(axis),value)
                        animframes[frameidx][bname]['rot'+str(axis)] = degrees(value)
                    
        print ("animframes:",animframes)        
        fps = 30.0
        startframe = 7
        interval = 6
        endframe = 55
        movethres = 0.5
        rotthres = 0.5 #degrees
        sleepperframe = 1.0/fps
        #conversion time:
        #output a bos script
        #simplify mini rots and mini moves
        #the first frame can be ignored
        frame_indexes = sorted(animframes.keys())
       
        filepath = bpy.data.filepath
        directory = os.path.dirname(filepath)
        print(directory,filepath)
        AXES = 'XZY'
        BOSAXIS = ['x-axis','z-axis','y-axis']
        newfile_name = filepath + ".bos_export.txt"
        outf = open(newfile_name,'w')
        outf.write("// Generated for %s\n// Using https://github.com/Beherith/Skeletor_S3O \n"%filepath)
        outf.write("// this animation uses the static-var animFramesPerKeyframe which contains how many frames each keyframe takes\n")
        if ISWALK and VARIABLESPEED:
            outf.write("static-var animSpeed, maxSpeed, animFramesPerKeyframe, bMoving;\n")
            
        else:
            outf.write("static-var bAnimate;\n")
            

        animSpeed = [frame_indexes[i] - frame_indexes[i-1] for i in range(2,len(frame_indexes))]
        animFPK = 4
        if len(animSpeed) == 0:
            print ("MEGA WARNING: NO DETECTABLE FRAMES!")
            return
        else:
            animFPK = float(sum(animSpeed))/(len(frame_indexes)-2)
            if ISWALK and (animFPK- round(animFPK) > 0.00001):
                warn = "//Animframes spacing is %f, THIS SHOULD BE AN INTEGER, SPACE YOUR KEYFRAMES EVENLY!\n"%animFPK
                outf.write(warn)
                print(warn)
            
        stopwalking_maxspeed = {} #dict of of bos commands, with max velocity in it to define the stopwalking function
        firstframestance_positions = {} #dict of bos commands, with the target of the piece as value
        if ISWALK:
            outf.write("Walk() {//%s from %s \n"%("Created by https://github.com/Beherith/Skeletor_S3O",filepath ))
        else:
            outf.write("Animate() {//%s from %s \n"%("Created by https://github.com/Beherith/Skeletor_S3O",filepath ))
        
        firststep = True
        if not ISWALK:
            firststep = False
            
        for i, frameidx in enumerate(frame_indexes):
            if i == 0 and not FIRSTFRAMESTANCE: #skip first piece
                continue
            
            thisframe = animframes[frame_indexes[i]]
            prevframe = animframes[frame_indexes[i-1]]
            
            framedelta = frame_indexes[i] - frame_indexes[i-1]
            sleeptime = sleepperframe * framedelta
            
            if i > 0:
                if firststep:
                    outf.write("\tif (bMoving) { //Frame:%i\n"%frameidx)
                else:
                    if ISWALK:
                        outf.write("\t\tif (bMoving) { //Frame:%i\n"%frameidx)
                    else:
                        outf.write("\t\tif (bAnimate) { //Frame:%i\n"%frameidx)
                    
            for bname in sorted(thisframe.keys()):
                motions = thisframe[bname]
                rotations_sum = 0
                
                for axis, value in motions.items():
                    #find previous value
                    #TODO: fix missing keyframes for individual anims and interpolate from last known keyframe for curve!
                    # handle separately for idle anims, as they dont require accurate keyframe reinterpolation
                    sleeptime = sleepperframe * framedelta
                    prevvalue = 0
                    prevframe = i-1
                    foundprev = False
                    for previous in range(i-1,-1,-1):
                        if bname in animframes[frame_indexes[previous]] and axis in animframes[frame_indexes[previous]][bname]:
                            prevvalue = animframes[frame_indexes[previous]][bname][axis]
                            foundprev = True
                            prevframe = previous
                            break
                    if not foundprev and i>0:
                        print ("Warning: Failed to find previous position for bone",bname,'axis',axis,'frame', frame_indexes[i])                  
                    else:
                        pass
                        #sleeptime = sleepperframe * (frame_indexes[i] - frame_indexes[prevframe])
                        
                    axidx = AXES[int(axis[-1])]
                    ax = int(axis[-1])
                    axmul = [-1.0,-1.0,1.0]
                    if abs(value-prevvalue)<0.1: 
                        print ("%i Ignored %s %s of %.6f delta"%(frameidx,bname,axis,value-prevvalue))
                        continue
                    else:
                        
                        stopwalking_cmd = 'turn %s to %s'
                        boscmd =  '\t\t\tturn %s to %s <%.6f> speed <%.6f> %s; '
                        if axis.startswith('location'):
                            
                            axmul = [1.0,1.0,1.0]
                            boscmd =  '\t\t\tmove %s to %s [%.6f] speed [%.6f] %s; '
                            stopwalking_cmd = 'move %s to %s'
                        
                        stopwalking_cmd = stopwalking_cmd % (bname,BOSAXIS[ax])
                        if FIRSTFRAMESTANCE and i ==0:
                            firstframestance_positions[stopwalking_cmd]=value * axmul[ax]
 
                                
                        maxvelocity = abs(value-prevvalue) / sleeptime
                        if stopwalking_cmd in stopwalking_maxspeed:
                            if maxvelocity > stopwalking_maxspeed[stopwalking_cmd]:
                                stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
                        else:
                            stopwalking_maxspeed[stopwalking_cmd] = maxvelocity
                        rotations_sum += abs(value-prevvalue)
                        
                        #  '\t\t\tmove %s to %s [%.6f] speed [%.6f]; '
                        
                        if VARIABLESPEED:
                            BOS = boscmd %(
                                    bname,
                                    BOSAXIS[ax],
                                    value * axmul[ax],
                                    abs(value-prevvalue)*fps,
                                    '/ animSpeed'
                                    
                            )
                        else:      
                            BOS = boscmd %(
                                    bname,
                                    BOSAXIS[ax],
                                    value * axmul[ax],
                                    abs(value-prevvalue) /sleeptime,
                                    ''
                            )
                        if rotations_sum > 130:
                            gwarn = "WARNING: possible gimbal lock issue detected in frame %i bone %s"%(frameidx, bname)
                            print (gwarn)        
                            BOS += '//'+gwarn+'\n'
                        if not foundprev:
                            BOS += '//' + "Failed to find previous position for bone"+bname+'axis'+axis 
                        if i>0:
                            outf.write(BOS+'\n')
                        else:
                            if FIRSTFRAMESTANCE:
                                stopwalking_cmd
                                
            if i>0:
                if firststep or not VARIABLESPEED:
                    outf.write('\t\tsleep %i;\n'%(33*framedelta -1))
                else:
                    outf.write('\t\tsleep ((33*animSpeed) -1);\n')

                if firststep:
                    outf.write("\t}\n")
                    outf.write("\twhile(bMoving) {\n")
                    firststep = False
                else:
                    outf.write('\t\t}\n')
                        
        if ISWALK:
            outf.write('\t}\n')

        outf.write('}\n')
        if ISWALK:
            outf.write('// Call this from MotionControl()!\nStopWalking() {\n')
        else:
            outf.write('// Call this from MotionControl()!\nStopAnimation() {\n')
        for restore in sorted(stopwalking_maxspeed.keys()):
            if FIRSTFRAMESTANCE:
                stance_position = 0
                if restore in firstframestance_positions:
                    stance_position = firstframestance_positions[restore]
                else:
                    print ("Stance key %s not found in %s"%(restore,firstframestance_positions))
                if restore.startswith('turn'):
                    outf.write('\t'+restore+ ' <%.6f> speed <%.6f>;\n'%(stance_position,stopwalking_maxspeed[restore]))
                if restore.startswith('move'):
                    outf.write('\t'+restore+ ' [%.6f] speed [%.6f];\n'%(stance_position,stopwalking_maxspeed[restore]))
            else:
                if restore.startswith('turn'):
                    outf.write('\t'+restore+ ' <0> speed <%.6f>;\n'%stopwalking_maxspeed[restore])
                if restore.startswith('move'):
                    outf.write('\t'+restore+ ' [0] speed [%.6f];\n'%stopwalking_maxspeed[restore])
        outf.write('}\n')
        
        if ISWALK and VARIABLESPEED:
            outf.write('UnitSpeed(){\n')
            outf.write(' maxSpeed = get MAX_SPEED; // this returns cob units per frame i think\n')
            outf.write(' animFramesPerKeyframe = %i; //we need to calc the frames per keyframe value, from the known animtime\n'%animFPK)
            outf.write(' maxSpeed = maxSpeed + (maxSpeed /(2*animFramesPerKeyframe)); // add fudge\n')
            outf.write(' while(TRUE){\n')
            outf.write('  animSpeed = (get CURRENT_SPEED);\n')
            outf.write('  if (animSpeed<1) animSpeed=1;\n')
            outf.write('  animSpeed = (maxSpeed * %i) / animSpeed; \n' % animFPK)
            outf.write('  //get PRINT(maxSpeed, animFramesPerKeyframe, animSpeed);\n')
            outf.write('  if (animSpeed<%i) animSpeed=%i;\n' %(int(animFPK/2), int(animFPK/2)))
            outf.write('  if (animspeed>%i) animSpeed = %i;\n'%(animFPK*2, animFPK*2))
            outf.write('  sleep %i;\n'%(33*animFPK -1))
            outf.write(' }\n}\n')
        
        outf.close()
        print ("Done writing bos!", " ISWALK = ",ISWALK, "Varspeed = ",VARIABLESPEED)
        print ("bonesinIKchains:",bonesinIKchains)
        print ("boneswithcurves:",boneswithcurves)


def register():
    bpy.utils.register_class(MySettings)
    bpy.types.Scene.my_tool = PointerProperty(type=MySettings)
    bpy.utils.register_class(SkeletorOperator)
    bpy.utils.register_class(SkeletorRotator)
    bpy.utils.register_class(SkeletorBOSMaker)
    bpy.utils.register_class(Skelepanel)
    bpy.utils.register_class(SimpleBoneAnglesPanel)
    
def unregister():
    bpy.utils.unregister_class(SkeletorOperator)
    bpy.utils.unregister_class(MySettings)
    bpy.utils.unregister_class(SkeletorRotator)
    bpy.utils.unregister_class(SkeletorBOSMaker)
    bpy.utils.unregister_class(Skelepanel)
    bpy.utils.unregister_class(SimpleBoneAnglesPanel)
    del bpy.types.Scene.my_tool
    
if __name__ == "__main__":
    register()
    
    
