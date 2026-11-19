from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes.feed import router as feed_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.crawler import router as crawler_router

app = FastAPI(
    title="Antigravity Procurement Intelligence",
    description="Autonomous Moroccan Public Procurement (BDC & AO) Intelligence Engine with RBAC",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(crawler_router)
app.include_router(feed_router)
app.include_router(analytics_router)

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="fr" class="h-full bg-slate-900 text-slate-100">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bergag &bull; Moroccan Procurement Intelligence</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
        [x-cloak] { display: none !important; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
    </style>
</head>
<body class="h-full font-sans antialiased bg-slate-950 text-slate-100 selection:bg-emerald-500 selection:text-slate-950" x-data="dashboardApp()" x-init="init()">
    <div class="min-h-full flex flex-col">
        
        <!-- Top App Bar -->
        <header class="bg-slate-900/90 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap justify-between items-center gap-4">
                
                <!-- Brand & System Badge -->
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center font-black text-xl text-slate-950 shadow-lg shadow-emerald-500/20">
                        ⚡
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h1 class="text-lg font-black tracking-tight text-white">BERGAG <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">v2.0 RBAC</span></h1>
                        </div>
                        <p class="text-[11px] text-slate-400">Portail Marocain des Marchés Publics &bull; Décret 2-22-431</p>
                    </div>
                </div>

                <!-- Live Role Switcher (Interactive Persona Demo Bar) -->
                <div class="flex items-center bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
                    <span class="text-slate-400 px-2 font-medium hidden sm:inline">Rôle Actif :</span>
                    <button @click="switchRole('admin')" :class="currentUser.role === 'admin' ? 'bg-emerald-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>👑</span> Fondateur (Admin)
                    </button>
                    <button @click="switchRole('analyst')" :class="currentUser.role === 'analyst' ? 'bg-indigo-500 text-white font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>📊</span> Estimateur (Analyst)
                    </button>
                    <button @click="switchRole('viewer')" :class="currentUser.role === 'viewer' ? 'bg-amber-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>👁️</span> Commercial (Viewer)
                    </button>
                </div>

                <!-- Profile Switcher & User Profile Dropdown -->
                <div class="flex items-center gap-3">
                    <div class="relative">
                        <select x-model="selectedProfile" @change="fetchFeed()" class="bg-slate-800 border border-slate-700 text-white text-xs rounded-xl px-3 py-2 focus:ring-2 focus:ring-emerald-500 outline-none pr-8 cursor-pointer">
                            <option value="cctv_security">📹 Vidéosurveillance & Sécurité</option>
                            <option value="software_data">💻 Logiciel & Données</option>
                        </select>
                    </div>

                    <div class="flex items-center gap-2 pl-2 border-l border-slate-800">
                        <div class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs uppercase"
                             :class="{
                                'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30': currentUser.role === 'admin',
                                'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30': currentUser.role === 'analyst',
                                'bg-amber-500/20 text-amber-400 border border-amber-500/30': currentUser.role === 'viewer'
                             }"
                             x-text="currentUser.full_name.substring(0, 2)">
                        </div>
                        <div class="hidden md:block text-left text-xs">
                            <div class="font-semibold text-white leading-tight" x-text="currentUser.full_name"></div>
                            <div class="text-[10px] text-slate-400 uppercase tracking-wider" x-text="currentUser.role"></div>
                        </div>
                    </div>
                </div>

            </div>
        </header>

        <!-- Sub-Nav Modules Bar -->
        <div class="bg-slate-900 border-b border-slate-800/80 px-4 sm:px-6 lg:px-8">
            <div class="max-w-7xl mx-auto flex items-center justify-between overflow-x-auto py-2 gap-4">
                <nav class="flex items-center gap-1.5 text-xs font-semibold">
                    <button @click="activeModule = 'feed'" :class="activeModule === 'feed' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>🎯</span> Opportunités BDC & AO
                        <span class="px-1.5 py-0.2 bg-slate-900 text-slate-400 text-[10px] rounded-full" x-text="items.length"></span>
                    </button>
                    
                    <button x-show="hasPermission('radar:view_competitors') || hasPermission('radar:view_all')" @click="activeModule = 'radar'; fetchRadarData()" :class="activeModule === 'radar' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>📊</span> Radar Stratégique
                    </button>

                    <button x-show="hasPermission('profiles:view') || hasPermission('profiles:manage')" @click="activeModule = 'profiles'; fetchProfilesData()" :class="activeModule === 'profiles' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>📁</span> Studio Profils & Catalogues
                    </button>

                    <button x-show="hasPermission('crawler:telemetry')" @click="activeModule = 'crawler'; fetchCrawlerStatus()" :class="activeModule === 'crawler' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>🛰️</span> Centre Crawler
                        <span class="w-2 h-2 rounded-full" :class="crawlerTelemetry.status === 'crawling' ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'"></span>
                    </button>

                    <button x-show="hasPermission('users:manage')" @click="activeModule = 'team'; fetchTeamUsers()" :class="activeModule === 'team' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>👥</span> Équipe & RBAC
                    </button>
                </nav>

                <!-- Live Status & WAF Indicator -->
                <div class="hidden lg:flex items-center gap-2 text-[11px] text-slate-400 font-mono">
                    <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    <span>WAF F5 ASM : <strong class="text-emerald-400">Bypass Actif</strong></span>
                </div>
            </div>
        </div>

        <!-- Main Workspace -->
        <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
            
            <!-- ========================================== -->
            <!-- MODULE 1: DYNAMIC OPPORTUNITY FEED         -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'feed'" x-cloak class="space-y-5">
                
                <!-- Dynamic Multi-Axis Filter Studio -->
                <div class="bg-slate-900/90 rounded-2xl border border-slate-800 p-4 shadow-xl space-y-3">
                    <div class="flex flex-col md:flex-row justify-between items-center gap-3">
                        
                        <!-- Search Box with instant clear -->
                        <div class="relative w-full md:w-96">
                            <input type="text" x-model="searchQuery" @input.debounce.250ms="fetchFeed()" placeholder="Recherche par mot-clé, objet, référence, acheteur..." class="w-full bg-slate-950 border border-slate-800 pl-10 pr-8 py-2 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent">
                            <span class="absolute left-3 top-2.5 text-slate-500 text-xs">🔍</span>
                            <button x-show="searchQuery" @click="searchQuery = ''; fetchFeed()" class="absolute right-2.5 top-2 text-slate-500 hover:text-slate-300 text-xs">&times;</button>
                        </div>

                        <!-- Score Threshold Segmented Controls -->
                        <div class="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs w-full md:w-auto">
                            <button @click="minScore = 0; fetchFeed()" :class="minScore === 0 ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg transition-all flex-1 md:flex-initial">
                                Tous (<span x-text="items.length"></span>)
                            </button>
                            <button @click="minScore = 50; fetchFeed()" :class="minScore === 50 ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg transition-all flex-1 md:flex-initial">
                                ⚠️ &ge; 50%
                            </button>
                            <button @click="minScore = 80; fetchFeed()" :class="minScore === 80 ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3 py-1.5 rounded-lg transition-all flex-1 md:flex-initial">
                                🎯 &ge; 80% (GO)
                            </button>
                        </div>

                        <!-- View Mode Switcher -->
                        <div class="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
                            <button @click="viewMode = 'table'" :class="viewMode === 'table' ? 'bg-slate-800 text-white' : 'text-slate-500 hover:text-slate-300'" class="p-1.5 rounded-lg">
                                ☰ Table
                            </button>
                            <button @click="viewMode = 'cards'" :class="viewMode === 'cards' ? 'bg-slate-800 text-white' : 'text-slate-500 hover:text-slate-300'" class="p-1.5 rounded-lg">
                                ☷ Cartes
                            </button>
                        </div>

                    </div>

                    <!-- Faceted Filters Bar -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-2 border-t border-slate-800/80 text-xs">
                        
                        <!-- Filter 1: Moroccan Regions -->
                        <div>
                            <label class="text-[10px] text-slate-500 font-semibold block mb-1">Région / Territoire</label>
                            <select x-model="selectedRegion" @change="fetchFeed()" class="w-full bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none">
                                <option value="all">Toutes les régions (National)</option>
                                <option value="Casablanca">Casablanca-Settat</option>
                                <option value="Rabat">Rabat-Salé-Kénitra</option>
                                <option value="Fès">Fès-Meknès</option>
                                <option value="Marrakech">Marrakech-Safi</option>
                                <option value="Tanger">Tanger-Tétouan-Al Hoceïma</option>
                                <option value="Souss">Souss-Massa</option>
                                <option value="Oriental">L'Oriental</option>
                                <option value="Béni Mellal">Béni Mellal-Khénifra</option>
                                <option value="Drâa">Drâa-Tafilalet</option>
                                <option value="Laâyoune">Laâyoune-Sakia El Hamra</option>
                            </select>
                        </div>

                        <!-- Filter 2: Category -->
                        <div>
                            <label class="text-[10px] text-slate-500 font-semibold block mb-1">Catégorie Marché</label>
                            <select x-model="selectedCategory" @change="fetchFeed()" class="w-full bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none">
                                <option value="all">Toutes les prestations</option>
                                <option value="Fournitures">Fournitures</option>
                                <option value="Services">Services</option>
                                <option value="Travaux">Travaux</option>
                            </select>
                        </div>

                        <!-- Filter 3: Urgency / Deadline -->
                        <div>
                            <label class="text-[10px] text-slate-500 font-semibold block mb-1">Délai de Réception</label>
                            <select x-model="selectedUrgency" @change="fetchFeed()" class="w-full bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none">
                                <option value="all">Tous les délais</option>
                                <option value="urgent_24h">🚨 Critique (&lt; 24 heures)</option>
                                <option value="urgent_48h">⏳ Urgent (&lt; 48 heures)</option>
                            </select>
                        </div>

                        <!-- Filter 4: Quick Reset & Feedback Filter -->
                        <div class="flex items-end">
                            <button @click="resetFilters()" class="w-full bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border border-slate-700/60 flex items-center justify-center gap-1.5">
                                <span>↺</span> Réinitialiser Filtres
                            </button>
                        </div>

                    </div>
                </div>

                <!-- TABLE VIEW -->
                <div x-show="viewMode === 'table'" class="bg-slate-900 rounded-2xl border border-slate-800 shadow-xl overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-950/80 border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                                    <th class="py-3 px-4">Score & Décision</th>
                                    <th class="py-3 px-4">ID & Réf</th>
                                    <th class="py-3 px-4">Objet de la Consultation</th>
                                    <th class="py-3 px-4">Acheteur Public & Lieu</th>
                                    <th class="py-3 px-4">Date Limite</th>
                                    <th class="py-3 px-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/70">
                                <template x-for="item in items" :key="item.portal_id">
                                    <tr class="hover:bg-slate-800/40 transition-colors">
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <span :class="{
                                                'bg-emerald-500/10 text-emerald-400 border-emerald-500/30': item.match_score >= 80,
                                                'bg-amber-500/10 text-amber-400 border-amber-500/30': item.match_score >= 50 && item.match_score < 80,
                                                'bg-rose-500/10 text-rose-400 border-rose-500/30': item.match_score < 50
                                            }" class="px-2.5 py-1 rounded-full font-bold border inline-flex items-center gap-1.5 text-[11px]">
                                                <span x-text="item.match_score >= 80 ? '🎯' : (item.match_score >= 50 ? '⚠️' : '❌')"></span>
                                                <span x-text="item.match_score.toFixed(0) + '% ' + item.decision_verdict"></span>
                                            </span>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap font-mono text-slate-400">
                                            <div class="font-bold text-white text-xs" x-text="'#' + item.portal_id"></div>
                                            <div class="text-[11px] text-slate-400 truncate max-w-[120px]" x-text="item.reference"></div>
                                        </td>
                                        <td class="py-3.5 px-4">
                                            <div class="font-medium text-slate-100 line-clamp-2 max-w-lg text-xs leading-relaxed" x-text="item.title"></div>
                                            <div class="text-[11px] text-slate-500 mt-1 flex items-center gap-2">
                                                <span class="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded" x-text="item.line_item_count + ' articles au devis'"></span>
                                                <span x-text="'&bull; ' + item.main_category"></span>
                                            </div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <div class="font-semibold text-slate-200 truncate max-w-xs" x-text="item.buyer_name"></div>
                                            <div class="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                                                <span>📍</span> <span x-text="item.execution_location"></span>
                                            </div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap">
                                            <div class="font-bold text-rose-400 font-mono" x-text="item.deadline_at"></div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap text-right space-x-1.5">
                                            <button @click="openModal(item.portal_id)" class="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg text-xs transition-colors">
                                                Fiche 60s
                                            </button>
                                            <a :href="item.portal_url" target="_blank" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-lg text-xs transition-colors">
                                                Portail ↗
                                            </a>
                                        </td>
                                    </tr>
                                </template>
                                <tr x-show="items.length === 0 && !loading">
                                    <td colspan="6" class="py-16 text-center text-slate-500">
                                        <div class="text-3xl mb-2">🔍</div>
                                        <div class="text-sm font-medium">Aucune consultation ne correspond à ces critères.</div>
                                        <div class="text-xs text-slate-600 mt-1">Modifiez vos filtres ou sélectionnez un autre profil d'activité.</div>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- CARDS VIEW -->
                <div x-show="viewMode === 'cards'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <template x-for="item in items" :key="item.portal_id">
                        <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl hover:border-slate-700 transition-all flex flex-col justify-between">
                            <div>
                                <div class="flex justify-between items-start gap-2 mb-3">
                                    <span :class="{
                                        'bg-emerald-500/10 text-emerald-400 border-emerald-500/30': item.match_score >= 80,
                                        'bg-amber-500/10 text-amber-400 border-amber-500/30': item.match_score >= 50 && item.match_score < 80,
                                        'bg-rose-500/10 text-rose-400 border-rose-500/30': item.match_score < 50
                                    }" class="px-2 py-0.5 rounded-full font-bold border text-[11px] inline-flex items-center gap-1">
                                        <span x-text="item.match_score >= 80 ? '🎯' : (item.match_score >= 50 ? '⚠️' : '❌')"></span>
                                        <span x-text="item.match_score.toFixed(0) + '% ' + item.decision_verdict"></span>
                                    </span>
                                    <span class="font-mono text-[11px] text-slate-500" x-text="'#' + item.portal_id"></span>
                                </div>

                                <h3 class="font-bold text-slate-100 text-sm leading-snug line-clamp-2 mb-2" :title="item.title" x-text="item.title"></h3>
                                <p class="text-xs text-slate-400 mb-3 truncate" x-text="item.buyer_name"></p>

                                <div class="space-y-1.5 text-xs text-slate-400 bg-slate-950 p-3 rounded-xl border border-slate-800/80 mb-4 font-mono">
                                    <div class="flex justify-between">
                                        <span class="text-slate-500">Réf :</span>
                                        <span class="text-slate-300 font-bold" x-text="item.reference"></span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-500">Lieu :</span>
                                        <span class="text-slate-300" x-text="item.execution_location"></span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-slate-500">Délai :</span>
                                        <span class="text-rose-400 font-bold" x-text="item.deadline_at"></span>
                                    </div>
                                </div>
                            </div>

                            <div class="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                                <button @click="openModal(item.portal_id)" class="flex-1 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs rounded-xl transition-colors">
                                    Fiche 60s
                                </button>
                                <a :href="item.portal_url" target="_blank" class="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-xl transition-colors">
                                    Portail ↗
                                </a>
                            </div>
                        </div>
                    </template>
                </div>

            </div>

            <!-- ========================================== -->
            <!-- MODULE 2: STRATEGIC MARKET RADAR           -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'radar'" x-cloak class="space-y-6">
                <!-- KPI Banners -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">Plafond Statutaire BDC (Art. 91)</div>
                        <div class="text-2xl font-black text-white">500,000 MAD <span class="text-xs font-normal text-slate-400">TTC / an</span></div>
                        <div class="text-xs text-slate-400 mt-2">Décret 2-22-431. Au-delà, un Appel d'Offres (AO) est légalement requis.</div>
                    </div>

                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">Concentration Budgétaire T4</div>
                        <div class="text-2xl font-black text-emerald-400" x-text="(seasonality?.q4_concentration_pct || 0) + '%'"></div>
                        <div class="text-xs text-slate-400 mt-2" x-text="seasonality?.seasonality_insight || 'Accélération budgétaire confirmée d\\'octobre à décembre.'"></div>
                    </div>

                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1">Base d'Adjudications TGR</div>
                        <div class="text-2xl font-black text-indigo-400">~340,000 <span class="text-xs font-normal text-slate-400">résultats</span></div>
                        <div class="text-xs text-slate-400 mt-2">Suivi systématique des prix gagnants, du nombre de devis et des concurrents.</div>
                    </div>
                </div>

                <!-- Two Column Radar Layout -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    
                    <!-- Left: Top Competitors -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="font-bold text-white text-base">Top Fournisseurs Adjudicataires</h3>
                                <p class="text-xs text-slate-400">Concurrents les plus actifs par montant cumulé remporté (MAD TTC)</p>
                            </div>
                            <span class="text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2.5 py-1 rounded-full font-bold">Attributions</span>
                        </div>

                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[11px]">
                                        <th class="py-2.5 px-3">Entreprise Adjudicataire</th>
                                        <th class="py-2.5 px-3 text-center">Victoires</th>
                                        <th class="py-2.5 px-3 text-right">Total Attribué</th>
                                        <th class="py-2.5 px-3 text-right">Contrat Moyen</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/60">
                                    <template x-for="c in competitors" :key="c.winner_name">
                                        <tr class="hover:bg-slate-800/40">
                                            <td class="py-2.5 px-3 font-semibold text-slate-200" x-text="c.winner_name"></td>
                                            <td class="py-2.5 px-3 text-center">
                                                <span class="bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded-full font-bold font-mono" x-text="c.total_wins"></span>
                                            </td>
                                            <td class="py-2.5 px-3 text-right font-mono font-bold text-emerald-400" x-text="c.total_awarded_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2.5 px-3 text-right font-mono text-slate-400" x-text="c.avg_contract_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Right: Buyer Velocity & Article 91 Alarm -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="font-bold text-white text-base">Vélocité Budgétaire Acheteurs</h3>
                                <p class="text-xs text-slate-400">Acheteurs publics approchant le plafond BDC de 500k MAD (Article 91)</p>
                            </div>
                            <span class="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-1 rounded-full font-bold">Détection AO</span>
                        </div>

                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[11px]">
                                        <th class="py-2.5 px-3">Acheteur Public</th>
                                        <th class="py-2.5 px-3 text-center">BDC</th>
                                        <th class="py-2.5 px-3 text-right">Dépense BDC</th>
                                        <th class="py-2.5 px-3">Statut Plafond (500k)</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/60">
                                    <template x-for="b in buyers" :key="b.buyer_name">
                                        <tr class="hover:bg-slate-800/40">
                                            <td class="py-2.5 px-3 font-medium text-slate-300 max-w-xs truncate" :title="b.buyer_name" x-text="b.buyer_name"></td>
                                            <td class="py-2.5 px-3 text-center font-bold text-slate-400 font-mono" x-text="b.bdc_count"></td>
                                            <td class="py-2.5 px-3 text-right font-mono font-bold text-white" x-text="b.total_spent_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2.5 px-3">
                                                <div class="flex items-center gap-2">
                                                    <div class="w-20 bg-slate-800 rounded-full h-2 overflow-hidden">
                                                        <div :class="b.upcoming_ao_signal ? 'bg-rose-500' : (b.budget_exhaustion_pct > 50 ? 'bg-amber-400' : 'bg-emerald-400')" class="h-2 rounded-full" :style="'width: ' + b.budget_exhaustion_pct + '%'"></div>
                                                    </div>
                                                    <span class="font-bold font-mono text-[11px]" :class="b.upcoming_ao_signal ? 'text-rose-400' : 'text-slate-400'" x-text="b.budget_exhaustion_pct + '%'"></span>
                                                    <template x-if="b.upcoming_ao_signal">
                                                        <span class="px-1.5 py-0.5 bg-rose-500/20 text-rose-300 font-bold text-[10px] rounded border border-rose-500/30">AO Requis!</span>
                                                    </template>
                                                </div>
                                            </td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>
            </div>

            <!-- ========================================== -->
            <!-- MODULE 3: PROFILE & CATALOG STUDIO         -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'profiles'" x-cloak class="space-y-6">
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <div class="flex justify-between items-center mb-6">
                        <div>
                            <h2 class="text-lg font-bold text-white">Studio des Profils Métier & Catalogues Déclaratifs</h2>
                            <p class="text-xs text-slate-400">Règles de filtrage, catalogues BOM et exclusions négatives déclarées en YAML</p>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-4">
                            <div class="flex items-center justify-between">
                                <span class="font-bold text-emerald-400 text-sm">📹 Vidéosurveillance & Sécurité Physique</span>
                                <span class="text-[11px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">cctv_security.yaml</span>
                            </div>
                            <div class="text-xs text-slate-400 space-y-1">
                                <div><strong>Catégories autorisées :</strong> Fournitures, Services</div>
                                <div><strong>Délai minimum :</strong> 24 heures</div>
                                <div><strong>Mots-clés positifs :</strong> camera, nvr, dvr, switch poe, videosurveillance, disque dur</div>
                                <div><strong>Veto négatif :</strong> gardiennage, securite privee, extincteur, alarme incendie</div>
                            </div>
                        </div>

                        <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-4">
                            <div class="flex items-center justify-between">
                                <span class="font-bold text-indigo-400 text-sm">💻 Logiciel, Programmation & Données</span>
                                <span class="text-[11px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">software_data.yaml</span>
                            </div>
                            <div class="text-xs text-slate-400 space-y-1">
                                <div><strong>Catégories autorisées :</strong> Services, Fournitures</div>
                                <div><strong>Délai minimum :</strong> 24 heures</div>
                                <div><strong>Mots-clés positifs :</strong> logiciel, application web, api, base de donnees, dashboard, devops</div>
                                <div><strong>Veto négatif :</strong> maconnerie, plomberie, electricite batiment, mobilier de bureau</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ========================================== -->
            <!-- MODULE 4: CRAWLER OPERATIONS CENTER        -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'crawler'" x-cloak class="space-y-6">
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                        <div>
                            <h2 class="text-lg font-bold text-white">Centre d'Opérations Scraping & Télémétrie WAF</h2>
                            <p class="text-xs text-slate-400">Contrôle du daemon de collecte autonome et état de navigation sur le Portail TGR</p>
                        </div>

                        <div x-show="hasPermission('crawler:trigger')" class="flex items-center gap-3">
                            <select x-model="crawlPagesInput" class="bg-slate-950 border border-slate-800 text-xs rounded-xl px-3 py-2 text-slate-300 outline-none">
                                <option value="1">1 page (50 avis)</option>
                                <option value="2">2 pages (100 avis)</option>
                                <option value="5">5 pages (250 avis)</option>
                            </select>
                            <button @click="triggerCrawl()" :disabled="crawlerTelemetry.status === 'crawling'" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-800 text-slate-950 font-bold text-xs rounded-xl transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2">
                                <span x-show="crawlerTelemetry.status !== 'crawling'">⚡</span>
                                <span x-show="crawlerTelemetry.status === 'crawling'" class="animate-spin">⚙️</span>
                                <span x-text="crawlerTelemetry.status === 'crawling' ? 'Collecte en cours...' : 'Lancer Collecte Live'"></span>
                            </button>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Statut Démon</span>
                            <span class="font-bold text-sm capitalize flex items-center gap-2 mt-1" :class="crawlerTelemetry.status === 'crawling' ? 'text-amber-400' : 'text-emerald-400'">
                                <span class="w-2.5 h-2.5 rounded-full" :class="crawlerTelemetry.status === 'crawling' ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'"></span>
                                <span x-text="crawlerTelemetry.status"></span>
                            </span>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Dernier Run</span>
                            <span class="font-bold text-sm text-slate-200 mt-1 block font-mono" x-text="crawlerTelemetry.last_run_at"></span>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Durée Dernière Session</span>
                            <span class="font-bold text-sm text-slate-200 mt-1 block font-mono" x-text="crawlerTelemetry.last_duration_seconds + ' s'"></span>
                        </div>
                        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Protection WAF F5</span>
                            <span class="font-bold text-xs text-emerald-400 mt-1 block font-mono" x-text="crawlerTelemetry.waf_status"></span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ========================================== -->
            <!-- MODULE 5: TEAM & RBAC MANAGEMENT           -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'team'" x-cloak class="space-y-6">
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <h2 class="text-lg font-bold text-white mb-2">Gestion d'Équipe & Matrice des Permissions (RBAC)</h2>
                    <p class="text-xs text-slate-400 mb-6">Contrôle granulaire des accès selon le rôle professionnel au sein de l'organisation</p>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead>
                                <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[11px]">
                                    <th class="py-3 px-4">Utilisateur</th>
                                    <th class="py-3 px-4">Titre Professionnel</th>
                                    <th class="py-3 px-4">Rôle</th>
                                    <th class="py-3 px-4">Périmètre & Permissions Accédées</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/60">
                                <template x-for="u in teamUsers" :key="u.id">
                                    <tr class="hover:bg-slate-800/40">
                                        <td class="py-3 px-4">
                                            <div class="font-bold text-white" x-text="u.full_name"></div>
                                            <div class="text-[11px] text-slate-500 font-mono" x-text="u.email"></div>
                                        </td>
                                        <td class="py-3 px-4 text-slate-300" x-text="u.title"></td>
                                        <td class="py-3 px-4">
                                            <span class="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono"
                                                  :class="{
                                                    'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30': u.role === 'admin',
                                                    'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30': u.role === 'analyst',
                                                    'bg-amber-500/10 text-amber-400 border border-amber-500/30': u.role === 'viewer'
                                                  }"
                                                  x-text="u.role">
                                            </span>
                                        </td>
                                        <td class="py-3 px-4">
                                            <div class="flex flex-wrap gap-1 max-w-md">
                                                <template x-for="p in u.permissions" :key="p">
                                                    <span class="px-1.5 py-0.5 rounded bg-slate-950 text-slate-400 text-[10px] border border-slate-800 font-mono" x-text="p"></span>
                                                </template>
                                            </div>
                                        </td>
                                    </tr>
                                </template>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

        </main>

        <!-- 60-Second Decision Card Modal with Interactive Margin Tool -->
        <div x-show="modalOpen" x-cloak class="fixed inset-0 z-50 overflow-y-auto bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div @click.away="modalOpen = false" class="bg-slate-900 rounded-3xl shadow-2xl border border-slate-800 max-w-4xl w-full max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                
                <!-- Modal Header -->
                <div class="bg-slate-950 p-6 border-b border-slate-800 flex justify-between items-start">
                    <div>
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-xs uppercase tracking-wider text-emerald-400 font-mono font-bold" x-text="'BDC #' + activeTender?.portal_id + ' &bull; Réf: ' + activeTender?.reference"></span>
                            <span class="text-xs text-slate-500">&bull;</span>
                            <span class="text-xs text-slate-400" x-text="activeTender?.main_category"></span>
                        </div>
                        <h3 class="text-base font-bold text-white leading-snug max-w-2xl" x-text="activeTender?.title"></h3>
                    </div>
                    <button @click="modalOpen = false" class="text-slate-400 hover:text-white text-2xl font-light leading-none p-1">&times;</button>
                </div>

                <!-- Modal Body -->
                <div class="p-6 overflow-y-auto space-y-6 flex-1 text-xs">
                    
                    <!-- Metadata Grid -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950 p-4 rounded-2xl border border-slate-800">
                        <div>
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Acheteur Public</span>
                            <span class="font-bold text-slate-200" x-text="activeTender?.buyer_name"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Territoire</span>
                            <span class="font-bold text-slate-200" x-text="activeTender?.execution_location"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Date Limite</span>
                            <span class="font-bold text-rose-400 font-mono" x-text="activeTender?.deadline_at"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Prestation</span>
                            <span class="font-bold text-slate-200" x-text="activeTender?.prestation_type || 'Non spécifié'"></span>
                        </div>
                    </div>

                    <!-- Interactive Margin & Pricing Estimator Tool (Analyst & Admin only) -->
                    <div x-show="hasPermission('tender:pricing_calculator')" class="bg-gradient-to-br from-slate-950 to-slate-900 p-5 rounded-2xl border border-emerald-500/20 shadow-lg space-y-3">
                        <div class="flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-white text-xs flex items-center gap-1.5">
                                    <span>💰</span> Outil d'Estimation Marge & Prix d'Offre (Moins-Disant)
                                </h4>
                                <p class="text-[10px] text-slate-400">Ajustez la marge commerciale cible pour calculer le devis compétitif recommandé</p>
                            </div>
                            <span class="font-mono font-bold text-emerald-400 text-sm" x-text="targetMarginPct + '% Marge'"></span>
                        </div>

                        <!-- Slider -->
                        <div class="space-y-1">
                            <input type="range" min="15" max="50" step="1" x-model="targetMarginPct" class="w-full accent-emerald-500 cursor-pointer">
                            <div class="flex justify-between text-[10px] text-slate-500 font-mono">
                                <span>15% (Agressif)</span>
                                <span>30% (Équilibré)</span>
                                <span>50% (Confortable)</span>
                            </div>
                        </div>

                        <!-- Pricing Breakdown -->
                        <div class="grid grid-cols-3 gap-3 pt-2 text-center font-mono">
                            <div class="bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                                <span class="text-[10px] text-slate-500 block uppercase">Coût Plancher Estimé</span>
                                <span class="text-sm font-bold text-slate-300" x-text="(estimatedBaseCost).toLocaleString('fr-FR') + ' DH'"></span>
                            </div>
                            <div class="bg-emerald-500/10 p-2.5 rounded-xl border border-emerald-500/30">
                                <span class="text-[10px] text-emerald-400 block uppercase font-bold">Devis Recommandé TTC</span>
                                <span class="text-sm font-black text-emerald-400" x-text="(estimatedBaseCost * (1 + targetMarginPct/100)).toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></span>
                            </div>
                            <div class="bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                                <span class="text-[10px] text-slate-500 block uppercase">Marge Brute Prévue</span>
                                <span class="text-sm font-bold text-indigo-400" x-text="(estimatedBaseCost * (targetMarginPct/100)).toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></span>
                            </div>
                        </div>
                    </div>

                    <!-- Line Items Table -->
                    <div>
                        <h4 class="font-bold text-white mb-2 text-xs flex justify-between items-center">
                            <span>Bordereau des Prix & Articles au Devis</span>
                            <span class="text-slate-400 font-normal" x-text="(activeTender?.line_items?.length || 0) + ' articles demandés'"></span>
                        </h4>

                        <div class="border border-slate-800 rounded-2xl overflow-hidden bg-slate-950">
                            <table class="w-full text-xs">
                                <thead class="bg-slate-900 border-b border-slate-800 text-slate-400 font-bold uppercase text-[10px]">
                                    <tr>
                                        <th class="py-2.5 px-3 text-left">N°</th>
                                        <th class="py-2.5 px-3 text-left">Désignation & Spécifications</th>
                                        <th class="py-2.5 px-3 text-center">Quantité</th>
                                        <th class="py-2.5 px-3 text-right">TVA</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/60">
                                    <template x-for="item in activeTender?.line_items" :key="item.item_order">
                                        <tr class="hover:bg-slate-900/50">
                                            <td class="py-2 px-3 font-mono font-bold text-slate-500" x-text="'#' + item.item_order"></td>
                                            <td class="py-2 px-3">
                                                <div class="font-semibold text-slate-200" x-text="item.designation"></div>
                                                <div class="text-[11px] text-slate-500 line-clamp-1 mt-0.5" x-text="item.technical_specs"></div>
                                            </td>
                                            <td class="py-2 px-3 text-center font-bold text-slate-300 font-mono" x-text="item.quantity + ' ' + item.unit"></td>
                                            <td class="py-2 px-3 text-right text-slate-400 font-mono" x-text="item.tva_rate + '%'"></td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>

                <!-- Modal Footer with Workflow Actions -->
                <div class="bg-slate-950 border-t border-slate-800 p-4 flex justify-between items-center">
                    <div x-show="hasPermission('tender:action')" class="space-x-2">
                        <button @click="recordAction('shortlisted')" class="px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 rounded-xl text-xs font-bold transition-colors">
                            ⭐ Retenir (Shortlist)
                        </button>
                        <button @click="recordAction('in_preparation')" class="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition-colors">
                            📝 En Chiffrage
                        </button>
                        <button @click="recordAction('rejected')" class="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition-colors">
                            ❌ Ignorer
                        </button>
                    </div>

                    <a :href="activeTender?.portal_url" target="_blank" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-colors inline-flex items-center gap-1.5 ml-auto">
                        Consulter sur le Portail Officiel &rarr;
                    </a>
                </div>

            </div>
        </div>

    </div>

    <script>
        function dashboardApp() {
            return {
                activeModule: 'feed',
                viewMode: 'table',
                selectedProfile: 'cctv_security',
                minScore: 0,
                searchQuery: '',
                selectedRegion: 'all',
                selectedCategory: 'all',
                selectedUrgency: 'all',
                items: [],
                competitors: [],
                buyers: [],
                seasonality: null,
                teamUsers: [],
                loading: false,
                modalOpen: false,
                activeTender: null,
                targetMarginPct: 30,
                estimatedBaseCost: 85000,
                crawlPagesInput: 1,

                currentUser: {
                    id: 'usr-admin-01',
                    email: 'admin@bergag.ma',
                    full_name: 'Hamza Senhaji',
                    role: 'admin',
                    title: 'Fondateur & Directeur Exécutif',
                    permissions: [
                        'feed:view', 'feed:export', 'tender:action', 'tender:pricing_calculator',
                        'radar:view_all', 'radar:article91_alarms', 'profiles:manage',
                        'crawler:trigger', 'crawler:telemetry', 'users:manage'
                    ]
                },

                crawlerTelemetry: {
                    status: 'idle',
                    last_run_at: 'Aujourd\\'hui 17:32',
                    last_duration_seconds: 20.4,
                    waf_status: 'Healthy (HTTP 200 - F5 Passed)'
                },

                init() {
                    this.fetchFeed();
                },

                hasPermission(permission) {
                    return this.currentUser.permissions && this.currentUser.permissions.includes(permission);
                },

                async switchRole(roleName) {
                    try {
                        const res = await fetch('/api/auth/switch-demo-role', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ role: roleName })
                        });
                        const data = await res.json();
                        this.currentUser = data.user;
                        // Reset module view if user lacks permission for current module
                        if (this.activeModule === 'crawler' && !this.hasPermission('crawler:telemetry')) {
                            this.activeModule = 'feed';
                        }
                        if (this.activeModule === 'team' && !this.hasPermission('users:manage')) {
                            this.activeModule = 'feed';
                        }
                        this.fetchFeed();
                    } catch (e) {
                        console.error('Error switching role:', e);
                    }
                },

                async fetchFeed() {
                    this.loading = true;
                    try {
                        let url = `/api/feed?profile_name=${this.selectedProfile}&min_score=${this.minScore}&role=${this.currentUser.role}`;
                        if (this.searchQuery) url += `&search=${encodeURIComponent(this.searchQuery)}`;
                        if (this.selectedRegion !== 'all') url += `&region=${encodeURIComponent(this.selectedRegion)}`;
                        if (this.selectedCategory !== 'all') url += `&category=${encodeURIComponent(this.selectedCategory)}`;
                        if (this.selectedUrgency !== 'all') url += `&urgency=${encodeURIComponent(this.selectedUrgency)}`;
                        
                        const res = await fetch(url);
                        this.items = await res.json();
                    } catch (e) {
                        console.error('Error fetching feed:', e);
                    } finally {
                        this.loading = false;
                    }
                },

                resetFilters() {
                    this.searchQuery = '';
                    this.minScore = 0;
                    this.selectedRegion = 'all';
                    this.selectedCategory = 'all';
                    this.selectedUrgency = 'all';
                    this.fetchFeed();
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

                async fetchProfilesData() {
                    // Loaded profiles state
                },

                async fetchCrawlerStatus() {
                    try {
                        const res = await fetch('/api/crawler/status');
                        if (res.ok) {
                            this.crawlerTelemetry = await res.json();
                        }
                    } catch (e) {
                        console.error('Error fetching crawler status:', e);
                    }
                },

                async triggerCrawl() {
                    if (!this.hasPermission('crawler:trigger')) return;
                    try {
                        const res = await fetch('/api/crawler/run', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ pages: parseInt(this.crawlPagesInput), send_emails: false })
                        });
                        const data = await res.json();
                        alert(data.message || 'Collecte démarrée !');
                        this.crawlerTelemetry.status = 'crawling';
                        setTimeout(() => this.fetchCrawlerStatus(), 3000);
                    } catch (e) {
                        alert('Erreur: ' + e);
                    }
                },

                async fetchTeamUsers() {
                    try {
                        const res = await fetch('/api/auth/users');
                        if (res.ok) {
                            this.teamUsers = await res.json();
                        }
                    } catch (e) {
                        console.error('Error fetching team:', e);
                    }
                },

                async openModal(portalId) {
                    try {
                        const res = await fetch(`/api/tenders/${portalId}`);
                        this.activeTender = await res.json();
                        // Calibrate a mock base cost for the margin estimator
                        const count = this.activeTender.line_items?.length || 1;
                        this.estimatedBaseCost = Math.round(count * 22500);
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
                                action: actionName,
                                bid_amount_mad: this.estimatedBaseCost * (1 + this.targetMarginPct / 100)
                            })
                        });
                        alert(`Action enregistrée avec succès : ${actionName}`);
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
    """Serves the single-page responsive procurement dashboard with RBAC"""
    return HTMLResponse(content=HTML_DASHBOARD)
