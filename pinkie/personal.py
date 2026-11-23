"""Personal touches for Aayusha. Edit the name and the little notes here.

The name can also be changed in the app: Settings (gear icon) -> "who's this for?".
"""

NAME = "Aayusha"

# Little notes the otter says, one at a time. {name} becomes her name.
NOTES = [
    "hi {name}! \U0001F9A6",
    "you're my favorite song ♡",
    "otterly adorable",
    "cutie alert!!",
    "otters hold hands so they don't drift apart ♡",
    "press play, pretty girl",
    "this player is all yours, {name}",
    "sing along, cutie!",
    "you + me = best duet ♡",
    "drink some water, cutie \U0001F9A6",
]


def title(name: str) -> str:
    return f"{name}'s Music Player"


def speaker_name(name: str) -> str:
    """How the built-in speaker shows up in Spotify's device list."""
    return f"{name}'s Player"
