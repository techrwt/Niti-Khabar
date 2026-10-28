"""Step 1: assets/images ki saari images ko WebP me badlo (original tabhi delete jab WebP verify ho jaye)."""
import sys
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMG_DIR, SRC_EXT, KEEP_NAMES, Report, normalize_name

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False

MAX_SIDE = 1600


def to_webp(src: Path, dst: Path):
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        im.save(dst, "WEBP", quality=82, method=6)  # metadata/EXIF save nahi hota = strip


def verify(dst: Path) -> bool:
    try:
        with Image.open(dst) as im:
            im.load()
            return im.format == "WEBP" and im.width > 0 and im.height > 0
    except Exception:
        return False


def main():
    rep = Report("1. Images ko WebP me badlo")
    if not IMG_DIR.exists():
        print("assets/images folder nahi mila, kuch convert karna nahi.")
        return 0
    files = sorted(p for p in IMG_DIR.iterdir() if p.is_file())
    jobs, targets = [], {}
    for p in files:
        ext = p.suffix.lower()
        if p.name.lower() in KEEP_NAMES or ext == ".webp" or p.name.startswith("."):
            continue
        if ext not in SRC_EXT:
            if p.name != ".gitkeep":
                rep.warn("IMG_UNSUPPORTED", f"'{p.name}' ka format support nahi hai, ise chhod diya gaya.",
                         "jpg/png/jfif/bmp/tiff/gif/heic ya webp me save karke dobara daalein.", file=f"assets/images/{p.name}")
            continue
        norm = normalize_name(p.stem)
        if not norm:
            rep.error("IMG_BAD_NAME", f"'{p.name}' ke naam me a-z / 0-9 hai hi nahi (sirf hindi ya symbols), isliye naam nahi ban sakta.",
                      "File ka naam angrezi letters/digits me rakhein, jaise rbi-news-1.jpg", file=f"assets/images/{p.name}")
            continue
        targets.setdefault(norm, []).append(p)
        jobs.append((p, norm))

    converted = 0
    for norm, srcs in targets.items():
        dst = IMG_DIR / f"{norm}.webp"
        if len(srcs) > 1:
            names = " aur ".join(f"'{s.name}'" for s in srcs)
            rep.error("IMG_NAME_CLASH", f"{names} dono ka normalized naam '{norm}.webp' ban raha hai, ek dusre ko overwrite karenge.",
                      "Inme se ek file ka naam badal dein ya ek hata dein.", file=f"assets/images/{srcs[0].name}")
            continue
        if dst.exists():
            rep.error("IMG_WEBP_EXISTS", f"'{srcs[0].name}' ko '{dst.name}' banana tha, par ye naam pehle se maujood hai.",
                      f"Agar nayi image se badalna hai to purani '{dst.name}' delete karein; warna nayi file ka naam badal dein.",
                      file=f"assets/images/{srcs[0].name}")
            continue
        src = srcs[0]
        if src.suffix.lower() in (".heic", ".heif") and not HEIF_OK:
            rep.error("IMG_HEIC", f"'{src.name}' HEIC hai par pillow-heif install nahi hai.",
                      "requirements.txt me pillow-heif hai, workflow me 'pip install -r requirements.txt' chalna chahiye; ya photo ko jpg me badal dein.",
                      file=f"assets/images/{src.name}")
            continue
        try:
            with Image.open(src) as im:
                if src.suffix.lower() == ".gif" and getattr(im, "n_frames", 1) > 1:
                    rep.warn("IMG_ANIMATED_GIF", f"'{src.name}' animated GIF hai, as-is chhod diya (WebP nahi banaya).",
                             "Agar animation nahi chahiye to ek normal jpg/png daalein.", file=f"assets/images/{src.name}")
                    continue
            to_webp(src, dst)
            if not verify(dst):
                dst.unlink(missing_ok=True)
                raise ValueError("WebP ban gayi par dobara kholne par theek nahi nikli")
            src.unlink()
            converted += 1
            print(f"✅ {src.name} -> {dst.name}")
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as e:
            dst.unlink(missing_ok=True)
            rep.error("IMG_CORRUPT", f"'{src.name}' khul/convert nahi hui ({type(e).__name__}: {e}).",
                      "Image kharab ho sakti hai. Original device se dobara save/export karke daalein (jpg ya png).",
                      file=f"assets/images/{src.name}")

    print(f"\n{converted} image(s) WebP me convert hui.")
    rep.emit()
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
