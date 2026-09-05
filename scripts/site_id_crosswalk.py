"""
site_id_crosswalk.py
====================
Canonical screen-identity resolver shared by every pipeline.

Micromedia is migrating its screen codes from the legacy 5-digit scheme
(``MM ID``, e.g. 50001) to a new scheme (``NEW MM ID``, e.g. 10001 / 30067 /
60004 / 70001). Locomizer's monthly exports arrive under *either* scheme
depending on the month, so a single fixed join key silently drops whichever
scheme a given file did not use. Measured on the current data set, joining on
``MM ID`` alone left 51 fact-table CODEs orphaned; ~20 of those were simply the
same screens arriving under their new code.

This module defines ONE canonical key per screen and a crosswalk that maps
every historical identifier onto it, so footfall / demographics / brand-affinity
rows join regardless of which scheme that month used.

Canonical rule (agreed with Micromedia, 2026-07)
------------------------------------------------
    SITE_ID = NEW MM ID  when the screen has one
            = MM ID       otherwise (screen not yet migrated)

The crosswalk maps BOTH the old ``MM ID`` and the ``NEW MM ID`` of every screen
onto that screen's ``SITE_ID``. Demographics additionally resolves by display
name, because its feed carries no CODE column and occasionally omits the numeric
prefix (``"Dorset Street ..."`` instead of ``"50319 - Dorset Street ..."``).

Unresolved codes are returned UNCHANGED (never dropped), so genuine orphans —
screens absent from the master site list entirely — stay visible and flagged
downstream, consistent with the project's "flag, don't drop" rule.

Usage
-----
    from site_id_crosswalk import Crosswalk
    xw = Crosswalk.load()                        # reads master_sites_unified.csv
    df["SITE_ID"], matched = xw.resolve_ids(df["CODE"])
    # demographics (id first, then name fallback):
    df["SITE_ID"], matched, method = xw.resolve_with_name(df["CODE"], df["DISPLAY NAME"])

__version__ = "1.0.0"
"""

import os
import pandas as pd

__version__ = "1.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MASTER_CSV = os.path.join(
    BASE_DIR, "..", "data", "processed", "sites", "master_sites_unified.csv"
)


def _norm(value):
    """Normalise an identifier to a clean string, or '' if blank/NaN.

    Handles float artefacts from CSV round-trips (``"50001.0"`` -> ``"50001"``).
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "<na>"):
        return ""
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _norm_name(value):
    """Normalise a display name for case/space-insensitive matching."""
    s = _norm(value)
    return " ".join(s.lower().split())


class Crosswalk:
    """Resolves any historical screen identifier to its canonical SITE_ID."""

    def __init__(self, id_map, name_map, site_ids, canonical_by_mm):
        self.id_map = id_map                    # {old or new id -> SITE_ID}
        self.name_map = name_map                # {normalised display name -> SITE_ID}
        self.site_ids = site_ids                # set of canonical SITE_IDs
        self.canonical_by_mm = canonical_by_mm  # {MM ID -> SITE_ID} (for the master itself)

    # -- construction ---------------------------------------------------------
    @classmethod
    def from_master(cls, master_df):
        mm_col, new_col, name_col = "MM ID", "NEW MM ID", "Display Name"
        id_map, name_map, canonical_by_mm = {}, {}, {}
        site_ids = set()

        for _, row in master_df.iterrows():
            mm = _norm(row.get(mm_col))
            new = _norm(row.get(new_col))
            site_id = new if new else mm          # canonical rule
            if not site_id:
                continue                          # no usable identifier at all
            site_ids.add(site_id)
            if mm:
                id_map[mm] = site_id
                canonical_by_mm[mm] = site_id
            if new:
                id_map[new] = site_id
            nm = _norm_name(row.get(name_col))
            if nm:
                # first writer wins; master is deduplicated to one row per screen
                name_map.setdefault(nm, site_id)

        return cls(id_map, name_map, site_ids, canonical_by_mm)

    @classmethod
    def load(cls, master_csv=None):
        path = master_csv or DEFAULT_MASTER_CSV
        master_df = pd.read_csv(path, dtype=str)
        return cls.from_master(master_df)

    @classmethod
    def load_or_none(cls, master_csv=None):
        """Like load(), but returns (crosswalk, message).

        If the master CSV is missing (e.g. a fact pipeline was run before
        build_master_sites.py), returns (None, reason) so the caller can fall
        back to leaving CODE unmapped rather than crashing.
        """
        path = master_csv or DEFAULT_MASTER_CSV
        if not os.path.exists(path):
            return None, (
                f"master site list not found at {path} — run build_master_sites.py "
                f"first. SITE_ID will mirror CODE for this run."
            )
        try:
            return cls.load(path), "ok"
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"could not build crosswalk ({exc}); SITE_ID will mirror CODE."

    # -- resolution -----------------------------------------------------------
    def resolve_ids(self, code_series):
        """Map a CODE series to SITE_ID via the id crosswalk.

        Returns (site_id_series[str], matched_mask[bool]). Unmatched codes are
        returned unchanged so orphans remain visible.
        """
        codes = code_series.map(_norm)
        site = codes.map(lambda c: self.id_map.get(c, c))
        matched = codes.map(lambda c: c in self.id_map)
        return site.astype("string"), matched

    def resolve_with_name(self, code_series, name_series):
        """Resolve by id first, then fall back to display-name matching.

        Used by the demographics pipeline, whose feed carries no CODE column and
        sometimes omits the 5-digit prefix. Returns
        (site_id_series[str], matched_mask[bool], method_series[str]) where
        method is one of 'id', 'name', or 'unresolved'.
        """
        codes = code_series.map(_norm)
        names = name_series.map(_norm_name)

        site, matched, method = [], [], []
        for c, nm in zip(codes, names):
            if c in self.id_map:
                site.append(self.id_map[c]); matched.append(True); method.append("id")
            elif nm in self.name_map:
                site.append(self.name_map[nm]); matched.append(True); method.append("name")
            else:
                site.append(c); matched.append(False); method.append("unresolved")

        idx = code_series.index
        return (
            pd.Series(site, index=idx, dtype="string"),
            pd.Series(matched, index=idx),
            pd.Series(method, index=idx, dtype="string"),
        )

    def to_frame(self):
        """Return the id crosswalk as a tidy DataFrame for export/audit."""
        rows = [{"SOURCE_ID": k, "SITE_ID": v} for k, v in sorted(self.id_map.items())]
        return pd.DataFrame(rows, columns=["SOURCE_ID", "SITE_ID"])
