import re
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Any

def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def parse_date(date_str: str | None) -> str | None:
    """Parses French portal datetimes like '27/11/2026 14:00' or '18/11/2026 16:15'"""
    if not date_str:
        return None
    cleaned = clean_text(date_str)
    # Match standard dd/mm/yyyy hh:mm
    match = re.search(r'(\d{2})/(\d{2})/(\d{4})\s*(?:à|a)?\s*(\d{2}):(\d{2})', cleaned)
    if match:
        day, month, year, hour, minute = match.groups()
        return f"{year}-{month}-{day}T{hour}:{minute}:00+01:00"
    return None

def parse_total_results(html: str) -> int:
    """Parses total matching results count from .content__resultat (e.g. 'Nombre de résultats : 1611')"""
    soup = BeautifulSoup(html, 'html.parser')
    res_div = soup.select_one('.content__resultat')
    if res_div:
        text = clean_text(res_div.get_text())
        match = re.search(r'(\d+[\s\d]*)', text)
        if match:
            clean_num = match.group(1).replace(' ', '')
            try:
                return int(clean_num)
            except ValueError:
                pass
    return 0

def parse_listing_page(html: str) -> list[dict[str, Any]]:
    """Parses active consultation cards from /bdc/entreprise/consultation/"""
    soup = BeautifulSoup(html, 'html.parser')
    results = []

    cards = soup.select('.bdc-card')
    for card in cards:
        # Reference
        ref_el = card.select_one('.bdc-card__ref')
        reference = clean_text(ref_el.get_text()) if ref_el else ""

        # Title / Object
        title_el = card.select_one('.bdc-card__title')
        title = clean_text(title_el.get_text()) if title_el else ""
        if title_el and title_el.get('data-bs-title'):
            title = clean_text(title_el.get('data-bs-title'))

        # Buyer & Location
        meta_spans = card.select('.bdc-card__meta span')
        buyer_name = clean_text(meta_spans[0].get_text()) if len(meta_spans) > 0 else ""
        location = clean_text(meta_spans[1].get_text()) if len(meta_spans) > 1 else ""

        # Status & Closing Date
        side = card.select_one('.bdc-card__side')
        status = "active"
        if side:
            v_el = side.select_one('.bdc-card__v')
            if v_el and "annulé" in v_el.get_text().lower():
                status = "annule"

        # Portal ID from link
        link_el = card.select_one('a[href*="/show/"]')
        portal_id = None
        if link_el:
            href = link_el.get('href', '')
            match = re.search(r'/show/(\d+)', href)
            if match:
                portal_id = int(match.group(1))

        # Deadline
        facts = card.select('.bdc-card__facts div')
        deadline_raw = None
        for fact in facts:
            dt = fact.select_one('dt')
            dd = fact.select_one('dd')
            if dt and "limite" in dt.get_text().lower() and dd:
                deadline_raw = clean_text(dd.get_text())
                break

        results.append({
            "portal_id": portal_id,
            "reference": reference,
            "title": title,
            "buyer_name": buyer_name,
            "execution_location": location,
            "status": status,
            "deadline_raw": deadline_raw,
            "deadline_at": parse_date(deadline_raw)
        })

    return results

def parse_detail_page(html: str, portal_id: int | None = None) -> dict[str, Any]:
    """Parses consultation detail page /bdc/entreprise/consultation/show/{id}"""
    soup = BeautifulSoup(html, 'html.parser')

    # Reference
    ref_el = soup.select_one('h4')
    reference = clean_text(ref_el.get_text()).replace('#', '') if ref_el else ""

    # Title / Object
    obj_el = soup.select_one('.bdc-objet')
    title = clean_text(obj_el.get_text()) if obj_el else ""

    # Buyer
    buyer_el = soup.select_one('#building + div span:last-child')
    buyer_name = clean_text(buyer_el.get_text()) if buyer_el else ""

    # Dates
    pub_el = soup.select_one('#dateMiseEnLigne + div span.truncate-one-line')
    published_raw = pub_el.get('data-bs-title') or pub_el.get_text() if pub_el else None
    
    dead_el = soup.select_one('#calendar + div span:last-child')
    deadline_raw = clean_text(dead_el.get_text()) if dead_el else None

    # Location
    loc_el = soup.select_one('#location + div span.truncate-one-line')
    location = loc_el.get('data-bs-title') or loc_el.get_text() if loc_el else None

    # Category & Prestation
    cat_el = soup.select_one('#category + div span:last-child')
    main_category = clean_text(cat_el.get_text()) if cat_el else "Fournitures"

    prest_el = soup.select_one('#screwdriver + div span:last-child')
    prestation_type = clean_text(prest_el.get_text()) if prest_el else ""

    # Attachment
    attachment_link = soup.select_one('a[href*="/download/"]')
    attachment_url = attachment_link.get('href') if attachment_link else None
    attachment_filename = clean_text(attachment_link.get_text()) if attachment_link else None

    # Line Items (Accordion items)
    line_items = []
    for idx, acc in enumerate(soup.select('.accordion-item'), start=1):
        btn = acc.select_one('.content__article--card')
        order_el = btn.select_one('.font-bold') if btn else None
        order_str = clean_text(order_el.get_text()) if order_el else f"#{idx:02d}"
        
        full_title = clean_text(btn.get_text(' ', strip=True)) if btn else ""
        item_title = clean_text(full_title.replace(order_str, ''))

        body = acc.select_one('.accordion-body')
        specs_el = body.select_one('.text-black') if body else None
        specs = clean_text(specs_el.get_text()) if specs_el else ""

        mini_cards = body.select('.content__article--subMiniCard') if body else []
        unit = clean_text(mini_cards[0].get_text()) if len(mini_cards) > 0 else "U"
        qty_str = clean_text(mini_cards[1].get_text()).replace(' ', '').replace(',', '.') if len(mini_cards) > 1 else "1.0"
        tva_str = clean_text(mini_cards[2].get_text()).replace('%', '').strip() if len(mini_cards) > 2 else "20.0"
        warranty = clean_text(mini_cards[3].get_text()) if len(mini_cards) > 3 else None

        try:
            quantity = float(qty_str)
        except ValueError:
            quantity = 1.0

        try:
            tva_rate = float(tva_str)
        except ValueError:
            tva_rate = 20.0

        line_items.append({
            "item_order": idx,
            "order_code": order_str,
            "designation": item_title,
            "technical_specs": specs,
            "unit": unit,
            "quantity": quantity,
            "tva_rate": tva_rate,
            "warranty_required": warranty if warranty != "-" else None
        })

    return {
        "portal_id": portal_id,
        "reference": reference,
        "title": title,
        "buyer_name": buyer_name,
        "published_at": parse_date(published_raw),
        "deadline_at": parse_date(deadline_raw),
        "execution_location": clean_text(location),
        "main_category": main_category,
        "prestation_type": prestation_type,
        "attachment_available": bool(attachment_url),
        "attachment_url": attachment_url,
        "attachment_filename": attachment_filename,
        "line_items": line_items
    }

def parse_results_page(html: str) -> list[dict[str, Any]]:
    """Parses historical award cards from /bdc/entreprise/consultation/resultat"""
    soup = BeautifulSoup(html, 'html.parser')
    awards = []

    for card in soup.select('.bdc-card'):
        ref_el = card.select_one('.bdc-card__ref')
        reference = clean_text(ref_el.get_text()) if ref_el else ""

        title_el = card.select_one('.bdc-card__title')
        title = title_el.get('data-bs-title') or title_el.get_text() if title_el else ""

        buyer_el = card.select_one('.bdc-card__meta')
        buyer_name = clean_text(buyer_el.get_text()) if buyer_el else ""

        # Date & Status
        side = card.select_one('.bdc-card__side')
        status = "Attribué"
        published_raw = None
        if side:
            v_el = side.select_one('.bdc-card__v')
            if v_el:
                status = clean_text(v_el.get_text())
            s_el = side.select_one('.bdc-card__s')
            if s_el:
                published_raw = clean_text(s_el.get_text()).replace('Publié le', '').strip()

        # Facts: Devis count, Winner, Amount
        devis_count = None
        winner_name = ""
        amount_ttc = 0.0

        winner_el = card.select_one('.bdc-card__winner')
        if winner_el:
            winner_name = clean_text(winner_el.get_text())

        money_el = card.select_one('.bdc-card__money')
        if money_el:
            raw_money = clean_text(money_el.get_text()).replace('MAD', '').replace(' ', '').replace(',', '.')
            try:
                amount_ttc = float(raw_money)
            except ValueError:
                amount_ttc = 0.0

        for fact in card.select('.bdc-card__facts div'):
            dt = fact.select_one('dt')
            dd = fact.select_one('dd')
            if dt and "devis" in dt.get_text().lower() and dd:
                try:
                    devis_count = int(clean_text(dd.get_text()))
                except ValueError:
                    devis_count = None
                break

        awards.append({
            "reference": reference,
            "title": clean_text(title),
            "buyer_name": buyer_name,
            "status": status,
            "published_at": parse_date(published_raw),
            "winner_name": winner_name,
            "amount_ttc": amount_ttc,
            "devis_received_count": devis_count
        })

    return awards

