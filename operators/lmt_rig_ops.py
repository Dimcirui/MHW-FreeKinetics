# -*- coding: utf-8 -*-
"""
Created on Sat Aug 14 19:00:29 2021

@author: AsteriskAmpersand
"""
import bpy
import os
from bpy.app.handlers import persistent
from mathutils import Vector
from ..blender.blenderOps import fetchBoneFunction,animationLength,completeBasis,boneNameToId
from ..blender.tetherOps import updateAnimationBoneFunctions,boneFunctionId
from ..ui.HKIcons import pcoll
# Left Leg Orientation and IK
# 250 -> 16
# Right Leg Orientation and IK
# 249 -> 20
# Head (No Rotation)
# 252 -> 4
# Neck (No Rotation)
# 254 -> 3
# Right Hand 
# 247 -> 12
# Left Hand
# 248 -> 8


def getRigs(self,context):
    return [(obj.name,obj.name,"") for obj in bpy.data.objects if obj.type == "ARMATURE" and "FreeHK_GuideClone_" not in obj.name]

def getMHWArmatures(self,context):
    return [(obj.name,obj.name,"") for obj in bpy.data.objects if obj.type == "ARMATURE" and "FreeHK_GuideClone_" not in obj.name]


# ---------------------------------------------------------------------------
# External .bmap support
# A .bmap is a source-rig -> MHW bone map produced by external retarget tooling.
# Format: blank-line-separated 4-line records --
#   <targetMhBone>%<bool>%<space>%<x,y,z>%<x,y,z>%<scale>%<bool>%<bool>%<axis>%
#   <sourceBoneName>
#   <bool>
#   <bool>
# target "None" / "" means the source bone is unmapped. We keep the original
# format for interoperability with existing bmap files.
# ---------------------------------------------------------------------------
def bmapDir():
    addonRoot = os.path.dirname(os.path.dirname(__file__))   # operators/ -> addon root
    d = os.path.join(addonRoot, "bmaps")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def listBmapFiles():
    try:
        return sorted(f for f in os.listdir(bmapDir()) if f.lower().endswith(".bmap"))
    except Exception:
        return []

def parseBmap(filepath):
    """Return {sourceBoneName: {target, space, pos, rot, scale, axis, flags}} for mapped
    bones only (target not None/empty)."""
    entries = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f]
    except Exception as e:
        print("Free Kinetics: failed to read bmap %s: %s" % (filepath, repr(e)))
        return entries
    def pvec(s):
        try:
            return tuple(float(x) for x in s.split(","))
        except Exception:
            return (0.0, 0.0, 0.0)
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        header = lines[i]
        name = lines[i + 1] if i + 1 < n else ""
        b1 = lines[i + 2] if i + 2 < n else ""
        b2 = lines[i + 3] if i + 3 < n else ""
        i += 4
        parts = header.split("%")
        target = parts[0].strip() if parts else ""
        if not name.strip() or not target or target == "None":
            continue
        entries[name] = {
            "target": target,
            "space": parts[2] if len(parts) > 2 else "ABSOLUTE",
            "pos": pvec(parts[3]) if len(parts) > 3 else (0.0, 0.0, 0.0),
            "rot": pvec(parts[4]) if len(parts) > 4 else (0.0, 0.0, 0.0),
            "scale": (float(parts[5]) if len(parts) > 5 and parts[5] else 1.0),
            "axis": parts[8] if len(parts) > 8 else "Y",
            "flags": (b1.strip() == "True", b2.strip() == "True"),
        }
    return entries

_bmap_enum_cache = []
def getBmapItems(self, context):
    global _bmap_enum_cache
    files = listBmapFiles()
    _bmap_enum_cache = [(f, f, "") for f in files] or [("", "(no .bmap files)", "")]
    return _bmap_enum_cache


class RigTransferData(bpy.types.PropertyGroup):
    #nextAction = bpy.props.PointerProperty(name = "Next Animation", type="Action")    
    rigType: bpy.props.EnumProperty(name = "Rig Type",
                                      items = [("Humanoid","Humanoid","Humanoid Rig"),#,pcoll["FREEHK_PL"].icon_id,0),
                                               ("Monster2","Biped Monster","Biped Monster"),#,pcoll["FREEHK_EM2"].icon_id,1),
                                               ("Monster4","Quadruped Monster","Quadruped Monster"),#,pcoll["FREEHK_EM4"].icon_id,2),
                                               ("Custom","Generic Rig","Generic Rig"),#,pcoll["FREEHK_Custom"].icon_id,3),
                                               ],
                                      default = "Humanoid")
    cat: bpy.props.BoolProperty(name = "CAT Rig", description = "Perform CAT Normalization Operations",default = False)                               
    byname: bpy.props.BoolProperty(name = "Transfer by Name", description = "Transfer Animation based on Bone Names (instead of bone functions)",default = False)
    sourceName: bpy.props.EnumProperty(name = "Source Rig", description = "Non-MHW Armature with Animation", items = getRigs)
    targetName: bpy.props.EnumProperty(name = "Target Rig", description = "MHW Armature to bake Animation into", items = getMHWArmatures) 
    bake: bpy.props.BoolProperty(name = "Bake",default = True)
    groundRoot: bpy.props.BoolProperty(name = "Root as Ground Level", description = "Set the Root as the ground level after baking",default = True)
    bmapFile: bpy.props.EnumProperty(name = "Bmap", description = "External bone map to tag the source rig with", items = getBmapItems)
    
    
class PlatformIKMapping(bpy.types.PropertyGroup):
    platformName: bpy.props.StringProperty(name = "Platform Role")
    platformBoneFunction: bpy.props.IntProperty(name = "Platform Function")
    platformBoneTarget: bpy.props.IntProperty(name = "Target Function")
    platformTracking: bpy.props.EnumProperty(name = "Tracking Type",
                                      items = [("Ground","Ground Shadow","Follows another bone at flat ground level (used for feet)"),
                                               ("Translation","Translation","Follows another bone position but not rotation (used for neck)"),
                                               ("Rotation","Rotation","Follows another bone's rotation (not used by platforms)"),
                                               ("Transform","Transform","Identically copies another bone (used by wrists)"),
                                               ])

class PlatformGroup(bpy.types.PropertyGroup):
    bone_presets: bpy.props.CollectionProperty(type=PlatformIKMapping)    


class PlatformSingleton(bpy.types.PropertyGroup):
    presets: bpy.props.CollectionProperty(type=PlatformGroup)

def setDefaultCollectionValue():
    registerPresetRigOps(bpy.context.scene.freehk_rig_ops_platform)

def onRegister(scene, depsgraph=None):
    setDefaultCollectionValue()
    # the handler isn't needed anymore, so remove it
    try:
        bpy.app.handlers.depsgraph_update_post.remove(onRegister)    
    except:
        pass

@persistent
def onFileLoaded(scene):
    onRegister(scene)

def registerPresetRigOps(platformCollection):
    if not platformCollection.presets:
        for presetn,platforms in platformDefaults.items():
            preset = platformCollection.presets.add()
            preset.name = presetn
            for name,function,default,track in platforms:
                platform = preset.bone_presets.add()
                platform.name = name
                platform.platformName = name
                platform.platformBoneFunction = function
                platform.platformBoneTarget = default
                platform.platformTracking = track

class RigTransferTools(bpy.types.Panel):
    bl_category = "MHW Tools"
    bl_idname = "FREEHK_PT_rig_props"
    bl_label = "Rig Transfer Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    addon_key = __package__.split('.')[0]
    
    def draw(self, context):
        addon = context.preferences.addons[self.addon_key]
        self.addon_props = addon.preferences
        props = bpy.context.scene.freehk_rig_ops
        layout = self.layout
        layout.prop(props,"cat")
        if not props.cat:
            layout.prop(props,"byname")
        layout.prop(props,"rigType")        
        layout.prop(props,"sourceName")
        layout.prop(props,"targetName")
        layout.prop(props,"bake")
        if props.bake:
            layout.prop(props,"groundRoot")
        row = layout.row(align = True)
        row.prop(props,"bmapFile",text = "Bmap")
        row.operator("freehk.open_bmap_folder",text = "",icon = "FILE_FOLDER")
        layout.operator("freehk.apply_bmap",icon = "BONE_DATA")
        layout.operator("freehk.rig_transfer",icon = "MOD_ARMATURE")
        #col = layout.column(align = True)
        platform = bpy.context.scene.freehk_rig_ops_platform
        for bone in platform.presets[props.rigType].bone_presets:
            box = layout.box()
            box = box.column(align=True)
            box.label(text=bone.platformName)
            row = box.row(align = True)
            if props.rigType == "Custom":
                row.prop(bone,"platformBoneFunction")
            else:
                row.label(text="Platform Function: "+str(bone.platformBoneFunction))
            row.prop(bone,"platformBoneTarget")
            box.prop(bone,"platformTracking")
                

platformDefaults = {
                    "Humanoid":[("Neck",254,3,"Translation"),
                                ("Head",252,4,"Translation"),
                                ("Right Wrist",247,12,"Transform"),
                                ("Left Wrist",248,8,"Transform"),
                                ("Right Leg",249,20,"Transform"),
                                ("Left Leg",250,16,"Transform")],
                    
                    "Monster2":[("Neck Base",251,3,"Translation"),
                                ("Head",252,3,"Translation"),
                                ("Neck",254,3,"Translation"),
                                ("Right Leg",249,90,"Ground"),
                                ("Left Leg",250,80,"Ground"),
                                ("Unknown",253,-1,"Ground")],
    
                    "Monster4":[("Neck Base",251,3,"Translation"),
                                ("Head",252,3,"Translation"),
                                ("Neck",254,3,"Translation"),
                                ("Front Right Leg",247,-2,"Ground"),
                                ("Front Left Leg",248,-2,"Ground"),
                                ("Back Right Leg",249,-2,"Ground"),
                                ("Back Left Leg",250,-2,"Ground"),
                                ("Unknown",253,-1,"Ground")],
    
                    "Custom":[("Platform 0",247,-2,"Transform"),
                            ("Platform 1",248,-2,"Transform"),
                            ("Platform 2",249,-2,"Transform"),
                            ("Platform 3",250,-2,"Transform"),
                            ("Platform 4",251,-2,"Transform"),
                            ("Platform 5",252,-2,"Transform"),
                            ("Platform 6",253,-2,"Transform"),
                            ("Platform 7",254,-2,"Transform"),
                            ("Platform 8",255,-2,"Transform")],
                    }
    

class AnimationMissing(Exception):
    pass

#Source is a MHW Metarig with exotic animations
#Target is a MHW Basic Rig with orthogonal arm elements etc.

#source = ""
#target = ""

def clearConstraints(skeleton,action):
    delete = set()
    valid = {}
    for bone in skeleton.pose.bones:
        if bone not in valid:
            valid[bone] = set()
        for constraint in bone.constraints:
            if constraint.type == "COPY_ROTATION":
                valid[bone].add("rotation_euler")
                valid[bone].add("rotation_quaternion")
            elif constraint.type == "COPY_LOCATION":
                valid[bone].add("location")
            elif constraint.type == "COPY_SCALE":
                valid[bone].add("scale")
            elif constraint.type == "COPY_TRANSFORMS":
                valid[bone].add("rotation_euler")
                valid[bone].add("rotation_quaternion")
                valid[bone].add("location")
                valid[bone].add("scale")
            else:
                raise KeyError(constraint.type)
        print(bone.name)
        print(valid[bone])
            
    
    for fcurve in action.fcurves:
        if "." not in fcurve.data_path:
            continue
        d = fcurve.data_path.split(".")
        bone,transform = '.'.join(d[:-1]),d[-1]
        pbone = skeleton.path_resolve(bone)
        if not(pbone in valid and transform in valid[pbone]):
            delete.add(fcurve)
        if transform == "scale":
            if all((kf.co[1] == 1 for kf in fcurve.keyframe_points)):
                delete.add(fcurve)
            
    for c in delete:
        action.fcurves.remove(c)
            
    for bone in skeleton.pose.bones:
        constraints = list(bone.constraints)
        for c in constraints:
            bone.constraints.remove(c)

def bakeAnimation(context,target):
    context.view_layer.update()
    prev_mode = target.mode # save
    selection = [obj for obj in bpy.context.scene.objects if obj.select_get()]
    for obj in selection: obj.select_set(False)
    active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = target
    target.select_set(True)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.nla.bake(frame_start=context.scene.frame_start, 
                     frame_end=context.scene.frame_end, 
                     step=1, 
                     only_selected=False, 
                     visual_keying=True, 
                     clear_constraints=False, 
                     clear_parents=False, 
                     use_current_action=True, 
                     bake_types={'POSE'})
    clearConstraints(active,active.animation_data.action)
    #Don't Clear Constraints
    #Use them to know what parts of the animation to delete after the baking process
    target.select_set(False)
    for obj in selection: obj.select_set(True)
    bpy.ops.object.mode_set(mode=prev_mode) # restore
    bpy.context.view_layer.objects.active = active

def muteGlobal(catAction):
    for fcurve in catAction:
        if "." not in fcurve.data_path:
            fcurve.mute = True

def getBoneFunction(bone):
    return boneFunctionId(bone)


trackerName = "__Animation_Tracker_Bone__"
class RigAnimationTransfer(bpy.types.Operator):
    bl_idname = "freehk.rig_transfer"
    bl_label = "Rig Transfer"
    bl_options = {'REGISTER', 'PRESET', 'UNDO'}
    bl_description = "Transfer Animation from Rig to MHW Skeleton"
    #sourceName = bpy.props.EnumProperty(name = "Source Rig", description = "Non-MHW Armature with Animation", items = getRigs)
    #targetName = bpy.props.EnumProperty(name = "Target Rig", description = "MHW Armature to bake Animation into", items = getMHWArmatures) 
    #bake = bpy.props.BoolProperty(name = "Bake",default = True)
    #groundRoot = bpy.props.BoolProperty(name = "Root as Ground Level", description = "Set the Root as the ground level after baking",default = True)

    #def invoke(self, context, event):
    #    return context.window_manager.invoke_props_dialog(self)

    #def draw(self, context):
    #    row = self.layout
    #    row.prop(self, "sourceName")
    #    row.prop(self, "targetName")
    #    row.prop(self, "bake")
    #    row.prop(self, "groundRoot")
    
    def addMissingTrackers(self,boneMapping):
        matchedPairs = self.constraintFallthrough.items()#[(250,16),(249,20),(252,4),(254,3),(247,12),(248,8)]
        for l,r in matchedPairs:
            if l not in boneMapping:
                if r in boneMapping:
                    boneMapping[l] = boneMapping[r]
        return
    
    humanoidCases = {"CTRL_Root":-1,
                        "CTRL_Leg_IK_L":250,
                        "CTRL_Leg_IK_R":249,
                        "CTRL_Hand_IK_L":248,
                        "CTRL_Hand_IK_R":247
                        }
    
    def addSpecialCases(self,mapper,bone):
        if not self.humanoid:
            return
        candidate = None
        candidates = {trackerName+c:v for c,v in self.humanoidCases.items()}
        if bone.name in candidates:
            candidate = candidates[bone.name]
        if candidate and candidate not in mapper:
            mapper[candidate] = bone
            
    def orthogonalizeSpecialCases(self,bone):
        if bone.name in self.humanoidCases:
            return self.humanoidCases[bone.name]
        else:
            return None
    
    def groundedConstraint(self,bone,target):
        targetArmature,targetBone = target
        c = bone.constraints.new("COPY_LOCATION")
        c.target = targetArmature
        c.subtarget = targetBone.name
        c.use_y = False
        c = bone.constraints.new("COPY_ROTATION")
        c.target = targetArmature
        c.subtarget = targetBone.name
        c.use_x = False
        c.use_z = False
        if hasattr(self,"ground") and self.ground:
            c = bone.constraints.new("COPY_LOCATION")
            c.target = targetArmature
            c.subtarget = self.ground
            c.use_x = False
            c.use_z = False
    @staticmethod
    def translationConstraint(bone,target):
        targetArmature,targetBone = target
        c = bone.constraints.new("COPY_LOCATION")
        c.target = targetArmature
        c.subtarget = targetBone.name
    @staticmethod
    def localTranslationConstraint(bone,target):
        targetArmature,targetBone = target
        c = bone.constraints.new("COPY_LOCATION")
        c.target = targetArmature
        c.subtarget = targetBone.name
        c.target_space = "LOCAL_WITH_PARENT"
        c.owner_space = "LOCAL_WITH_PARENT"
    @staticmethod
    def rotationConstraint(bone,target):
        targetArmature,targetBone = target
        c = bone.constraints.new("COPY_ROTATION")
        c.target = targetArmature
        c.subtarget = targetBone.name
    @staticmethod
    def transformConstraint(bone,target):
        targetArmature,targetBone = target
        c = bone.constraints.new("COPY_TRANSFORMS")
        c.target = targetArmature
        c.subtarget = targetBone.name
    
    def getConstraintMaker(self,bf):
        if bf in [-1]:
            return self.transformConstraint
        if bf in [0]:
            return self.localTranslationConstraint
        if bf in self.constraintMapDict:
            return self.constraintMapDict[bf]
        #if bf in [252,254]:
        #    return self.translationConstraint
        #if bf in [-1,247,248]:
        #    return self.transformConstraint
        #if bf in [249,250]:
        #    return self.groundedConstraint
        return self.rotationConstraint
    
    
    @staticmethod
    def doubleBoneDict(repeatableDict):
        new = {}
        for key,val in repeatableDict.items():
            if val.name not in new:
                new[val.name] = set()
            new[val.name].add(key)
        return new
    
    def addConstraints(self,source,copy,target):
        targetMapper = {}
        for bone in target.pose.bones:
            bf = getBoneFunction(bone)
            if bf is not None:
                targetMapper[bf] = bone
        
        boneMapper = {}
        for bone in copy.pose.bones:
            bf = getBoneFunction(bone)
            if bf is not None and "__orthogonalizer__" in bone:
                boneMapper[bf] = bone
            self.addSpecialCases(boneMapper,bone)
        self.addMissingTrackers(boneMapper)
        clonableBones = self.doubleBoneDict(boneMapper)
        
        self.ground = boneMapper[-1].name if -1 in boneMapper else None            
            
        #clonableBones = { bone.name:func for func,bone in boneMapper.items()}
        for bone in copy.pose.bones:            
            subtarget = bone
            self.transformConstraint(bone,(source,subtarget))
            if bone.name in clonableBones:
                for bf in clonableBones[bone.name]:
                    #Create the constraint linking the pair of bones
                    if bf in targetMapper:
                        subtarget = bone
                        constraintMaker = self.getConstraintMaker(bf)
                        constraintMaker(targetMapper[bf],(copy,subtarget))
        return
    
    def calculateDelta(self,bf,boneMapper):
        if bf in boneMapper:
            orthogonal = boneMapper[bf]
            delta = (orthogonal.matrix @ Vector((0,1,0,0))).normalized().to_3d()
        else:
            delta = Vector((0,1,0))
        return delta
    
    def generateOrthogonalizer(self,copy,target):
        boneMapper = {}
        for bone in target.pose.bones:
            bf = getBoneFunction(bone)
            if bf is not None:
                boneMapper[bf] = bone      
        
        prev_mode = copy.mode # save
        active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = copy
        bpy.ops.object.mode_set(mode='EDIT')
        additions = []
        ebs = copy.data.edit_bones
        for bone,ebone in zip(copy.pose.bones,ebs):
            bf = getBoneFunction(bone)            
            if bf is not None:
                delta = self.calculateDelta(bf,boneMapper)
                head = bone.head
                additions.append((trackerName+bone.name,head,delta,ebone,bf))
            elif self.humanoid:
                bf = self.orthogonalizeSpecialCases(bone)
                if bf is not None:
                    delta = self.calculateDelta(bf,boneMapper)
                    head = bone.head
                    additions.append((trackerName+bone.name,head,delta,ebone,None))
                
                
    
        orthogonal = {}
        for name,head,delta,parent,bf in additions:
            eb = ebs.new(name)
            eb.parent = parent
            eb.tail = head+delta
            eb.head = head
            eb.hide = True
            orthogonal[eb.name] = bf
            
        bpy.ops.object.mode_set(mode=prev_mode) # restore
        bpy.context.view_layer.objects.active = active
        for bone in copy.pose.bones:
            if bone.name in orthogonal:
                bone["__orthogonalizer__"] = True
                bone["boneFunction"] = orthogonal[bone.name]
    
    def bakeOperation(self,context,source,target):
        if not source.animation_data or not source.animation_data.action:
            raise AnimationMissing("No animation data to bake")
        actionname = "FreeHK_"+source.animation_data.action.name
        if not target.animation_data:
            animData = target.animation_data_create()
        else:
            animData = target.animation_data
        newAction = bpy.data.actions.new(actionname)
        animData.action = newAction
        bakeAnimation(context,target)
        return newAction


    #Clone Armature
    @staticmethod
    def cloneArmature(source,copyAction = True):
        #copy = source.copy()
        copy = bpy.data.objects.new('FreeHK_GuideClone_'+source.name, source.data)
        bpy.context.scene.collection.objects.link(copy)
        if copyAction and source.animation_data:
            if source.animation_data.action:
                new_action = bpy.data.actions.new(name = "FreeHK_"+source.animation_data.action.name)
                copy.animation_data_create()
                copy.animation_data.action = new_action
            else:
                raise AnimationMissing()
        bpy.context.view_layer.update()
        
        functionCloning = {}
        for sourcePB in source.pose.bones:
            bf = getBoneFunction(sourcePB)
            if bf is not None:
                functionCloning[sourcePB.name] = bf                
        for copyPB in copy.pose.bones:
            if copyPB.name in functionCloning:
                copyPB["boneFunction"] = functionCloning[copyPB.name]
                
        #copy.animation_data_clear()
        copy.modifiers.clear()
        copy.constraints.clear()
        return copy

    def deleteHelper(self,mesh):
        objs = bpy.data.objects
        objs.remove(objs[mesh.name], do_unlink=True)
        return
    
    def nullRootY(self,action):
        for fcurve in action.fcurves:
            if fetchBoneFunction(fcurve) == -1 and fcurve.array_index == 1 and "location" in fcurve.data_path.split(".")[-1]:
                for kf in fcurve.keyframe_points:
                    kf.co[1] = 0
                fcurve.update()
    
    def FreeHKProps(self,action,target):
        updateAnimationBoneFunctions(target,action)
        action.freehk.tetherFrame = target
        action.freehk.starType = "LMT_Action"
        action.freehk.frameCount = animationLength(action)
        completeBasis(action)
    
    def enumerateBoneFunctions(self,skeleton):
        bf = {}
        for bone in skeleton.pose.bones:
            bfun = getBoneFunction(bone)
            if bfun is not None:
                bf[bfun] = bone.name
        return bf
    
    def mapNames(self,context,source,target):
        bfs = self.enumerateBoneFunctions(source)
        mapper = {}
        for bone in target.pose.bones:
            bf = getBoneFunction(bone)
            if bf is not None:
                if bf in bfs:
                    mapper[bfs[bf]] = bone.name
        for mesh in context.scene.objects:
            if mesh.type == "MESH":
                for mod in mesh.modifiers:
                    if mod.type == "ARMATURE" and mod.object == source:
                        for group in mesh.vertex_groups:
                            if group.name in mapper:
                                group.name = mapper[group.name]
                        mod.object = target
    
    def generatePlatformMapping(self,mapping):
        trackingMap = {"Ground":self.groundedConstraint,
                        "Translation":self.translationConstraint,
                        "Rotation":self.rotationConstraint,
                        "Transform":self.transformConstraint,
                        }
        constraintMapDict = {}#From true bone function to constraint
        constraintFallthrough = {}#From platform  to substitute
        for boneEntry in mapping:
            function = boneEntry.platformBoneFunction
            target = boneEntry.platformBoneTarget
            tracking = boneEntry.platformTracking
            constraintMapDict[function] = trackingMap[tracking]
            constraintFallthrough[function] = target
        self.constraintMapDict = constraintMapDict
        self.constraintFallthrough = constraintFallthrough
    
    def extractPanelData(self,ctx):
        options = ctx.scene.freehk_rig_ops
        mapping = ctx.scene.freehk_rig_ops_platform.presets[options.rigType].bone_presets
        self.sourceName = options.sourceName
        self.targetName = options.targetName
        self.cat = options.cat
        self.byname = options.byname
        self.humanoid = options.rigType == "Humanoid"
        self.bake = options.bake
        self.groundRoot = options.groundRoot
        self.platformMapping = self.generatePlatformMapping(mapping)
    
    def transferFunctions(self,source,target):
        bonemap = {}
        for bone in source.pose.bones:
            bf = getBoneFunction(bone)
            if bf is not None:
                bonemap[bone.name] = bf
        for bone in target.pose.bones:
            if bone.name in bonemap:
                bone["boneFunction"] = bonemap[bone.name]
                bone.bone["boneFunction"] = bonemap[bone.name]
    
    def execute(self,context):
        self.extractPanelData(context)
        if self.sourceName not in bpy.data.objects:
            return {'FINISHED'}
        if self.targetName not in bpy.data.objects:
            return {'FINISHED'}
        if self.sourceName == self.targetName:
            return {'FINISHED'}
        source = bpy.data.objects[self.sourceName]
        target = bpy.data.objects[self.targetName]
        self.source = source
        self.target = target
        if not source.animation_data or not source.animation_data.action:
            return {'FINISHED'}
        if self.cat:
            functionalizeArmature(source)
            applyTransformSkeleton(source,context)  
            muteGlobal(source.animation_data.action.fcurves)
        elif self.byname:
            self.transferFunctions(target,source)
        copy = self.cloneArmature(source,copyAction = False)
        self.generateOrthogonalizer(copy, target)
        self.addConstraints(source,copy,target)
        if self.bake:
            action = self.bakeOperation(context,source,target)
            self.FreeHKProps(action,target)
            if self.groundRoot:
                self.nullRootY(action) 
            self.deleteHelper(copy)
            self.mapNames(context,source,target)
        return {'FINISHED'}


def boneFunctionFromString(string):
    try:
        return int(string.split(".")[-1])
    except:
        None
    
def functionalizeArmature(target):
    for bone in target.pose.bones:
        bf = boneFunctionFromString(bone.name)
        if bf is not None:
            bone.bone["boneFunction"] = bf
            bone["boneFunction"] = bf

def applyTransform(obj):
    sel_objs = [objs for objs in bpy.context.selected_objects]
    for objs in sel_objs: objs.select_set(False)
    prev_mode = obj.mode # save
    old_active = bpy.context.view_layer.objects.active
    #
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.transform_apply( location = True, scale = True, rotation = True)
    #
    bpy.ops.object.mode_set(mode=prev_mode) # restore
    bpy.context.view_layer.objects.active = old_active
    obj.select_set(False)
    for objs in sel_objs: objs.select_set(True)
    bpy.context.view_layer.update()
    
def applyTransformSkeleton(skeleton,context):
    applyTransform(skeleton)
    for mesh in context.scene.objects:
        if mesh.type == "MESH":
            for mod in mesh.modifiers:
                if mod.type == "ARMATURE" and mod.object == skeleton:
                    applyTransform(mod)
                        
class CATBoneFunction(bpy.types.Operator):
    bl_idname = "freehk.cat_bone_function"
    bl_label = "Bone Functions for CAT Rig"
    bl_options = {'REGISTER', 'PRESET', 'UNDO'}
    bl_description = "Assign Bone Functions to CAT rig"
    
    @classmethod
    def poll(cls,context):
        return context.active_object and context.active_object.type == "ARMATURE"
    
    def execute(self,context):
        functionalizeArmature(context.active_object)
        return {"FINISHED"}
    
    
class OpenBmapFolder(bpy.types.Operator):
    bl_idname = "freehk.open_bmap_folder"
    bl_label = "Open Bmap Folder"
    bl_description = "Open the folder where .bmap retarget maps are kept (drop your .bmap files here)"
    def execute(self, context):
        try:
            bpy.ops.wm.path_open(filepath=bmapDir())
        except Exception as e:
            self.report({'WARNING'}, "Could not open folder: %s" % repr(e))
            return {'CANCELLED'}
        return {'FINISHED'}

class ApplyBmap(bpy.types.Operator):
    bl_idname = "freehk.apply_bmap"
    bl_label = "Apply Bmap to Source"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = ("Tag the Source rig's bones with MHW bone functions from the selected "
                      ".bmap, so Rig Transfer can map them. Non-destructive: only adds a "
                      "'boneFunction' custom property to matching source bones.")
    def execute(self, context):
        props = context.scene.freehk_rig_ops
        fname = props.bmapFile
        if not fname:
            self.report({'WARNING'}, "No .bmap selected (drop files via Open Bmap Folder)")
            return {'CANCELLED'}
        source = bpy.data.objects.get(props.sourceName)
        if source is None or source.type != 'ARMATURE':
            self.report({'WARNING'}, "Source rig not found")
            return {'CANCELLED'}
        entries = parseBmap(os.path.join(bmapDir(), fname))
        if not entries:
            self.report({'WARNING'}, "Bmap empty or unreadable")
            return {'CANCELLED'}
        tagged = 0
        for pb in source.pose.bones:
            e = entries.get(pb.name)
            if not e:
                continue
            fid = boneNameToId(e["target"])
            if fid is not None:
                pb["boneFunction"] = fid
                pb.bone["boneFunction"] = fid
                tagged += 1
        self.report({'INFO'}, "Bmap '%s' applied: %d/%d source bones tagged"
                    % (fname, tagged, len(source.pose.bones)))
        return {'FINISHED'}

classes = [RigTransferData, PlatformIKMapping, PlatformGroup, PlatformSingleton, RigTransferTools,RigAnimationTransfer,CATBoneFunction,OpenBmapFolder,ApplyBmap]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.freehk_rig_ops = bpy.props.PointerProperty(type=RigTransferData)
    bpy.types.Scene.freehk_rig_ops_platform = bpy.props.PointerProperty(type=PlatformSingleton)
    bpy.app.handlers.depsgraph_update_post.append(onRegister)
    bpy.app.handlers.load_post.append(onFileLoaded)
    
def unregister():
    del bpy.types.Scene.freehk_rig_ops
    del bpy.types.Scene.freehk_rig_ops_platform
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.app.handlers.load_post.remove(onFileLoaded)

