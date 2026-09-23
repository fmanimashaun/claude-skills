"""Mutation guard: palette_gates. Declared here, run by scripts/mutation_check.py (#1235).

Each gate is disabled in turn; each must be caught by the brand-pack-lint fixture that measures it
against numbers the data-viz method's own validator produced. The simulation mutation drops
deuteranopia, which is the vision the fidara failure (dE 4.8) is only visible under.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="palette_gates",
    subject="scripts/palette_gates.py",
    selftest="scripts/palette_gates.py",
    mutations=(
        Mutation(
            "the lightness band is no longer a gate",
            "    if band:\n",
            "    if False:\n",
            "reliance FAILS the band gate",
        ),
        Mutation(
            "the chroma floor is no longer a gate",
            "    if grey:\n",
            "    if False:\n",
            "reliance FAILS the chroma gate",
        ),
        Mutation(
            "colour-blind separation is no longer a gate",
            "    if dE < CVD_FLOOR:\n",
            "    if False:\n",
            "fidara FAILS the colour-blind gate",
        ),
        Mutation(
            "normal-vision separation is no longer a gate",
            "    if dE < NORMAL_FLOOR:\n",
            "    if False:\n",
            "reliance FAILS the normal-vision gate",
        ),
        Mutation(
            "deuteranopia is no longer simulated",
            '    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),\n',
            "",
            "fidara FAILS the colour-blind gate",
        ),
        Mutation(
            # THE FIRES-ON-EVERYTHING MUTATION: a gate that fails every palette is as useless as none.
            "every palette fails the normal-vision floor",
            "NORMAL_FLOOR = 15.0\n",
            "NORMAL_FLOOR = 1000.0\n",
            "validated palette passes every gate",
        ),
    ),
)
