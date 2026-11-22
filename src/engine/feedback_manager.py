import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Set, List, Tuple

logger = logging.getLogger(__name__)

STORAGE_FILE = Path("data/alignment_feedback_ledger.json")

# Comprehensive procurement, administrative, and geographic stopwords to avoid learning noisy non-domain words
STOPWORDS = {
    # Grammar & prepositions
    "pour", "dans", "avec", "sans", "sous", "vers", "chez", "tout", "tous", "toute", "toutes",
    "autre", "autres", "divers", "diverses", "selon", "suite", "afin", "plus", "moins", "tres", "très",
    "meme", "même", "d'un", "d'une", "des", "les", "une", "par", "sur",

    # Procurement & transactional terminology
    "achat", "achats", "fourniture", "fournitures", "acquisition", "acquisitions",
    "travaux", "service", "services", "travail", "prestation", "prestations",
    "materiel", "matériel", "equipement", "équipement", "equipements", "équipements",
    "lot", "lots", "marche", "marché", "marches", "marchés", "projet", "projets",
    "appel", "appels", "offre", "offres", "devis", "bordereau", "cahier", "charges",
    "prescriptions", "cautionnement", "provisoire", "definitif", "ouverture", "plis",
    "soumissionnaire", "concurrent", "concurrents", "titulaire", "compte", "profit",
    "benefice", "bénéfice", "cadre", "avenant", "ordre", "bureau", "seance", "séance",
    "commission", "delai", "délai", "delais", "dépôt", "depot", "execution", "exécution",
    "lieu", "lieux", "montant", "montants", "prix", "unitaire", "total", "estimation",
    "caution", "garantie", "piece", "pièces", "pieces", "dossier", "dossiers",
    "reglement", "règlement", "consultation", "consultations", "avis", "mise", "place",
    "objet", "reference", "référence", "code", "article", "articles", "annee", "année",
    "date", "numero",

    # Public institutions & Moroccan administrative entities (NEVER learn buyer types as sector keywords!)
    "commune", "communes", "communal", "communale", "communales", "communaux",
    "province", "provinces", "provincial", "provinciale", "provinciaux",
    "prefecture", "prefectures", "prefectoral", "prefectorale",
    "wilaya", "wilayas", "ministere", "ministère", "ministeres", "ministères",
    "direction", "directions", "delegation", "délégation", "delegations",
    "conseil", "conseils", "institut", "instituts", "centre", "centres",
    "royaume", "maroc", "marocain", "marocaine", "marocains", "marocaines",
    "societe", "société", "societes", "sociétés", "agence", "agences",
    "academie", "académie", "académies", "fondation", "fondations",
    "office", "offices", "etablissement", "établissement", "etablissements",
    "autorite", "autorité", "administration", "administrations", "pachalik",
    "cercle", "cercles", "caidat", "tribunal", "tribunaux", "cour",
    "hopital", "hôpital", "hopitaux", "universite", "université", "faculte", "faculté",
    "ecole", "école", "ecoles", "chambre", "secretariat", "secrétariat",

    # Geographic locations & cities
    "ville", "region", "région", "rabat", "casablanca", "marrakech", "fes", "fès",
    "tanger", "agadir", "oujda", "kenitra", "kénitra", "tetouan", "tétouan",
    "sale", "salé", "meknes", "meknès", "temara", "témara", "safi", "el jadida",
    "jadida", "nador", "beni mellal", "berrechid", "khemisset", "khémisset",
    "settat", "berkane", "taourirt", "taza", "errachidia", "taroudant", "guelmim",
    "khenifra", "khénifra", "ouarzazate", "al haouz", "haouz", "benslimane",
    "tiflet", "dakhla", "laayoune", "laâyoune", "ifrane", "azrou"
}

def strip_accents(text: str) -> str:
    """Normalizes text by removing diacritics / accents"""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

def extract_tokens(text: str) -> Set[str]:
    """Extracts distinctive meaningful domain tokens (>= 4 chars, non-stopwords)"""
    if not text:
        return set()
    norm = strip_accents(text)
    words = re.findall(r'\b[a-zA-Z0-9_\u0600-\u06FF]{4,}\b', norm)
    return {w for w in words if w not in STOPWORDS and not w.isdigit()}

def normalize_profile_key(profile_identifier: str) -> str:
    """Canonicalizes profile identifiers (slugs, file names, or display titles) to standard profile slugs"""
    if not profile_identifier:
        return "it_hardware"
    lowered = profile_identifier.lower().strip()
    if "software" in lowered or "logiciel" in lowered or "data" in lowered:
        return "software_data"
    if "cctv" in lowered or "secur" in lowered or "video" in lowered:
        return "cctv_security"
    if "hardware" in lowered or "materiel" in lowered or "reseau" in lowered or "network" in lowered:
        return "it_hardware"
    return lowered.replace(" ", "_")

class AlignmentFeedbackManager:
    """
    Enterprise-grade Reinforcement Learning from Human Feedback (RLHF) & Active Learning Manager.
    
    Capabilities:
    1. Records domain expert confirmations ('is_aligned' = True) and rejections ('is_aligned' = False)
       for each tender under a specific business profile.
    2. Maintains dual persistence: PostgreSQL database records with a resilient JSON ledger fallback.
    3. Mines vocabulary from confirmed tenders to continuously train and improve the scoring & candidate
       search models for all future tenders in the sector.
    """
    def __init__(self):
        # Key: (portal_id: int, profile_name: str) -> feedback_dict
        self._feedbacks: Dict[Tuple[int, str], Dict[str, Any]] = {}
        # Cached learned terms per profile
        self._aligned_terms_cache: Dict[str, Set[str]] = {}
        self._rejected_terms_cache: Dict[str, Set[str]] = {}
        self._load_from_storage()

    def _load_from_storage(self):
        """Loads feedback ledger from disk fallback"""
        if STORAGE_FILE.exists():
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    for item in raw_data.values():
                        pid = int(item.get("portal_id", 0))
                        p_name = str(item.get("profile_name", ""))
                        if pid and p_name:
                            self._feedbacks[(pid, p_name)] = item
                self._rebuild_vocabulary_cache()
                logger.info(f"[FeedbackManager] Loaded {len(self._feedbacks)} alignment feedbacks from storage.")
            except Exception as e:
                logger.warning(f"[FeedbackManager] Could not read feedback ledger: {e}")
                self._feedbacks = {}
        else:
            self._feedbacks = {}

    def _save_to_storage(self):
        """Persists current feedback ledger to disk"""
        try:
            STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Serialize with string keys "portal_id:profile_name"
            serialized = {
                f"{k[0]}:{k[1]}": v for k, v in self._feedbacks.items()
            }
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[FeedbackManager] Could not save feedback ledger: {e}")

    def _rebuild_vocabulary_cache(self):
        """Rebuilds the learned vocabulary sets per profile for active learning, pruning any stopwords"""
        self._aligned_terms_cache.clear()
        self._rejected_terms_cache.clear()
        
        for (pid, p_name), data in self._feedbacks.items():
            terms = set(data.get("learned_terms", []))
            # Cleanse against current STOPWORDS
            clean_terms = {t for t in terms if t not in STOPWORDS and len(t) >= 4 and not t.isdigit()}
            data["learned_terms"] = list(clean_terms)
            if not clean_terms:
                continue
            if data.get("is_aligned"):
                if p_name not in self._aligned_terms_cache:
                    self._aligned_terms_cache[p_name] = set()
                self._aligned_terms_cache[p_name].update(clean_terms)
            else:
                if p_name not in self._rejected_terms_cache:
                    self._rejected_terms_cache[p_name] = set()
                self._rejected_terms_cache[p_name].update(clean_terms)

    def record_feedback(
        self,
        portal_id: int,
        profile_name: str,
        is_aligned: bool,
        user_name: str = "Expert Métier",
        user_notes: Optional[str] = None,
        tender_title: Optional[str] = None,
        line_items_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records or updates human alignment feedback for a tender against a profile.
        Extracts key domain terms to feed the active learning vocabulary model.
        """
        canonical_profile = normalize_profile_key(profile_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Mine vocabulary from title & line items
        combined_text = f"{tender_title or ''} {line_items_text or ''}".strip()
        learned_terms = list(extract_tokens(combined_text))

        feedback_entry = {
            "portal_id": portal_id,
            "profile_name": canonical_profile,
            "is_aligned": is_aligned,
            "user_name": user_name,
            "user_notes": user_notes or ("Confirmé aligné avec le profil" if is_aligned else "Signalé hors secteur"),
            "feedback_at": now_iso,
            "learned_terms": learned_terms
        }

        self._feedbacks[(portal_id, canonical_profile)] = feedback_entry
        self._rebuild_vocabulary_cache()
        self._save_to_storage()

        logger.info(
            f"[FeedbackManager] Recorded feedback for #{portal_id} under '{canonical_profile}': "
            f"aligned={is_aligned}, mined {len(learned_terms)} terms."
        )
        return feedback_entry

    def delete_feedback(self, portal_id: int, profile_name: str) -> bool:
        """Removes human feedback for a tender under a profile (reverts to AI-only scoring)"""
        canonical_profile = normalize_profile_key(profile_name)
        key = (portal_id, canonical_profile)
        if key in self._feedbacks:
            del self._feedbacks[key]
            self._rebuild_vocabulary_cache()
            self._save_to_storage()
            logger.info(f"[FeedbackManager] Cleared feedback for #{portal_id} under '{canonical_profile}'.")
            return True
        return False

    def get_feedback(self, portal_id: int, profile_name: str) -> Optional[Dict[str, Any]]:
        """Returns recorded human feedback if present, otherwise None"""
        canonical_profile = normalize_profile_key(profile_name)
        return self._feedbacks.get((portal_id, canonical_profile))

    def get_aligned_portal_ids(self, profile_name: Optional[str] = None) -> Set[int]:
        """Returns the set of portal_ids confirmed as aligned for this profile (or all profiles if None)"""
        canonical_profile = normalize_profile_key(profile_name) if profile_name else None
        return {
            pid for (pid, p), v in self._feedbacks.items()
            if (canonical_profile is None or p == canonical_profile) and v.get("is_aligned")
        }

    def get_misaligned_portal_ids(self, profile_name: Optional[str] = None) -> Set[int]:
        """Returns the set of portal_ids rejected as misaligned for this profile"""
        canonical_profile = normalize_profile_key(profile_name) if profile_name else None
        return {
            pid for (pid, p), v in self._feedbacks.items()
            if (canonical_profile is None or p == canonical_profile) and not v.get("is_aligned")
        }

    def get_learned_terms(self, profile_name: str) -> List[str]:
        """Returns all terms learned from confirmed aligned tenders for this profile"""
        canonical_profile = normalize_profile_key(profile_name)
        return sorted(list(self._aligned_terms_cache.get(canonical_profile, set())))

    def calculate_active_learning_adjustment(self, tender_text: str, profile_name: str) -> Tuple[float, List[str]]:
        """
        Computes active learning score adjustment for unconfirmed tenders based on similarity
        to human-confirmed (bonus) vs human-rejected (penalty) tenders.
        
        Returns:
            (adjustment_delta: float between -15.0 and +12.0, matched_exemplar_terms: list[str])
        """
        if not tender_text:
            return 0.0, []

        tokens = extract_tokens(tender_text)
        if not tokens:
            return 0.0, []

        canonical_profile = normalize_profile_key(profile_name)
        aligned_terms = self._aligned_terms_cache.get(canonical_profile, set())
        rejected_terms = self._rejected_terms_cache.get(canonical_profile, set())

        aligned_hits = tokens.intersection(aligned_terms)
        rejected_hits = tokens.intersection(rejected_terms)

        delta = 0.0
        if aligned_hits:
            # Positive active learning bonus (+2.5% per distinctive hit, up to +12.0%)
            delta += min(12.0, len(aligned_hits) * 2.5)

        if rejected_hits and not aligned_hits:
            # Negative penalty if tender matches terms from rejected false positives
            delta -= min(15.0, len(rejected_hits) * 3.0)

        return round(delta, 1), sorted(list(aligned_hits))

    def get_profile_stats(self, profile_name: str) -> Dict[str, Any]:
        """Returns statistics on human feedback and active learning for a profile"""
        canonical_profile = normalize_profile_key(profile_name)
        aligned_count = sum(1 for (pid, p), v in self._feedbacks.items() if p == canonical_profile and v.get("is_aligned"))
        misaligned_count = sum(1 for (pid, p), v in self._feedbacks.items() if p == canonical_profile and not v.get("is_aligned"))
        learned_terms = self._aligned_terms_cache.get(canonical_profile, set())

        return {
            "profile_name": canonical_profile,
            "total_feedbacks": aligned_count + misaligned_count,
            "aligned_count": aligned_count,
            "misaligned_count": misaligned_count,
            "learned_terms_count": len(learned_terms),
            "sample_learned_terms": sorted(list(learned_terms))[:15]
        }

# Global singleton feedback manager
feedback_manager = AlignmentFeedbackManager()
