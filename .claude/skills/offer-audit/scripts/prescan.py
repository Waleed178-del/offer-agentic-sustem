#!/usr/bin/env python3
"""Deterministic prescan of one offer PDF. Runs before Agent 1.

Produces, under RUN_DIR/OFFER_ID/corpus:
  pages/NNN.txt         layout-preserving text per page (pdftotext -layout)
  full_text.txt         all pages with === PAGE NNN === markers
  images/page-NNN.png   renders of low-text or image-heavy pages for vision
and RUN_DIR/OFFER_ID/prescan.json with:
  lexicon hits per category, corruption tokens, blank-cell candidates,
  vision queue, section header candidates, ocr_required flag.

This is the anti-recall-loss anchor: Agent 5 must close every lexicon hit.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, die, dump_json, load_json, load_state, offer_dir  # noqa: E402

LOW_TEXT_CHARS = 350
RENDER_DPI = 150
HEADER_RE = re.compile(r"^\s{0,6}((?:\d{1,2}\.){0,4}\d{1,2})\.?\s{1,6}([A-Z][A-Za-z0-9 /&,()'\-]{3,90})\s*$")


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        die(f"required tool not installed: {cmd[0]} (install poppler-utils)")
    except subprocess.CalledProcessError as exc:
        die(f"{' '.join(cmd)} failed: {exc.stderr.strip()}")
    return ""


def images_per_page(pdf: Path) -> dict[int, int]:
    counts: dict[int, int] = {}
    try:
        out = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return counts
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) > 4 and parts[0].isdigit():
            try:
                w, h = int(parts[3]), int(parts[4])
            except ValueError:
                continue
            if w * h >= 200 * 200:  # ignore logos and bullets
                pg = int(parts[0])
                counts[pg] = counts.get(pg, 0) + 1
    return counts


def compile_lexicon(lex: dict) -> dict[str, list[re.Pattern]]:
    out = {}
    for cat, pats in lex.items():
        if cat.startswith("_") or cat in ("corruption_tokens", "units_for_blank_detection"):
            continue
        out[cat] = [re.compile(p, re.IGNORECASE) for p in pats]
    return out


def line_context(text: str, start: int, end: int, width: int = 160) -> str:
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le == -1 else le
    snippet = re.sub(r"\s+", " ", text[ls:le]).strip()
    return snippet[:width]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--offer", required=True)
    ap.add_argument("--no-render", action="store_true", help="skip PNG rendering")
    ap.add_argument("--dpi", type=int, default=RENDER_DPI)
    a = ap.parse_args()

    run_dir = Path(a.run_dir).resolve()
    st = load_state(run_dir)
    if a.offer not in st["offers"]:
        die(f"unknown offer {a.offer}")
    pdf = Path(st["offers"][a.offer]["pdf_path"])
    odir = offer_dir(run_dir, a.offer)
    pages_dir = odir / "corpus" / "pages"
    img_dir = odir / "corpus" / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    raw = run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"])
    page_texts = raw.split("\f")
    if page_texts and not page_texts[-1].strip():
        page_texts = page_texts[:-1]
    n_pages = st["offers"][a.offer].get("page_count") or len(page_texts)
    while len(page_texts) < n_pages:
        page_texts.append("")

    lex = load_json(SKILL_DIR / "config" / "lexicon.json")
    patterns = compile_lexicon(lex)
    corruption_tokens = lex["corruption_tokens"]
    unit_tokens = lex["units_for_blank_detection"]
    unit_re = re.compile("|".join(re.escape(u) for u in unit_tokens))

    imgs = images_per_page(pdf)
    hits: dict[str, list[dict]] = {cat: [] for cat in patterns}
    corruption: list[dict] = []
    blanks: list[dict] = []
    headers: list[dict] = []
    vision_queue: list[dict] = []
    char_counts = []

    with open(odir / "corpus" / "full_text.txt", "w", encoding="utf-8") as full:
        for idx, text in enumerate(page_texts, start=1):
            (pages_dir / f"{idx:03d}.txt").write_text(text, encoding="utf-8")
            full.write(f"\n=== PAGE {idx:03d} ===\n{text}")
            chars = len(re.sub(r"\s", "", text))
            char_counts.append(chars)

            for cat, pats in patterns.items():
                for pat in pats:
                    for m in pat.finditer(text):
                        hits[cat].append({"page": idx, "match": m.group(0), "context": line_context(text, m.start(), m.end())})
            for tok in corruption_tokens:
                start = 0
                while True:
                    pos = text.find(tok, start)
                    if pos == -1:
                        break
                    corruption.append({"page": idx, "token": tok, "context": line_context(text, pos, pos + len(tok))})
                    start = pos + len(tok)
            for line in text.splitlines():
                if unit_re.search(line):
                    stripped = unit_re.sub("", line)
                    if not re.search(r"\d", stripped) and len(stripped.strip()) > 3:
                        blanks.append({"page": idx, "line": re.sub(r"\s+", " ", line).strip()[:160]})
                hm = HEADER_RE.match(line)
                if hm and len(line.strip()) < 100:
                    headers.append({"page": idx, "number": hm.group(1), "title": hm.group(2).strip()})

            reasons = []
            if chars < LOW_TEXT_CHARS:
                reasons.append(f"low_text({chars} chars)")
            if imgs.get(idx):
                reasons.append(f"images({imgs[idx]})")
            if reasons:
                vision_queue.append({"page": idx, "reasons": reasons, "image": f"corpus/images/page-{idx:03d}.png"})

    ocr_required = n_pages > 0 and sum(1 for c in char_counts if c < 50) / n_pages > 0.6

    if not a.no_render:
        for item in vision_queue:
            pg = item["page"]
            prefix = img_dir / f"page-{pg:03d}"
            subprocess.run(["pdftoppm", "-r", str(a.dpi), "-f", str(pg), "-l", str(pg), "-png", "-singlefile", str(pdf), str(prefix)],
                           capture_output=True, check=False)

    # dedupe identical hits on the same page/context
    for cat in hits:
        seen = set()
        uniq = []
        for h in hits[cat]:
            k = (h["page"], h["context"])
            if k not in seen:
                seen.add(k)
                uniq.append(h)
        hits[cat] = uniq
    for i, c in enumerate(corruption, start=1):
        c["corruption_id"] = f"C-{i:03d}"

    summary = {
        "offer_id": a.offer,
        "pdf_path": str(pdf),
        "page_count": n_pages,
        "ocr_required": ocr_required,
        "chars_per_page": char_counts,
        "vision_queue": vision_queue,
        "section_header_candidates": headers,
        "corruption": corruption,
        "blank_cell_candidates": blanks,
        "lexicon_hits": hits,
        "lexicon_hit_counts": {k: len(v) for k, v in hits.items()},
    }
    dump_json(odir / "prescan.json", summary)
    print(f"{a.offer}: {n_pages} pages | ocr_required={ocr_required} | vision_queue={len(vision_queue)} pages")
    print(f"  corruption tokens: {len(corruption)} | blank-cell candidates: {len(blanks)} | header candidates: {len(headers)}")
    print("  lexicon hits: " + ", ".join(f"{k}={len(v)}" for k, v in hits.items()))
    print(f"  wrote {odir / 'prescan.json'}")


if __name__ == "__main__":
    main()
