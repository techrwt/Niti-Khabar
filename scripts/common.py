"""Saari scripts ke liye shared helpers: config, naam normalize, error report."""
import json, os, re, sys, subprocess, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
IMG_DIR = ROOT / "assets" / "images"
BATCH_DIR = ROOT / "Data" / "batches"
SRC_EXT = {".jpg", ".jpeg", ".png", ".jfif", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif"}
KEEP_NAMES = {"logo.png", "favicon.png"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_name(stem: str) -> str:
    s = stem.strip().lower().replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p.name))]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_site():
    return read_json(ROOT / "config" / "site.json")


def load_categories():
    cats = read_json(ROOT / "config" / "categories.json")
    return sorted(cats, key=lambda c: c.get("order", 99))


def rel(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except Exception:
        return str(p)


def parse_dt(value):
    """ISO string -> aware datetime (IST). Galat ho to ValueError."""
    d = dt.datetime.fromisoformat(str(value).strip())
    if d.tzinfo is None:
        d = d.replace(tzinfo=IST)
    return d.astimezone(IST)


_git_cache = {}


def first_commit_time(path: Path):
    """Batch file ke pehle git commit ka time, nahi to file mtime (IST)."""
    key = str(path)
    if key in _git_cache:
        return _git_cache[key]
    result = None
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%aI", "--", rel(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        ).stdout.strip().splitlines()
        if out:
            result = parse_dt(out[-1])
    except Exception:
        result = None
    if result is None:
        result = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=IST)
    _git_cache[key] = result
    return result


def image_index():
    """assets/images ki .webp files: normalized stem -> Path"""
    idx = {}
    if IMG_DIR.exists():
        for p in sorted(IMG_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() == ".webp":
                idx.setdefault(normalize_name(p.stem), p)
    return idx


def esc_cmd(s: str) -> str:
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def esc_prop(s: str) -> str:
    return esc_cmd(s).replace(":", "%3A").replace(",", "%2C")


class Report:
    """Saari galtiyan ek saath jama karo, phir ek saath dikhao."""

    def __init__(self, step: str):
        self.step = step
        self.errors = []
        self.warnings = []

    def _add(self, bucket, code, what, fix, file=None, art=None, slug=None, field=None):
        bucket.append(dict(code=code, what=what, fix=fix, file=file, art=art, slug=slug, field=field))

    def error(self, code, what, fix, **kw):
        self._add(self.errors, code, what, fix, **kw)

    def warn(self, code, what, fix, **kw):
        self._add(self.warnings, code, what, fix, **kw)

    @staticmethod
    def _where(i):
        parts = []
        if i["file"]:
            parts.append(Path(str(i["file"])).name)
        if i["art"] is not None:
            parts.append(f"article #{i['art']}" + (f" (slug: {i['slug']})" if i["slug"] else ""))
        if i["field"]:
            parts.append(f"field: {i['field']}")
        return " → ".join(parts)

    def line(self, i, icon):
        where = self._where(i)
        head = f"{icon} [{i['code']}] " + (where + " | " if where else "")
        return f"{head}Kya galat hai: {i['what']} | Kaise theek karein: {i['fix']}"

    def emit(self):
        gha = os.environ.get("GITHUB_ACTIONS") == "true"
        for i in self.warnings:
            print(self.line(i, "⚠️"))
            if gha:
                self._annotate("warning", i)
        for i in self.errors:
            print(self.line(i, "❌"))
            if gha:
                self._annotate("error", i)
        print()
        print(f"Natija: {len(self.errors)} error, {len(self.warnings)} warning.")
        summ = os.environ.get("GITHUB_STEP_SUMMARY")
        if summ:
            with open(summ, "a", encoding="utf-8") as f:
                f.write(self.markdown())

    def _annotate(self, level, i):
        props = []
        if i["file"]:
            props.append(f"file={esc_prop(rel(i['file']) if Path(str(i['file'])).is_absolute() else i['file'])}")
        props.append(f"title={esc_prop(i['code'])}")
        msg = f"{self._where(i)} | {i['what']} | Theek karein: {i['fix']}"
        print(f"::{level} {','.join(props)}::{esc_cmd(msg)}")

    def markdown(self):
        def cell(x):
            return str(x if x is not None else "-").replace("|", "\\|").replace("\n", " ")
        out = []
        if self.errors:
            out.append(f"## ❌ Fail hua step: {self.step}\n")
        else:
            out.append(f"## ✅ Step pass: {self.step}\n")
        for title, items in (("Errors (inhe theek karna zaruri hai)", self.errors), ("Warnings (deploy nahi rokengi)", self.warnings)):
            if not items:
                continue
            out.append(f"### {title}\n")
            out.append("| File | Article | Field | Galti | Solution |\n|---|---|---|---|---|")
            for i in items:
                art = (f"#{i['art']} {i['slug'] or ''}").strip() if i["art"] is not None else "-"
                out.append(f"| {cell(Path(str(i['file'])).name if i['file'] else '-')} | {cell(art)} | {cell(i['field'])} | **{cell(i['code'])}**: {cell(i['what'])} | {cell(i['fix'])} |")
            out.append("")
        return "\n".join(out) + "\n"
