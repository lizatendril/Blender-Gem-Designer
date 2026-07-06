"""Utilities for loading and managing the geometry node group from the asset .blend."""

from __future__ import annotations

import math
import os
from typing import Any

import bpy

NODE_GROUP_NAME = "GemTierCutter"
ASSET_BLEND = "gem_tier_cutter.blend"


def get_addon_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_node_group() -> bpy.types.NodeGroup:
    ng = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if ng is not None:
        return ng

    asset_path = os.path.join(get_addon_dir(), ASSET_BLEND)
    if not os.path.exists(asset_path):
        raise FileNotFoundError(f"Asset blend not found: {asset_path}")

    with bpy.data.libraries.load(asset_path, link=False) as (data_from, data_to):
        if NODE_GROUP_NAME in data_from.node_groups:
            data_to.node_groups = [NODE_GROUP_NAME]
        else:
            available = data_from.node_groups[:]
            raise KeyError(
                f"Node group '{NODE_GROUP_NAME}' not found in {asset_path}. "
                f"Available: {available}"
            )

    ng = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if ng is None:
        raise RuntimeError(f"Failed to load '{NODE_GROUP_NAME}' from {asset_path}")
    return ng


def _get_socket_map(ng: bpy.types.NodeGroup) -> dict[str, str]:
    expected = {"Base Index", "Rotational Symmetry", "Mirror Symmetry", "Angle", "Height"}
    socket_map: dict[str, str] = {}
    for node in ng.nodes:
        if node.type == 'GROUP_INPUT':
            for sock in node.outputs:
                if sock.name in expected:
                    socket_map[sock.name] = sock.identifier
                    expected.discard(sock.name)
    if expected:
        print(f"[Gem Designer] WARNING: Missing sockets in '{ng.name}': {expected}")
        print(f"[Gem Designer] Available: {[s.name for s in ng.interface.items_tree]}")
    return socket_map


_socket_map_cache: dict[str, dict[str, str]] = {}


def apply_tier_modifier(
    obj: bpy.types.Object,
    tier_index: int,
    tier_data: dict[str, Any],
    gear: int = 96,
) -> bool:
    """Create or update a geometry-nodes modifier for one tier.

    Returns True if any input values actually changed (useful for avoiding
    unnecessary bake invalidation).
    """
    ng = load_node_group()
    tier_name: str = tier_data.get("name", f"Tier {tier_index + 1}")

    # Find existing modifier by tier_index marker
    mod: bpy.types.NodesModifier | None = None
    for m in obj.modifiers:
        if m.get("gem_tier_index") == tier_index:
            mod = m
            break

    if mod is None:
        internal_name = f"GemTier_{tier_index:03d}"
        mod = obj.modifiers.new(name=internal_name, type='NODES')
        mod.node_group = ng

    mod.show_viewport = True
    mod.show_render = True
    mod.name = f"Tier: {tier_name}"
    mod["gem_tier_index"] = tier_index

    if NODE_GROUP_NAME not in _socket_map_cache:
        _socket_map_cache[NODE_GROUP_NAME] = _get_socket_map(ng)
    socket_map = _socket_map_cache[NODE_GROUP_NAME]

    # Convert teeth → degrees for GN inputs
    deg_per_tooth = 360.0 / max(gear, 1)
    tooth_0based = tier_data.get("base_index", 96) % gear
    gn_base_index = tooth_0based * deg_per_tooth
    gn_mirror = tier_data.get("mirror_symmetry", 0) * deg_per_tooth

    side: str = tier_data.get("side", "CROWN")
    diagram_angle: float = tier_data.get("angle", 45.0)
    if side == "CROWN":
        gn_angle = 90.0 - diagram_angle
    else:
        gn_angle = diagram_angle - 90.0

    values: dict[str, float] = {
        "Base Index": gn_base_index,
        "Rotational Symmetry": tier_data.get("rotational_symmetry", 8),
        "Mirror Symmetry": gn_mirror,
        "Angle": gn_angle,
        "Height": tier_data.get("height", 0.0),
    }

    changed = False
    for name, value in values.items():
        identifier = socket_map.get(name)
        if identifier is None:
            continue
        try:
            current: float = mod[identifier]
            if abs(current - value) > 1e-6:
                mod[identifier] = value
                changed = True
        except Exception as e:
            print(f"[Gem Designer] ERROR setting '{identifier}' = {value}: {e}")

    return changed


def sync_modifiers(
    obj: bpy.types.Object,
    tiers: list[dict[str, Any]],
    gear: int = 96,
    active_tier_idx: int = -1,
) -> None:
    kept_indices: set[int] = set()
    for i, tier in enumerate(tiers):
        if not tier.get("enabled", True):
            continue
        apply_tier_modifier(obj, i, tier, gear=gear)
        kept_indices.add(i)

    for mod in list(obj.modifiers):
        idx = mod.get("gem_tier_index")
        if idx is not None and idx not in kept_indices:
            obj.modifiers.remove(mod)


def bake_tier_modifier(obj: bpy.types.Object, mod: bpy.types.NodesModifier) -> bool:
    """Bake the 'Bake' node inside a single geometry-nodes modifier.

    Skips if already baked.  Returns True if a bake was triggered.
    """
    if mod.get("gem_baked"):
        return False

    if not hasattr(mod, "bakes"):
        return False

    for bake in mod.bakes:
        if bake.node.name == "Bake":
            try:
                bpy.ops.object.geometry_node_bake_single(
                    session_uid=bake.id_data.session_uid,
                    modifier_name=mod.name,
                    bake_id=bake.bake_id,
                )
                mod["gem_baked"] = True
                return True
            except (AttributeError, RuntimeError) as e:
                print(f"[Gem Designer] Bake failed for '{mod.name}': {e}")
                return False

    return False


def _unbake_modifier(obj: bpy.types.Object, mod: bpy.types.NodesModifier) -> bool:
    """Delete bake data for the 'Bake' node in a single modifier.

    Skips if already unbaked.  Returns True if bake data was deleted.
    """
    if not mod.get("gem_baked"):
        return False

    if not hasattr(mod, "bakes"):
        return False

    for bake in mod.bakes:
        if bake.node.name == "Bake":
            try:
                bpy.ops.object.geometry_node_bake_delete_single(
                    session_uid=bake.id_data.session_uid,
                    modifier_name=mod.name,
                    bake_id=bake.bake_id,
                )
                mod["gem_baked"] = False
                return True
            except (AttributeError, RuntimeError) as e:
                print(f"[Gem Designer] Unbake failed for '{mod.name}': {e}")
                return False

    return False


def bake_all_tiers(obj: bpy.types.Object) -> int:
    """Bake every 'Bake' node in all tier modifiers on the object.

    Returns the number of bake nodes successfully triggered.
    """
    baked = 0
    for mod in obj.modifiers:
        if mod.type != 'NODES':
            continue
        if mod.get("gem_tier_index") is None:
            continue
        if bake_tier_modifier(obj, mod):
            baked += 1
    return baked


def unbake_all_tiers(obj: bpy.types.Object) -> int:
    """Delete bake data for all tier modifiers on the object.

    Returns the number of bake nodes deleted.
    """
    deleted = 0
    for mod in obj.modifiers:
        if mod.type != 'NODES':
            continue
        if mod.get("gem_tier_index") is None:
            continue
        if _unbake_modifier(obj, mod):
            deleted += 1
    return deleted


def bake_all_except(obj: bpy.types.Object, skip_tier_idx: int) -> tuple[int, int]:
    """Bake all tier modifiers except the one at skip_tier_idx.
    Unbakes the skipped tier so its geometry updates live.

    Returns (baked, unbaked) counts.
    """
    baked = 0
    unbaked = 0
    for mod in obj.modifiers:
        if mod.type != 'NODES':
            continue
        idx = mod.get("gem_tier_index")
        if idx is None:
            continue
        if idx == skip_tier_idx:
            if _unbake_modifier(obj, mod):
                unbaked += 1
        else:
            if bake_tier_modifier(obj, mod):
                baked += 1
    return baked, unbaked
