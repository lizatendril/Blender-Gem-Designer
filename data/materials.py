# Gem optical properties for realistic materials
# RI values are mid-range; dispersion from gemological references

GEMS = {
    "Garnet (Almandine)": {"ri": 1.79, "dispersion": 0.024, "color": (0.6, 0.1, 0.1)},
    "Aquamarine":         {"ri": 1.575, "dispersion": 0.014, "color": (0.4, 0.7, 0.9)},
    "Spinel":             {"ri": 1.72, "dispersion": 0.020, "color": (0.8, 0.3, 0.5)},
    "Peridot":            {"ri": 1.67, "dispersion": 0.020, "color": (0.5, 0.8, 0.2)},
    "Topaz":              {"ri": 1.625, "dispersion": 0.014, "color": (0.6, 0.8, 1.0)},
    "Sphene (Titanite)":  {"ri": 1.95, "dispersion": 0.051, "color": (0.7, 0.8, 0.3)},
    "Zircon":             {"ri": 1.95, "dispersion": 0.039, "color": (0.6, 0.7, 0.9)},
    "Quartz":             {"ri": 1.545, "dispersion": 0.013, "color": (0.9, 0.9, 0.9)},
    "Sapphire":           {"ri": 1.765, "dispersion": 0.018, "color": (0.2, 0.3, 0.9)},
    "Ruby":               {"ri": 1.765, "dispersion": 0.018, "color": (0.9, 0.1, 0.2)},
    "Diamond":            {"ri": 2.417, "dispersion": 0.044, "color": (0.95, 0.95, 0.95)},
    "Cubic Zirconia":     {"ri": 2.15, "dispersion": 0.060, "color": (0.9, 0.9, 0.9)},
    "Moissanite":         {"ri": 2.67, "dispersion": 0.104, "color": (0.9, 0.9, 0.9)},
    "YAG":                {"ri": 1.83, "dispersion": 0.028, "color": (0.5, 0.9, 0.5)},
    "Glass":              {"ri": 1.51, "dispersion": 0.008, "color": (0.8, 0.85, 0.9)},
}

GEM_NAMES = [(name, name) for name in GEMS.keys()]
