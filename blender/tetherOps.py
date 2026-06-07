# -*- coding: utf-8 -*-
"""
Created on Mon Jul 26 20:37:56 2021

@author: AsteriskAmpersand
"""
import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
from mathutils import Matrix,Vector,Quaternion,Euler
from math import radians
from .blenderOps import breakPath,transformSize,setBoneFunction,fetchBoneFunction,replaceBoneName,customizeFCurve,boneNameToId

# Coordinate frame that modern MHW Model Editor (3.x+) bakes into the armature on
# mod3 import: rotate +90 deg about X (Y-up -> Z-up) and scale 0.01.
# The legacy mod3 importer FreeKinetics was built for kept bones in MHW-native space
# and provided an explicit "Root" bone (boneFunction -1) as the parent of the top
# bones. The modern importer drops that Root and bakes this conversion instead, which
# leaves the parentless top bones (e.g. 000, 101, 102, 247-253) without the implicit
# Root frame -> they fly off by M.inv (x100 scale, -90 deg). We re-supply it as a
# virtual root parent for parentless bones only.
MHW_IMPORT_MATRIX = Matrix.Rotation(radians(90.0), 4, 'X') @ Matrix.Scale(0.01, 4)

def virtualRootMatrix(bone):
    """Armature-space frame to use as the implicit parent of a parentless bone.
    Identity for legacy armatures that still carry an explicit 'Root' bone;
    the modern mod3 import conversion otherwise."""
    idd = getattr(bone, "id_data", None)
    arm = idd.data if (idd is not None and getattr(idd, "type", None) == 'ARMATURE') else idd
    try:
        if "Root" in arm.bones:
            return Matrix.Identity(4)
    except Exception:
        pass
    return MHW_IMPORT_MATRIX

def boneFunctionId(b):
    """MHW bone-function id for an armature bone (PoseBone or Bone), or None.
    Priority: legacy 'boneFunction' custom property, then bone-name parsing
    (MhBone_083 / bonefunction_083 / BoneFunction.083)."""
    if "boneFunction" in b:
        return b["boneFunction"]
    bone = getattr(b, "bone", None)
    if bone is not None and "boneFunction" in bone:
        return bone["boneFunction"]
    return boneNameToId(b.name)

class FreeHK_IncompleteFCurve(Exception):
    # Constructor or Initializer 
    def __init__(self, errlist): 
        self.errors = errlist

def extractNonReference(fcurveSet):
    sortedTuples = [list(sorted(filter(lambda x: x.co[0]>=0,fcurve.keyframe_points),key = lambda x: x.co[0])) for fcurve in fcurveSet]
    return sortedTuples

def extractChannels(fcurveSet):
    sortedTuples = [list(sorted(fcurve.keyframe_points,key = lambda x: x.co[0])) for fcurve in sorted(fcurveSet,key = lambda x: x.array_index)]
    return sortedTuples

def extractAllFrames(fcurveSet):
    channels = extractChannels(fcurveSet)
    return [tuple(map(lambda x: x.co[1],frameTuple)) for frameTuple in zip(*channels)]

def channelToVec(channels):
    return list(zip(*channels))

def vecToChannels(vecs):
    return channelToVec(vecs)

def verifySynchronicity(fcurveSet):
    sortedKeyframes = extractChannels(fcurveSet)
    lengths = list(map(len,sortedKeyframes))
    maxlength = max(lengths)
    minlength = min(lengths)
    if maxlength != minlength:
        return False
    for timeTuple in zip(*sortedKeyframes):
        timings = [t.co[0] for t in timeTuple]
        maxima,minima = max(timings),min(timings)
        if maxima != minima:
            return False
    return True

CHANNEL_COUNT = 0
SYNCHRONICITY = 1

def verifyTuplings(action):
    propertyDictionary = {}
    propertySize = {}
    errors = []
    for fcurve in action.fcurves:
        actionPath = fcurve.data_path
        transformTarget,transformType =  breakPath(actionPath)
        tsize = transformSize(transformType)
        fold = fcurve.array_index//4
        if not tsize:
            continue
        else:
            propertySize[actionPath] = tsize
        if (actionPath,fold) not in propertyDictionary:
            propertyDictionary[(actionPath,fold)] = []
        propertyDictionary[(actionPath,fold)].append(fcurve)
    for (actionPath,fold) in propertyDictionary:
        if len(propertyDictionary[(actionPath,fold)]) != propertySize[actionPath]:
            errors.append(((actionPath,fold),CHANNEL_COUNT))
        if not verifySynchronicity(propertyDictionary[(actionPath,fold)]):
            errors.append(((actionPath,fold),SYNCHRONICITY))
    return errors, propertyDictionary

def extractReference(fcurve):
    reference = None
    for keyf in fcurve:
        if keyf.co[0] == -1:
            reference = keyf.co[1]
    if reference is None:
        reference = 0
    return reference
        
def reconstructReference(fcurveSet):
    return [extractReference(fcurve) for fcurve in sorted(fcurveSet,lambda x: x.array_index)]

def collectTuplings(action):
    errs,curves = verifyTuplings(action)
    tuplings = []
    if errs:
        #TODO - Handle incomplete tuplings on more "idiot proof" modes
        raise FreeHK_IncompleteFCurve(errs)
    for (path,fold),fcurves in curves.items():
        #referenceFrame = reconstructReference(fcurves)
        keyframes = extractAllFrames(fcurves)
        tuplings.append(((path,fold),fcurves,keyframes))
    return tuplings
    #TODO - Patch from here on as well
        
def insertVectorialKeymatches(fcurveSet,channelReplacements):
    sortedChannels = extractChannels(fcurveSet)
    for channel,newframes in zip(sortedChannels,channelReplacements):
        for frame,value in zip(channel,newframes):
            frame.co[1] = value
    for f in fcurveSet:
        f.update()
    return

def updateAnimationBoneFunctions(skeleton,action):
    for fcurve in action.fcurves:
        try:
            pbone = getBoneFromPath(skeleton,fcurve.data_path)
            function = boneFunctionId(pbone)
            if function is None: raise ValueError("Functionless Bone %s"%pbone.name)
            setBoneFunction(fcurve,function)
        except:
            #TODO - Need an error handler to log the errors happening here
            pass

def boneFunctionMap(skeleton):
    result = {}
    for bone in skeleton.pose.bones:
        fid = boneFunctionId(bone)
        if fid is not None:
            result[fid] = bone
    return result

def updateAnimationNames(skeleton,action):
    if skeleton:        
        skeletonFunctions = boneFunctionMap(skeleton)
        for fcurve in action.fcurves:
            func = fetchBoneFunction(fcurve)
            if func in skeletonFunctions:
                nbone = skeletonFunctions[func]
                fcurve.data_path = replaceBoneName(fcurve.data_path,nbone.name)
    
def getBoneFromPath(armature,path):
    try: 
        return armature.path_resolve(path).owner.data
    except:
        return None

def scaleMatrix(vec):
    m = Matrix.Identity(4)
    for i in range(len(vec)):
        m[i][i]=vec[i]
    return m

def translationMatrix(vec):
    m = Matrix.Identity(4)
    for i in range(len(vec)):
        m[i][3]=vec[i]
    return m

def basisTransformForType(ttype):
    if ttype == "rotation_quaternion":
        return Quaternion
    elif ttype == "location":
        return Vector
    elif ttype == "scale":
        return Vector
    elif ttype == "rotation_euler":
        return Quaternion

def basicTransformsForType(ttype):
    if ttype == "rotation_quaternion":
        return lambda x: Quaternion(x)
    elif ttype == "location":
        return lambda x: Vector(x)
    elif ttype == "scale":
        return lambda x: Vector(x)
    elif ttype == "rotation_euler":
        return lambda x:  Euler(x)

def transformsForType(ttype):
    if ttype == "rotation_quaternion":
        dataRead = lambda x: Quaternion(x).to_matrix().to_4x4()
        dataWrite = lambda x: x.to_quaternion()
    elif ttype == "location":
        dataRead = lambda x: translationMatrix(Vector(x))
        dataWrite = lambda x: x.to_translation()
    elif ttype == "scale":
        dataRead = lambda x:  scaleMatrix(Vector(x))
        dataWrite = lambda x: x.to_scale()
    elif ttype == "rotation_euler":
        dataRead = lambda x:  Euler(x).to_matrix().to_4x4()
        dataWrite = lambda x: x.to_euler()
    return dataRead,dataWrite
   
def _scaledTranslation(mat, s):
    """Scale only the translation component (rotation matrices have zero
    translation so they are unaffected). Compensates the modern importer's
    baked 0.01 scale + inherit_scale='NONE', under which location basis values
    are not auto-scaled by the rig's conversion."""
    if s != 1.0:
        mat = mat.copy()
        mat.translation = mat.translation * s
    return mat

def strackerForwardTransform(bone,nmatrix):
    try:
        local = bone.bone.matrix_local.inverted()#(bone.matrix.inverted()*bone.matrix_channel)
    except:
        print(bone.name)
        print(bone.matrix)
        raise
    vr = virtualRootMatrix(bone)
    if not bone.parent:
        # Parentless top bones (body root + IK controllers 249/250/252...) were
        # children of the legacy 'Root' bone; their location is already in the right
        # space and must NOT be rescaled (rescaling collapses them to the origin).
        return local @ vr @ nmatrix
    else:
        # Parented bones: their location is a parent-relative delta and DOES need the
        # rig's import scale. Scale the INPUT so forward/inverse stay exact inverses.
        parent = bone.parent.bone.matrix_local#bone.parent.matrix_channel.inverted()*bone.parent.matrix
        nmatrix = _scaledTranslation(nmatrix, vr.to_scale()[0])
        return local @ parent @ nmatrix

def strackerInverseTransform(bone,nmatrix):
    try:
        local = bone.bone.matrix_local#(bone.matrix.inverted()*bone.matrix_channel)
    except:
        print(bone.name)
        print(bone.matrix)
        raise
    vr = virtualRootMatrix(bone)
    if not bone.parent:
        return vr.inverted() @ local @ nmatrix      # parentless: no rescale (mirror of forward)
    else:
        parent = bone.parent.bone.matrix_local#bone.parent.matrix_channel.inverted()*bone.parent.matrix
        result = parent.inverted() @ local @ nmatrix
        s = vr.to_scale()[0]
        return _scaledTranslation(result, (1.0/s) if s else 1.0)

def e_output(*args,**kwargs):
    pass

def boneTransform(bone,ttype,kfTuplets,operation):
    read,write = transformsForType(ttype)    
    return [write(operation(bone,read(keyf))) for keyf in kfTuplets]
    
def unapplyBoneTransform(bone,ttype,kfTuplets):
    return vecToChannels(boneTransform(bone,ttype,kfTuplets,strackerInverseTransform))

def applyBoneTransform(bone,ttype,kfTuplets):
    return vecToChannels(boneTransform(bone,ttype,kfTuplets,strackerForwardTransform))
        
def tetherOperator(action,tether,preUpdateFunction,updateFunction,postUpdateFunction):
    if not tether:
        return
    addon_key = __package__.split('.')[0]
    addon = bpy.context.preferences.addons[addon_key]
    implicitTether = addon.preferences.implicit_tether 
    if implicitTether:
        armature = tether
        preUpdateFunction(armature,action)
    #TODO - Handle error from missing tuplings.
    tuplings = collectTuplings(action)
    for (path,fold), fcurves, vectorKeys in tuplings:        
        animBone = getBoneFromPath(tether,path)
        if animBone:
            transformTarget,transformType =  breakPath(path)
            updatedKeyframeChannels = updateFunction(animBone,transformType,vectorKeys)
            postUpdateFunction(fcurves, updatedKeyframeChannels)
        

#before clearing the tether, assign bone functions if the armature
#has a compatible bone, even if the link isn't explicit already
#when re-tethering check the orphans for bone functions the new one might have
#and proceed to rename appropiately

#Tether TO is based on bone function (So call updateAnimationNames)
#Tether FROM is based on bone name (So call updateAnimationBoneFunction)

def _rootChannelMatrices(action):
    """Per-keyframe MHW matrices from the orphan pose.bones["Root"] channels."""
    loc=[None,None,None]; rot=[None,None,None,None]
    for fc in action.fcurves:
        if fc.data_path == 'pose.bones["Root"].location' and fc.array_index < 3:
            loc[fc.array_index]=fc
        elif fc.data_path == 'pose.bones["Root"].rotation_quaternion' and fc.array_index < 4:
            rot[fc.array_index]=fc
    if not any(loc) and not any(rot):
        return None
    frames=set()
    for fc in loc+rot:
        if fc:
            for k in fc.keyframe_points: frames.add(k.co[0])
    out=[]
    for f in sorted(frames):
        l=Vector([(loc[i].evaluate(f) if loc[i] else 0.0) for i in range(3)])
        if any(rot):
            q=Quaternion([(rot[i].evaluate(f) if rot[i] else (1.0 if i==0 else 0.0)) for i in range(4)])
        else:
            q=Quaternion()
        out.append((f, Matrix.Translation(l) @ q.to_matrix().to_4x4()))
    return out

def applyRootToObject(action, armature):
    """Map the LMT Root (boneFunction -1) channel onto the armature OBJECT's animation,
    conjugated into the rig's converted frame:  object = M . Root_mhw . M^-1 .
    Modern mod3 armatures have no explicit 'Root' bone, so the whole-character root
    motion (which used to live on that bone) is re-homed on the object. The armature's
    bones are left untouched (mod3-export safe)."""
    if armature is None:
        return
    try:
        if "Root" in armature.data.bones:   # legacy armature still drives Root via its bone
            return
    except Exception:
        return
    mats=_rootChannelMatrices(action)
    if not mats:
        return
    M=MHW_IMPORT_MATRIX; Mi=M.inverted()
    armature.rotation_mode='QUATERNION'
    for fc in list(action.fcurves):
        if fc.data_path in ("location","rotation_quaternion"):
            action.fcurves.remove(fc)
    locfc=[action.fcurves.new("location",index=i) for i in range(3)]
    rotfc=[action.fcurves.new("rotation_quaternion",index=i) for i in range(4)]
    for f,m in mats:
        om=M @ m @ Mi
        t=om.to_translation(); q=om.to_quaternion()
        for i in range(3): locfc[i].keyframe_points.insert(f,t[i],options={'FAST'})
        for i in range(4): rotfc[i].keyframe_points.insert(f,q[i],options={'FAST'})
    for fc in locfc+rotfc:
        fc.update()
    for fc in list(action.fcurves):           # drop the now-redundant orphan Root channels
        if fc.data_path.startswith('pose.bones["Root"]'):
            action.fcurves.remove(fc)

def restoreRootFromObject(action, armature):
    """Export-side inverse of applyRootToObject.
    Modern mod3 armatures have no explicit 'Root' bone, so whole-character root
    motion (LMT boneFunction -1) lives on the armature OBJECT's animation, placed
    there at import via  object = M . Root_mhw . M^-1 . Here we read it back and
    synthesize transient pose.bones["Root"] channels in MHW space
    ( Root_mhw = M^-1 . object . M ) carrying boneFunction -1, so the normal export
    pipeline writes the LMT Root entry. Those channels are NOT in the armature's
    boneFunctionMap, so the tether-inverse passes them through untouched (the values
    are already MHW-space). Returns the synthesized fcurves so the caller removes
    them after export, leaving the action's object animation intact (mod3-export safe).
    No-op for legacy armatures (explicit 'Root' bone) or when Root channels already
    exist on the action."""
    synth = []
    if armature is None:
        return synth
    try:
        if "Root" in armature.data.bones:    # legacy armature drives Root via its bone
            return synth
    except Exception:
        return synth
    for fc in action.fcurves:                # explicit Root channels already present
        if fc.data_path.startswith('pose.bones["Root"]'):
            return synth
    loc=[None,None,None]; rot=[None,None,None,None]; eul=[None,None,None]
    for fc in action.fcurves:
        if fc.data_path == "location" and fc.array_index < 3:
            loc[fc.array_index]=fc
        elif fc.data_path == "rotation_quaternion" and fc.array_index < 4:
            rot[fc.array_index]=fc
        elif fc.data_path == "rotation_euler" and fc.array_index < 3:
            eul[fc.array_index]=fc
    if not any(loc) and not any(rot) and not any(eul):
        return synth
    frames=set()
    for fc in loc+rot+eul:
        if fc:
            for k in fc.keyframe_points: frames.add(k.co[0])
    if not frames:
        return synth
    # Densify to every integer frame across the span: the LMT keyframe buffer stores the
    # inter-keyframe gap as a single byte (max 255), so sparse object keyframes (e.g. a
    # 580-frame dance keyed only at endpoints) would overflow. Per-frame keying keeps
    # every gap at 1, matching how real in-game Root tracks are stored.
    lo=int(round(min(frames))); hi=int(round(max(frames)))
    denseFrames=range(lo,hi+1) if hi>lo else sorted(frames)
    # Euler rotation order to reconstruct a rotation matrix when the object animates in
    # euler rather than quaternion (baked FBX default).
    eorder=getattr(armature,"rotation_mode","XYZ")
    if eorder not in {'XYZ','XZY','YXZ','YZX','ZXY','ZYX'}: eorder='XYZ'
    M=MHW_IMPORT_MATRIX; Mi=M.inverted()
    rl=[action.fcurves.new('pose.bones["Root"].location',index=i) for i in range(3)]
    rr=[action.fcurves.new('pose.bones["Root"].rotation_quaternion',index=i) for i in range(4)]
    for f in denseFrames:
        l=Vector([(loc[i].evaluate(f) if loc[i] else 0.0) for i in range(3)])
        if any(rot):
            q=Quaternion([(rot[i].evaluate(f) if rot[i] else (1.0 if i==0 else 0.0)) for i in range(4)])
            rotmat=q.to_matrix().to_4x4()
        elif any(eul):
            e=Euler([(eul[i].evaluate(f) if eul[i] else 0.0) for i in range(3)], eorder)
            rotmat=e.to_matrix().to_4x4()
        else:
            rotmat=Matrix.Identity(4)
        rm=Mi @ (Matrix.Translation(l) @ rotmat) @ M
        t=rm.to_translation(); rq=rm.to_quaternion()
        for i in range(3): rl[i].keyframe_points.insert(f,t[i],options={'FAST'})
        for i in range(4): rr[i].keyframe_points.insert(f,rq[i],options={'FAST'})
    synth=rl+rr
    for fc in synth:
        customizeFCurve(fc,0,-1)              # encoding auto-detect, boneFunction -1
        fc.update()
    return synth

def _inferSourceArmature(action, target):
    """The armature OBJECT currently animated by this action - its implicit source
    frame. Used when an action has no recorded tetherFrame (e.g. a baked / externally
    imported animation): its fcurve values are really expressed in the pose space of
    the rig it is posed on, NOT neutral MHW space, so a re-target must invert that rig
    first. Returns a non-target armature carrying the action, or None."""
    candidates = [o for o in bpy.data.objects
                  if o.type == 'ARMATURE' and o.animation_data
                  and o.animation_data.action == action]
    for o in candidates:
        if o is not target:
            return o
    return None

def clearReferences(action, target=None):
    tether = action.freehk.tetherFrame
    if tether is None and target is not None:
        # No recorded source. For a re-target (Transfer & Update, target set) the values
        # are usually a baked pose on some rig, not neutral MHW. Infer that rig as the
        # source so we invert it before forwarding onto the target; otherwise a lone
        # forward double-applies the rig conversion and collapses every bone to origin.
        src = _inferSourceArmature(action, target)
        if src is not None:
            tether = src
            print("Free Kinetics: inferred source tether '%s' for untethered action '%s'."
                  % (src.name, action.name))

    preUpdateFunction = updateAnimationBoneFunctions
    updateFunction = unapplyBoneTransform
    postUpdateFunction = insertVectorialKeymatches
    tetherOperator(action,tether,preUpdateFunction,updateFunction,postUpdateFunction)

    action.freehk.tetherFrame = None

def targetReferenceFromClear(action,referenceFrame):
    tether = referenceFrame

    preUpdateFunction = updateAnimationNames
    updateFunction = applyBoneTransform
    postUpdateFunction = insertVectorialKeymatches
    tetherOperator(action,tether,preUpdateFunction,updateFunction,postUpdateFunction)

    action.freehk.tetherFrame = referenceFrame
    try:
        applyRootToObject(action, referenceFrame)
    except Exception as e:
        print("FreeKinetics: root-to-object mapping skipped:", repr(e))

"""    
def prepareExportAction(action,options):
    stowed = []
    def stowActions(self,fcurves,updatedKeyframeChannels):
        stowed += updatedKeyframeChannels
    tether = action.freehk.tetherFrame
    
    if not options.applyPatchLevels(action):
        return None
        
    preUpdateFunction = updateAnimationBoneFunctions
    updateFunction = unapplyBoneTransform
    postUpdateFunction = pass
    tetherOperator(action,tether,preUpdateFunction,updateFunction,postUpdateFunction)
    
    return
"""
    
def transferTether(actions,tether):
    for action in actions:
        clearReferences(action, tether)
        targetReferenceFromClear(action, tether)

# Body IK controllers: bone-function -> (target deform bone-function, copy mode).
# Empirically tuned for the modern MhBone humanoid: hand IK tracks the PALM (057/040),
# not the wrist (012/008), and head IK tracks the head bone (004, position only, per the
# game's "Translation" platform default). Edit/extend this table to cover more rigs.
#   mode 'FULL' = location + rotation ; mode 'LOC' = location only.
# These HAVE a deform bone to follow, so the result is faithful.
IK_BODY_MAP = [
    (247, 57, 'FULL'),   # Right hand IK -> right palm
    (248, 40, 'FULL'),   # Left  hand IK -> left  palm
    (252,  4, 'LOC'),    # Head IK        -> head (position only)
]

# Ground/anchor IK controllers: bone-function -> constant MHW-space location (identity
# rotation, single reference frame). These have NO deform bone to track, so they are pinned
# to a fixed point and the result is a best-effort baseline that usually needs manual touch-up.
# Verified against the original co00_06.lmt: 253 ("ground / virtual horizon") sits at the MHW
# origin across every action; 251 (upper-body/neck-base anchor) baselines around (0,10,0).
IK_GROUND_MAP = [
    (253, (0.0,  0.0, 0.0)),   # ground anchor = MHW origin
    (251, (0.0, 10.0, 0.0)),   # neck-base / upper-body anchor: stable baseline (Y=10, X/Z=0)
]
# NOTE (Rig Transfer / bmap roadmap): when a bmap already maps a source bone onto one of
# these IK controllers (e.g. MMD's "全ての親" -> MhBone_253), the transfer should use that
# mapping directly and only fall back to recalculateBody/GroundIKBones for the IK bones the
# bmap leaves unmapped.

def _bakeAssign(armature, action):
    if not armature.animation_data:
        armature.animation_data_create()
    prev = armature.animation_data.action
    armature.animation_data.action = action
    return prev

def _wipeIKChannels(action, bone):
    path = 'pose.bones["%s"].' % bone.name
    for fcv in list(action.fcurves):
        if fcv.data_path == path + "location" or fcv.data_path == path + "rotation_quaternion":
            action.fcurves.remove(fcv)
    bone.rotation_mode = 'QUATERNION'

def _tagIKBoneFunctions(action, bones):
    for ik in bones:
        bf = boneFunctionId(ik)
        if bf is None:
            continue
        path = 'pose.bones["%s"].' % ik.name
        for fcv in action.fcurves:
            if fcv.data_path.startswith(path):
                setBoneFunction(fcv, bf)

def recalculateBodyIKBones(armature, action, mapping=None):
    """Bake the BODY IK controllers (hands, head) so each coincides in armature/pose space
    with its target deform bone, sampled at the target's own keyframes, writing into `action`.
    Fixes baked/authored animations where these controllers were left at rest (hands snap to
    the body centre in game). Action must be tethered to `armature`; export inverts to MHW.
    Non-destructive to the armature (only this action's keyframes change)."""
    if armature is None or action is None:
        return
    if mapping is None:
        mapping = IK_BODY_MAP
    fmap = boneFunctionMap(armature)
    pairs = [(fmap[ik], fmap[tg], mode) for ik, tg, mode in mapping
             if ik in fmap and tg in fmap]
    if not pairs:
        print("Free Kinetics: Recalculate Body IK - no matching IK/target bones on '%s'." % armature.name)
        return
    prevAction = _bakeAssign(armature, action)
    fc = action.freehk.frameCount
    if not fc or fc < 1:
        fc = int(max((k.co[0] for f in action.fcurves for k in f.keyframe_points), default=1))
    # Sample only at the frames the TARGET bones are actually keyed on - follow the source's
    # own keyframe structure rather than force-keying every frame (avoids LMT bloat).
    sampleFrames = set()
    for _, tg, _ in pairs:
        p = 'pose.bones["%s"].' % tg.name
        for fcv in action.fcurves:
            if fcv.data_path in (p + "location", p + "rotation_quaternion", p + "rotation_euler"):
                for k in fcv.keyframe_points:
                    sampleFrames.add(int(round(k.co[0])))
    sampleFrames = sorted(sampleFrames) if sampleFrames else list(range(0, int(fc) + 1))
    for ik, _, _ in pairs:
        _wipeIKChannels(action, ik)
    scene = bpy.context.scene
    view = bpy.context.view_layer
    saved = scene.frame_current
    for f in sampleFrames:
        scene.frame_set(f)
        view.update()
        targets = [(ik, tg.matrix.copy(), mode) for ik, tg, mode in pairs]  # read before writing
        for ik, tmat, mode in targets:
            if mode == 'FULL':
                ik.matrix = tmat
                ik.keyframe_insert("location", frame=f)
                ik.keyframe_insert("rotation_quaternion", frame=f)
            else:  # LOC: keep the IK bone's own orientation, match position only
                m = ik.matrix.copy()
                m.translation = tmat.translation
                ik.matrix = m
                ik.keyframe_insert("location", frame=f)
    scene.frame_set(saved)
    view.update()
    _tagIKBoneFunctions(action, [p[0] for p in pairs])
    armature.animation_data.action = prevAction if prevAction else action

def recalculateGroundIKBones(armature, action, mapping=None):
    """Pin the GROUND/anchor IK controllers (251/253) to a constant MHW point (single
    reference keyframe). These have no deform bone to follow, so this is a best-effort
    baseline - expect to fine-tune the MHW values in IK_GROUND_MAP per character. The pose
    basis is derived by running the MHW target through the import-forward transform; export
    then inverts it back to the exact MHW constant. Non-destructive to the armature."""
    if armature is None or action is None:
        return
    if mapping is None:
        mapping = IK_GROUND_MAP
    fmap = boneFunctionMap(armature)
    consts = [(fmap[ik], Vector(loc)) for ik, loc in mapping if ik in fmap]
    if not consts:
        print("Free Kinetics: Recalculate Ground IK - no matching IK bones on '%s'." % armature.name)
        return
    prevAction = _bakeAssign(armature, action)
    for ik, mhwloc in consts:
        _wipeIKChannels(action, ik)
        ik.matrix_basis = strackerForwardTransform(ik, Matrix.Translation(mhwloc))
        ik.keyframe_insert("location", frame=0)
        ik.keyframe_insert("rotation_quaternion", frame=0)
    _tagIKBoneFunctions(action, [c[0] for c in consts])
    armature.animation_data.action = prevAction if prevAction else action

def completeMissingChannels(action): 
    errs, curveMap = verifyTuplings(action)
    for (actionPath,fold),errType in errs:
        if errType == CHANNEL_COUNT:
            transformTarget,transformType =  breakPath(actionPath)
            tsize = transformSize(transformType)
            missingIndices = set(range(tsize))
            for curve in curveMap[(actionPath,fold)]:
                try:
                    missingIndices.remove(curve.array_index%4)
                except:
                    pass
            for i in missingIndices:
                f = action.fcurves.new(data_path = actionPath, index = i+4*fold)
                f.mute = fold
                customizeFCurve(f, starType = 0,boneFunction = -2)
                
                
def synchronizeKeyframes(action):
    errs, curveMap = verifyTuplings(action)
    for (actionPath,fold),errType in errs:
        if errType == SYNCHRONICITY:
            curvePoints = [set((k.co[0] for k in curve.keyframe_points if k.co[0]>=0)) for curve in curveMap[(actionPath,fold)]]
            synchronizedSet = set()
            for c in curvePoints: synchronizedSet = synchronizedSet.union(c)
            for points,curve in zip(curvePoints,curveMap[(actionPath,fold)]):
                newPoints = synchronizedSet.difference(points)
                values = []
                for point in newPoints:
                    t = point
                    values.append((t,curve.evaluate(t)))
                for v in values:
                    kp = curve.keyframe_points.insert(*v)

def resampleFCurve(fcurve,resampleRate):
    frames = list(sorted(((k.co[0] for k in fcurve.keyframe_points if k.co[0]>=0))))
    for l,r in zip(frames[:-1],frames[1:]):
        distance = r-l
        values = []
        for d in range(int((distance-1)//resampleRate)):
            t = l+(d+1)*resampleRate
            values.append((t,fcurve.evaluate(t)))
        for v in values:
            kp = fcurve.keyframe_points.insert(*v)
            

def resampleAction(action,resampleRate):
    for fcurve in action.fcurves:
        resampleFCurve(fcurve,resampleRate)