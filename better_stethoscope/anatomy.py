"""Standard cardiac auscultation positions (the "five points of the heart").

NOTE: These are the classic anatomic landmarks taught in every physical
diagnosis course; they are provided so the CLI can prompt the operator and so
each recording is labelled with where on the chest it was taken -- a
physician reviewing the audio later needs that context.

The mnemonic for the default order is A-P-E-T-M: Aortic, Pulmonic, Erb's
point, Tricuspid, Mitral -- a downhill sweep from the patient's right to
the apex.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    slug: str        # machine-friendly key used in filenames and the CLI
    name: str        # human name
    landmark: str    # where to place the chestpiece
    listen_for: str   # what this window is classically best for


POSITIONS: dict[str, Position] = {
    p.slug: p
    for p in [
        Position(
            slug="aortic",
            name="Aortic area",
            landmark="2nd intercostal space at the right sternal border",
            listen_for="aortic stenosis murmur, aortic ejection click, S2 splitting",
        ),
        Position(
            slug="pulmonic",
            name="Pulmonic area",
            landmark="2nd intercostal space at the left sternal border",
            listen_for="pulmonic stenosis murmur, PDA continuous murmur, S2 (P2 component)",
        ),
        Position(
            slug="erbs",
            name="Erb's point",
            landmark="3rd intercostal space at the left sternal border",
            listen_for=(
                "aortic regurgitation, radiation of aortic stenosis murmur, "
                "a balanced 'middle' window for S1/S2 quality"
            ),
        ),
        Position(
            slug="tricuspid",
            name="Tricuspid area",
            landmark="4th-5th intercostal space at the left lower sternal border",
            listen_for="tricuspid regurgitation murmur, right-sided S3/S4 gallops",
        ),
        Position(
            slug="mitral",
            name="Mitral area (apex)",
            landmark="5th intercostal space at the midclavicular line (the apex beat)",
            listen_for=(
                "S1 loudness, mitral regurgitation/stenosis murmurs, "
                "left-sided S3/S4 gallops -- the single richest window; "
                "record here first if you only take one"
            ),
        ),
        # Free-form option for anything outside the classic five (carotids,
        # back, lung fields, a graft site...) -- the CLI accepts any label.
    ]
}

DEFAULT_ORDER = ["aortic", "pulmonic", "erbs", "tricuspid", "mitral"]


def get_position(slug: str) -> Position:
    """Look up a position by slug; unknown slugs become ad-hoc positions.

    WHY: operators sometimes want 'apex_lateral', 'carotid', or 'back_lung'
    labels. Rather than failing, we mint a Position on the fly so the
    recording still gets a clean, filename-safe label.
    """
    if slug in POSITIONS:
        return POSITIONS[slug]
    safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in slug.lower()).strip("_")
    return Position(slug=safe, name=slug, landmark="operator-defined", listen_for="-")