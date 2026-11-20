"""
Multi-channel Enterprise Webhook Dispatcher
Dispatches structured real-time alert notifications for high-fit procurement opportunities
(Slack, Microsoft Teams, WhatsApp business gateway, and generic JSON webhooks).
"""

import logging
from typing import Dict, Any, Optional
import httpx
from src.config.settings import settings
from src.profiles.schema import CompanyProfileSchema
from src.engine.scoring_cascade import CascadeEvaluationResult

logger = logging.getLogger(__name__)


def build_webhook_payload(
    tender_data: Dict[str, Any],
    result: CascadeEvaluationResult,
    profile: CompanyProfileSchema
) -> Dict[str, Any]:
    """
    Constructs a universal multi-channel notification payload.
    Provides standard JSON event schema, Slack blocks, and MS Teams sections.
    """
    portal_id = tender_data.get("portal_id", "N/A")
    ref = tender_data.get("reference", "N/A")
    title = tender_data.get("title", "")
    buyer = tender_data.get("buyer_name", "Acheteur Inconnu")
    deadline = tender_data.get("deadline_at", "N/A")
    location = tender_data.get("execution_location", "Maroc")
    items = tender_data.get("line_items", [])
    matched_items = [m for m in result.line_item_matches if m.get("is_matched")]

    app_base_url = (settings.app_url or "http://localhost:8000").rstrip("/")
    fiche_url = f"{app_base_url}/#tender={portal_id}"
    portal_url = f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{portal_id}"

    verdict_label = "RECOMMENDED GO" if result.decision_recommendation == "GO" else result.decision_recommendation
    badge_emoji = "🎯" if result.overall_score >= 80.0 else ("⚠️" if result.overall_score >= 50.0 else "❌")

    formatted_summary = (
        f"{badge_emoji} *[OPPORTUNITÉ BDC #{portal_id}] — Score {result.overall_score:.0f}% ({verdict_label})*\n"
        f"📋 *Réf:* {ref}\n"
        f"🏛️ *Acheteur:* {buyer}\n"
        f"🏷️ *Objet:* {title}\n"
        f"📍 *Lieu:* {location} | ⏰ *Délai:* {deadline}\n"
        f"📦 *Articles:* {len(matched_items)}/{len(items)} compatibles catalogue\n"
        f"⚡ *Fiche 60s:* {fiche_url}\n"
        f"🏛️ *Portail TGR:* {portal_url}"
    )

    # Slack Block Kit structure
    slack_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{badge_emoji} BDC #{portal_id} : {result.overall_score:.0f}% - {verdict_label}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Acheteur:*\n{buyer}"},
                {"type": "mrkdwn", "text": f"*Référence:*\n{ref}"},
                {"type": "mrkdwn", "text": f"*Échéance:*\n{deadline}"},
                {"type": "mrkdwn", "text": f"*Couverture:*\n{len(matched_items)}/{len(items)} articles"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Objet:* {title}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⚡ Ouvrir Fiche 60s"},
                    "url": fiche_url,
                    "style": "primary"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🏛️ Avis Officiel TGR"},
                    "url": portal_url
                }
            ]
        }
    ]

    # Microsoft Teams MessageCard structure
    teams_card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "059669" if result.overall_score >= 80 else "D97706",
        "summary": f"Nouvelle Opportunité BDC #{portal_id} ({result.overall_score:.0f}%)",
        "sections": [{
            "activityTitle": f"{badge_emoji} Opportunité BDC #{portal_id} — {verdict_label}",
            "activitySubtitle": f"Score d'adéquation: {result.overall_score:.0f}% pour {profile.profile_name}",
            "facts": [
                {"name": "Acheteur:", "value": buyer},
                {"name": "Référence:", "value": ref},
                {"name": "Délai de dépôt:", "value": str(deadline)},
                {"name": "Articles compatibles:", "value": f"{len(matched_items)} / {len(items)}"}
            ],
            "markdown": True
        }],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Ouvrir Fiche 60s",
                "targets": [{"os": "default", "uri": fiche_url}]
            },
            {
                "@type": "OpenUri",
                "name": "Portail TGR",
                "targets": [{"os": "default", "uri": portal_url}]
            }
        ]
    }

    return {
        "event": "high_fit_tender_detected",
        "tender": {
            "portal_id": portal_id,
            "reference": ref,
            "title": title,
            "buyer_name": buyer,
            "execution_location": location,
            "deadline_at": str(deadline),
            "line_item_count": len(items),
            "matched_item_count": len(matched_items)
        },
        "evaluation": {
            "overall_score": result.overall_score,
            "verdict": result.decision_recommendation,
            "coverage_score": result.coverage_score,
            "red_flags": result.red_flags,
            "llm_reasoning": result.llm_reasoning
        },
        "profile": {
            "profile_name": profile.profile_name,
            "profile_id": str(profile.profile_id) if hasattr(profile, "profile_id") else None
        },
        "links": {
            "fiche_url": fiche_url,
            "portal_url": portal_url
        },
        "formatted_text": formatted_summary,
        "slack": {
            "text": formatted_summary,
            "blocks": slack_blocks
        },
        "teams": teams_card
    }


class WebhookDispatcher:
    """
    Asynchronous enterprise webhook dispatcher for Slack, Teams, WhatsApp, and generic HTTP endpoints.
    """
    def __init__(self, default_webhook_url: Optional[str] = None):
        self.default_webhook_url = default_webhook_url or settings.webhook_url

    async def send_notification(
        self,
        tender_data: Dict[str, Any],
        result: CascadeEvaluationResult,
        profile: CompanyProfileSchema,
        webhook_url: Optional[str] = None
    ) -> bool:
        """
        Builds and dispatches the multi-channel notification.
        """
        payload = build_webhook_payload(tender_data, result, profile)
        target_url = webhook_url or self.default_webhook_url

        if not target_url:
            logger.info(
                f"[MOCK WEBHOOK] No webhook URL configured. Would dispatch alert for tender "
                f"#{tender_data.get('portal_id')} (Score: {result.overall_score:.0f}%):\n"
                f"{payload['formatted_text']}"
            )
            return True

        return await self._dispatch_http(target_url, payload)

    async def _dispatch_http(self, url: str, payload: Dict[str, Any]) -> bool:
        """
        Executes HTTP POST request with timeout and error handling.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 201, 202, 204):
                    logger.info(f"Webhook notification successfully delivered to {url} (status {resp.status_code})")
                    return True
                else:
                    logger.warning(
                        f"Webhook delivery to {url} returned non-success HTTP status {resp.status_code}: {resp.text[:200]}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to deliver webhook notification to {url}: {e}")
            return False
