import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class PillarScore(BaseModel):
    score: float = 0.0
    matched_keywords: List[str] = Field(default_factory=list)

class AIMatchingDiagnosis(BaseModel):
    """
    Structured deep diagnostic assessment of a procurement avis 
    against the Programming, Web, Data & AI profile.
    """
    matching_rate: float = Field(..., ge=0.0, le=100.0, description="Overall AI matching rate (0-100%)")
    rating_label: str = Field(..., description="EXCELLENT_MATCH, STRONG_MATCH, MODERATE_MATCH, LOW_MATCH, MISMATCH")
    verdict: str = Field(..., description="GO, CONSIDER, NO-GO")
    confidence: float = Field(..., ge=0.0, le=100.0, description="Confidence score in the diagnostic")
    primary_domain: str = Field(..., description="Identified core specialization")
    sub_scores: Dict[str, float] = Field(default_factory=dict, description="Pillar breakdown: web, software, data, ai, devops")
    detected_technologies: List[str] = Field(default_factory=list, description="Extracted tech stack, frameworks, platforms")
    deliverability_feasibility: str = Field(default="HIGH", description="HIGH, MEDIUM, LOW")
    hardware_dependency: str = Field(default="NONE", description="NONE, LOW, MEDIUM, HIGH")
    red_flags_and_gaps: List[str] = Field(default_factory=list, description="Operational risks, missing capabilities, out-of-scope demands")
    strategic_recommendation: str = Field(..., description="Actionable bidding advice")
    diagnostic_summary: str = Field(..., description="Comprehensive explanatory diagnostic paragraph")
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AIAvisDiagnostician:
    """
    Deep Content Diagnostician for Moroccan Public Procurement Avis.
    Inspects title, category, prestation, administrative metadata, and line-item specs
    to compute an in-depth AI Matching Rate and technical diagnostic against the
    Programming, Web, Data & AI profile.
    """

    # Domain vocabulary rules for deep tech classification
    PILLARS = {
        "web_development": {
            "label": "Développement Web & Portails",
            "weight": 1.0,
            "patterns": [
                r"\bweb\b", r"\bsite\s+web\b", r"\bportail\b", r"\bportails?\s+web\b",
                r"\bintranet\b", r"\bextranet\b", r"\bwordpress\b", r"\bdrupal\b",
                r"\b(?:cms\s+(?:wordpress|drupal|joomla|headless|web)|système\s+de\s+gestion\s+de\s+contenu)\b",
                r"\breact\b", r"\b(?:vue\.js|vuejs)\b", r"\bangular\b", r"\bnode(?:\.js)?\b",
                r"\bnext(?:\.js)?\b", r"\blaravel\b", r"\bsymfony\b", r"\bdjango\b",
                r"\bflask\b", r"\bfastapi\b", r"\bphp\b", r"\bjavascript\b", r"\btypescript\b",
                r"\bfrontend\b", r"\bfront-end\b", r"\bui\s*/\s*ux\b",
                r"\bergonomie\s+(?:web|applicative|numérique|ui|ux|d['’]interface)\b",
                r"\bresponsive(?:\s+design)?\b", r"\bhtml5?\b", r"\bcss3?\b", r"\btailwind\b",
                r"\brest\s+api\b", r"\bapi\s+rest\b", r"\bgraphql\b", r"\bguichet\s+unique\b",
                r"\bplateforme\s+(?:en\s+ligne|web)\b", r"\brefonte\s+(?:du\s+)?site\b",
                r"\bapplications?\s+web\b"
            ],
            "display_terms": {
                "react": "React.js", "vue.js": "Vue.js", "vuejs": "Vue.js", "angular": "Angular",
                "node": "Node.js", "next": "Next.js", "laravel": "Laravel", "symfony": "Symfony",
                "django": "Django", "fastapi": "FastAPI", "wordpress": "WordPress", "drupal": "Drupal",
                "php": "PHP", "typescript": "TypeScript", "javascript": "JavaScript", "graphql": "GraphQL",
                "portail": "Portail Web", "intranet": "Intranet", "ui/ux": "UI/UX"
            }
        },
        "software_programming": {
            "label": "Génie Logiciel & Programmation",
            "weight": 1.0,
            "patterns": [
                r"\blogiciel\s+(?:sur\s+mesure|métier|de\s+gestion|intégré|applicatif)\b",
                r"\b(?:développement|developpement)\s+(?:logiciel|applicatif|informatique|web|mobile|full[\s-]*stack|back[\s-]*end|front[\s-]*end|sur\s+mesure|d['’]applications?|de\s+logiciels?|de\s+plateforme|de\s+portail|de\s+système|api)\b",
                r"\bconception\s+et\s+(?:développement|developpement)\b",
                r"\bprogiciel\b",
                r"\bapplication\s+(?:métier|mobile|web|informatique|de\s+gestion)\b", r"\bsur\s+mesure\b", r"\bgénie\s+logiciel\b",
                r"\bcode\s+source\b", r"\bbackend\b", r"\bback-end\b", r"\bmicroservices?\b",
                r"\bpython\b", r"\bjava\b", r"\bspring\s+boot\b", r"\bc#\b", r"\basp\.net\b",
                r"\bgolang\b", r"\bflutter\b", r"\breact\s+native\b",
                r"\b(?:application|développement)\s+(?:mobile\s+)?(?:ios|android)\b",
                r"\btma\b", r"\btierce\s+maintenance\b", r"\bmaintenance\s+(?:applicative|de\s+logiciels?)\b",
                r"\bdématérialisation\b",
                r"\b(?:mise\s+en\s+place|développement|refonte|maintenance|conception)\s+(?:d['’]un\s+|du\s+)?système\s+d['’]information\b",
                r"\binteropérabilité\b", r"\bgestion\s+électronique\s+des\s+documents\b", r"\bged\b"
            ],
            "display_terms": {
                "python": "Python", "java": "Java", "spring": "Spring Boot", "c#": "C# / .NET",
                "flutter": "Flutter", "react native": "React Native", "microservice": "Microservices",
                "tma": "TMA / Tierce Maintenance", "ged": "GED / Dématérialisation",
                "progiciel": "Progiciel Métier", "application métier": "Application Sur Mesure",
                "application mobile": "Application Mobile"
            }
        },
        "data_engineering_bi": {
            "label": "Ingénierie de Données & Décisionnel (BI)",
            "weight": 0.95,
            "patterns": [
                r"\bbusiness\s+intelligence\b", r"\b(?:solution|outil|plateforme|projet)\s+bi\b",
                r"\bdécisionnel\b", r"\bdecisionnel\b",
                r"\btableaux?\s+de\s+bord\b", r"\bdashboards?\b", r"\bentrepôt\s+de\s+données\b",
                r"\bdata\s+warehouse\b", r"\bdatamart\b", r"\betl\b", r"\belt\b",
                r"\bpipeline\s+(?:de\s+données|data|etl)\b",
                r"\bsql\b", r"\bpostgresql\b", r"\bmysql\b", r"\boracle\b", r"\bpower\s*bi\b",
                r"\btableau\s+software\b", r"\bsuperset\b", r"\bmetabase\b",
                r"\b(?:outil|plateforme|système|solution)\s+de\s+reporting\b|\breporting\s+(?:bi|décisionnel|automatisé|statistique)\b",
                r"\banalytics?\b", r"\bmigration\s+de\s+données\b", r"\bgouvernance\s+des\s+données\b",
                r"\bqualité\s+des\s+données\b", r"\btraitement\s+de\s+données\b", r"\bbig\s+data\b"
            ],
            "display_terms": {
                "power bi": "Power BI", "powerbi": "Power BI", "tableau software": "Tableau BI",
                "superset": "Apache Superset", "etl": "ETL / Pipeline Data", "postgresql": "PostgreSQL",
                "oracle": "Oracle DB", "sql": "SQL Database", "tableau de bord": "Dashboard BI",
                "décisionnel": "Business Intelligence", "data warehouse": "Data Warehouse"
            }
        },
        "ai_automation": {
            "label": "Intelligence Artificielle & Automatisation",
            "weight": 0.90,
            "patterns": [
                r"\bintelligence\s+artificielle\b",
                r"\b(?:solution|plateforme|modèle|système|agent|outil)s?\s+d['’]?ia\b|\bia\s+générative\b",
                r"\bmachine\s+learning\b",
                r"\bapprentissage\s+automatique\b", r"\bdeep\s+learning\b", r"\bnlp\b",
                r"\btraitement\s+automatique\s+du\s+langage\b",
                r"\b(?:moteur|solution|module|logiciel|système)\s+ocr\b",
                r"\breconnaissance\s+(?:optique\s+de\s+)?caractères\b", r"\brpa\b",
                r"\bautomatisation\s+des\s+processus\b", r"\bchatbot\b", r"\bagent\s+conversationnel\b",
                r"\bllm\b", r"\bvision\s+par\s+ordinateur\b", r"\bmodèle\s+prédictif\b"
            ],
            "display_terms": {
                "intelligence artificielle": "Intelligence Artificielle",
                "reconnaissance optique": "OCR / Reconnaissance Optique",
                "chatbot": "Chatbot / Agent IA", "rpa": "Automatisation RPA",
                "machine learning": "Machine Learning", "llm": "LLM / Traitement Langage"
            }
        },
        "cloud_devops": {
            "label": "Cloud, DevOps & Hébergement",
            "weight": 0.85,
            "patterns": [
                r"(?<!creative\s)\bcloud\s+(?:computing|architecture|infrastructure|hébergement|hybride|privé|public|native|aws|azure|gcp)\b|\binfrastructure\s+cloud\b|\bmigration\s+(?:vers\s+le\s+)?cloud\b",
                r"\bdevops\b", r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b",
                r"\bconteneurisation\b", r"\bci\s*/\s*cd\b",
                r"\bhébergement\s+(?:web|applicatif|cloud|serveur|plateforme|site|données)\b",
                r"\bserveur\s+web\b", r"\bnginx\b", r"\bapache\b", r"\baws\b", r"\bazure\b",
                r"\bgcp\b", r"\b(?:serveur|administration|environnement|système)\s+linux\b",
                r"\bsécurité\s+applicative\b"
            ],
            "display_terms": {
                "docker": "Docker", "kubernetes": "Kubernetes", "devops": "DevOps",
                "ci/cd": "CI/CD DevOps", "hébergement web": "Hébergement Web",
                "azure": "Microsoft Azure", "aws": "AWS"
            }
        }
    }

    # Off-the-shelf (COTS) software / license purchases without custom development
    COTS_LICENSE_PATTERNS = [
        r"\banti[\s-]*virus\b", r"\badobe\s+creative\s+cloud\b", r"\bphotoshop\b",
        r"\bmicrosoft\s+(?:office|365)\b", r"\boffice\s+365\b", r"\bwindows\s+(?:10|11|server)\b",
        r"\bautocad\b", r"\barcgis\b", r"\bsage\s+frp\b", r"\bfoxta\b", r"\barticulate\s+360\b",
        r"\bedr\b", r"\bkaspersky\b", r"\bfortinet\b"
    ]

    # Physical hardware indicators that dilute software match
    HARDWARE_PATTERNS = [
        (r"\bimprimantes?\b", "Imprimantes"),
        (r"\bphotocopieurs?\b|\bphotocopieuses?\b", "Photocopieurs"),
        (r"\bduplicopieurs?\b", "Duplicopieurs"),
        (r"\bscanners?\b", "Scanners"),
        (r"\btoners?\b|\bcartouches?\b", "Consommables d'impression"),
        (r"\bmatériels?\s+de\s+bureau\b|\bmobilier\s+de\s+bureau\b", "Matériel & mobilier de bureau"),
        (r"\bserveurs?\s+(?:rack|en\s+baie|physiques?)\b", "Serveurs physiques en rack"),
        (r"\bcâblage\s+(?:informatique|réseau|rj45|cuivre)\b", "Câblage physique / Courants faibles"),
        (r"\barmoire\s+de\s+brassage\b", "Armoire de brassage physique"),
        (r"\bordinateurs?(?:\s+de\s+bureau|\s+portables?)?\b|\blaptops?\b|\bpc\s+de\s+bureau\b|\btablettes?\b", "Postes de travail / PC / Tablettes"),
        (r"\bmatériels?\s+informatiques?\b|\bdisques?\s+durs?\b|\bonduleurs?\b", "Matériel informatique physique"),
        (r"\bécrans?\s+d['’]affichage\b|\bvideoprojecteurs?\b|\bvidéoprojecteurs?\b", "Matériel de projection"),
        (r"\bcaméras?(?:\s+ip|\s+de\s+surveillance)?\b", "Vidéosurveillance"),
        (r"\bswitchs?\b|\brouteurs?\b|\bpare-feu\s+physique\b", "Équipements réseau physiques")
    ]

    # Non-IT strictly incompatible indicators (Stage 1 drop, checked on intent/title/designations)
    NON_IT_VETO_PATTERNS = [
        (r"\b(?:camion|engin|tracteur|benne|voiture|ambulance|véhicule|vehicule|vidange|pneus?|gasoil|carburant|matériel\s+de\s+transport)\b", "Véhicules, transport ou carburants"),
        (r"\b(?:génie\s+civil|travaux\s+de\s+construction|travaux\s+d['’](?:aménagement|réhabilitation|réfection|rénovation)|maçonnerie|peinture|plomberie|étanchéité|bâtiment)\b", "Travaux de BTP, aménagement & construction civile"),
        (r"\b(?:gardiennage|nettoyage\s+des\s+locaux|sécurité\s+gardiennage|restauration|traiteur|pause\s+café)\b", "Services généraux, gardiennage ou traiteur"),
        (r"\b(?:médicaments?|réactifs?\s+de\s+laboratoire|dispositifs?\s+médicaux|fongibles\s+médicaux|fils\s+chirurgicaux|chirurgie|dentaire|radiologie|lunettes\s+de\s+correction)\b", "Médical, optique, laboratoire ou pharmacie"),
        (r"\b(?:dératisation|désinsectisation|désinfection|espaces?\s+verts?|jardinage|engrais|semences|aliments?\s+de\s+bétail)\b", "Hygiène, espaces verts ou agriculture"),
        (r"\b(?:habillement|tenues?\s+de\s+(?:travail|protection)|chaussures\s+de\s+sécurité|mobilier\s+scolaire|billetterie\s+aérienne|hébergement\s+hôtelier)\b", "Habillement, mobilier scolaire ou voyages"),
        (r"\b(?:fournitures?\s+(?:de\s+bureau|scolaires?|pédagogiques?|d['’]enseignement)|tableaux?\s+magnétiques?|petit\s+outillage|dossier\s+topographique)\b", "Fournitures de bureau/scolaires, outillage ou topographie"),
    ]

    @classmethod
    def diagnose_tender(
        cls,
        tender_data: Dict[str, Any],
        profile: Optional[Any] = None
    ) -> AIMatchingDiagnosis:
        """
        Executes a deep inspection avis-by-avis and returns an AIMatchingDiagnosis.
        """
        title = (tender_data.get("title") or "").strip()
        ref = (tender_data.get("reference") or "").strip()
        prestation = (tender_data.get("prestation_type") or "").strip()
        buyer_name = (tender_data.get("buyer_name") or "Acheteur Public").strip()
        category = (tender_data.get("main_category") or "Fournitures").strip()
        location = (tender_data.get("execution_location") or "National").strip()
        deadline_str = tender_data.get("deadline_at") or ""
        line_items = tender_data.get("line_items", [])

        # 1. Check for immediate non-IT veto or cancellation
        is_cancelled = (
            "annul" in title.lower() or
            "annul" in ref.lower() or
            (tender_data.get("status") or "").lower().strip() in ("annule", "annulé", "cancelled")
        )
        if is_cancelled:
            return AIMatchingDiagnosis(
                matching_rate=0.0,
                rating_label="MISMATCH",
                verdict="NO-GO",
                confidence=100.0,
                primary_domain="Consultation Annulée",
                sub_scores={},
                detected_technologies=[],
                deliverability_feasibility="LOW",
                hardware_dependency="NONE",
                red_flags_and_gaps=["Avis d'achat officiellement annulé ou infructueux."],
                strategic_recommendation="⛔ Ne pas répondre : la procédure a été formellement annulée par l'acheteur public.",
                diagnostic_summary=f"Consultation {ref} de {buyer_name} classée sans suite ou annulée."
            )

        # Full corpus construction
        combined_text_parts = [title, prestation, category]
        items_text_list = []
        for item in line_items:
            desig = item.get("designation") or ""
            specs = item.get("technical_specs") or ""
            combined_text_parts.extend([desig, specs])
            items_text_list.append(f"{desig} {specs}")

        full_corpus = " ".join(combined_text_parts).lower()
        intent_corpus = " ".join([title, prestation, category] + [
            (item.get("designation") or "") for item in line_items
        ]).lower()

        # Check non-IT veto against intent_corpus (title, prestation, designations)
        for pattern, reason in cls.NON_IT_VETO_PATTERNS:
            if re.search(pattern, intent_corpus, re.IGNORECASE):
                return AIMatchingDiagnosis(
                    matching_rate=0.0,
                    rating_label="MISMATCH",
                    verdict="NO-GO",
                    confidence=98.0,
                    primary_domain="Hors Secteur Informatique",
                    sub_scores={k: 0.0 for k in cls.PILLARS},
                    detected_technologies=[],
                    deliverability_feasibility="LOW",
                    hardware_dependency="NONE",
                    red_flags_and_gaps=[f"Exclusion formelle : {reason}"],
                    strategic_recommendation="⛔ Écarter : cette consultation relève d'un domaine totalement hors informatique/web/data.",
                    diagnostic_summary=f"Disqualifié d'emblée : la consultation concerne des prestations de {reason.lower()} sans composante de programmation."
                )

        # 2. Analyze Line Items FIRST: Software vs Hardware Breakdown
        # Checking hardware designation before specs prevents printer compatibility lists
        # (e.g. "compatible Android, iOS, Cloud") from being misclassified as software items.
        software_items_count = 0
        hardware_items_count = 0
        unmatched_items = []

        detected_hardware_types = []
        for pat, hw_label in cls.HARDWARE_PATTERNS:
            if re.search(pat, full_corpus, re.IGNORECASE):
                detected_hardware_types.append(hw_label)

        total_items = max(len(line_items), 1)
        for item in line_items:
            desig = (item.get("designation") or "").lower()
            specs = (item.get("technical_specs") or "").lower()
            item_text = f"{desig} {specs}"

            is_hw_desig = any(
                re.search(pat, desig, re.IGNORECASE)
                for pat, _ in cls.HARDWARE_PATTERNS
            )
            is_sw_desig = any(
                re.search(pat, desig, re.IGNORECASE)
                for conf in cls.PILLARS.values()
                for pat in conf["patterns"]
            )
            is_sw_full = any(
                re.search(pat, item_text, re.IGNORECASE)
                for conf in cls.PILLARS.values()
                for pat in conf["patterns"]
            )
            is_hw_full = any(
                re.search(pat, item_text, re.IGNORECASE)
                for pat, _ in cls.HARDWARE_PATTERNS
            )

            if is_hw_desig and not is_sw_desig:
                hardware_items_count += 1
            elif is_sw_full and not is_hw_desig:
                software_items_count += 1
            elif is_hw_full:
                hardware_items_count += 1
            else:
                unmatched_items.append(item.get("designation", "Article non qualifié"))

        # 3. Assess Hardware Dependency
        if not detected_hardware_types and hardware_items_count == 0:
            hardware_dep = "NONE"
        elif software_items_count > hardware_items_count:
            hardware_dep = "LOW"
        elif software_items_count == hardware_items_count and software_items_count > 0:
            hardware_dep = "MEDIUM"
        else:
            hardware_dep = "HIGH"

        # 4. Evaluate Pillar Scores & Extract Detected Technologies
        # If the tender is predominantly physical hardware, score pillars against
        # intent_corpus (title, prestation, designations) so OS/Cloud compatibility
        # clauses inside hardware datasheets do not trigger software pillars.
        scoring_corpus = intent_corpus if (hardware_dep == "HIGH" and software_items_count == 0) else full_corpus

        # Detect COTS (off-the-shelf license) purchases without custom development signals
        has_cots_signal = any(
            re.search(pat, intent_corpus, re.IGNORECASE)
            for pat in cls.COTS_LICENSE_PATTERNS
        )
        has_custom_dev_signal = any(
            re.search(pat, intent_corpus, re.IGNORECASE)
            for pat in [
                r"\b(?:développement|developpement)\s+(?:logiciel|applicatif|web|mobile|sur\s+mesure|d['’]applications?)\b",
                r"\bsur\s+mesure\b", r"\bcode\s+source\b", r"\brefonte\b",
                r"\bportail\s+web\b", r"\bsite\s+web\b", r"\bapplications?\s+web\b",
                r"\btma\b", r"\bmaintenance\s+applicative\b", r"\bapi\s+rest\b", r"\brest\s+api\b"
            ]
        )
        is_cots_only = has_cots_signal and not has_custom_dev_signal

        pillar_results: Dict[str, PillarScore] = {}
        all_detected_techs = set()

        for pillar_id, conf in cls.PILLARS.items():
            matched_keywords: List[str] = []
            effective_hits = 0.0
            for pat in conf["patterns"]:
                in_intent = re.search(pat, intent_corpus, re.IGNORECASE)
                in_scoring = in_intent or re.search(pat, scoring_corpus, re.IGNORECASE)
                if in_intent:
                    effective_hits += 1.5
                    matched_keywords.append(in_intent.group(0))
                elif in_scoring:
                    effective_hits += 1.0
                    matched_keywords.append(in_scoring.group(0))

            # Map to display terms using strict word boundaries
            for term_key, display_label in conf["display_terms"].items():
                if re.search(rf"\b{re.escape(term_key)}\b", scoring_corpus, re.IGNORECASE):
                    all_detected_techs.add(display_label)

            # Compute normalized score for this pillar (0-100) from distinct weighted concepts
            if effective_hits >= 5.0:
                p_score = 100.0
            elif effective_hits >= 4.0:
                p_score = 85.0
            elif effective_hits >= 3.0:
                p_score = 70.0
            elif effective_hits >= 2.0:
                p_score = 50.0
            elif effective_hits >= 1.0:
                p_score = 30.0
            else:
                p_score = 0.0

            # Dampen sub-scores when tender is hardware-dominated or COTS-only
            if hardware_dep == "HIGH":
                p_score = round(p_score * (0.0 if software_items_count == 0 else 0.25), 1)
            elif hardware_dep == "MEDIUM":
                p_score = round(p_score * 0.70, 1)

            if is_cots_only:
                p_score = round(p_score * 0.25, 1)

            pillar_results[pillar_id] = PillarScore(score=p_score, matched_keywords=matched_keywords)

        # 5. Determine Primary Domain
        best_pillar = max(pillar_results.keys(), key=lambda k: pillar_results[k].score)
        best_pillar_score = pillar_results[best_pillar].score

        if is_cots_only and best_pillar_score < 30.0:
            primary_domain = "Licences & Progiciels Standards (COTS)"
        elif best_pillar_score < 20.0 and hardware_dep == "HIGH":
            primary_domain = "Fourniture de Matériel Pur (Sans Dév)"
        elif best_pillar_score < 20.0:
            primary_domain = "Informatique Générale / Non Spécifié"
        else:
            primary_domain = cls.PILLARS[best_pillar]["label"]

        # 6. Calculate Overall AI Matching Rate (0 - 100%)
        # Base from top 2 pillars
        sorted_scores = sorted([p.score for p in pillar_results.values()], reverse=True)
        top1 = sorted_scores[0]
        top2 = sorted_scores[1] if len(sorted_scores) > 1 else 0.0

        base_tech_rate = (top1 * 0.75) + (top2 * 0.25)

        # Line-item software ratio bonus/penalty
        if len(line_items) > 0:
            sw_ratio = software_items_count / total_items
            line_item_factor = sw_ratio * 100.0
            # Blended with technical density
            raw_match_rate = (base_tech_rate * 0.60) + (line_item_factor * 0.40)
        else:
            # When no discrete line items are available, rely on text density
            raw_match_rate = base_tech_rate

        # Hardware damping factor: If pure hardware without programming, sharply penalize
        if hardware_dep == "HIGH":
            if base_tech_rate <= 35.0:
                raw_match_rate = min(15.0, raw_match_rate * 0.20)
            else:
                raw_match_rate = raw_match_rate * 0.50
        elif hardware_dep == "MEDIUM":
            raw_match_rate = raw_match_rate * 0.80

        if is_cots_only:
            raw_match_rate = min(25.0, raw_match_rate * 0.35)

        # Prestation type boost (only when not hardware-dominated or COTS-only)
        if not is_cots_only and hardware_dep != "HIGH":
            if "maintenance de logiciels" in prestation.lower() or "études, conseil" in prestation.lower() or "développement" in prestation.lower():
                raw_match_rate = min(100.0, raw_match_rate + 10.0)

        matching_rate = round(max(0.0, min(100.0, raw_match_rate)), 1)

        # 7. Rating Label & Operational Verdict
        if matching_rate >= 80.0:
            rating_label = "EXCELLENT_MATCH"
            verdict = "GO"
        elif matching_rate >= 65.0:
            rating_label = "STRONG_MATCH"
            verdict = "GO"
        elif matching_rate >= 45.0:
            rating_label = "MODERATE_MATCH"
            verdict = "CONSIDER"
        elif matching_rate >= 20.0:
            rating_label = "LOW_MATCH"
            verdict = "CONSIDER"
        else:
            rating_label = "MISMATCH"
            verdict = "NO-GO"

        # 8. Red Flags, Operational Risks & Gaps
        red_flags: List[str] = []
        if is_cots_only:
            red_flags.append("Achat de licences/progiciels standards (COTS) sans développement sur mesure")
        if hardware_dep == "HIGH":
            red_flags.append(f"Marché à forte dominance matérielle : {', '.join(detected_hardware_types[:3])}")
        elif hardware_dep == "MEDIUM":
            red_flags.append(f"Composante matérielle requise : nécessite un partenariat grossiste ({', '.join(detected_hardware_types[:2])})")

        # Operational timing check
        if deadline_str:
            try:
                # Support multiple date formats
                dl_dt = None
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        clean_d = deadline_str.split("+")[0].split("Z")[0]
                        dl_dt = datetime.strptime(clean_d, fmt)
                        break
                    except ValueError:
                        continue
                if dl_dt:
                    now = datetime.now()
                    hours_rem = (dl_dt - now).total_seconds() / 3600.0
                    if hours_rem <= 0:
                        verdict = "NO-GO"
                        red_flags.append("Délai de dépôt expiré (consultation clôturée)")
                    elif hours_rem < 24.0:
                        red_flags.append(f"Urgence critique : moins de 24h avant clôture ({hours_rem:.1f}h)")
                        if verdict == "GO":
                            verdict = "CONSIDER"
            except Exception:
                pass

        if len(unmatched_items) > 3:
            red_flags.append(f"Articles hors catalogue standard : {len(unmatched_items)} postes à sous-traiter ou pricer")

        # 9. Strategic Actionable Recommendation
        if rating_label == "EXCELLENT_MATCH":
            rec = "🚀 Opportunité Prioritaire (P1) : Répondre directement en chef de file. Le besoin est 100% aligné avec le profil Web, Logiciel et Données."
        elif rating_label == "STRONG_MATCH":
            if hardware_dep in ("MEDIUM", "HIGH"):
                rec = "🤝 Réponse en Groupement Conseillée : Excellente part logicielle mais inclut du matériel physique. S'associer avec un revendeur agréé."
            else:
                rec = "🎯 Candidature Recommandée (P2) : Périmètre technique très proche, étudier le cahier des charges et chiffrer l'offre."
        elif rating_label == "MODERATE_MATCH":
            rec = "⚠️ Arbitrage Requis : Consultation mixte ou à dominante intégration. Ne soumissionner que si un partenaire matériel est déjà mobilisé."
        elif rating_label == "LOW_MATCH":
            rec = "🔍 Vigilance : Alignement partiel ou très minoritaire sur le code/web. Risque de marge faible."
        else:
            rec = "⛔ Ignorer : Hors cible pour un profil de développement, web et data (fourniture matérielle ou prestation hors secteur)."

        # 10. Executive Diagnostic Summary
        tech_str = ", ".join(sorted(list(all_detected_techs))) if all_detected_techs else "Non spécifié"
        sw_summary = f"{software_items_count}/{total_items} postes identifiés développement/données" if len(line_items) > 0 else "Analyse basée sur l'intitulé et la prestation"

        summary_parts = [
            f"L'avis d'achat '{title}' émis par '{buyer_name}' a été diagnostiqué avec un taux de correspondance de {matching_rate:.0f}% ({rating_label}).",
            f"Domaine principal détecté : {primary_domain}.",
            f"Technologies identifiées : {tech_str}.",
            f"Bordereau : {sw_summary}. Dépendance matérielle physique : {hardware_dep}."
        ]
        if red_flags:
            summary_parts.append(f"Points de vigilance : {'; '.join(red_flags)}.")

        summary = " ".join(summary_parts)

        # Confidence metric
        confidence = 90.0 if len(line_items) > 0 else 75.0
        if is_cancelled:
            confidence = 100.0

        return AIMatchingDiagnosis(
            matching_rate=matching_rate,
            rating_label=rating_label,
            verdict=verdict,
            confidence=confidence,
            primary_domain=primary_domain,
            sub_scores={k: round(v.score, 1) for k, v in pillar_results.items()},
            detected_technologies=sorted(list(all_detected_techs)),
            deliverability_feasibility="HIGH" if not red_flags else ("MEDIUM" if len(red_flags) <= 2 else "LOW"),
            hardware_dependency=hardware_dep,
            red_flags_and_gaps=red_flags,
            strategic_recommendation=rec,
            diagnostic_summary=summary,
            evaluated_at=datetime.now(timezone.utc).isoformat()
        )
