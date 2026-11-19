from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes.feed import router as feed_router
from src.api.routes.analytics import router as analytics_router

app = FastAPI(
    title="Antigravity Procurement Intelligence",
    description="Autonomous Moroccan Public Procurement (BDC & AO) Intelligence Engine",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feed_router)
app.include_router(analytics_router)

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="fr" class="h-full bg-slate-50">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity | Moroccan Procurement Intelligence</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
        [x-cloak] { display: none !important; }
    </style>
</head>
<body class="h-full font-sans antialiased text-slate-800" x-data="dashboardApp()" x-init="init()">
    <div class="min-h-full flex flex-col">
        
        <!-- Header -->
        <header class="bg-slate-900 text-white shadow-lg border-b border-slate-800 sticky top-0 z-40">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col sm:flex-row justify-between items-center gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-lg bg-emerald-500 flex items-center justify-center font-bold text-xl text-slate-950 shadow-md shadow-emerald-500/20">
                        ⚡
                    </div>
                    <div>
                        <h1 class="text-xl font-bold tracking-tight">Antigravity Procurement</h1>
                        <p class="text-xs text-slate-400">Portail Marocain des Marchés Publics &bull; Décret 2-22-431</p>
                    </div>
                </div>

                <!-- Navigation Tabs -->
                <div class="flex items-center bg-slate-800 p-1 rounded-xl border border-slate-700 text-xs font-semibold">
                    <button @click="activeTab = 'feed'" :class="activeTab === 'feed' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-300 hover:text-white'" class="px-4 py-1.5 rounded-lg transition-all">
                        🎯 Opportunités Directes (BDC)
                    </button>
                    <button @click="activeTab = 'radar'; fetchRadarData()" :class="activeTab === 'radar' ? 'bg-emerald-500 text-slate-950 shadow' : 'text-slate-300 hover:text-white'" class="px-4 py-1.5 rounded-lg transition-all">
                        📊 Radar Stratégique & Marché
                    </button>
                </div>

                <!-- Profile Switcher -->
                <div class="flex items-center gap-2.5">
                    <label class="text-xs font-medium text-slate-300">Profil :</label>
                    <select x-model="selectedProfile" @change="fetchFeed()" class="bg-slate-800 border border-slate-700 text-white text-xs rounded-lg px-2.5 py-1.5 focus:ring-2 focus:ring-emerald-500 outline-none">
                        <option value="cctv_security">📹 Vidéosurveillance & Sécurité</option>
                        <option value="software_data">💻 Logiciel & Données</option>
                    </select>
                </div>
            </div>
        </header>

        <!-- Main Content -->
        <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
            
            <!-- VIEW 1: ACTIVE FEED -->
            <div x-show="activeTab === 'feed'" x-cloak>
                <!-- Controls Bar -->
                <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-4 mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
                    <div class="relative w-full md:w-96">
                        <input type="text" x-model="searchQuery" @input.debounce.300ms="fetchFeed()" placeholder="Rechercher par objet, acheteur ou référence..." class="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent">
                        <span class="absolute left-3 top-2.5 text-slate-400">🔍</span>
                    </div>

                    <!-- Filter Tabs -->
                    <div class="flex items-center gap-2 w-full md:w-auto">
                        <button @click="minScore = 0; fetchFeed()" :class="minScore === 0 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'" class="px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors">
                            Tous les avis
                        </button>
                        <button @click="minScore = 50; fetchFeed()" :class="minScore === 50 ? 'bg-amber-600 text-white' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'" class="px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors">
                            ⚠️ &ge; 50% Pertinence
                        </button>
                        <button @click="minScore = 80; fetchFeed()" :class="minScore === 80 ? 'bg-emerald-600 text-white' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'" class="px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors">
                            🎯 &ge; 80% (GO Uniquement)
                        </button>
                    </div>
                </div>

                <!-- Feed Table -->
                <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr class="bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                                    <th class="py-3 px-4">Score & Décision</th>
                                    <th class="py-3 px-4">Réf & N°</th>
                                    <th class="py-3 px-4">Objet de la Consultation</th>
                                    <th class="py-3 px-4">Acheteur Public</th>
                                    <th class="py-3 px-4">Date Limite</th>
                                    <th class="py-3 px-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                <template x-for="item in items" :key="item.portal_id">
                                    <tr class="hover:bg-slate-50/80 transition-colors">
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <span :class="{
                                                'bg-emerald-100 text-emerald-800 border-emerald-300': item.match_score >= 80,
                                                'bg-amber-100 text-amber-800 border-amber-300': item.match_score >= 50 && item.match_score < 80,
                                                'bg-rose-100 text-rose-800 border-rose-300': item.match_score < 50
                                            }" class="px-2.5 py-1 rounded-full text-xs font-bold border inline-flex items-center gap-1">
                                                <span x-text="item.match_score >= 80 ? '🎯' : (item.match_score >= 50 ? '⚠️' : '❌')"></span>
                                                <span x-text="item.match_score.toFixed(0) + '% ' + item.decision_verdict"></span>
                                            </span>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap font-mono text-xs text-slate-600">
                                            <div class="font-bold text-slate-900" x-text="'#' + item.portal_id"></div>
                                            <div x-text="item.reference"></div>
                                        </td>
                                        <td class="py-3.5 px-4">
                                            <div class="font-medium text-slate-900 line-clamp-2 max-w-lg" x-text="item.title"></div>
                                            <div class="text-xs text-slate-400 mt-0.5" x-text="item.line_item_count + ' articles au devis &bull; ' + item.main_category"></div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <div class="font-medium text-slate-800" x-text="item.buyer_name"></div>
                                            <div class="text-xs text-slate-500" x-text="item.execution_location || 'Lieu non spécifié'"></div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <div class="font-semibold text-rose-600" x-text="item.deadline_at"></div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap text-right space-x-2">
                                            <button @click="openModal(item.portal_id)" class="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium rounded-lg transition-colors">
                                                Fiche 60s
                                            </button>
                                            <a :href="item.portal_url" target="_blank" class="px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition-colors">
                                                Portail ↗
                                            </a>
                                        </td>
                                    </tr>
                                </template>
                                <tr x-show="items.length === 0 && !loading">
                                    <td colspan="6" class="py-12 text-center text-slate-400">
                                        Aucune consultation trouvée pour ces critères de filtrage.
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- VIEW 2: STRATEGIC RADAR & MARKET INTELLIGENCE -->
            <div x-show="activeTab === 'radar'" x-cloak class="space-y-6">
                
                <!-- KPI Banners -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Plafond Statutaire BDC (Art. 91)</div>
                        <div class="text-2xl font-black text-slate-900">500,000 MAD <span class="text-xs font-normal text-slate-500">TTC / an</span></div>
                        <div class="text-xs text-slate-500 mt-2">Décret 2-22-431. Au-delà, un Appel d'Offres (AO) public est légalement obligatoire.</div>
                    </div>

                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Concentration Budgétaire T4</div>
                        <div class="text-2xl font-black text-emerald-600" x-text="(seasonality?.q4_concentration_pct || 0) + '%'"></div>
                        <div class="text-xs text-slate-500 mt-2" x-text="seasonality?.seasonality_insight || 'Calcul de l\\'accélération budgétaire d\\'octobre à décembre.'"></div>
                    </div>

                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
                        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Base d'Adjudications Historiques</div>
                        <div class="text-2xl font-black text-indigo-600">~340,000 <span class="text-xs font-normal text-slate-500">résultats</span></div>
                        <div class="text-xs text-slate-500 mt-2">Suivi systématique des prix gagnants, du nombre de devis et des attributaires.</div>
                    </div>
                </div>

                <!-- Two Column Radar Layout -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    
                    <!-- Left: Top Competitors -->
                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="font-bold text-slate-900 text-base">Top Fournisseurs Adjudicataires</h3>
                                <p class="text-xs text-slate-500">Concurrents les plus actifs par montant cumulé remporté (MAD TTC)</p>
                            </div>
                            <span class="text-xs bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full font-semibold">Attributions</span>
                        </div>

                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[11px]">
                                        <th class="py-2.5 px-3">Entreprise Adjudicataire</th>
                                        <th class="py-2.5 px-3 text-center">Victoires</th>
                                        <th class="py-2.5 px-3 text-right">Total Attribué</th>
                                        <th class="py-2.5 px-3 text-right">Contrat Moyen</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    <template x-for="c in competitors" :key="c.winner_name">
                                        <tr class="hover:bg-slate-50/70">
                                            <td class="py-2.5 px-3 font-semibold text-slate-800" x-text="c.winner_name"></td>
                                            <td class="py-2.5 px-3 text-center">
                                                <span class="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-bold" x-text="c.total_wins"></span>
                                            </td>
                                            <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-900" x-text="c.total_awarded_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2.5 px-3 text-right font-mono text-slate-500" x-text="c.avg_contract_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                        </tr>
                                    </template>
                                    <tr x-show="competitors.length === 0">
                                        <td colspan="4" class="py-8 text-center text-slate-400">Aucune donnée de concurrent disponible.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Right: Buyer Velocity & Article 91 Alarm -->
                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="font-bold text-slate-900 text-base">Vélocité Budgétaire Acheteurs</h3>
                                <p class="text-xs text-slate-500">Acheteurs publics approchant le plafond BDC de 500k MAD (Article 91)</p>
                            </div>
                            <span class="text-xs bg-amber-100 text-amber-800 px-2.5 py-1 rounded-full font-semibold">Détection AO</span>
                        </div>

                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[11px]">
                                        <th class="py-2.5 px-3">Acheteur Public</th>
                                        <th class="py-2.5 px-3 text-center">BDC Passés</th>
                                        <th class="py-2.5 px-3 text-right">Dépense BDC</th>
                                        <th class="py-2.5 px-3">Statut Plafond (500k)</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    <template x-for="b in buyers" :key="b.buyer_name">
                                        <tr class="hover:bg-slate-50/70">
                                            <td class="py-2.5 px-3 font-medium text-slate-800 max-w-xs truncate" :title="b.buyer_name" x-text="b.buyer_name"></td>
                                            <td class="py-2.5 px-3 text-center font-bold text-slate-600" x-text="b.bdc_count"></td>
                                            <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-900" x-text="b.total_spent_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2.5 px-3">
                                                <div class="flex items-center gap-2">
                                                    <div class="w-20 bg-slate-200 rounded-full h-2 overflow-hidden">
                                                        <div :class="b.upcoming_ao_signal ? 'bg-rose-500' : (b.budget_exhaustion_pct > 50 ? 'bg-amber-500' : 'bg-emerald-500')" class="h-2 rounded-full" :style="'width: ' + b.budget_exhaustion_pct + '%'"></div>
                                                    </div>
                                                    <span class="font-bold text-[11px]" :class="b.upcoming_ao_signal ? 'text-rose-600' : 'text-slate-600'" x-text="b.budget_exhaustion_pct + '%'"></span>
                                                    <template x-if="b.upcoming_ao_signal">
                                                        <span class="px-1.5 py-0.5 bg-rose-100 text-rose-700 font-bold text-[10px] rounded" title="Alerte: Risque de saucissonnage de contrat - Appel d'Offres requis">AO Requis!</span>
                                                    </template>
                                                </div>
                                            </td>
                                        </tr>
                                    </template>
                                    <tr x-show="buyers.length === 0">
                                        <td colspan="4" class="py-8 text-center text-slate-400">Aucun acheteur enregistré pour cet exercice.</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>

            </div>

        </main>

        <!-- 60-Second Decision Card Modal -->
        <div x-show="modalOpen" x-cloak class="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div @click.away="modalOpen = false" class="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                
                <!-- Modal Header -->
                <div class="bg-slate-900 text-white p-6 flex justify-between items-start">
                    <div>
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-xs uppercase tracking-wider text-slate-400 font-mono" x-text="'BDC #' + activeTender?.portal_id + ' &bull; Réf: ' + activeTender?.reference"></span>
                        </div>
                        <h3 class="text-lg font-bold leading-snug max-w-2xl" x-text="activeTender?.title"></h3>
                    </div>
                    <button @click="modalOpen = false" class="text-slate-400 hover:text-white text-2xl font-light leading-none">&times;</button>
                </div>

                <!-- Modal Body -->
                <div class="p-6 overflow-y-auto space-y-6 flex-1 text-sm">
                    <div class="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-xl border border-slate-100">
                        <div>
                            <span class="text-slate-500 text-xs block">Acheteur Public</span>
                            <span class="font-semibold text-slate-800" x-text="activeTender?.buyer_name"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-xs block">Lieu d'exécution</span>
                            <span class="font-semibold text-slate-800" x-text="activeTender?.execution_location || 'Non spécifié'"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-xs block">Date limite de réception</span>
                            <span class="font-bold text-rose-600" x-text="activeTender?.deadline_at"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-xs block">Prestation & Catégorie</span>
                            <span class="font-medium text-slate-700" x-text="activeTender?.main_category"></span>
                        </div>
                    </div>

                    <!-- Line Items Table -->
                    <div>
                        <h4 class="font-bold text-slate-900 mb-3 text-sm flex items-center justify-between">
                            <span>Articles & Spécifications Techniques</span>
                            <span class="text-xs text-slate-500 font-normal" x-text="(activeTender?.line_items?.length || 0) + ' articles demandés'"></span>
                        </h4>
                        <div class="border border-slate-200 rounded-xl overflow-hidden">
                            <table class="w-full text-xs">
                                <thead class="bg-slate-50 border-b border-slate-200 text-slate-500">
                                    <tr>
                                        <th class="py-2.5 px-3 text-left">N°</th>
                                        <th class="py-2.5 px-3 text-left">Désignation</th>
                                        <th class="py-2.5 px-3 text-center">Quantité</th>
                                        <th class="py-2.5 px-3 text-right">TVA</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100">
                                    <template x-for="item in activeTender?.line_items" :key="item.item_order">
                                        <tr class="hover:bg-slate-50/50">
                                            <td class="py-2 px-3 font-mono font-bold text-slate-400" x-text="'#' + item.item_order"></td>
                                            <td class="py-2 px-3">
                                                <div class="font-semibold text-slate-900" x-text="item.designation"></div>
                                                <div class="text-[11px] text-slate-500 line-clamp-1" x-text="item.technical_specs"></div>
                                            </td>
                                            <td class="py-2 px-3 text-center font-bold text-slate-700" x-text="item.quantity + ' ' + item.unit"></td>
                                            <td class="py-2 px-3 text-right text-slate-500" x-text="item.tva_rate + '%'"></td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Modal Footer -->
                <div class="bg-slate-50 border-t border-slate-200 p-4 flex justify-between items-center">
                    <div class="space-x-2">
                        <button @click="recordAction('shortlisted')" class="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors">
                            ⭐ Retenir (Shortlist)
                        </button>
                        <button @click="recordAction('rejected')" class="px-3.5 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-semibold transition-colors">
                            ❌ Ignorer (Skip)
                        </button>
                    </div>
                    <a :href="activeTender?.portal_url" target="_blank" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition-colors inline-flex items-center gap-1.5">
                        Consulter sur le Portail Officiel &rarr;
                    </a>
                </div>

            </div>
        </div>

    </div>

    <script>
        function dashboardApp() {
            return {
                activeTab: 'feed',
                selectedProfile: 'cctv_security',
                minScore: 0,
                searchQuery: '',
                items: [],
                competitors: [],
                buyers: [],
                seasonality: null,
                loading: false,
                modalOpen: false,
                activeTender: null,

                init() {
                    this.fetchFeed();
                },

                async fetchFeed() {
                    this.loading = true;
                    try {
                        let url = `/api/feed?profile_name=${this.selectedProfile}&min_score=${this.minScore}`;
                        if (this.searchQuery) url += `&search=${encodeURIComponent(this.searchQuery)}`;
                        const res = await fetch(url);
                        this.items = await res.json();
                    } catch (e) {
                        console.error('Error fetching feed:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                async fetchRadarData() {
                    try {
                        const [compRes, buyerRes, seasRes] = await Promise.all([
                            fetch('/api/analytics/competitors?limit=15'),
                            fetch('/api/analytics/buyers'),
                            fetch('/api/analytics/seasonality')
                        ]);
                        this.competitors = await compRes.json();
                        this.buyers = await buyerRes.json();
                        this.seasonality = await seasRes.json();
                    } catch (e) {
                        console.error('Error fetching radar data:', e);
                    }
                },

                async openModal(portalId) {
                    try {
                        const res = await fetch(`/api/tenders/${portalId}`);
                        this.activeTender = await res.json();
                        this.modalOpen = true;
                    } catch (e) {
                        alert('Erreur lors du chargement des détails: ' + e);
                    }
                },

                async recordAction(actionName) {
                    if (!this.activeTender) return;
                    try {
                        await fetch('/api/actions', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                profile_id: '00000000-0000-0000-0000-000000000000',
                                tender_id: this.activeTender.portal_id,
                                action: actionName
                            })
                        });
                        alert(`Action enregistrée: ${actionName}`);
                        this.modalOpen = false;
                    } catch (e) {
                        alert('Erreur: ' + e);
                    }
                }
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the single-page responsive procurement dashboard"""
    return HTMLResponse(content=HTML_DASHBOARD)
