import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from src.engine.award_similarity import AwardSimilarityEngine, extract_meaningful_tokens


def _make_award(
    *,
    reference: str,
    title: str,
    buyer: str,
    winner: str,
    amount_ttc: float,
    devis_count: int = 3,
    days_ago: int = 30,
    status: str = "Attribué",
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        reference=reference,
        title_raw=title,
        buyer_name_raw=buyer,
        winner_name=winner,
        amount_ttc=Decimal(str(amount_ttc)),
        devis_received_count=devis_count,
        status=status,
        published_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def test_extract_meaningful_tokens_filters_boilerplate():
    tokens = extract_meaningful_tokens(
        "Achat et fourniture de caméras de vidéosurveillance NVR au profit de la Direction"
    )
    assert "achat" not in tokens
    assert "fourniture" not in tokens
    assert "direction" not in tokens
    assert "cameras" in tokens
    assert "videosurveillance" in tokens
    assert "nvr" in tokens


def test_analyze_candidates_ranks_similarity_prices_and_competitors():
    candidates = [
        _make_award(
            reference="10/2026",
            title="Achat de caméras de vidéosurveillance IP et enregistreur NVR",
            buyer="AGENCE URBAINE DE TAZA",
            winner="SECURITAS MAROC SARL",
            amount_ttc=120000.0,
            devis_count=4,
            days_ago=20,
        ),
        _make_award(
            reference="11/2026",
            title="Fourniture et installation de caméras vidéosurveillance NVR et switch PoE",
            buyer="COMMUNE DE FES",
            winner="SECURITAS MAROC SARL",
            amount_ttc=140000.0,
            devis_count=3,
            days_ago=60,
        ),
        _make_award(
            reference="12/2026",
            title="Acquisition de caméras de surveillance et disque dur NVR",
            buyer="PROVINCE DE GUERCIF",
            winner="TECH VISION SARL",
            amount_ttc=100000.0,
            devis_count=2,
            days_ago=90,
        ),
        _make_award(
            reference="99/2026",
            title="Travaux de peinture et réfection de toiture",
            buyer="COMMUNE DE RABAT",
            winner="BTP ATLAS",
            amount_ttc=450000.0,
            devis_count=5,
            days_ago=15,
        ),
    ]

    result = AwardSimilarityEngine.analyze_candidates(
        tender_title="Achat de caméras de vidéosurveillance et NVR",
        buyer_name="AGENCE URBAINE DE TAZA",
        line_item_titles=["Caméra IP Dôme 4MP", "Enregistreur NVR 16 canaux"],
        candidates=candidates,
        min_similarity=20.0,
        limit=10,
    )

    assert result["total_matched"] == 3
    assert len(result["similar_awards"]) == 3
    # Same buyer + highest overlap should rank first
    assert result["similar_awards"][0]["reference"] == "10/2026"
    assert result["similar_awards"][0]["same_buyer"] is True

    pe = result["price_estimation"]
    assert pe["sample_size"] == 3
    assert pe["min_mad"] == 100000.0
    assert pe["median_mad"] == 120000.0
    assert pe["max_mad"] == 140000.0
    assert pe["avg_devis_count"] == 3.0
    assert pe["competition_level"] == "Modérée"

    comps = result["top_competitors"]
    assert comps[0]["winner_name"] == "SECURITAS MAROC SARL"
    assert comps[0]["wins_count"] == 2
    assert comps[0]["same_buyer_wins"] == 1
    assert comps[0]["avg_amount_mad"] == 130000.0


def test_analyze_candidates_handles_empty_gracefully():
    result = AwardSimilarityEngine.analyze_candidates(
        tender_title="Fourniture de licences cloud",
        buyer_name="MINISTERE",
        line_item_titles=[],
        candidates=[],
    )
    assert result["total_matched"] == 0
    assert result["price_estimation"]["sample_size"] == 0
    assert result["price_estimation"]["confidence"] == "Aucune"
    assert result["top_competitors"] == []
    assert result["similar_awards"] == []


def test_institution_name_does_not_match_unrelated_catering_or_ac():
    """
    Regression for BDC #411863: 'Achat de matériel de bureau pour la Faculté d'Economie et de Gestion de Safi'
    must NOT match 'Restauration ... Faculté d'Economie et de Gestion de Kenitra' just because of institution words.
    """
    candidates = [
        _make_award(
            reference="CATER/2026",
            title="Restauration dans le cadre des concours de master à la Faculté d'Economie et de Gestion de Kenitra",
            buyer="FACULTE D'ECONOMIE ET DE GESTION KENITRA",
            winner="Chraibi Amina",
            amount_ttc=3575.0,
        ),
        _make_award(
            reference="OFFICE/2026",
            title="Achat de fourniture de bureau au profit de la Faculté d'Economie et de Gestion D'EL KELAA DES SRAGHNA",
            buyer="FACULTE D'ECONOMIE ET DE GESTION D'EL KELAA DES SRAGHNA",
            winner="TAJ NOVA SARL",
            amount_ttc=32843.0,
        ),
    ]

    result = AwardSimilarityEngine.analyze_candidates(
        tender_title="Achat de matériel de bureau pour la Faculté d'Economie et de Gestion de Safi",
        buyer_name="FACULTE D'ECONOMIE ET DE GESTION DE SAFI",
        line_item_titles=["Imprimante Multifonction Laser Monochrome A3", "Duplicopieur A4/A3", "Scanner A3"],
        candidates=candidates,
        min_similarity=20.0,
        limit=10,
    )

    matched_refs = [a["reference"] for a in result["similar_awards"]]
    assert "CATER/2026" not in matched_refs
    assert "OFFICE/2026" in matched_refs
