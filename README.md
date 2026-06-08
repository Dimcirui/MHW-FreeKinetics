![Project Logo](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics/blob/main/icons/HKLogo.fw.png?raw=true)

# Free Kinetics — Blender 4.x port of Free Hyperkinetics

A community port of **AsteriskAmpersand's [Free Hyperkinetics](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics)** — a Blender addon for editing *Monster Hunter World*'s **LMT / TIML / EFX** animation files — from **Blender 2.79c** to the **modern 4.x generation (targeting Blender 4.3 LTS)**, adapted to the current **MHW Model Editor (mod3) "MhBone_NNN" armatures**.

> The original tool and essentially all of its engineering and format research are **AsteriskAmpersand's**. This fork only ports it to modern Blender and adapts/extends the animation-transfer workflow. See **Credits**.

# Introduction

Free Kinetics edits MHW's LMT, TIML and EFX files. It consists of three interconnected modules: the titular animation engine (an extension of Blender's skeleton, actions and F-Curves to MHW LMT animations and tracks), an Independent TIML Works module (extending actions and keyframes to MHW TIML animations/tracks), and an extension to Blender's node system that unifies the two and exposes MHW animation metadata hierarchies.

It aims to be WYSIWYG: when the exporter must fill in missing data it does so to match what is visible in Blender, and where metadata conflicts with the view it defers to the view. Tools are provided to make the view and metadata agree (in either direction), and exporter settings can tweak this behaviour.

# Requirements

- **Blender 4.3 LTS** (the 4.x generation). Tested on 4.3 / 4.4.
- **Blender 5.0+ is not supported** — 5.0 moved to slotted ("Baklava") actions and removed `action.fcurves`, which this addon relies on. 5.1+ is explicitly out of scope.
- A MHW armature. Both kinds are supported:
  - Legacy 2.79-importer skeletons (explicit `Root` bone, `BoneFunction.NNN` naming, MHW-native space).
  - Modern **MhBone_NNN** armatures from the current MHW Model Editor mod3 importer (no `Root` bone; a `rotate90X · scale0.01` conversion baked into the bone rest).

# What this port changes

Relative to the original 2.79c addon (see `MIGRATION_PLAN.md` for the full, tiered changelog):

- **API migration** to Blender 2.8+/4.x (property annotations, `@` matrix operator, menu/icon/panel renames, `depsgraph_update_post`, node `init()`, int/float strictness, …). Intended to be behaviour-neutral.
- **Modern MhBone adaptation** — the animation *tether* and *export* maths were rewritten to work on armatures that have no explicit `Root` bone and bake the mod3 conversion into the rest pose: virtual-root coordinate conversion, IK-controller handling, and whole-character **root motion mapped to / from the armature object**.
- **New authoring tools** for porting external animations (e.g. MMD) onto the MHW skeleton:
  - **Rig Transfer** with external **`.bmap`** bone maps (`Open Bmap Folder` / `Apply Bmap`) and a **Time Scale** factor.
  - **Redefine Rest Pose (Keep Animation)** — convert an A-pose source rig to T-pose without breaking its animation (no Auto-Rig Pro required).
  - **Recalculate IK Bones** — bake the IK controllers from their deform-bone targets (hands→palms, legs→ankles, head, neck) and pin the ground anchors (251/253), with per-controller checkboxes.
- **Display rename** to **"Free Kinetics"** (sidebar tab **"MHW Kinetics"**).

# .blend compatibility

All internal identifiers are deliberately unchanged — operator ids (`freehk.*`), custom properties (`freehk_*`), the node tree (`FreeHKNodeTree`), icon keys (`FREEHK_*`) and class names. Files authored with the original 2.79c Free Hyperkinetics open and work unchanged; only user-facing labels were renamed.

# Usage and Documentation

The editing systems are unchanged from the original, so the upstream tutorials still apply for the core LMT/TIML/EFX concepts: the [modding wiki article](https://github.com/Ezekial711/MonsterHunterWorldModding/wiki/Free-Hyperkinetics-and-Independent-TIML-Works-Overview).

The MMD → MHW authoring workflow added by this port, in short:
1. Align the source rig's feet to the world ground.
2. **Redefine Rest Pose** the source from A-pose to T-pose (unassign the action, rotate the shoulders/upper-arms, run it, re-assign).
3. **Apply Bmap** to tag the source bones, then **Rig Transfer** onto the MhBone armature (use **Time Scale** to retime if needed).
4. **Recalculate IK Bones** (tick the controllers you want).
5. Export the LMT.

# Background and Credits

The original Free Hyperkinetics — the entire tool, and a great deal of MHW animation-format research — was written by **AsteriskAmpersand**. This repository is a port of that work to modern Blender, maintained by **Dimcirui**.

## Thanks
* **AsteriskAmpersand** — the original Free Hyperkinetics (the whole engine and most of the format work).
* **Stracker** and **PredatorCZ** for a significant amount of the background format work, including most of the datatypes.
* **Silvris** for the TIML work that forms the basis of the TIMLWorks (TW) engine.
* **DMQW ICE** for the EFX work that is part of the TIMLWorks (TW) engine.
* **LyraVeil** for edge cases and issues with previous import-only tools.

# A Request From the Original Author

![TinyLogo](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics/blob/main/icons/TinyLogo.fw.png)

(Preserved from AsteriskAmpersand's original README.)

If you use this tool and find it useful, please credit its use appropriately on mods and link to it so interested people can also try it.

Please avoid posting mods made with this tool on NexusMods, given the anti-modding attitudes that site has shown and the damage it has done to small modding communities.

Please do not use this to produce in-game pornography. There are already thousands of tools and platforms for that; please don't further associate this tool or the game's modding scene with that sort of content. It's an open-source license and this can't be enforced — it's asked nicely.

# Contributing

Issues and bugs can be logged through this fork's issue tracker; well-documented PRs are welcome.

For the original tool and to support its author's continued MH-series tooling, see AsteriskAmpersand's [upstream repository](https://github.com/AsteriskAmpersand/MHW-Free-HyperKinetics) and [Patreon](https://www.patreon.com/members?membershipType=active_patron).
