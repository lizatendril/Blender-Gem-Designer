# Gem optical properties for the "Gem (Birefringent)" shader node group.
#
# Values referenced:
#   - main_ior / birefringence_ior: from gemological references
#   - dispersion: difference in RI between red and blue wavelengths (B-G interval)
#   - color: RGB approximate for absorption
#   - color_density: absorption strength (higher = darker/deeper color)
#   - has_birefringence: "" or "Birefringence" (sets the node-group menu switch)
#   - render_dispersion: "No Dispersion" | "First-bounce Dispersion" | "Full Dispersion"

from __future__ import annotations

from typing import Any

GEMS: dict[str, dict[str, Any]] = {
    "Ruby":               {
        "main_ior": 1.761, "birefringence_ior": 1.770,
        "dispersion": 0.018, "color": (0.9, 0.1, 0.2),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Sapphire":           {
        "main_ior": 1.760, "birefringence_ior": 1.768,
        "dispersion": 0.018, "color": (0.2, 0.3, 0.9),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Garnet (Almandine)": {
        "main_ior": 1.790, "birefringence_ior": 1.790,
        "dispersion": 0.024, "color": (0.6, 0.1, 0.1),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
    "Aquamarine":         {
        "main_ior": 1.575, "birefringence_ior": 1.580,
        "dispersion": 0.014, "color": (0.4, 0.7, 0.9),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Spinel":             {
        "main_ior": 1.720, "birefringence_ior": 1.720,
        "dispersion": 0.020, "color": (0.8, 0.3, 0.5),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
    "Peridot":            {
        "main_ior": 1.670, "birefringence_ior": 1.690,
        "dispersion": 0.020, "color": (0.5, 0.8, 0.2),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Topaz":              {
        "main_ior": 1.625, "birefringence_ior": 1.635,
        "dispersion": 0.014, "color": (0.6, 0.8, 1.0),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Sphene (Titanite)":  {
        "main_ior": 1.900, "birefringence_ior": 2.034,
        "dispersion": 0.051, "color": (0.7, 0.8, 0.3),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Zircon":             {
        "main_ior": 1.920, "birefringence_ior": 1.960,
        "dispersion": 0.039, "color": (0.6, 0.7, 0.9),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Quartz":             {
        "main_ior": 1.544, "birefringence_ior": 1.553,
        "dispersion": 0.013, "color": (0.9, 0.9, 0.9),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "Diamond":            {
        "main_ior": 2.417, "birefringence_ior": 2.417,
        "dispersion": 0.044, "color": (0.95, 0.95, 0.95),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
    "Cubic Zirconia":     {
        "main_ior": 2.150, "birefringence_ior": 2.150,
        "dispersion": 0.060, "color": (0.9, 0.9, 0.9),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
    "Moissanite":         {
        "main_ior": 2.650, "birefringence_ior": 2.690,
        "dispersion": 0.104, "color": (0.9, 0.9, 0.9),
        "color_density": 5.0, "has_birefringence": "Birefringence",
    },
    "YAG":                {
        "main_ior": 1.830, "birefringence_ior": 1.830,
        "dispersion": 0.028, "color": (0.5, 0.9, 0.5),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
    "Glass":              {
        "main_ior": 1.510, "birefringence_ior": 1.510,
        "dispersion": 0.008, "color": (0.8, 0.85, 0.9),
        "color_density": 5.0, "has_birefringence": "No birefringence",
    },
}

GEM_NAMES: list[tuple[str, str]] = [(name, name) for name in GEMS.keys()]

# Default render-dispersion mode for new materials
DEFAULT_RENDER_DISPERSION = "Full Dispersion"

# Common aliases that GCS / GemCAD files may use instead of the full gem name.
# Keys are lowercase; values map to keys in GEMS.
_GEM_ALIASES: dict[str, str] = {
    "cz": "Cubic Zirconia",
    "cubic zirconia": "Cubic Zirconia",
    "c.z.": "Cubic Zirconia",
    "almandine": "Garnet (Almandine)",
    "garnet": "Garnet (Almandine)",
    "titanite": "Sphene (Titanite)",
    "yag": "YAG",
    "moissy": "Moissanite",
    "sapphire": "Sapphire",
    "ruby": "Ruby",
    "diamond": "Diamond",
    "emerald": "Glass",  # No emerald preset yet — fall back to glass
    "tourmaline": "Quartz",  # No tourmaline preset yet — fall back
    "topaz": "Topaz",
    "peridot": "Peridot",
    "spinel": "Spinel",
    "sphene": "Sphene (Titanite)",
    "zircon": "Zircon",
    "quartz": "Quartz",
    "aquamarine": "Aquamarine",
    "glass": "Glass",
}


def detect_gem_type(text: str) -> str | None:
    """Try to match arbitrary text to a known gem type.

    Returns the GEMS key on match, or None if no match found.
    Matching is case-insensitive and tries:
      1. Exact key match
      2. Substring match (longest key first)
      3. Common alias lookup
    """
    if not text:
        return None

    text_lower = text.strip().lower()

    # 1. Exact match against GEMS keys
    for name in GEMS:
        if name.lower() == text_lower:
            return name

    # 2. Substring match — longest key first so "Sphene (Titanite)"
    #    wins over partial matches like "Sphene"
    for name in sorted(GEMS.keys(), key=len, reverse=True):
        if name.lower() in text_lower:
            return name

    # 3. Alias lookup
    for alias, gem_name in _GEM_ALIASES.items():
        if alias in text_lower:
            return gem_name

    return None
