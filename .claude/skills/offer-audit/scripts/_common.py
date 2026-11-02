"""Shared helpers for the offer-audit scripts.

Standard library only. jsonschema is used when installed, otherwise a
minimal built-in validator covers the subset of JSON Schema used by the
files in ../schemas.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = SKILL_DIR / "schemas"

WORKER_FILES = {
    2: "agent_2.json",
    3: "agent_3.json",
    4: "agent_4.json",
    5: "agent_5.json",
}
AGENT_IDS = {
    2: "AGENT_2_PRESS_HYDRAULICS",
    3: "AGENT_3_THERMAL_UTILITIES",
    4: "AGENT_4_DOWNSTREAM_HANDLING",
    5: "AGENT_5_RISK_AND_SCOPE",
}
AGENT_NUM_BY_ID = {v: k for k, v in AGENT_IDS.items()}

# Which worker owns which Document Map domain. Agent 5 reads everything.
DOMAIN_OWNER = {
    "FEEDING": 2,
    "PRESS": 2,
    "HYDRAULICS": 2,
    "TOOLING": 2,
    "UTILITIES": 3,
    "FURNACE": 3,
    "QUENCH": 3,
    "AGEING": 3,
    "DIE_OVEN": 3,
    "HANDLING": 4,
    "STRETCHER": 4,
    "SAW": 4,
    "CONVEYOR": 4,
    "GENERAL": 5,
    "COMMERCIAL": 5,
    "ELECTRICAL": 5,
    "AUTOMATION": 5,
    "SAFETY": 5,
    "SCOPE_SPLIT": 5,
    "OPTIONS": 5,
    "SERVICES": 5,
    "OTHER": 5,
}


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"missing file {path}")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(path)


def offer_dir(run_dir: Path, offer_id: str) -> Path:
    d = run_dir / offer_id
    if not d.is_dir():
        die(f"offer directory not found: {d} (did you run state.py init?)")
    return d


def load_state(run_dir: Path) -> dict:
    return load_json(run_dir / "state.json")


# ---------------------------------------------------------------- schema

def load_schema(name: str) -> dict:
    return load_json(SCHEMA_DIR / name)


def validate_schema(instance: Any, schema: dict) -> list[str]:
    """Return a list of human readable errors. Empty list means valid."""
    try:
        import jsonschema  # type: ignore

        validator_cls = jsonschema.validators.validator_for(schema)
        validator = validator_cls(schema)
        errors = []
        for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            errors.append(f"{loc}: {err.message}")
        return errors
    except ImportError:
        return _mini_validate(instance, schema, schema, "<root>")


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPE_MAP[t])


def _mini_validate(inst: Any, sch: dict, root: dict, loc: str) -> list[str]:
    errs: list[str] = []
    if "$ref" in sch:
        ref = sch["$ref"]
        if not ref.startswith("#/"):
            return [f"{loc}: unsupported $ref {ref}"]
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part]
        return _mini_validate(inst, target, root, loc)
    if "const" in sch and inst != sch["const"]:
        errs.append(f"{loc}: expected const {sch['const']!r}")
    if "enum" in sch and inst not in sch["enum"]:
        errs.append(f"{loc}: {inst!r} is not one of {sch['enum']}")
    if "type" in sch:
        types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_type_ok(inst, t) for t in types):
            errs.append(f"{loc}: expected type {types}, got {type(inst).__name__}")
            return errs
    if isinstance(inst, str):
        if "minLength" in sch and len(inst) < sch["minLength"]:
            errs.append(f"{loc}: shorter than {sch['minLength']}")
        if "maxLength" in sch and len(inst) > sch["maxLength"]:
            errs.append(f"{loc}: longer than {sch['maxLength']}")
        if "pattern" in sch and not re.search(sch["pattern"], inst):
            errs.append(f"{loc}: does not match {sch['pattern']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in sch and inst < sch["minimum"]:
            errs.append(f"{loc}: below minimum {sch['minimum']}")
        if "maximum" in sch and inst > sch["maximum"]:
            errs.append(f"{loc}: above maximum {sch['maximum']}")
    if isinstance(inst, list):
        if "minItems" in sch and len(inst) < sch["minItems"]:
            errs.append(f"{loc}: fewer than {sch['minItems']} items")
        if "items" in sch:
            for i, item in enumerate(inst):
                errs.extend(_mini_validate(item, sch["items"], root, f"{loc}/{i}"))
    if isinstance(inst, dict):
        for req in sch.get("required", []):
            if req not in inst:
                errs.append(f"{loc}: missing required property {req!r}")
        props = sch.get("properties", {})
        for key, val in inst.items():
            if key in props:
                errs.extend(_mini_validate(val, props[key], root, f"{loc}/{key}"))
            elif sch.get("additionalProperties") is False:
                errs.append(f"{loc}: unexpected property {key!r}")
            elif isinstance(sch.get("additionalProperties"), dict):
                errs.extend(_mini_validate(val, sch["additionalProperties"], root, f"{loc}/{key}"))
    return errs


# ------------------------------------------------------------ text / pages

_QUOTE_TRANSLATION = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
    "³": "3", "²": "2",
})


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_QUOTE_TRANSLATION).lower()
    # de-hyphenate line wraps such as "electri-\ncal"
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")


def tokens(s: str) -> list[str]:
    return _TOKEN_RE.findall(norm_text(s))


def page_file(odir: Path, page: int) -> Path:
    return odir / "corpus" / "pages" / f"{page:03d}.txt"


def vlm_file(odir: Path, page: int) -> Path:
    return odir / "corpus" / "pages" / f"{page:03d}.vlm.md"


def page_text(odir: Path, page: int, include_vlm: bool = True) -> str:
    parts = []
    p = page_file(odir, page)
    if p.exists():
        parts.append(p.read_text(encoding="utf-8", errors="replace"))
    if include_vlm:
        v = vlm_file(odir, page)
        if v.exists():
            parts.append(v.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def quote_segments(quote: str) -> list[str]:
    """Split on ellipses and on explicit '...' so each verbatim piece is checked."""
    pieces = re.split(r"\.\.\.|…|\[\.\.\.\]", quote)
    out = []
    for piece in pieces:
        piece = piece.strip().strip("\"'").strip()
        if len(tokens(piece)) >= 2:
            out.append(piece)
    return out or [quote]


def match_quote(quote: str, text: str, fuzzy_threshold: float = 0.85) -> tuple[str, float]:
    """Return (status, score). status in EXACT, FUZZY, FAILED.

    EXACT: every segment is a normalized substring of text.
    FUZZY: every segment has >= threshold of its tokens present in order-free
           page token multiset (tables lose layout in text extraction).
    """
    ntext = norm_text(text)
    segs = quote_segments(quote)
    if all(norm_text(seg) in ntext for seg in segs):
        return "EXACT", 1.0
    page_tokens: dict[str, int] = {}
    for t in tokens(text):
        page_tokens[t] = page_tokens.get(t, 0) + 1
    worst = 1.0
    for seg in segs:
        seg_tokens = tokens(seg)
        if not seg_tokens:
            continue
        avail = dict(page_tokens)
        hit = 0
        for t in seg_tokens:
            if avail.get(t, 0) > 0:
                avail[t] -= 1
                hit += 1
        worst = min(worst, hit / len(seg_tokens))
    if worst >= fuzzy_threshold:
        return "FUZZY", round(worst, 3)
    return "FAILED", round(worst, 3)


def iter_payloads(odir: Path) -> Iterable[tuple[int, Path]]:
    for num, name in WORKER_FILES.items():
        p = odir / "payloads" / name
        if p.exists():
            yield num, p


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(" ", " ")
        # accept "4.000" european thousands only when unambiguous is impossible, so
        # keep simple: strip spaces used as thousands separators, use dot decimals
        s = s.replace(" ", "")
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
            s = s.replace(",", "")
        elif re.fullmatch(r"-?\d+,\d+", s):
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None
