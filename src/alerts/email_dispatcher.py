import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any
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

            <!-- CTA Action Button -->
            <div style="margin-top: 32px; text-align: center;">
                <a href="{portal_url}" style="background-color: #2563EB; color: #FFFFFF; text-decoration: none; font-size: 15px; font-weight: 600; padding: 12px 24px; border-radius: 6px; display: inline-block;">
                    📄 Consulter l'Avis Officiel sur le Portail &rarr;
                </a>
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

LIEN DIRECT PORTAIL:
{portal_url}
===================================================================
"""

class EmailDispatcher:
    """
    Sends responsive Decision Cards via Gmail SMTP with STARTTLS.
    """
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.recipient = settings.alert_recipient_email or self.user

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
