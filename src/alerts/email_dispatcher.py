import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, List, Optional
from src.config.settings import settings
from src.profiles.schema import CompanyProfileSchema
from src.engine.scoring_cascade import CascadeEvaluationResult

logger = logging.getLogger(__name__)

def render_decision_card_html(
    tender_data: Dict[str, Any], 
    result: CascadeEvaluationResult, 
    profile: CompanyProfileSchema
) -> str:
    """Generates a responsive executive HTML Decision Card for Gmail"""
    portal_id = tender_data.get("portal_id", "N/A")
    ref = tender_data.get("reference", "N/A")
    buyer = tender_data.get("buyer_name", "Acheteur Inconnu")
    title = tender_data.get("title", "")
    deadline = tender_data.get("deadline_at", "N/A")
    location = tender_data.get("execution_location", "Maroc")
    portal_url = f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{portal_id}"
    app_base_url = (settings.app_url or "http://localhost:8000").rstrip("/")
    fiche_url = f"{app_base_url}/#tender={portal_id}"

    # Badge styling
    if result.overall_score >= 80.0:
        badge_color = "#059669" # Emerald green
        badge_text = f"🎯 {result.overall_score:.0f}% - RECOMMENDED GO"
    elif result.overall_score >= 50.0:
        badge_color = "#D97706" # Amber
        badge_text = f"⚠️ {result.overall_score:.0f}% - CONSIDER"
    else:
        badge_color = "#DC2626" # Red
        badge_text = f"❌ {result.overall_score:.0f}% - NO-GO"

    # Line items table rows
    item_rows = ""
    for item in result.line_item_matches:
        status_icon = "✅" if item["is_matched"] else "⚠️"
        sku = item.get("matched_catalog_sku") or "Hors catalogue"
        item_rows += f"""
        <tr style="border-bottom: 1px solid #E5E7EB;">
            <td style="padding: 8px 12px; font-weight: bold; color: #374151;">#{item['item_order']:02d}</td>
            <td style="padding: 8px 12px; color: #111827;">{item['designation']}</td>
            <td style="padding: 8px 12px; text-align: center; color: #4B5563;">{item['quantity']} {item['unit']}</td>
            <td style="padding: 8px 12px; text-align: right; color: {'#059669' if item['is_matched'] else '#DC2626'}; font-weight: 500;">
                {status_icon} {sku}
            </td>
        </tr>
        """

    # Red flags
    red_flag_html = ""
    if result.red_flags:
        flags = "".join(f"<li style='margin-bottom: 4px;'>{f}</li>" for f in result.red_flags)
        red_flag_html = f"""
        <div style="background-color: #FEF3C7; border-left: 4px solid #F59E0B; padding: 12px 16px; margin: 16px 0; border-radius: 4px;">
            <strong style="color: #92400E;">Points de vigilance & contraintes :</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #78350F; font-size: 14px;">
                {flags}
            </ul>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F3F4F6; margin: 0; padding: 20px; color: #1F2937;">
    <div style="max-width: 640px; margin: 0 auto; background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        
        <!-- Header -->
        <div style="background-color: #1E293B; color: #FFFFFF; padding: 20px 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #94A3B8;">Avis d'Achat BDC #{portal_id} &bull; Réf: {ref}</span>
                <span style="background-color: {badge_color}; color: #FFFFFF; font-size: 12px; font-weight: bold; padding: 4px 8px; border-radius: 4px;">
                    {badge_text}
                </span>
            </div>
            <h2 style="margin: 0; font-size: 18px; font-weight: 600; line-height: 1.4;">{title}</h2>
        </div>

        <div style="padding: 24px;">
            <!-- Metadata Grid -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
                <tr>
                    <td style="padding: 6px 0; color: #6B7280; width: 140px;">🏛️ Acheteur :</td>
                    <td style="padding: 6px 0; font-weight: 600; color: #111827;">{buyer}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #6B7280;">📍 Lieu d'exécution :</td>
                    <td style="padding: 6px 0; color: #111827;">{location}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #6B7280;">⏳ Date limite remise :</td>
                    <td style="padding: 6px 0; font-weight: bold; color: #DC2626;">{deadline}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #6B7280;">🎯 Couverture devis :</td>
                    <td style="padding: 6px 0; font-weight: bold; color: #059669;">{result.coverage_score:.0f}% des articles couverts</td>
                </tr>
            </table>

            <!-- Executive Summary -->
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px;">
                <div style="font-weight: 600; font-size: 13px; color: #475569; text-transform: uppercase; margin-bottom: 4px;">Synthèse de décision :</div>
                <div style="font-size: 14px; color: #1E293B; line-height: 1.5;">{result.llm_reasoning}</div>
            </div>

            {red_flag_html}

            <!-- Line Items Table -->
            <div style="margin-top: 24px;">
                <h4 style="margin: 0 0 12px 0; font-size: 15px; color: #111827;">Détail des articles demandés ({len(result.line_item_matches)} articles) :</h4>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #F9FAFB; border-bottom: 2px solid #E5E7EB;">
                                <th style="padding: 8px 12px; text-align: left; color: #6B7280;">N°</th>
                                <th style="padding: 8px 12px; text-align: left; color: #6B7280;">Désignation</th>
                                <th style="padding: 8px 12px; text-align: center; color: #6B7280;">Quantité</th>
                                <th style="padding: 8px 12px; text-align: right; color: #6B7280;">Statut</th>
                            </tr>
                        </thead>
                        <tbody>
                            {item_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Dual CTA Action Buttons (Internal Fiche 60s vs External Official TGR) -->
            <div style="margin-top: 32px; padding: 20px; background-color: #F8FAFC; border-radius: 8px; border: 1px solid #E2E8F0; text-align: center;">
                <div style="display: inline-block; vertical-align: middle; margin: 4px 6px;">
                    <a href="{fiche_url}" style="background-color: #059669; color: #FFFFFF; text-decoration: none; font-size: 14px; font-weight: 700; padding: 12px 22px; border-radius: 6px; display: inline-block; box-shadow: 0 2px 4px rgba(5, 150, 105, 0.25);">
                        ⚡ Ouvrir la Fiche 60s Interactive &rarr;
                    </a>
                </div>
                <div style="display: inline-block; vertical-align: middle; margin: 4px 6px;">
                    <a href="{portal_url}" target="_blank" rel="noopener noreferrer" style="background-color: #1E293B; color: #E2E8F0; border: 1px solid #475569; text-decoration: none; font-size: 13px; font-weight: 600; padding: 11px 18px; border-radius: 6px; display: inline-block;">
                        🏛️ Consulter l'Avis Portail TGR &#8599;
                    </a>
                </div>
                <div style="font-size: 11px; color: #64748B; margin-top: 12px; line-height: 1.5; text-align: center;">
                    <strong>Fiche 60s :</strong> Calculateur de marge interne, conformité catalogue & export du bordereau Excel.<br>
                    <strong>Portail TGR :</strong> Consultation de l'avis officiel & dépôt réglementaire de l'offre.
                </div>
            </div>

            <p style="font-size: 12px; color: #9CA3AF; text-align: center; margin-top: 24px;">
                Alerte générée automatiquement par Antigravity Intelligence &bull; Profil : {profile.profile_name}
            </p>
        </div>
    </div>
</body>
</html>
"""
    return html

def render_decision_card_text(
    tender_data: Dict[str, Any], 
    result: CascadeEvaluationResult, 
    profile: CompanyProfileSchema
) -> str:
    """Generates plain-text ASCII Decision Card for fallback"""
    portal_id = tender_data.get("portal_id", "N/A")
    ref = tender_data.get("reference", "N/A")
    buyer = tender_data.get("buyer_name", "Acheteur Inconnu")
    title = tender_data.get("title", "")
    deadline = tender_data.get("deadline_at", "N/A")
    portal_url = f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{portal_id}"
    app_base_url = (settings.app_url or "http://localhost:8000").rstrip("/")
    fiche_url = f"{app_base_url}/#tender={portal_id}"
    verdict_label = "RECOMMENDED GO" if result.decision_recommendation == "GO" else result.decision_recommendation

    return f"""===================================================================
DECISION CARD: Moroccan Procurement Intelligence
Avis BDC #{portal_id} | Ref: {ref}
OVERALL ALIGNMENT: {result.overall_score:.0f}% ({verdict_label})
===================================================================

OBJET: {title}
ACHETEUR: {buyer}
DATE LIMITE: {deadline}
COUVERTURE: {result.coverage_score:.0f}% des articles

SYNTHÈSE:
{result.llm_reasoning}

POINTS DE VIGILANCE:
{chr(10).join('- ' + f for f in result.red_flags) if result.red_flags else 'Aucune contrainte bloquante détectée.'}

ACTIONS RECOMMANDÉES:
⚡ FICHE 60s INTERACTIVE (Chiffrage & Décision) : {fiche_url}
🏛️ AVIS OFFICIEL PORTAIL TGR (Dépôt réglementaire) : {portal_url}
===================================================================
"""

class EmailDispatcher:
    """
    Sends responsive Decision Cards via Gmail SMTP with STARTTLS.
    """
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user.strip() if settings.smtp_user else ""
        self.password = settings.smtp_password.replace(" ", "").strip() if settings.smtp_password else ""
        self.recipient = (settings.alert_recipient_email or self.user).strip()

    def _send_sync(self, subject: str, text_body: str, html_body: str) -> bool:
        if not self.user or not self.password:
            logger.info(f"[MOCK EMAIL] Gmail SMTP not configured. Would send to {self.recipient}:\nSubject: {subject}")
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Antigravity BDC Alerts <{self.user}>"
        msg["To"] = self.recipient

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.user, self.password)
                server.send_message(msg)
                logger.info(f"Decision Card email successfully sent to {self.recipient} via Gmail SMTP")
                return True
        except Exception as e:
            logger.error(f"Failed to send email via Gmail SMTP: {e}")
            return False

    async def send_decision_card(
        self, 
        tender_data: Dict[str, Any], 
        result: CascadeEvaluationResult, 
        profile: CompanyProfileSchema
    ) -> bool:
        """Asynchronously dispatches decision card email"""
        ref = tender_data.get("reference", "")
        verdict = "RECOMMENDED GO" if result.decision_recommendation == "GO" else result.decision_recommendation
        subject = f"[{result.overall_score:.0f}% {verdict}] {tender_data.get('title', '')[:50]} (Réf: {ref})"

        html_body = render_decision_card_html(tender_data, result, profile)
        text_body = render_decision_card_text(tender_data, result, profile)

        return await asyncio.to_thread(self._send_sync, subject, text_body, html_body)

    async def send_daily_digest(
        self,
        items: List[Dict[str, Any]],
        digest_date: str,
        min_score: float = 70.0,
    ) -> bool:
        """Dispatches the 08:00 AM consolidated daily digest of new offers >= min_score."""
        if not items:
            logger.info(f"[DailyDigest] No new offers >= {min_score:.0f}% for {digest_date}; skipping email.")
            return False

        count = len(items)
        top_score = max(max(float(i.get("ai_score", 0.0)), float(i.get("cascade_score", 0.0))) for i in items)
        subject = (
            f"📊 Digest Marchés Publics {digest_date} : "
            f"{count} nouvelle{'s' if count > 1 else ''} offre{'s' if count > 1 else ''} "
            f"≥ {min_score:.0f}% (Top: {top_score:.0f}%)"
        )
        html_body = render_daily_digest_html(items, digest_date, min_score)
        text_body = render_daily_digest_text(items, digest_date, min_score)
        return await asyncio.to_thread(self._send_sync, subject, text_body, html_body)


def render_daily_digest_html(
    items: List[Dict[str, Any]],
    digest_date: str,
    min_score: float = 70.0,
) -> str:
    """Generates a detailed executive HTML Daily Digest email for 08:00 AM."""
    app_base_url = (settings.app_url or "https://bergag.nexenflow.com").rstrip("/")
    cards_html = ""

    for idx, item in enumerate(items, start=1):
        portal_id = item.get("portal_id", "N/A")
        ref = item.get("reference", "N/A")
        title = item.get("title", "")
        buyer = item.get("buyer_name", "Acheteur Inconnu")
        location = item.get("execution_location") or "Maroc"
        deadline = item.get("deadline_at", "N/A")
        ai_score = float(item.get("ai_score", 0.0))
        cascade_score = float(item.get("cascade_score", 0.0))
        best_score = max(ai_score, cascade_score)
        domain = item.get("ai_domain") or "IT / Logiciel / Data"
        headroom = item.get("art91_headroom_mad")
        headroom_str = f"{headroom:,.0f} MAD" if headroom is not None else "Non renseigné"

        badge_bg = "#059669" if best_score >= 80.0 else "#D97706"
        portal_url = f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{portal_id}"
        fiche_url = f"{app_base_url}/#tender={portal_id}"

        line_items = item.get("line_items") or []
        li_rows = ""
        for li in line_items[:10]:
            li_rows += f"""
            <tr style="border-bottom:1px solid #E5E7EB;">
                <td style="padding:6px 8px;color:#374151;font-weight:600;">#{int(li.get('item_order', 0)):02d}</td>
                <td style="padding:6px 8px;color:#111827;">{li.get('designation', '')}</td>
                <td style="padding:6px 8px;text-align:right;color:#4B5563;white-space:nowrap;">{li.get('quantity', 1)} {li.get('unit', 'U')}</td>
            </tr>"""
        if len(line_items) > 10:
            li_rows += f"""<tr><td colspan="3" style="padding:6px 8px;color:#6B7280;font-style:italic;">+ {len(line_items) - 10} autre(s) article(s) sur la Fiche 60s…</td></tr>"""

        red_flags = item.get("red_flags") or []
        flags_html = ""
        if red_flags:
            flags_li = "".join(f"<li>{f}</li>" for f in red_flags[:4])
            flags_html = f"""
            <div style="background:#FEF3C7;border-left:4px solid #F59E0B;padding:8px 12px;margin:10px 0;font-size:12px;color:#78350F;">
                <strong>Vigilance :</strong>
                <ul style="margin:4px 0 0 0;padding-left:18px;">{flags_li}</ul>
            </div>"""

        cards_html += f"""
        <div style="border:1px solid #E2E8F0;border-radius:8px;margin-bottom:20px;overflow:hidden;background:#FFFFFF;">
            <div style="background:#0F172A;color:#FFFFFF;padding:12px 16px;">
                <div style="font-size:12px;color:#94A3B8;margin-bottom:4px;">
                    #{idx} &bull; BDC #{portal_id} &bull; Réf: {ref} &bull; {domain}
                    <span style="float:right;background:{badge_bg};color:#FFFFFF;padding:2px 8px;border-radius:4px;font-weight:700;">
                        IA {ai_score:.0f}% | Cascade {cascade_score:.0f}%
                    </span>
                </div>
                <div style="font-size:15px;font-weight:700;line-height:1.35;">{title}</div>
            </div>
            <div style="padding:14px 16px;font-size:13px;color:#1F2937;">
                <table style="width:100%;border-collapse:collapse;margin-bottom:10px;">
                    <tr><td style="padding:3px 0;color:#6B7280;width:140px;">🏛️ Acheteur :</td><td style="font-weight:600;">{buyer}</td></tr>
                    <tr><td style="padding:3px 0;color:#6B7280;">📍 Lieu :</td><td>{location}</td></tr>
                    <tr><td style="padding:3px 0;color:#6B7280;">⏳ Clôture :</td><td style="color:#DC2626;font-weight:700;">{deadline}</td></tr>
                    <tr><td style="padding:3px 0;color:#6B7280;">💰 Marge Art. 91 :</td><td style="font-weight:600;color:#059669;">{headroom_str}</td></tr>
                </table>
                {flags_html}
                <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:8px;">
                    <thead>
                        <tr style="background:#F8FAFC;border-bottom:2px solid #E2E8F0;">
                            <th style="padding:6px 8px;text-align:left;color:#64748B;">N°</th>
                            <th style="padding:6px 8px;text-align:left;color:#64748B;">Désignation</th>
                            <th style="padding:6px 8px;text-align:right;color:#64748B;">Qté</th>
                        </tr>
                    </thead>
                    <tbody>{li_rows}</tbody>
                </table>
                <div style="margin-top:14px;text-align:left;">
                    <a href="{fiche_url}" style="background:#059669;color:#FFFFFF;text-decoration:none;font-weight:700;font-size:12px;padding:8px 14px;border-radius:5px;display:inline-block;margin-right:8px;">⚡ Ouvrir Fiche 60s</a>
                    <a href="{portal_url}" target="_blank" style="background:#1E293B;color:#E2E8F0;text-decoration:none;font-weight:600;font-size:12px;padding:8px 14px;border-radius:5px;display:inline-block;">🏛️ Portail TGR</a>
                </div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#F1F5F9;margin:0;padding:20px;color:#0F172A;">
    <div style="max-width:700px;margin:0 auto;">
        <div style="background:#1E293B;color:#FFFFFF;padding:20px 24px;border-radius:8px 8px 0 0;">
            <div style="font-size:12px;color:#94A3B8;text-transform:uppercase;letter-spacing:0.05em;">Veille Quotidienne 08h00 &bull; {digest_date}</div>
            <h1 style="margin:6px 0 0 0;font-size:20px;">📊 {len(items)} Nouvelle(s) Opportunité(s) ≥ {min_score:.0f}%</h1>
        </div>
        <div style="background:#F8FAFC;padding:20px;border-radius:0 0 8px 8px;border:1px solid #E2E8F0;border-top:none;">
            {cards_html}
            <p style="font-size:11px;color:#64748B;text-align:center;margin:12px 0 0 0;">
                Digest automatique envoyé uniquement pour les nouvelles offres détectées depuis le dernier envoi.
            </p>
        </div>
    </div>
</body>
</html>"""


def render_daily_digest_text(
    items: List[Dict[str, Any]],
    digest_date: str,
    min_score: float = 70.0,
) -> str:
    """Plain-text fallback for the 08:00 AM daily digest."""
    app_base_url = (settings.app_url or "https://bergag.nexenflow.com").rstrip("/")
    lines = [
        f"DIGEST MARCHÉS PUBLICS ({digest_date}) - {len(items)} nouvelle(s) offre(s) >= {min_score:.0f}%",
        "=" * 72,
        "",
    ]
    for idx, item in enumerate(items, start=1):
        pid = item.get("portal_id", "N/A")
        lines.extend([
            f"[{idx}] BDC #{pid} (Réf: {item.get('reference', 'N/A')}) | IA: {float(item.get('ai_score', 0)):.0f}% | Cascade: {float(item.get('cascade_score', 0)):.0f}%",
            f"Objet     : {item.get('title', '')}",
            f"Acheteur  : {item.get('buyer_name', '')}",
            f"Clôture   : {item.get('deadline_at', '')}",
            f"Fiche 60s : {app_base_url}/#tender={pid}",
            f"TGR       : https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{pid}",
            "-" * 72,
        ])
    return "\n".join(lines)
