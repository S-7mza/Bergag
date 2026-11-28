import html
import io
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OG_WIDTH = 1200
OG_HEIGHT = 630

_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

_FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

_FONT_CANDIDATES_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/consolab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
]


def _load_font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if mono:
        candidates = _FONT_CANDIDATES_MONO
    elif bold:
        candidates = _FONT_CANDIDATES_BOLD
    else:
        candidates = _FONT_CANDIDATES_REGULAR
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def _truncate(text: str, max_len: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip() + "…"


def _wrap_text_px(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> List[str]:
    """Pixel-accurate word wrapping with ellipsis on overflow."""
    words = " ".join((text or "").split()).split(" ")
    if not words or words == [""]:
        return []
    lines: List[str] = []
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip() if current else word
        w, _ = _text_size(draw, candidate, font)
        if w <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
                current = word
            else:
                # Single long word
                lines.append(_truncate(word, 28))
                current = ""
            if len(lines) == max_lines:
                # Append ellipsis to last line if words remain
                last = lines[-1]
                while _text_size(draw, last + "…", font)[0] > max_width and len(last) > 4:
                    last = last[:-1].rstrip()
                lines[-1] = last + "…"
                return lines
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: Tuple[int, int, int, int],
    outline: Tuple[int, int, int, int],
    text_color: Tuple[int, int, int, int],
    pad_x: int = 16,
    height: int = 36,
    radius: int = 10,
) -> int:
    tw, th = _text_size(draw, text, font)
    pw = tw + pad_x * 2
    draw.rounded_rectangle(
        [(x, y), (x + pw, y + height)],
        radius=radius,
        fill=fill,
        outline=outline,
        width=1,
    )
    tx = x + pad_x
    ty = y + (height - th) // 2 - 2
    draw.text((tx, ty), text, fill=text_color, font=font)
    return pw


def _create_base_canvas() -> Image.Image:
    """Creates a 1200x630 dark RGBA canvas with subtle grid & ambient radial glows."""
    canvas = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (9, 12, 18, 255))

    # Ambient radial glow layer (emerald top-left, indigo bottom-right)
    glow = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-180, -180), (540, 440)], fill=(16, 185, 129, 36))
    gdraw.ellipse([(680, 220), (1380, 820)], fill=(99, 102, 241, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=90))
    canvas = Image.alpha_composite(canvas, glow)

    # Subtle architectural dot grid
    grid = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    grdraw = ImageDraw.Draw(grid)
    for gx in range(28, OG_WIDTH, 36):
        for gy in range(28, OG_HEIGHT, 36):
            grdraw.point((gx, gy), fill=(148, 163, 184, 28))
    canvas = Image.alpha_composite(canvas, grid)

    # Main glass card
    card = Image.new("RGBA", (OG_WIDTH, OG_HEIGHT), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card)
    cdraw.rounded_rectangle(
        [(32, 28), (OG_WIDTH - 32, OG_HEIGHT - 28)],
        radius=26,
        fill=(15, 20, 30, 228),
        outline=(51, 65, 85, 130),
        width=2,
    )
    # Top accent gradient bar (emerald -> indigo)
    cdraw.rounded_rectangle([(32, 28), (OG_WIDTH // 2, 35)], radius=4, fill=(16, 185, 129, 255))
    cdraw.rounded_rectangle([(OG_WIDTH // 2 - 8, 28), (OG_WIDTH - 32, 35)], radius=4, fill=(99, 102, 241, 255))
    canvas = Image.alpha_composite(canvas, card)
    return canvas


def _draw_radial_gauge(rate: float, size: int = 196) -> Image.Image:
    """
    Draws a supersampled (2x) anti-aliased circular progress gauge for the AI Match Rate.
    """
    scale = 2
    s = size * scale
    gauge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gauge)

    if rate >= 75:
        arc_color = (16, 185, 129, 255)      # Emerald
        glow_color = (16, 185, 129, 45)
        txt_color = (110, 231, 183, 255)
    elif rate >= 45:
        arc_color = (245, 158, 11, 255)      # Amber
        glow_color = (245, 158, 11, 40)
        txt_color = (252, 211, 77, 255)
    elif rate >= 20:
        arc_color = (99, 102, 241, 255)      # Indigo
        glow_color = (99, 102, 241, 40)
        txt_color = (165, 180, 252, 255)
    else:
        arc_color = (100, 116, 139, 255)     # Slate
        glow_color = (100, 116, 139, 25)
        txt_color = (203, 213, 225, 255)

    pad = 18 * scale
    stroke = 16 * scale
    box = [(pad, pad), (s - pad, s - pad)]

    # Inner subtle fill + track ring
    draw.ellipse(box, fill=glow_color)
    draw.arc(box, start=0, end=360, fill=(30, 41, 59, 255), width=stroke)

    # Progress arc starting at 12 o'clock (-90 deg)
    clamped = max(0.0, min(100.0, rate))
    if clamped > 0:
        end_angle = -90 + (360.0 * clamped / 100.0)
        draw.arc(box, start=-90, end=end_angle, fill=arc_color, width=stroke)

    # Center percentage text (scaled proportionally to gauge size)
    ratio = size / 192.0
    font_num = _load_font(max(16, int(46 * scale * ratio)), bold=True, mono=True)
    font_lbl = _load_font(max(10, int(14 * scale * ratio)), bold=True)
    num_str = f"{clamped:.0f}%"
    nw, nh = _text_size(draw, num_str, font_num)
    draw.text(((s - nw) // 2, (s - nh) // 2 - int(12 * scale * ratio)), num_str, fill=txt_color, font=font_num)

    lbl_str = "MATCH IA"
    lw, lh = _text_size(draw, lbl_str, font_lbl)
    draw.text(((s - lw) // 2, (s + nh) // 2 - int(4 * scale * ratio)), lbl_str, fill=(148, 163, 184, 255), font=font_lbl)

    return gauge.resize((size, size), Image.Resampling.LANCZOS)


def _draw_brand_header(draw: ImageDraw.ImageDraw, badge_right: Optional[str] = None) -> None:
    font_logo = _load_font(26, bold=True)
    font_brand = _load_font(22, bold=True)
    font_sub = _load_font(16, bold=False)

    # Emerald logo tile
    draw.rounded_rectangle([(68, 60), (114, 106)], radius=12, fill=(16, 185, 129, 255))
    lw, lh = _text_size(draw, "B", font_logo)
    draw.text((68 + (46 - lw) // 2, 60 + (46 - lh) // 2 - 2), "B", fill=(9, 12, 18, 255), font=font_logo)

    draw.text((130, 61), "BERGAG", fill=(255, 255, 255, 255), font=font_brand)
    draw.text((130, 88), "Veille Marchés Publics Maroc  •  Décret 2-22-431", fill=(148, 163, 184, 255), font=font_sub)

    if badge_right:
        font_pill = _load_font(16, bold=True, mono=True)
        pw, _ = _text_size(draw, badge_right, font_pill)
        _draw_pill(
            draw,
            x=OG_WIDTH - 68 - (pw + 32),
            y=65,
            text=badge_right,
            font=font_pill,
            fill=(6, 78, 59, 255),
            outline=(16, 185, 129, 255),
            text_color=(110, 231, 183, 255),
            pad_x=16,
            height=34,
            radius=10,
        )


def _render_dashboard_card(canvas: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    _draw_brand_header(draw, badge_right="bergag.nexenflow.com")

    font_h1 = _load_font(44, bold=True)
    font_sub = _load_font(21, bold=False)
    font_feat = _load_font(19, bold=True)
    font_ui_sm = _load_font(15, bold=True)
    font_ui_xs = _load_font(14, bold=False)

    # Left column: Hero pitch
    draw.text((68, 150), "Intelligence IA des", fill=(255, 255, 255, 255), font=font_h1)
    draw.text((68, 204), "Marchés Publics", fill=(52, 211, 153, 255), font=font_h1)

    desc_lines = _wrap_text_px(
        draw,
        "Détection en temps réel des Bons de Commande & Appels d'Offres, scoring multi-profils et analyse des concurrents.",
        font_sub,
        max_width=560,
        max_lines=3,
    )
    y = 276
    for line in desc_lines:
        draw.text((68, y), line, fill=(148, 163, 184, 255), font=font_sub)
        y += 30

    features = [
        "Diagnostic IA 5 Piliers (Web, Logiciel, Data, IA, Cloud)",
        "Radar Acheteurs & Suivi Plafond 500k MAD TTC",
        "Radar Concurrents, Lots & Historique d'Attribution",
    ]
    fy = 398
    for feat in features:
        draw.ellipse([(68, fy + 3), (88, fy + 23)], fill=(6, 78, 59, 255), outline=(16, 185, 129, 255), width=2)
        draw.line([(73, fy + 13), (77, fy + 17), (84, fy + 9)], fill=(110, 231, 183, 255), width=2)
        draw.text((100, fy), feat, fill=(226, 232, 240, 255), font=font_feat)
        fy += 38

    # Right column: Sleek Mini-UI Preview Card (Stripe/Linear style)
    mx1, my1, mx2, my2 = 684, 146, 1132, 540
    draw.rounded_rectangle(
        [(mx1, my1), (mx2, my2)],
        radius=20,
        fill=(11, 15, 25, 255),
        outline=(51, 65, 85, 170),
        width=2,
    )
    draw.text((mx1 + 24, my1 + 22), "APERÇU DIAGNOSTIC IA", fill=(129, 140, 248, 255), font=_load_font(14, bold=True, mono=True))
    _draw_pill(
        draw, mx2 - 126, my1 + 16, "GO • P1", _load_font(14, bold=True, mono=True),
        fill=(6, 78, 59, 255), outline=(16, 185, 129, 255), text_color=(110, 231, 183, 255),
        pad_x=14, height=28, radius=8
    )

    # Mini gauge inside preview card
    mini_gauge = _draw_radial_gauge(92.0, size=132)
    canvas.alpha_composite(mini_gauge, (mx1 + 24, my1 + 66))
    draw = ImageDraw.Draw(canvas)

    draw.text((mx1 + 174, my1 + 78), "Portail Web & API", fill=(255, 255, 255, 255), font=_load_font(20, bold=True))
    draw.text((mx1 + 174, my1 + 108), "Ministère du Numérique", fill=(148, 163, 184, 255), font=font_ui_xs)
    draw.text((mx1 + 174, my1 + 132), "0% Matériel • Sur Mesure", fill=(52, 211, 153, 255), font=font_ui_xs)

    # 5 pillar mini bars
    bars = [
        ("Web & Portails", 0.95, (129, 140, 248, 255)),
        ("Génie Logiciel", 0.90, (56, 189, 248, 255)),
        ("Data & BI", 0.45, (52, 211, 153, 255)),
        ("IA & Automatisation", 0.30, (192, 132, 252, 255)),
        ("Cloud & DevOps", 0.55, (45, 212, 191, 255)),
    ]
    by = my1 + 220
    for label, ratio, col in bars:
        draw.text((mx1 + 24, by), label, fill=(203, 213, 225, 255), font=font_ui_sm)
        pct_txt = f"{int(ratio * 100)}%"
        pw, _ = _text_size(draw, pct_txt, font_ui_sm)
        draw.text((mx2 - 24 - pw, by), pct_txt, fill=(255, 255, 255, 255), font=font_ui_sm)
        bar_x1, bar_x2 = mx1 + 206, mx2 - 74
        draw.rounded_rectangle([(bar_x1, by + 5), (bar_x2, by + 13)], radius=4, fill=(30, 41, 59, 255))
        fill_w = max(8, int((bar_x2 - bar_x1) * ratio))
        draw.rounded_rectangle([(bar_x1, by + 5), (bar_x1 + fill_w, by + 13)], radius=4, fill=col)
        by += 32

    # Footer
    draw.text((68, 560), "marchéspublics.gov.ma  •  Surveillance & Scoring Automatisé", fill=(100, 116, 139, 255), font=font_ui_xs)
    return canvas


def _render_tender_card(canvas: Image.Image, tender_info: Dict[str, Any]) -> Image.Image:
    draw = ImageDraw.Draw(canvas)

    portal_id = tender_info.get("portal_id", "")
    source_type = (tender_info.get("source_type") or "BDC").upper()
    ref = _truncate(tender_info.get("reference") or f"#{portal_id}", 28)
    title = tender_info.get("title") or "Avis d'Achat Public"
    buyer = _truncate(tender_info.get("buyer_name") or "Acheteur Public", 64)
    location = _truncate(tender_info.get("execution_location") or "Maroc", 32)
    deadline = _truncate(tender_info.get("deadline_display") or "En cours", 24)
    match_rate = tender_info.get("matching_rate")
    verdict = (tender_info.get("verdict") or "").upper()
    primary_domain = _truncate(tender_info.get("primary_domain") or "", 42)
    hw_dep = (tender_info.get("hardware_dependency") or "").upper()
    techs: List[str] = tender_info.get("detected_technologies") or []

    _draw_brand_header(draw, badge_right=f"{source_type} • #{portal_id}")

    # Left column (x: 68..790) | Right column gauge card (x: 820..1132)
    font_pill = _load_font(16, bold=True, mono=True)
    font_title = _load_font(36, bold=True)
    font_meta_b = _load_font(20, bold=True)
    font_meta = _load_font(19, bold=False)
    font_sm = _load_font(16, bold=False)

    # Top pills row: Reference + Hardware/Domain pill
    px = 68
    pw = _draw_pill(
        draw, px, 136, f"Réf : {ref}", font_pill,
        fill=(30, 41, 59, 255), outline=(71, 85, 105, 180), text_color=(147, 197, 253, 255),
        pad_x=14, height=34, radius=9
    )
    px += pw + 12

    if hw_dep == "NONE":
        _draw_pill(
            draw, px, 136, "100% Logiciel / Services", font_pill,
            fill=(6, 78, 59, 180), outline=(16, 185, 129, 160), text_color=(110, 231, 183, 255),
            pad_x=14, height=34, radius=9
        )
    elif hw_dep == "HIGH":
        _draw_pill(
            draw, px, 136, "Dominante Matérielle", font_pill,
            fill=(127, 29, 29, 160), outline=(244, 63, 94, 160), text_color=(253, 164, 175, 255),
            pad_x=14, height=34, radius=9
        )

    # Title (up to 3 lines, pixel-wrapped)
    title_lines = _wrap_text_px(draw, title, font_title, max_width=720, max_lines=3)
    ty = 190
    for line in title_lines:
        draw.text((68, ty), line, fill=(255, 255, 255, 255), font=font_title)
        ty += 46

    # Metadata card on left bottom
    meta_y1 = 356
    draw.rounded_rectangle(
        [(68, meta_y1), (792, 502)],
        radius=16,
        fill=(11, 15, 25, 220),
        outline=(51, 65, 85, 140),
        width=1,
    )
    draw.text((90, meta_y1 + 18), "ACHETEUR PUBLIC", fill=(100, 116, 139, 255), font=_load_font(13, bold=True, mono=True))
    draw.text((90, meta_y1 + 38), buyer, fill=(241, 245, 249, 255), font=font_meta_b)

    draw.text((90, meta_y1 + 82), f"Lieu : {location}", fill=(148, 163, 184, 255), font=font_meta)
    draw.text((410, meta_y1 + 82), f"Clôture : {deadline}", fill=(252, 211, 77, 255), font=font_meta_b)

    # Bottom tech chips or domain
    chip_x = 68
    if techs:
        for tech in techs[:4]:
            cw = _draw_pill(
                draw, chip_x, 522, tech, _load_font(15, bold=True),
                fill=(49, 46, 129, 150), outline=(99, 102, 241, 150), text_color=(199, 210, 254, 255),
                pad_x=14, height=30, radius=8
            )
            chip_x += cw + 10
            if chip_x > 680:
                break
    elif primary_domain:
        draw.text((68, 526), f"Domaine IA : {primary_domain}", fill=(52, 211, 153, 255), font=_load_font(17, bold=True))

    # Right column: Score Gauge Panel (x: 822..1132, y: 136..554)
    rx1, ry1, rx2, ry2 = 822, 136, 1132, 554
    draw.rounded_rectangle(
        [(rx1, ry1), (rx2, ry2)],
        radius=20,
        fill=(11, 15, 25, 240),
        outline=(51, 65, 85, 170),
        width=2,
    )

    rate_val = float(match_rate) if match_rate is not None else 0.0
    gauge_img = _draw_radial_gauge(rate_val, size=192)
    canvas.alpha_composite(gauge_img, (rx1 + (rx2 - rx1 - 192) // 2, ry1 + 26))
    draw = ImageDraw.Draw(canvas)

    # Verdict pill below gauge
    if verdict == "GO":
        v_txt, v_bg, v_bd, v_fg = "VERDICT : GO", (6, 78, 59, 220), (16, 185, 129, 220), (110, 231, 183, 255)
    elif verdict == "CONSIDER":
        v_txt, v_bg, v_bd, v_fg = "À ARBITRER", (120, 53, 15, 200), (245, 158, 11, 200), (252, 211, 77, 255)
    else:
        v_txt, v_bg, v_bd, v_fg = "HORS CIBLE", (30, 41, 59, 220), (100, 116, 139, 180), (203, 213, 225, 255)

    v_font = _load_font(16, bold=True, mono=True)
    vw, _ = _text_size(draw, v_txt, v_font)
    _draw_pill(
        draw,
        x=rx1 + (rx2 - rx1 - (vw + 32)) // 2,
        y=ry1 + 242,
        text=v_txt,
        font=v_font,
        fill=v_bg,
        outline=v_bd,
        text_color=v_fg,
        pad_x=16,
        height=36,
        radius=10,
    )

    if primary_domain:
        dom_lines = _wrap_text_px(draw, primary_domain, _load_font(16, bold=True), max_width=270, max_lines=2)
        dy = ry1 + 302
        for dl in dom_lines:
            dw, _ = _text_size(draw, dl, _load_font(16, bold=True))
            draw.text((rx1 + (rx2 - rx1 - dw) // 2, dy), dl, fill=(203, 213, 225, 255), font=_load_font(16, bold=True))
            dy += 24

    # Footer URL
    draw.text((rx1 + 52, ry2 - 34), "bergag.nexenflow.com", fill=(100, 116, 139, 255), font=_load_font(15, bold=True, mono=True))
    return canvas


def generate_og_image(tender_info: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Generates a best-in-class 1200x630 PNG Open Graph preview card for either
    the main Bergag dashboard or a specific public procurement avis.
    """
    canvas = _create_base_canvas()
    if tender_info:
        canvas = _render_tender_card(canvas, tender_info)
    else:
        canvas = _render_dashboard_card(canvas)

    out = canvas.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_og_meta_tags(
    base_url: str,
    tender_info: Optional[Dict[str, Any]] = None,
    page_url: Optional[str] = None,
) -> str:
    """
    Renders Open Graph & Twitter Card meta tags for WhatsApp / social link previews.
    """
    clean_base = base_url.rstrip("/")

    if not tender_info:
        title = "Bergag • Veille Marchés Publics Maroc & Intelligence IA"
        description = (
            "Plateforme autonome de veille et d'analyse IA des marchés publics marocains "
            "(BDC & Appels d'Offres) : scoring multi-profils, diagnostic technique, Radar Acheteurs & Concurrents."
        )
        image_url = f"{clean_base}/og-image.png"
        canonical_url = page_url or f"{clean_base}/"
    else:
        portal_id = tender_info.get("portal_id")
        ref = tender_info.get("reference") or f"#{portal_id}"
        raw_title = " ".join((tender_info.get("title") or "Avis d'Achat Public").split())
        title = _truncate(f"[{ref}] {raw_title}", 100)

        buyer = _truncate(tender_info.get("buyer_name") or "Acheteur Public", 60)
        location = _truncate(tender_info.get("execution_location") or "Maroc", 30)
        deadline = _truncate(tender_info.get("deadline_display") or "En cours", 25)
        match_rate = tender_info.get("matching_rate")
        primary_domain = _truncate(tender_info.get("primary_domain") or "", 40)

        parts = [f"Acheteur : {buyer}", f"Lieu : {location}", f"Clôture : {deadline}"]
        if match_rate is not None:
            parts.append(f"Match IA : {float(match_rate):.0f}%")
        if primary_domain:
            parts.append(primary_domain)
        description = _truncate(" | ".join(parts), 220)

        image_url = f"{clean_base}/og-image/avis/{portal_id}.png"
        canonical_url = page_url or f"{clean_base}/avis/{portal_id}"

    e_title = html.escape(title, quote=True)
    e_desc = html.escape(description, quote=True)
    e_img = html.escape(image_url, quote=True)
    e_url = html.escape(canonical_url, quote=True)

    return "\n    ".join([
        f'<meta name="description" content="{e_desc}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Bergag • Veille Marchés Publics Maroc">',
        f'<meta property="og:url" content="{e_url}">',
        f'<meta property="og:title" content="{e_title}">',
        f'<meta property="og:description" content="{e_desc}">',
        f'<meta property="og:image" content="{e_img}">',
        f'<meta property="og:image:secure_url" content="{e_img}">',
        '<meta property="og:image:type" content="image/png">',
        f'<meta property="og:image:width" content="{OG_WIDTH}">',
        f'<meta property="og:image:height" content="{OG_HEIGHT}">',
        f'<meta property="og:image:alt" content="{e_title}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{e_title}">',
        f'<meta name="twitter:description" content="{e_desc}">',
        f'<meta name="twitter:image" content="{e_img}">',
    ])
