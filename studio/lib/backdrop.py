"""Chroma key backdrop: replace the scene's set with a plain keyable screen."""

COLORS = ("green", "blue")
_SOUNDSCAPE = "\n\noverall_soundscape:"


def normalize(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in COLORS else ""


def instruction(color: str) -> str:
    return (
        f"Filmed on a professional chroma key stage: the entire background is a seamless, evenly lit, "
        f"flat pure {color} screen with no set, no props, no floor line, no horizon, no shadows and no "
        f"gradient on the backdrop. The subject is lit separately with neutral white light, with no "
        f"{color} reflection on skin, hair or clothing."
    )


def apply(prompt: str, value) -> str:
    """Append the screen instruction to the visual description, never to the audio fields."""
    color = normalize(value)
    prompt = str(prompt or "")
    if not color or instruction(color) in prompt:
        return prompt
    head, marker, tail = prompt.partition(_SOUNDSCAPE)
    if marker:
        return f"{head.rstrip()} {instruction(color)}{marker}{tail}"
    return f"{prompt.rstrip()}\n\n{instruction(color)}"
