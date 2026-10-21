"""Lossless full-script splitting and validation, independent of AI providers."""

import re

from .core import WorkflowError

MAX_SCRIPT_LENGTH = 12000
MAX_FULL_SCRIPT_LENGTH = 120000
HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?\[?slide[ \t]+(\d+)\]?:?(?:\*\*)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def labelled_scripts(script, slides):
    """Return sections for explicit, standalone Slide N headings, or None."""
    headings = list(HEADING.finditer(script))
    if not headings:
        return None
    if script[: headings[0].start()].strip():
        raise WorkflowError(
            "Put all narration under a Slide 1 heading; text before the first heading is unassigned."
        )
    numbers = [int(heading[1]) for heading in headings]
    expected = [slide["number"] for slide in slides]
    if numbers != expected:
        raise WorkflowError(
            f"Use one heading for every slide, in order: Slide 1 through Slide {len(slides)}. "
            "Check for missing, repeated, or out-of-range slide numbers."
        )
    sections = [
        script[
            heading.end() : headings[index + 1].start() if index + 1 < len(headings) else len(script)
        ].strip()
        for index, heading in enumerate(headings)
    ]
    validate_sections(sections, len(slides))
    return sections


def script_units(script):
    """Keep original whitespace within units so concatenation preserves the source."""
    units = []
    start = 0
    for boundary in re.finditer(r"(?<=[.!?])\s+|\n[ \t]*\n", script):
        if script[start : boundary.end()].strip():
            units.append(script[start : boundary.end()])
            start = boundary.end()
    if script[start:].strip():
        units.append(script[start:])
    return units


def sections_from_boundaries(units, boundaries, count):
    """AI chooses only boundaries; narration is always reconstructed from source."""
    if not isinstance(boundaries, list) or len(boundaries) != count:
        raise WorkflowError(
            "Claude did not return a boundary for every slide. Try again or use Slide 1 headings."
        )
    sections = []
    start = 0
    for end in boundaries:
        if type(end) is not int or not start <= end <= len(units):
            raise WorkflowError(
                "Claude returned invalid script boundaries. Try again or use Slide 1 headings."
            )
        sections.append("".join(units[start:end]).strip())
        start = end
    if start != len(units):
        raise WorkflowError("Claude left part of the script unassigned. Try again or use Slide 1 headings.")
    validate_sections(sections, count)
    return sections


def validate_sections(sections, count):
    if len(sections) != count:
        raise WorkflowError("Provide a script section for every slide.")
    for number, section in enumerate(sections, 1):
        if len(section) > MAX_SCRIPT_LENGTH:
            raise WorkflowError(f"Slide {number} exceeds 12,000 characters. Split or shorten that section.")
