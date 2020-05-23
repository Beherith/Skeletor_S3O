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
        rootobject, rootname = getS3ORootObject()
        rootobject.rotation_euler[0] = pi/2.0 
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

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
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
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
                #continue
                piece.parent = pieces[piece.object.parent.name]
                piece.parent.children.append(piece)
                print (piece.name,'->', piece.parent.name)
        
        #final check that we have all set:
        rootpiece.recursefixworldpos(Vector((0,0,0)))
        print ("----------Final check:-----------")
        for k,v in pieces.items():
            print (k,v)
        
        #set the cursor to origin:
        bpy.ops.transform.translate(value=(0, 0, 0), orient_type='GLOBAL', orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)), orient_matrix_type='GLOBAL', mirror=True, use_proportional_edit=False, proportional_edit_falloff='SMOOTH', proportional_size=1, use_proportional_connected=False, use_proportional_projected=False, cursor_transform=True, release_confirm=True)

        
        scene = context.scene
        for obj in scene.objects:
            obj.select_set(False)
            obj.rotation_mode = 'ZXY'
        
        #add an armature!
        arm_data = bpy.data.armatures.new("Armature")
        
        armature_object =  bpy.data.objects.new("Armature", arm_data)
        armature_object.location=rootpiece.loc
        armature_object.show_in_front = True
        armature_object.rotation_mode = 'ZXY'
        
        context.collection.objects.link(armature_object)
        
        armature_object.select_set(True)
        
        context.view_layer.objects.active = armature_object
        
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        def get_endpoint(piece):
            if len(piece.children) == 1:
                #EZ return loc
                return piece.children[0].loc
            elif len(piece.children)>= 2:
                sumvec = Vector((0,0,0))
                for child in piece.children:
                    sumvec = sumvec + child.loc
                sumvec = sumvec / float(len(piece.children))
                return sumvec
            else: # end pieces point forward :D
                return Vector ((0,0,0))
        
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        
        for name, piece in pieces.items():
            newbone = arm_data.edit_bones.new(piece.name)
            newbone.name = piece.name
            
            #TODO CHANGE TO POSE MODE TO SET THESE!
            #newbone.rotation_mode = 'ZXY'
            
            newbone.head = piece.loc 
            tailpos =  piece.loc+Vector((0,0,10))
            if len(piece.children)==1:
                tailpos = piece.children[0].loc
            elif len(piece.children)>=2:
                tailpos = Vector((0,0,0))
                for child in piece.children:
                    tailpos = tailpos + child.loc
                tailpos = tailpos /len(piece.children)
            else: #end piece
                #TODO: CHECK FOR GEOMETRY, is it a foot or an arm or a tentacle
                if piece.mesh is not None:
                    minz = 100000
                    miny = 1000000
                    maxy = -1000000
                    for vertex in piece.mesh.vertices:
                        minz = min(minz,vertex.co[2])
                        miny = min(miny,vertex.co[1])
                        maxy = max(maxy,vertex.co[1])
                    if minz <= 2.0: 
                        #this looks like a foot
                        tailpos = piece.loc + Vector((0, miny, minz))
                        #better add the heel IK thing too XD
                        heelbone = arm_data.edit_bones.new(piece.parent.name+'.iktarget')
                        heelbone.head = newbone.head
                        heelbone.tail = newbone.head + Vector((0,maxy,0))
                        piece.parent.iktarget = heelbone
                    else:
                        #todo this is not a foot
                        tailpos = piece.loc + Vector((0, miny, minz))
                    # TODO we are also kind of a foot if we only have children with no meshes.
                else:
                    tailpos =  piece.loc+Vector((0,-5,0))
            newbone.tail = tailpos
            piece.bone = newbone
        
        for name,piece in pieces.items():
            if piece.parent is not None:
                piece.bone.parent = piece.parent.bone      
               
        bpy.ops.object.editmode_toggle() # i have no idea what im doing
        bpy.ops.object.posemode_toggle()
        
        for name,piece in pieces.items():
            if piece.iktarget is not None:
                
                chainlength = 0
                chainpos = piece
                while(len(chainpos.children) ==1  and chainpos.parent is not None):
                    chainlength +=1
                    chainpos = chainpos.parent
                print ('Adding iktarget to ',piece.name,'chain_length = ',chainlength)
                constraint = armature_object.pose.bones[piece.name].constraints.new('IK')
                constraint.target = armature_object
                constraint.subtarget = piece.name+'.iktarget'
                constraint.chain_count = chainlength

        #getting desperate here: https://blender.stackexchange.com/questions/77465/python-how-to-parent-an-object-to-a-bone-without-transformation
        for name,piece in pieces.items():
            
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
            ob = piece.object
            bpy.ops.object.select_all(action = 'DESELECT')
            armature_object.select_set(True)
            bpy.context.view_layer.objects.active = armature_object
            bpy.ops.object.mode_set(mode='EDIT')
            parent_bone = name
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
    
    
    
