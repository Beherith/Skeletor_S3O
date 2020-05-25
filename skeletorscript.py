import bpy
from math import pi
from mathutils import Vector, Euler, Matrix


class Skelepanel(bpy.types.Panel):
    bl_label = "Skeletor S30"
    bl_idname = "PT_Skelepanel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SkeletorS30"
    
    def draw(self,context):
        layout = self.layout

        row = layout.row()
        row.operator("skele.skeletorrotator",text = '1. Correctly rotate S3O')

        row = layout.row()
        row.operator('skele.skeletoroperator',text = '2. Create Skeleton')
        
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
            return n.lower.replace("l","_").replace('r','_')
        
        if tag is None:
            for i,child in enumerate(self.children):  
                isLR = False
                for k, sibling in enumerate(self.children):
                    if i!=k and nolrname(child.name)==nolrname(sibling.name):
                        isLR = True
                        if self.worldpos.x>0 : #LEFT
                            child.recurseleftrightbones(tag = '.L')
                        else:
                            child.recurseleftrightbones(tag = '.R')
                if not isLR:
                    child.recuseleftrightbones()
                        
        else:
            self.bonename = self.name+tag
            for child in self.children():
                child.recurseleftrightbones(tag = tag)
                
                
        
    
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
        self.skeletize(context = context)
        return {'FINISHED'}
        
    @staticmethod
    def skeletize(context):
        print ("skeletizing, very happy")
        
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
                
        print ("====ReParenting pieces to avoid AimX and AimY====")
        # if the parent of an object is called aimx* or aimy*, then reparent the piece to the parent of aimx or aimy actual parent
        for piece in pieces.values():
            if piece.object.parent is not None and piece.object.parent.name[0:4].lower() in ['aimx','aimy']:
                print("Reparenting ",piece.name, "from", piece.parent.name,'to', piece.parent.parent.name)
                piece.parent = pieces[piece.object.parent.parent.name]
                piece.parent.parent.children.append(piece)        
                piece.parent.children.remove(piece)
        
        
        #final check that we have all set:
        rootpiece.recursefixworldpos(Vector((0,0,0)))
        print ("----------Sanity check:-----------")
        for k,v in pieces.items():
            print (k,v)
        
        #set the cursor to origin:
        bpy.ops.transform.translate(value=(0, 0, 0), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False, cursor_transform=True, release_confirm=True)

        print ("====Setting rotation modes to Euler ZXY====")
        scene = context.scene
        for obj in scene.objects:
            obj.select_set(False)
            obj.rotation_mode = 'ZXY'
        
        #add an armature!
        
        
        print ("====Creating Armature====")
        arm_data = bpy.data.armatures.new("Armature")
        
        armature_object =  bpy.data.objects.new("Armature", arm_data)
        armature_object.location=Vector((0,0,0)) #rootpiece.loc
        armature_object.show_in_front = True
        armature_object.rotation_mode = 'ZXY'
        
        context.collection.objects.link(armature_object)
        
        armature_object.select_set(True)
        
        context.view_layer.objects.active = armature_object
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        print ("====Looking for mirrorable pieces===")
        #to enable : https://blender.stackexchange.com/questions/43720/how-to-mirror-a-walk-cycle
        
        rootpiece.recurseleftrightbones()    
        
        print ("====Adding Bones=====")
        
        for name, piece in pieces.items():
            newbone = arm_data.edit_bones.new(piece.bonename)
            newbone.name = piece.bonename
            
            #TODO CHANGE TO POSE MODE TO SET THESE!
            #newbone.rotation_mode = 'ZXY'
            
            newbone.head = piece.worldpos 
            tailpos =  piece.loc+Vector((0,0,10))
            if len(piece.children)==1:
                tailpos = piece.children[0].worldpos
            elif len(piece.children)>=2:
                tailpos = Vector((0,0,0))
                for child in piece.children:
                    tailpos = tailpos + child.worldpos
                tailpos = tailpos /len(piece.children)
            else: #end piece
                #TODO: CHECK FOR GEOMETRY, is it a foot or an arm or a tentacle ? 
                #TODO: Also
                if piece.mesh is not None:
                    minz = 100000
                    miny = 1000000
                    maxy = -1000000
                    for vertex in piece.mesh.vertices:
                        minz = min(minz,vertex.co[2])
                        miny = min(miny,vertex.co[1])
                        maxy = max(maxy,vertex.co[1])
                    if piece.worldpos[2] + minz <= 2.0: 
                        #this looks like a foot
                        tailpos = piece.worldpos + Vector((0, -miny, minz))
                        #better add the heel IK thing too XD
                        heelbone = arm_data.edit_bones.new('iktarget.'+piece.parent.bonename)
                        heelbone.head = newbone.head
                        heelbone.tail = newbone.head - Vector((0,maxy,0))
                        piece.parent.iktarget = heelbone
                    else:
                        #todo this is not a foot
                        tailpos = piece.worldpos + Vector((0, -miny, minz))
                    # TODO we are also kind of a foot if we only have children with no meshes.
                else:
                    tailpos =  piece.worldpos+Vector((0,-5,0))
            newbone.tail = tailpos
            print ("trying to add bone to %s\nat head:%s \ntail:%s"%(piece,newbone.head,newbone.tail))
            piece.bone = newbone
        #return
        print ("=====Reparenting Bone-Bones=======")
        
        for name,piece in pieces.items():
            if piece.parent is not None:
                piece.bone.parent = piece.parent.bone      
  
        bpy.ops.object.editmode_toggle() # i have no idea what im doing
        bpy.ops.object.posemode_toggle()
        
        
        print ("=====Setting IK Targets=======")
        
        for name,piece in pieces.items():
            if piece.iktarget is not None:
                
                chainlength = 0
                chainpos = piece
                while(len(chainpos.children) ==1  and chainpos.parent is not None):
                    chainlength +=1
                    chainpos = chainpos.parent
                print ('Adding iktarget to ',piece.name,'chain_length = ',chainlength)
                constraint = armature_object.pose.bones[piece.bonename].constraints.new('IK')
                constraint.target = armature_object
                constraint.subtarget = 'iktarget.'+piece.parent.bonename
                constraint.chain_count = chainlength
      
        print ("=====Parenting meshes to bones=======")
        #getting desperate here: https://blender.stackexchange.com/questions/77465/python-how-to-parent-an-object-to-a-bone-without-transformation
        for name,piece in pieces.items():
            
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
        
def register():
    bpy.utils.register_class(SkeletorOperator)
    bpy.utils.register_class(SkeletorRotator)
    bpy.utils.register_class(Skelepanel)
    
def unregister():
    
    bpy.utils.unregister_class(SkeletorOperator)
    bpy.utils.unregister_class(SkeletorRotator)
    bpy.utils.unregister_class(Skelepanel)
    
if __name__ == "__main__":
    register()
    
    
    
