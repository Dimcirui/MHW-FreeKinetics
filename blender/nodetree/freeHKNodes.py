# -*- coding: utf-8 -*-
"""
Created on Sun Jun 20 23:02:47 2021

@author: AsteriskAmpersand
"""
import bpy
from bpy.types import NodeTree, Node, NodeSocket
from ...error_handling.errorController import ErrorHandler

LMT_COLOR = (48,162,254)
EFX_COLOR = (82,216,37)
TIML_COLOR = (204,131,222)
GENERIC_COLOR = (202,198,215)   
nor = lambda x: [n/255 for n in x]
LMT_COLOR ,EFX_COLOR,TIML_COLOR,GENERIC_COLOR = nor(LMT_COLOR),nor(EFX_COLOR),nor(TIML_COLOR),nor(GENERIC_COLOR)
# Mix-in class for all custom nodes in this tree type.
# Defines a poll function to enable instantiation.

def align(offset):
    return offset+((-offset)%16)

def pad(data):
    return data+b'\x00'*((-len(data))%16)

def colorpick(idname):
    if "LMT" in idname:
            return LMT_COLOR
    if "EFX" in idname:
            return EFX_COLOR
    if "TIML" in idname:
            return TIML_COLOR
    return GENERIC_COLOR

structureCache = {}

def globalCacheClear():
    for key in list(structureCache.keys()):
        del structureCache[key]

class FreeHKNode:
    def __init__(self,*args,**kwargs):
        self.use_custom_color = True
        self.color = colorpick(self.bl_idname)
        super().__init__(*args,**kwargs)
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'FreeHKNodeTree'
    def validSocketInputs(self,socket,conflicts = None):
        validInputs = set()
        for socketLink in socket.links:
                if socket.name != socketLink.from_socket.name:
                    if conflicts is not None:
                        conflicts.append(("G_INPUT_TYPE_MISMATCH",self.name,socket.name,socketLink.from_node.name,socketLink.from_socket.name))
                        conflicts.logSolution("Illegal inputs were omitted from parsing of the graph")
                    #conflicts.handle(validInputs,socketLink.from_node)
                else:
                    #if socket.name not in validInputs: validInputs[socket.name] = set()
                    validInputs.add(socketLink.from_node)
        validInputs = list(sorted(validInputs,key = lambda x: x.location[1],reverse = True))
        return validInputs,conflicts
    def validInputs(self):
        #conflicts = ErrorHandler(self)
        validInputs = {}
        for socket in self.inputs:
            socketInputs,typeConflicts = self.validSocketInputs(socket)
            validInputs[socket.name] = socketInputs
        return validInputs#,typeConflicts
    def getInputs(self,nodeSocket,errors):
        return self.validSocketInputs(nodeSocket,errors)[0]
    def cleanup(self):
        self.cacheClear()
        inputLinks = self.validInputs()
        for nodeList in inputLinks.values():
            for entryNode in nodeList:
                entryNode.cleanup()
    def __createErrorHandler__(self):
        return ErrorHandler(self)
    def cacheCheck(self):
        return structureCache[self] if self in structureCache else None
    def cacheClear(self):
        if self in structureCache:
            del structureCache[self]
    def cacheAdd(self,structure):
        
        structureCache[self] = structure
    def export(self,error_handler = None):
        
        cache = self.cacheCheck()
        if cache is not None:
            return cache
        if error_handler is None:
            error_handler = ErrorHandler(self)
        self.error_handler = error_handler
        self.error_handler.takeOwnership(self)
        if self.inputs:
            validInputs,error_handler = self.validSocketInputs(self.inputs[self.__mainInput__],error_handler)
        else:
            validInputs = []        
        structure = self.basicStructure()
        substructure = []
        for i in validInputs:
            substructure.append(i.export(error_handler))
        #Stop if Graph errors found
        if not error_handler.verifyGraph():
            return None
        structure  = structure.extend(substructure)        
        #Stop if FCurve or Action errors found
        if not error_handler.verifyAnimations():
            return None
        self.cacheAdd(structure)
        return structure

### Node Add Menu (Blender 4.x: NODE_MT_add append) ###

def _freehk_tree(context):
    return (context.space_data is not None and
            context.space_data.tree_type == 'FreeHKNodeTree')

class NODE_MT_freehk_input(bpy.types.Menu):
    bl_idname = "NODE_MT_freehk_input"
    bl_label = "Input"
    def draw(self, context):
        layout = self.layout
        for type_name, label in [
            ("LMTActionNode",  "LMT Action"),
            ("TIMLActionNode", "TIML Action"),
        ]:
            props = layout.operator("node.add_node", text=label)
            props.type = type_name
            props.use_transform = True

class NODE_MT_freehk_data(bpy.types.Menu):
    bl_idname = "NODE_MT_freehk_data"
    bl_label = "Data"
    def draw(self, context):
        layout = self.layout
        for type_name, label in [
            ("LMTEntryNode",  "LMT Entry"),
            ("EFXEntryNode",  "EFX Entry"),
            ("TIMLDataNode",  "TIML Data"),
            ("TIMLEntryNode", "TIML Entry"),
        ]:
            props = layout.operator("node.add_node", text=label)
            props.type = type_name
            props.use_transform = True

class NODE_MT_freehk_output(bpy.types.Menu):
    bl_idname = "NODE_MT_freehk_output"
    bl_label = "Output"
    def draw(self, context):
        layout = self.layout
        for type_name, label in [
            ("LMTFileNode",  "LMT File"),
            ("EFXFileNode",  "EFX File"),
            ("TIMLFileNode", "TIML File"),
        ]:
            props = layout.operator("node.add_node", text=label)
            props.type = type_name
            props.use_transform = True

def _draw_freehk_add_menu(self, context):
    if not _freehk_tree(context):
        return
    layout = self.layout
    layout.separator()
    layout.menu("NODE_MT_freehk_input")
    layout.menu("NODE_MT_freehk_data")
    layout.menu("NODE_MT_freehk_output")

_category_menus = [
    NODE_MT_freehk_input,
    NODE_MT_freehk_data,
    NODE_MT_freehk_output,
]

classes = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for menu_cls in _category_menus:
        bpy.utils.register_class(menu_cls)
    bpy.types.NODE_MT_add.append(_draw_freehk_add_menu)

def unregister():
    bpy.types.NODE_MT_add.remove(_draw_freehk_add_menu)
    for menu_cls in reversed(_category_menus):
        bpy.utils.unregister_class(menu_cls)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
