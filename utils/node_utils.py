"""Utilities for loading and managing the geometry node group from the asset .blend."""

import math
import bpy
import os

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


def _get_socket_map(ng: bpy.types.NodeGroup) -> dict:
    expected = {"Base Index", "Rotational Symmetry", "Mirror Symmetry", "Angle", "Height"}
    socket_map = {}
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


_socket_map_cache = {}


def apply_tier_modifier(obj, tier_index: int, tier_data: dict, gear: int = 96):
    ng = load_node_group()
    tier_name = tier_data.get("name", f"Tier {tier_index+1}")

    # Find existing modifier by tier_index marker
    mod = None
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
    # base_index is 1-based (faceting convention): tooth 96 = 0°
    deg_per_tooth = 360.0 / max(gear, 1)
    tooth_0based = tier_data.get("base_index", 96) % gear
    gn_base_index = tooth_0based * deg_per_tooth
    gn_mirror = tier_data.get("mirror_symmetry", 0) * deg_per_tooth

    # Gem diagram angle (degrees) → GN pitch
    # Angle is stored as degrees in tier_data (converted by to_dict)
    side = tier_data.get("side", "CROWN")
    diagram_angle = tier_data.get("angle", 45.0)  # degrees in JSON
    if side == "CROWN":
        gn_angle = 90.0 - diagram_angle
    else:
        gn_angle = diagram_angle - 90.0

    values = {
        "Base Index": gn_base_index,
        "Rotational Symmetry": tier_data.get("rotational_symmetry", 8),
        "Mirror Symmetry": gn_mirror,
        "Angle": gn_angle,
        "Height": tier_data.get("height", 0.0),
    }

    for name, value in values.items():
        identifier = socket_map.get(name)
        if identifier is None:
            print(f"[Gem Designer] WARNING: socket '{name}' not found — skipping")
            continue
        try:
            mod[identifier] = value
        except Exception as e:
            print(f"[Gem Designer] ERROR setting '{identifier}' = {value}: {e}")


def sync_modifiers(obj, tiers: list[dict], gear: int = 96, active_tier_idx: int = -1):
    kept_indices = set()
    for i, tier in enumerate(tiers):
        if not tier.get("enabled", True):
            continue
        apply_tier_modifier(obj, i, tier, gear=gear)
        kept_indices.add(i)

    for mod in list(obj.modifiers):
        idx = mod.get("gem_tier_index")
        if idx is not None and idx not in kept_indices:
            obj.modifiers.remove(mod)
