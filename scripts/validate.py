"""Step 2: Batch JSON + images ki jaanch. Saari galtiyan ek saath dikhati hai."""
import json, re, sys, difflib, datetime as dt
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ROOT, BATCH_DIR, IMG_DIR, SLUG_RE, IST, Report, load_site, load_categories, natural_key,
                    normalize_name, parse_dt, first_commit_time, image_index, rel)

REQUIRED_STR = ["title", "slug", "category", "summary", "body", "source", "source_link", "image", "image_alt"]
TYPES = {"news", "explainer", "roundup"}
LINK_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
HTML_RE = re.compile(r"</?[a-zA-Z][^>]*>")
IMG_EXT_RE = re.compile(r"\.(jpe?g|png|jfif|bmp|tiff?|gif|heic|heif|webp)$", re.I)
PLACEHOLDER_HINTS = ("USERNAME", "YOUR", "example.com")


def is_https(u):
    try:
        p = urlparse(u)
        return p.scheme == "https" and bool(p.netloc) and "." in p.netloc
    except Exception:
        return False


def load_batches(rep):
    """Return list of raw article dicts with _file/_idx. JSON galti par error jama karta hai."""
    out = []
    files = sorted([p for p in BATCH_DIR.glob("*.json") if not p.name.startswith("_")], key=natural_key) if BATCH_DIR.exists() else []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            rep.error("JSON_SYNTAX", f"JSON syntax galat hai: line {e.lineno}, column {e.colno} ({e.msg}).",
                      "Us line ke aas-paas dekhein: kya koi comma (,) chhoot gaya ya extra hai, quote (\") band nahi hua, ya body ke andar \" ko \\\" nahi likha? jsonlint.com par file paste karke bhi check kar sakte hain.", file=f)
            continue
        except UnicodeDecodeError:
            rep.error("JSON_ENCODING", "File UTF-8 me nahi hai.", "File ko UTF-8 encoding me save karein (Notepad: Save As -> Encoding: UTF-8).", file=f)
            continue
        if not isinstance(data, list):
            rep.error("JSON_NOT_ARRAY", f"File ka top-level {type(data).__name__} hai, array [ ... ] hona chahiye.",
                      "Poori file [ se shuru aur ] par khatam honi chahiye, andar articles { ... } comma se alag.", file=f)
            continue
        for i, a in enumerate(data, 1):
            if not isinstance(a, dict):
                rep.error("ARTICLE_NOT_OBJECT", f"Item #{i} object { '{' }...{ '}' } nahi hai.", "Har article { } ke andar key-value form me hona chahiye.", file=f, art=i)
                continue
            a["_file"], a["_idx"] = f, i
            out.append(a)
    return out


def check_list_of_dicts(rep, a, field, keys):
    v = a.get(field)
    if v is None:
        return
    ctx = dict(file=a["_file"], art=a["_idx"], slug=a.get("slug"), field=field)
    if not isinstance(v, list):
        rep.error("BAD_TYPE", f"'{field}' list hona chahiye.", f"Aise likhein: \"{field}\": [{{" + ", ".join(f'\"{k}\": \"...\"' for k in keys) + "}]", **ctx)
        return
    for n, item in enumerate(v, 1):
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item.get(k).strip() for k in keys):
            rep.error("BAD_ITEM", f"'{field}' ke item #{n} me {', '.join(keys)} (text) zaruri hain.", "Har item me dono keys bharein, khaali na chhodein.", **ctx)


def validate(rep, strict_site=True):
    site, cats = load_site(), load_categories()
    cat_all = {c["slug"]: c for c in cats}
    cat_ok = {c["slug"] for c in cats if c.get("enabled", True)}
    arts = load_batches(rep)
    idx = image_index()
    slug_seen = {}
    good = []

    # ---- pehle slugs jama karo (internal links check ke liye) ----
    all_slugs = {a["slug"] for a in arts if isinstance(a.get("slug"), str) and SLUG_RE.match(a["slug"])}

    for a in arts:
        ctx = lambda field=None: dict(file=a["_file"], art=a["_idx"], slug=a.get("slug") if isinstance(a.get("slug"), str) else None, field=field)
        n_err = len(rep.errors)

        # required strings
        for k in REQUIRED_STR:
            if k not in a:
                rep.error("FIELD_MISSING", f"Zaruri field '{k}' hai hi nahi.", f"Article me \"{k}\": \"...\" jodein (sample ke liye Data/sample.json dekhein).", **ctx(k))
            elif not isinstance(a[k], str):
                rep.error("BAD_TYPE", f"'{k}' text (string) hona chahiye, mila: {type(a[k]).__name__}.", f"'{k}' ko \"...\" quotes me likhein.", **ctx(k))
            elif not a[k].strip():
                rep.error("FIELD_EMPTY", f"'{k}' khaali hai.", f"'{k}' me content bharein.", **ctx(k))
        for k in ("key_points", "tags"):
            v = a.get(k)
            if k not in a:
                rep.error("FIELD_MISSING", f"Zaruri field '{k}' hai hi nahi.", f"Article me \"{k}\": [\"...\", \"...\"] jodein.", **ctx(k))
            elif not isinstance(v, list) or any(not isinstance(x, str) or not x.strip() for x in v):
                rep.error("BAD_TYPE", f"'{k}' text ki list honi chahiye.", f"Aise likhein: \"{k}\": [\"pehla\", \"doosra\"]", **ctx(k))
            elif not v:
                (rep.error if k == "key_points" else rep.warn)("FIELD_EMPTY", f"'{k}' list khaali hai.", f"'{k}' me kam se kam 1-2 items daalein.", **ctx(k))

        slug = a.get("slug") if isinstance(a.get("slug"), str) else ""
        if slug:
            if not SLUG_RE.match(slug) or len(slug) > 80:
                rep.error("SLUG_INVALID", f"Slug '{slug}' galat hai (sirf chhote english letters, digits aur hyphen; max 80 akshar).",
                          "Jaise: rbi-sgb-redemption. Space, underscore, hindi ya capital letters hatayein.", **ctx("slug"))
            elif slug in slug_seen:
                f0, i0 = slug_seen[slug]
                rep.error("SLUG_DUPLICATE", f"Slug '{slug}' pehle se {f0.name} ke article #{i0} me use hua hai (ab {a['_file'].name} article #{a['_idx']}).",
                          "Dono me se ek article ka slug alag rakhein.", **ctx("slug"))
            else:
                slug_seen[slug] = (a["_file"], a["_idx"])

        # category
        c = a.get("category")
        if isinstance(c, str) and c.strip():
            if c not in cat_all:
                rep.error("CATEGORY_UNKNOWN", f"Category '{c}' config/categories.json me nahi hai.", "Inme se ek likhein: " + ", ".join(sorted(cat_ok)), **ctx("category"))
            elif c not in cat_ok:
                rep.error("CATEGORY_DISABLED", f"Category '{c}' abhi band (enabled=false) hai.", "Dusri category chunein ya categories.json me us category ko enabled: true karein.", **ctx("category"))

        # source link
        if isinstance(a.get("source_link"), str) and a["source_link"].strip() and not is_https(a["source_link"].strip()):
            rep.error("SOURCE_LINK_INVALID", f"source_link '{a['source_link']}' valid https:// link nahi hai.", "Poora link daalein, https:// se shuru, jaise https://www.rbi.org.in/...", **ctx("source_link"))

        # image
        im = a.get("image")
        if isinstance(im, str) and im.strip():
            stem = IMG_EXT_RE.sub("", im.strip())
            norm = normalize_name(stem)
            if not norm:
                rep.error("IMAGE_NAME_INVALID", f"image '{im}' se koi valid naam nahi bana (english letters/digits chahiye).", "Image ka naam jaise rbi-sgb-redemption likhein, bina extension ke.", **ctx("image"))
            elif norm not in idx:
                near = difflib.get_close_matches(norm, list(idx.keys()), n=3, cutoff=0.4)
                sugg = (" Sabse milte-jule naam: " + ", ".join(near) + ".") if near else (" assets/images me abhi koi milti-julti image nahi hai." if not idx else "")
                rep.error("IMAGE_NOT_FOUND", f"Image '{im}' (normalize hone par '{norm}.webp') assets/images me nahi mili.{sugg} Shayad extension, capital/small letters ya space ka fark hai, ya image upload nahi hui.",
                          f"assets/images me '{norm}.webp' hona chahiye. Ya to image upload karein (Step 1 use WebP bana dega), ya JSON me 'image' ka naam sahi karein (bina extension).", **ctx("image"))
            else:
                try:
                    with Image.open(idx[norm]) as pim:
                        pim.load()
                except Exception as e:
                    rep.error("IMAGE_CORRUPT", f"'{idx[norm].name}' kharab hai ({type(e).__name__}).", "Image dobara export karke daalein.", **ctx("image"))
                a["_image_path"], a["_image_stem"] = idx[norm], norm
            if IMG_EXT_RE.search(im.strip()):
                rep.warn("IMAGE_HAS_EXT", f"image me extension likha hai ('{im}'), ignore kiya gaya.", "Sirf naam likhein, bina .jpg/.png ke.", **ctx("image"))

        # optional fields
        if "article_type" in a and a["article_type"] not in TYPES:
            rep.error("BAD_VALUE", f"article_type '{a['article_type']}' galat hai.", "Inme se ek: news, explainer, roundup.", **ctx("article_type"))
        if "explainer" in a and not isinstance(a["explainer"], str):
            rep.error("BAD_TYPE", "'explainer' text hona chahiye.", "\"explainer\": \"...\" likhein.", **ctx("explainer"))
        check_list_of_dicts(rep, a, "glossary", ["term", "meaning"])
        check_list_of_dicts(rep, a, "faq", ["q", "a"])
        check_list_of_dicts(rep, a, "timeline", ["date", "event"])
        check_list_of_dicts(rep, a, "extra_sources", ["name", "link"])
        for s in a.get("extra_sources") or []:
            if isinstance(s, dict) and isinstance(s.get("link"), str) and not is_https(s["link"].strip()):
                rep.error("SOURCE_LINK_INVALID", f"extra_sources ka link '{s['link']}' valid https:// nahi hai.", "https:// se shuru hone wala poora link daalein.", **ctx("extra_sources"))

        # body
        body = a.get("body") if isinstance(a.get("body"), str) else ""
        for m in LINK_RE.finditer(body):
            if m.group(1).strip() not in all_slugs:
                rep.error("INTERNAL_LINK_BROKEN", f"[[{m.group(1)}|{m.group(2)}]] ka slug '{m.group(1).strip()}' kisi article me nahi mila.",
                          "Slug sahi karein (kisi maujood article ka slug) ya ye link hata dein.", **ctx("body"))
        if HTML_RE.search(body):
            rep.warn("BODY_RAW_HTML", "Body me HTML tags mile; unhe text ki tarah dikhaya jayega (HTML chalne nahi diya jata).", "HTML hatayein; subheading ke liye '## ', list ke liye '- ' use karein.", **ctx("body"))
        if body and len(body.strip()) < 300:
            rep.warn("BODY_SHORT", f"Body bahut chhoti hai ({len(body.strip())} akshar).", "SEO/AdSense ke liye khabar kam se kam kuch paragraphs ki rakhein.", **ctx("body"))
        if isinstance(a.get("title"), str) and len(a["title"]) > 70:
            rep.warn("TITLE_LONG", f"Title {len(a['title'])} akshar ka hai (70 se zyada).", "Title chhota karein, Google use kaat dega.", **ctx("title"))
        sm = a.get("summary")
        if isinstance(sm, str) and sm.strip() and not (120 <= len(sm.strip()) <= 160):
            rep.warn("SUMMARY_LENGTH", f"Summary {len(sm.strip())} akshar ki hai (behtar: 120-160).", "Summary ko 120-160 akshar ke beech rakhein.", **ctx("summary"))

        # dates
        for k in ("published", "updated"):
            if k in a and a[k] not in (None, ""):
                try:
                    d = parse_dt(a[k])
                    a["_" + k] = d
                    if k == "published" and d > dt.datetime.now(IST) + dt.timedelta(minutes=5):
                        rep.warn("DATE_FUTURE", f"published ({a[k]}) future me hai.", "Aaj ya pehle ki date daalein; ye article abhi bhi live hoga.", **ctx(k))
                except (ValueError, TypeError):
                    rep.error("DATE_FORMAT", f"{k} '{a[k]}' ka format galat hai.", "Aise likhein: 2026-10-27T09:30:00+05:30", **ctx(k))

        a["_ok"] = len(rep.errors) == n_err
        good.append(a)

    # ---- site-level warnings ----
    f = ROOT / "config" / "site.json"
    for k in ("contact_email", "address", "grievance_officer", "grievance_email", "editor_name"):
        if not str(site.get(k, "")).strip():
            rep.warn("SITE_PLACEHOLDER", f"config/site.json me '{k}' khaali hai (pages par 'jald uplabdh' dikhega).", f"site.json me '{k}' bharein.", file=f, field=k)
    if any(h in str(site.get("site_url", "")) for h in PLACEHOLDER_HINTS) and not site.get("custom_domain"):
        rep.warn("SITE_URL_PLACEHOLDER", "site.json ka site_url abhi placeholder hai (GitHub par build ho to repo se khud nikala jayega).", "Apna asli URL daalein, jaise https://niti-khabar.in (aur base_path khaali rakhein).", file=f, field="site_url")
    if not (IMG_DIR / "Logo.png").exists():
        rep.warn("LOGO_MISSING", "assets/images/Logo.png nahi mila; text wordmark 'Niti Khabar' dikhaya jayega.", "~800x200px transparent PNG banakar assets/images me Logo.png naam se daalein.", file=IMG_DIR / "Logo.png")
    return site, cats, good


def main():
    rep = Report("2. Batch aur Images ki jaanch (validate)")
    validate(rep)
    rep.emit()
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
