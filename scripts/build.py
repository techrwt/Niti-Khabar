"""Step 3: static site banao -> public/. Pehle validate chalta hai; error ho to build nahi banta (purani site safe rahe)."""
import hashlib, html, json, os, re, shutil, sys, datetime as dt
from pathlib import Path
from xml.sax.saxutils import escape as xesc
from markupsafe import Markup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, IMG_DIR, IST, Report, normalize_name, natural_key, first_commit_time, rel
from validate import validate, LINK_RE

PUBLIC = ROOT / "public"
CACHE = ROOT / ".cache" / "img"
WIDTHS = (400, 800, 1200)
PER_PAGE = 24
CHUNK = 30
MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
NAVY = (11, 31, 58)


# ---------------------------------------------------------------- helpers
def date_hi(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def minify_html(s):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    lines = [ln.strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def minify_css(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([{};,>])\s*", r"\1", s)
    s = re.sub(r":\s+", ":", s)
    return s.replace(";}", "}").strip()


def minify_js(s):
    # sirf poori-line comments aur khaali lines hatao (safe)
    out = []
    for ln in s.splitlines():
        t = ln.strip()
        if not t or t.startswith("//"):
            continue
        out.append(t)
    return "\n".join(out)


def write(path, text, minify=False):
    p = PUBLIC / path.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    if minify:
        text = minify_html(text)
    p.write_text(text, encoding="utf-8")


def slugify_tag(tag):
    n = normalize_name(tag)
    return n or "t-" + hashlib.sha1(tag.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- text rendering
def inline(text, base, pages=False):
    s = html.escape(text, quote=True)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = LINK_RE.sub(lambda m: f'<a href="{base}/news/{m.group(1).strip()}/">{m.group(2).strip()}</a>', s)
    if pages:
        def link(m):
            label, u = m.group(1), m.group(2)
            if u.startswith("mailto:(") or u.startswith("mailto:%28"):
                return label
            if u.startswith("/"):
                u = base + u
                return f'<a href="{u}">{label}</a>'
            ext = u.startswith("http")
            return f'<a href="{u}"' + (' rel="noopener noreferrer" target="_blank"' if ext else "") + f">{label}</a>"
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    return s


def render_body(text, base, pages=False):
    out, para, items = [], [], []

    def flush():
        nonlocal para, items
        if para:
            out.append("<p>" + inline(" ".join(para), base, pages) + "</p>")
            para = []
        if items:
            out.append("<ul>" + "".join("<li>" + inline(i, base, pages) + "</li>" for i in items) + "</ul>")
            items = []

    for raw in text.replace("\r\n", "\n").split("\n"):
        ln = raw.strip()
        if not ln:
            flush()
        elif ln.startswith("### "):
            flush(); out.append("<h3>" + inline(ln[4:], base, pages) + "</h3>")
        elif ln.startswith("## "):
            flush(); out.append("<h2>" + inline(ln[3:], base, pages) + "</h2>")
        elif ln.startswith(("- ", "* ")):
            if para:
                flush()
            items.append(ln[2:].strip())
        elif re.match(r"^\d+[.)]\s", ln):
            if para:
                flush()
            items.append(re.sub(r"^\d+[.)]\s", "", ln))
        else:
            if items:
                flush()
            para.append(ln)
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- images
def cover_save(im, size, path, fmt, **kw):
    im = ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
    im.save(path, fmt, **kw)


def get_font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def letter_icon(size, text="N"):
    im = Image.new("RGB", (size, size), NAVY)
    d = ImageDraw.Draw(im)
    f = get_font(int(size * 0.62))
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), text, font=f, fill="white")
    return im


def process_article_images(arts, rep):
    CACHE.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "img").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "og").mkdir(parents=True, exist_ok=True)
    info, done = {}, set()
    for a in arts:
        stem, src = a["_image_stem"], a["_image_path"]
        if stem in done:
            continue
        done.add(stem)
        h = hashlib.sha1(src.read_bytes()).hexdigest()[:10]
        with Image.open(src) as im0:
            im0.load()
            im = im0.convert("RGB") if im0.mode not in ("RGB", "RGBA") else im0.copy()
        ow, oh = im.size
        widths = sorted(set([w for w in WIDTHS if w < ow] + [min(ow, 1200)]))
        vs = {}
        for w in widths:
            hh = max(1, round(oh * w / ow))
            cp = CACHE / f"{stem}-{w}-{h}.webp"
            if not cp.exists():
                im.resize((w, hh), Image.LANCZOS).save(cp, "WEBP", quality=80, method=4)
            shutil.copyfile(cp, PUBLIC / "img" / f"{stem}-{w}.webp")
            vs[w] = hh
        og = CACHE / f"{stem}-og-{h}.jpg"
        if not og.exists():
            cover_save(im, (1200, 630), og, "JPEG", quality=85, optimize=True, progressive=True)
        shutil.copyfile(og, PUBLIC / "og" / f"{stem}.jpg")
        info[stem] = dict(ow=ow, oh=oh, vs=vs)
    return info


def build_brand(base):
    """Logo.png / Favicon.png se logo.webp, favicon.ico, apple-touch-icon, PWA icons, default OG."""
    logo = None
    lp = IMG_DIR / "Logo.png"
    fp = IMG_DIR / "Favicon.png"
    (PUBLIC / "icons").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "img").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "og").mkdir(parents=True, exist_ok=True)
    lim = None
    if lp.exists():
        try:
            with Image.open(lp) as x:
                lim = ImageOps.exif_transpose(x).convert("RGBA")
            ar = lim.width / lim.height
            th = 104
            tw = min(round(th * ar), 1000)
            lim.resize((tw, th), Image.LANCZOS).save(PUBLIC / "img" / "logo.webp", "WEBP", quality=90, method=4)
            logo = dict(w=round(52 * ar), h=52)
        except Exception as e:
            print(f"⚠️ Logo.png khul nahi paya ({e}); text wordmark use hoga.")
            lim = None
    if fp.exists():
        try:
            with Image.open(fp) as x:
                base_icon = ImageOps.fit(ImageOps.exif_transpose(x).convert("RGBA"), (512, 512), Image.LANCZOS)
        except Exception:
            base_icon = letter_icon(512).convert("RGBA")
    else:
        base_icon = letter_icon(512).convert("RGBA")
    flat = Image.new("RGB", (512, 512), "white")
    flat.paste(base_icon, mask=base_icon.split()[3])
    flat.resize((180, 180), Image.LANCZOS).save(PUBLIC / "apple-touch-icon.png")
    flat.resize((192, 192), Image.LANCZOS).save(PUBLIC / "icons" / "icon-192.png")
    flat.save(PUBLIC / "icons" / "icon-512.png")
    base_icon.resize((256, 256), Image.LANCZOS).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # default OG
    if lim is not None:
        bg = Image.new("RGB", (1200, 630), "white")
        w = min(760, lim.width * 3)
        l2 = lim.resize((w, round(w * lim.height / lim.width)), Image.LANCZOS)
        if l2.height > 300:
            l2 = l2.resize((round(l2.width * 300 / l2.height), 300), Image.LANCZOS)
        bg.paste(l2, ((1200 - l2.width) // 2, (630 - l2.height) // 2), l2)
    else:
        bg = Image.new("RGB", (1200, 630), NAVY)
        d = ImageDraw.Draw(bg)
        f = get_font(110)
        t = "Niti Khabar"
        bb = d.textbbox((0, 0), t, font=f)
        d.text(((1200 - (bb[2] - bb[0])) / 2 - bb[0], (630 - (bb[3] - bb[1])) / 2 - bb[1]), t, font=f, fill="white")
    bg.save(PUBLIC / "og" / "default.jpg", "JPEG", quality=88, optimize=True)
    return logo


# ---------------------------------------------------------------- main build
def main():
    t0 = dt.datetime.now(IST)
    rep = Report("3. Site banao (build)")
    site, cats_all, arts = validate(rep)
    if rep.errors:
        print("Build roka gaya: pehle ye galtiyan theek karein (purani site live rahegi).\n")
        rep.emit()
        return 1

    # ---- URL config
    base = (site.get("base_path") or "").strip().rstrip("/")
    site_url = (site.get("site_url") or "").strip().rstrip("/")
    domain = (site.get("custom_domain") or "").strip()
    placeholder = any(h in site_url for h in ("USERNAME", "YOUR", "example.com")) or not site_url
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if domain:
        site_url, base = "https://" + domain, ""
    elif placeholder and "/" in repo:
        owner, name = repo.split("/", 1)
        site_url = f"https://{owner}.github.io"
        base = "" if name.lower() == f"{owner}.github.io".lower() else "/" + name
        print(f"ℹ️ site_url placeholder tha, GitHub repo se nikala: {site_url}{base}")
    if base and not base.startswith("/"):
        base = "/" + base
    site = dict(site, site_url=site_url, base_path=base)
    ABS = site_url + base

    def url(path):
        return base + path

    def absu(path):
        return ABS + path

    # ---- reset output
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)

    cats = [c for c in cats_all if c.get("enabled", True)]
    cat_by = {c["slug"]: c for c in cats}

    # ---- brand + images
    logo = build_brand(base)
    img_info = process_article_images(arts, rep)

    # ---- articles prep
    files = sorted({a["_file"] for a in arts}, key=natural_key)
    rank = {f: i for i, f in enumerate(files)}
    for a in arts:
        pub = a.get("_published") or first_commit_time(a["_file"])
        a["published"] = pub
        a["updated"] = a.get("_updated")
        a["date_hi"] = date_hi(pub)
        a["updated_hi"] = date_hi(a["updated"]) if a["updated"] else ""
        a["path"] = f"/news/{a['slug']}/"
        a["abs_url"] = absu(a["path"])
        a["cat_name"] = cat_by[a["category"]]["name"]
        a["image_stem"] = a["_image_stem"]
        a["read_min"] = max(1, round(len(a["body"].split()) / 200))
        a["body_html"] = render_body(a["body"], base)
        a["tags"] = [t.strip() for t in a["tags"] if t.strip()]
        a["og_abs"] = absu(f"/og/{a['image_stem']}.jpg")
    arts.sort(key=lambda a: (a["published"], rank[a["_file"]], -a["_idx"]), reverse=True)
    by_slug = {a["slug"]: a for a in arts}

    # ---- pages
    pages, pdata = [], {}
    pf_dir = ROOT / "pages"
    fillers = {
        "SITE_NAME": site["site_name"], "SITE_NAME_HI": site.get("site_name_hi", site["site_name"]), "SITE_URL": ABS or site_url,
        "CONTACT_EMAIL": site.get("contact_email", ""), "ADDRESS": site.get("address", ""), "GRIEVANCE_OFFICER": site.get("grievance_officer", ""),
        "GRIEVANCE_EMAIL": site.get("grievance_email", ""), "EDITOR_NAME": site.get("editor_name", ""),
    }
    for pf in sorted(pf_dir.glob("*.md"), key=natural_key):
        raw = pf.read_text(encoding="utf-8")
        head, _, body = raw.partition("\n---\n")
        meta = {}
        for ln in head.splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip()] = v.strip()
        if not meta.get("title") or not body.strip():
            rep.warn("PAGE_FORMAT", "Page file ka format galat hai (upar title:/description:/order: phir --- line, phir content).", "pages/about.md jaisa format follow karein.", file=pf)
            continue

        def fill(m):
            key = m.group(1)
            if key not in fillers:
                rep.warn("PAGE_PLACEHOLDER_UNKNOWN", f"{{{{{key}}}}} naam ka placeholder maujood nahi hai.", "Placeholder ka naam check karein (jaise CONTACT_EMAIL, ADDRESS).", file=pf)
                return m.group(0)
            return fillers[key].strip() or "(जल्द उपलब्ध होगी)"
        body = re.sub(r"\{\{([A-Z_]+)\}\}", fill, body)
        p = dict(slug=pf.stem, title=meta["title"], desc=meta.get("description", meta["title"]), order=int(meta.get("order", 99)), html=render_body(body, base, pages=True))
        pages.append(p)
        pdata[p["slug"]] = p
    pages.sort(key=lambda p: p["order"])

    # ---- Jinja
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    env.globals["url"] = url
    env.filters["tojson_ld"] = lambda o: Markup(json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))

    def img(a, sizes, lead=False, thumb=False, alt=""):
        inf = img_info[a["image_stem"]]
        vs = inf["vs"]
        ws = sorted(vs)
        src_w = max([w for w in ws if w <= 800] or [ws[0]])
        srcset = ", ".join(f"{url('/img/' + a['image_stem'] + '-' + str(w) + '.webp')} {w}w" for w in ws)
        attrs = f'src="{url("/img/" + a["image_stem"] + "-" + str(src_w) + ".webp")}" srcset="{srcset}" sizes="{sizes}" width="{src_w}" height="{vs[src_w]}" alt="{html.escape(alt, quote=True)}" decoding="async"'
        attrs += ' fetchpriority="high"' if lead else ' loading="lazy"'
        return Markup(f"<img {attrs}>")
    env.globals["img"] = img

    # ---- static assets (hashed)
    assets = {}
    for name, fn, mn in (("css", "style.css", minify_css), ("js", "app.js", minify_js), ("ga", "ga.js", minify_js)):
        src = (ROOT / "static" / fn).read_text(encoding="utf-8")
        out = mn(src)
        h = hashlib.sha1(out.encode()).hexdigest()[:8]
        stem, ext = fn.rsplit(".", 1)
        hashed = f"{stem}.{h}.{ext}"
        (PUBLIC / hashed).write_text(out, encoding="utf-8")
        assets[name] = hashed
    for f in (ROOT / "static").iterdir():
        if f.name in ("_headers",):
            shutil.copyfile(f, PUBLIC / f.name)

    org = {"@context": "https://schema.org", "@type": "Organization", "name": site["site_name"], "alternateName": site.get("site_name_hi"), "url": absu("/"),
           "logo": {"@type": "ImageObject", "url": absu("/icons/icon-512.png")}}
    sameas = [v for v in site.get("social", {}).values() if v]
    if sameas:
        org["sameAs"] = sameas
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": site["site_name"], "url": absu("/"), "inLanguage": "hi-IN",
               "potentialAction": {"@type": "SearchAction", "target": absu("/search/") + "?q={search_term_string}", "query-input": "required name=search_term_string"}}
    now = t0
    common = dict(site=site, cats=cats, assets=assets, logo=logo, pages=pages, year=now.year, tagline=site.get("tagline", ""),
                  social_labels=[("x", "X (Twitter)"), ("facebook", "Facebook"), ("instagram", "Instagram"), ("youtube", "YouTube"), ("telegram", "Telegram"), ("whatsapp_channel", "WhatsApp चैनल")])
    default_og = absu("/og/default.jpg")

    def render(tpl, path, **ctx):
        c = dict(common)
        c.setdefault("og_image", default_og)
        c.update(ctx)
        c["jsonld"] = [org, website] + list(ctx.get("jsonld", []))
        c.setdefault("canonical", absu(path))
        c.setdefault("noindex", False)
        write(path.rstrip("/") + "/index.html" if path != "/404.html" else "/404.html", env.get_template(tpl).render(**c), minify=True)

    # ---- tags
    tag_map = {}
    for a in arts:
        for t in a["tags"]:
            tag_map.setdefault(slugify_tag(t), {"name": t, "items": []})["items"].append(a)
    tag_pages = {s: v for s, v in tag_map.items() if len(v["items"]) >= 3}
    for a in arts:
        a["tag_links"] = [dict(name=t, url=(url(f"/tag/{slugify_tag(t)}/") if slugify_tag(t) in tag_pages else None)) for t in a["tags"]]

    # ---- homepage
    latest = arts[:PER_PAGE]
    sections = []
    for c in cats:
        items = [a for a in arts if a["category"] == c["slug"]][:4]
        if items:
            sections.append(dict(slug=c["slug"], name=c["name"], arts=items))
    home_title = site.get("home_title") or f"{site.get('site_name_hi', site['site_name'])} ({site['site_name']}): ताज़ा हिंदी खबरें"
    render("home.html", "/", title=home_title, desc=site.get("description", ""), latest=latest, sections=sections, nav_active="home", noindex=False)
    # "/" ka output public/index.html
    # ---- listing pages (category / tag / archive)
    def listing(items, first_path, heading, title, desc, nav_active, blurb="", noindex=False, hide_if_empty=False):
        total = max(1, -(-len(items) // PER_PAGE))
        for n in range(1, total + 1):
            path = first_path if n == 1 else f"{first_path}page/{n}/"
            chunk = items[(n - 1) * PER_PAGE: n * PER_PAGE]
            prev_p = None if n == 1 else (first_path if n == 2 else f"{first_path}page/{n - 1}/")
            next_p = None if n == total else f"{first_path}page/{n + 1}/"
            pg = dict(n=n, total=total, prev=url(prev_p) if prev_p else None, next=url(next_p) if next_p else None)
            t = title if n == 1 else f"{title} - पेज {n}"
            render("category.html", path, items=chunk, pg=pg, heading=heading, blurb=blurb, title=t, desc=desc, nav_active=nav_active,
                   prev_url=absu(prev_p) if prev_p else None, next_url=absu(next_p) if next_p else None, noindex=noindex or not items,
                   jsonld=[{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                       {"@type": "ListItem", "position": 1, "name": "होम", "item": absu("/")},
                       {"@type": "ListItem", "position": 2, "name": heading, "item": absu(first_path)}]}])
    cat_items = {}
    for c in cats:
        items = [a for a in arts if a["category"] == c["slug"]]
        cat_items[c["slug"]] = items
        listing(items, f"/category/{c['slug']}/", c["name"], f"{c['name']}: ताज़ा खबरें | {site['site_name']}", c["description"], c["slug"], blurb=c["description"])
    for s, v in tag_pages.items():
        listing(v["items"], f"/tag/{s}/", f"#{v['name']}", f"{v['name']}: खबरें | {site['site_name']}", f"{v['name']} से जुड़ी सभी खबरें, {site['site_name']} पर।", "")
    listing(arts, "/archive/", "सभी खबरें", f"सभी खबरों का आर्काइव | {site['site_name']}", f"{site['site_name']} पर प्रकाशित सभी खबरें, नई से पुरानी।", "", noindex=False)

    # ---- articles
    for i, a in enumerate(arts):
        cands = []
        mytags = set(a["tags"])
        for b in arts:
            if b is a:
                continue
            sc = (2 if b["category"] == a["category"] else 0) + len(mytags & set(b["tags"]))
            if sc > 0:
                cands.append((sc, b["published"], b))
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
        related = [b for _, _, b in cands[:4]]
        title_tag = a["title"] if len(a["title"]) + len(site["site_name"]) + 3 > 70 else f"{a['title']} | {site['site_name']}"
        iso = lambda d: d.isoformat()
        cit = [a["source_link"]] + [s["link"] for s in a.get("extra_sources", [])]
        news = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": a["title"][:110], "description": a["summary"], "image": [a["og_abs"]],
                "datePublished": iso(a["published"]), "dateModified": iso(a["updated"] or a["published"]), "inLanguage": "hi-IN",
                "author": {"@type": "Organization", "name": site["site_name"], "url": absu("/editorial-policy/")},
                "publisher": {"@type": "Organization", "name": site["site_name"], "logo": {"@type": "ImageObject", "url": absu("/icons/icon-512.png")}},
                "mainEntityOfPage": {"@type": "WebPage", "@id": a["abs_url"]}, "articleSection": a["cat_name"], "keywords": ", ".join(a["tags"]),
                "isBasedOn": {"@type": "CreativeWork", "name": a["source"], "url": a["source_link"]}, "citation": cit}
        crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "होम", "item": absu("/")},
            {"@type": "ListItem", "position": 2, "name": a["cat_name"], "item": absu(f"/category/{a['category']}/")},
            {"@type": "ListItem", "position": 3, "name": a["title"], "item": a["abs_url"]}]}
        render("article.html", a["path"], a=a, title=title_tag, og_title=a["title"], desc=a["summary"], og_type="article", og_image=a["og_abs"],
               related=related, sidebar_latest=[x for x in arts if x is not a][:6], prev_a=arts[i - 1] if i > 0 else None, next_a=arts[i + 1] if i + 1 < len(arts) else None,
               nav_active=a["category"], jsonld=[news, crumbs],
               head_extra=Markup(f'<meta property="article:published_time" content="{iso(a["published"])}"><meta property="article:modified_time" content="{iso(a["updated"] or a["published"])}"><meta property="article:section" content="{html.escape(a["cat_name"])}">' + "".join(f'<meta property="article:tag" content="{html.escape(t, quote=True)}">' for t in a["tags"])))

    # ---- static pages, search, 404
    for p in pages:
        render("page.html", f"/{p['slug']}/", page=p, title=f"{p['title']} | {site['site_name']}", desc=p["desc"], nav_active="", sm_latest=arts[:30])
    render("page.html", "/search/", page=dict(slug="search", title="खबर खोजें", html=""), title=f"खबर खोजें | {site['site_name']}", desc=f"{site['site_name']} की खबरें खोजें।", noindex=True, nav_active="")
    render("404.html", "/404.html", title=f"पेज नहीं मिला | {site['site_name']}", desc="यह पेज नहीं मिला।", noindex=True, canonical=absu("/404.html"), nav_active="")

    # ---- JSON data
    D = PUBLIC / "data"
    D.mkdir(parents=True, exist_ok=True)

    def light(a):
        stem = a["image_stem"]
        vs = img_info[stem]["vs"]
        w = min(vs)
        return {"title": a["title"], "slug": a["slug"], "url": url(a["path"]), "category": a["category"], "category_name": a["cat_name"], "summary": a["summary"],
                "image": url(f"/img/{stem}-{w}.webp"), "tw": w, "th": vs[w], "published": a["published"].isoformat(), "date_hi": a["date_hi"]}

    def chunked(items, prefix):
        names = []
        for n in range(1, max(1, -(-len(items) // CHUNK)) + 1):
            part = items[(n - 1) * CHUNK: n * CHUNK]
            if not part and n > 1:
                break
            name = f"{prefix}-{n}.json"
            (D / name).write_text(json.dumps([light(a) for a in part], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            names.append(name)
        return names
    latest_files = chunked(arts, "latest") if arts else []
    cat_files = {c["slug"]: chunked(cat_items[c["slug"]], f"category-{c['slug']}") for c in cats if cat_items[c["slug"]]}
    (D / "search.json").write_text(json.dumps([{"t": a["title"], "s": a["slug"], "c": a["cat_name"], "g": a["tags"]} for a in arts], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (D / "index.json").write_text(json.dumps({"version": 1, "built": t0.isoformat(), "total": len(arts), "chunk_size": CHUNK, "base": base, "latest": latest_files, "categories": cat_files, "search": "search.json"}, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- sitemap / news sitemap / rss / robots / manifest
    urls = [(absu("/"), (arts[0]["updated"] or arts[0]["published"]).isoformat() if arts else None)]
    for c in cats:
        if cat_items[c["slug"]]:
            urls.append((absu(f"/category/{c['slug']}/"), (cat_items[c["slug"]][0]["published"]).isoformat()))
    for s in tag_pages:
        urls.append((absu(f"/tag/{s}/"), None))
    for a in arts:
        urls.append((a["abs_url"], (a["updated"] or a["published"]).isoformat()))
    for p in pages:
        urls.append((absu(f"/{p['slug']}/"), None))
    if arts:
        urls.append((absu("/archive/"), None))

    def urlset(rows):
        body = "".join(f"<url><loc>{xesc(u)}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>" for u, m in rows)
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>"
    smaps = ["sitemap.xml"]
    if len(urls) > 1000:
        parts = [urls[i:i + 1000] for i in range(0, len(urls), 1000)]
        smaps = []
        for n, part in enumerate(parts, 1):
            write(f"/sitemap-{n}.xml", urlset(part))
            smaps.append(f"sitemap-{n}.xml")
        idx = '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<sitemap><loc>{xesc(absu('/' + s))}</loc></sitemap>" for s in smaps) + "</sitemapindex>"
        write("/sitemap.xml", idx)
    else:
        write("/sitemap.xml", urlset(urls))
    recent = [a for a in arts if a["published"] >= t0 - dt.timedelta(days=2)][:1000]
    ns = "".join(f"<url><loc>{xesc(a['abs_url'])}</loc><news:news><news:publication><news:name>{xesc(site['site_name'])}</news:name><news:language>hi</news:language></news:publication><news:publication_date>{a['published'].isoformat()}</news:publication_date><news:title>{xesc(a['title'])}</news:title></news:news></url>" for a in recent)
    write("/news-sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' + ns + "</urlset>")

    def rfc822(d):
        return d.strftime("%a, %d %b %Y %H:%M:%S ") + "+0530"

    def feed(items, title, link, self_url):
        it = "".join(f"<item><title>{xesc(a['title'])}</title><link>{xesc(a['abs_url'])}</link><guid isPermaLink=\"true\">{xesc(a['abs_url'])}</guid><pubDate>{rfc822(a['published'])}</pubDate><category>{xesc(a['cat_name'])}</category><description>{xesc(a['summary'])}</description></item>" for a in items)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
                f"<title>{xesc(title)}</title><link>{xesc(link)}</link><description>{xesc(site.get('description', ''))}</description><language>hi-IN</language><lastBuildDate>{rfc822(t0)}</lastBuildDate>"
                f'<atom:link href="{xesc(self_url)}" rel="self" type="application/rss+xml"/>' + it + "</channel></rss>")
    write("/feed.xml", feed(arts[:50], site["site_name"], absu("/"), absu("/feed.xml")))
    for c in cats:
        if cat_items[c["slug"]]:
            write(f"/category/{c['slug']}/feed.xml", feed(cat_items[c["slug"]][:50], f"{c['name']} | {site['site_name']}", absu(f"/category/{c['slug']}/"), absu(f"/category/{c['slug']}/feed.xml")))
    robots = "User-agent: *\nAllow: /\n" + f"Disallow: {base}/search/\n\n" + "".join(f"Sitemap: {absu('/' + s)}\n" for s in ["sitemap.xml", "news-sitemap.xml"])
    write("/robots.txt", robots)
    write("/site.webmanifest", json.dumps({"name": site["site_name"], "short_name": site["site_name"][:12], "lang": "hi", "start_url": url("/"), "scope": url("/"), "display": "standalone",
                                           "background_color": "#FFFFFF", "theme_color": "#0B1F3A",
                                           "icons": [{"src": url("/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"}, {"src": url("/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"}]}, ensure_ascii=False, indent=1))
    write("/.nojekyll", "")
    if domain:
        write("/CNAME", domain + "\n")

    rep.emit()
    kb = lambda p: round(p.stat().st_size / 1024, 1)
    print(f"\n✅ Build ho gaya: {len(arts)} article, {len(cats)} categories, {len(pages)} pages -> public/")
    print(f"   home HTML: {kb(PUBLIC / 'index.html')} KB | CSS: {kb(PUBLIC / assets['css'])} KB | JS: {kb(PUBLIC / assets['js'])} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
