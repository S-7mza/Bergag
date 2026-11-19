from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes.feed import router as feed_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.crawler import router as crawler_router
from src.api.routes.batches import router as batches_router

app = FastAPI(
    title="Antigravity Procurement Intelligence",
    description="Autonomous Moroccan Public Procurement (BDC & AO) Intelligence Engine with RBAC",
    version="2.1.0"
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
app.include_router(batches_router)

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="fr" class="h-full bg-slate-950 text-slate-100 selection:bg-emerald-500 selection:text-slate-950">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bergag &bull; Moroccan Procurement Intelligence Command Center</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Alpine.js CDN -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <!-- Chart.js CDN for Executive Visualizations -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <style>
        [x-cloak] { display: none !important; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #020617; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
        .ambient-glow {
            background: radial-gradient(circle at 50% 0%, rgba(16, 185, 129, 0.08), transparent 70%);
        }
        @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .skeleton {
            background: linear-gradient(90deg, #0f172a 25%, #1e293b 50%, #0f172a 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
        }
    </style>
</head>
<body class="h-full font-sans antialiased bg-slate-950 text-slate-100 ambient-glow" 
      x-data="dashboardApp()" 
      x-init="init()"
      @keydown.window="handleGlobalKeydown($event)">

    <div class="min-h-full flex flex-col">
        
        <!-- Toast Notification Stack -->
        <div class="fixed top-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
            <template x-for="t in toasts" :key="t.id">
                <div class="pointer-events-auto p-4 rounded-2xl shadow-2xl border text-xs font-semibold flex items-center justify-between gap-3 animate-in fade-in slide-in-from-top-4 duration-200"
                     :class="{
                        'bg-emerald-950/90 text-emerald-200 border-emerald-500/40': t.type === 'success',
                        'bg-indigo-950/90 text-indigo-200 border-indigo-500/40': t.type === 'info',
                        'bg-amber-950/90 text-amber-200 border-amber-500/40': t.type === 'warning',
                        'bg-rose-950/90 text-rose-200 border-rose-500/40': t.type === 'error'
                     }">
                    <div class="flex items-center gap-2.5">
                        <span class="text-base" x-text="t.type === 'success' ? '✅' : (t.type === 'warning' ? '⚠️' : (t.type === 'error' ? '❌' : 'ℹ️'))"></span>
                        <span x-text="t.message"></span>
                    </div>
                    <button @click="removeToast(t.id)" class="text-slate-400 hover:text-white">&times;</button>
                </div>
            </template>
        </div>

        <!-- Top App Bar -->
        <header class="bg-slate-900/90 backdrop-blur-md border-b border-slate-800/80 sticky top-0 z-40">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap justify-between items-center gap-4">
                
                <!-- Brand & System Badge -->
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center font-black text-xl text-slate-950 shadow-lg shadow-emerald-500/20">
                        ⚡
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h1 class="text-lg font-black tracking-tight text-white">BERGAG <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">100/100 PRO</span></h1>
                        </div>
                        <p class="text-[11px] text-slate-400">Portail Marocain des Marchés Publics &bull; Décret 2-22-431</p>
                    </div>
                </div>

                <!-- Live Role Switcher (Interactive Persona Demo Bar) -->
                <div class="flex items-center bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
                    <span class="text-slate-500 px-2 font-medium hidden sm:inline text-[11px]">Rôle :</span>
                    <button @click="switchRole('admin')" :class="currentUser.role === 'admin' ? 'bg-emerald-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>👑</span> Admin
                    </button>
                    <button @click="switchRole('analyst')" :class="currentUser.role === 'analyst' ? 'bg-indigo-500 text-white font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>📊</span> Analyst
                    </button>
                    <button @click="switchRole('viewer')" :class="currentUser.role === 'viewer' ? 'bg-amber-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'" class="px-2.5 py-1 rounded-lg transition-all flex items-center gap-1.5">
                        <span>👁️</span> Viewer
                    </button>
                </div>

                <!-- Profile Switcher & User Profile Dropdown -->
                <div class="flex items-center gap-3">
                    <select x-model="selectedProfile" @change="fetchFeed()" class="bg-slate-800 border border-slate-700 text-white text-xs rounded-xl px-3 py-2 focus:ring-2 focus:ring-emerald-500 outline-none cursor-pointer">
                        <option value="cctv_security">📹 Vidéosurveillance & Sécurité</option>
                        <option value="software_data">💻 Logiciel & Données</option>
                    </select>

                    <button @click="authModalOpen = true" class="flex items-center gap-2 pl-2 border-l border-slate-800 hover:opacity-80 transition-opacity">
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
                    </button>
                </div>

            </div>
        </header>

        <!-- Sub-Nav Modules Bar -->
        <div class="bg-slate-900 border-b border-slate-800/80 px-4 sm:px-6 lg:px-8">
            <div class="max-w-7xl mx-auto flex items-center justify-between overflow-x-auto py-2 gap-4">
                <nav class="flex items-center gap-1.5 text-xs font-semibold">
                    <button @click="activeModule = 'feed'" :class="activeModule === 'feed' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>🎯</span> Opportunités BDC & AO
                        <span class="px-1.5 py-0.2 bg-slate-950 text-slate-400 text-[10px] rounded-full font-mono" x-text="items.length"></span>
                    </button>
                    
                    <button x-show="hasPermission('radar:view_competitors') || hasPermission('radar:view_all')" @click="activeModule = 'radar'; renderRadarCharts()" :class="activeModule === 'radar' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>📊</span> Radar Stratégique & Marché
                    </button>

                    <button x-show="hasPermission('profiles:view') || hasPermission('profiles:manage')" @click="activeModule = 'profiles'" :class="activeModule === 'profiles' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>📁</span> Studio Profils YAML
                    </button>

                    <button x-show="hasPermission('crawler:telemetry')" @click="activeModule = 'crawler'; fetchCrawlerStatus()" :class="activeModule === 'crawler' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>🛰️</span> Centre Crawler
                        <span class="w-2 h-2 rounded-full" :class="crawlerTelemetry.status === 'crawling' ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'"></span>
                    </button>

                    <button x-show="hasPermission('users:manage')" @click="activeModule = 'team'; fetchTeamUsers()" :class="activeModule === 'team' ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>👥</span> Équipe & RBAC
                    </button>

                    <button x-show="currentUser.role === 'admin' || hasPermission('batches:manage')" @click="activeModule = 'ingestion'; fetchIngestionDashboard()" :class="activeModule === 'ingestion' ? 'bg-slate-800 text-amber-400 border border-amber-500/30' : 'text-slate-400 hover:text-slate-200'" class="px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-2">
                        <span>⚡</span> Lots & Ingestion
                        <span class="px-1.5 py-0.2 bg-amber-500/20 text-amber-400 text-[10px] rounded-full font-bold border border-amber-500/30">Admin</span>
                    </button>
                </nav>

                <!-- Keyboard Shortcut Hint Pill -->
                <div class="hidden xl:flex items-center gap-3 text-[11px] text-slate-400 font-mono bg-slate-950 px-3 py-1 rounded-xl border border-slate-800">
                    <span>Raccourcis : <strong class="text-slate-200">J/K</strong> Défiler &bull; <strong class="text-slate-200">Entrée</strong> Fiche 60s &bull; <strong class="text-emerald-400">S</strong> Retenir &bull; <strong class="text-rose-400">X</strong> Ignorer</span>
                </div>
            </div>
        </div>

        <!-- Main Workspace -->
        <main class="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
            
            <!-- ========================================== -->
            <!-- MODULE 1: DYNAMIC OPPORTUNITY FEED         -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'feed'" x-cloak class="space-y-4">
                
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

                        <!-- Sorting Dropdown -->
                        <div class="flex items-center gap-2 text-xs">
                            <label class="text-slate-500 text-[11px] font-medium hidden sm:inline">Trier par :</label>
                            <select x-model="sortBy" @change="fetchFeed()" class="bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-xl px-2.5 py-2 outline-none focus:ring-1 focus:ring-emerald-500">
                                <option value="score_desc">🎯 Score Décroissant</option>
                                <option value="deadline_asc">⏳ Date Limite (Urgent)</option>
                                <option value="items_desc">📦 Nombre d'Articles</option>
                                <option value="id_desc">🆕 Plus Récents</option>
                            </select>
                        </div>

                        <!-- View Mode Switcher -->
                        <div class="hidden sm:flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
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
                                <option value="all">Toutes les régions</option>
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
                            <label class="text-[10px] text-slate-500 font-semibold block mb-1">Délai Légal Décret</label>
                            <select x-model="selectedUrgency" @change="fetchFeed()" class="w-full bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none">
                                <option value="all">Tous les délais</option>
                                <option value="urgent_24h">🚨 Critique (&lt; 24h)</option>
                                <option value="urgent_48h">⏳ BDC Urgent (&lt; 48h)</option>
                            </select>
                        </div>

                        <!-- Filter 4: Reset Button -->
                        <div class="flex items-end">
                            <button @click="resetFilters()" class="w-full bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border border-slate-700/60 flex items-center justify-center gap-1.5">
                                <span>↺</span> Réinitialiser Filtres
                            </button>
                        </div>

                    </div>

                    <!-- Active Filter Chips Bar -->
                    <div x-show="activeFilterChips.length > 0" class="flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-800/50">
                        <span class="text-[10px] text-slate-500 uppercase font-semibold mr-1">Filtres Actifs :</span>
                        <template x-for="chip in activeFilterChips" :key="chip.key">
                            <span class="px-2 py-0.5 rounded-full bg-slate-800 text-emerald-400 border border-slate-700 text-[10px] flex items-center gap-1.5 font-medium">
                                <span x-text="chip.label"></span>
                                <button @click="removeFilterChip(chip.key)" class="hover:text-white">&times;</button>
                            </span>
                        </template>
                    </div>

                </div>

                <!-- SKELETON SHIMMER LOADING STATE -->
                <div x-show="loading" class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-4">
                    <div class="skeleton h-8 w-1/3 rounded-lg"></div>
                    <div class="space-y-3">
                        <div class="skeleton h-12 w-full rounded-xl"></div>
                        <div class="skeleton h-12 w-full rounded-xl"></div>
                        <div class="skeleton h-12 w-full rounded-xl"></div>
                        <div class="skeleton h-12 w-full rounded-xl"></div>
                    </div>
                </div>

                <!-- TABLE VIEW -->
                <div x-show="!loading && viewMode === 'table'" class="bg-slate-900 rounded-2xl border border-slate-800 shadow-xl overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse text-xs">
                            <thead>
                                <tr class="bg-slate-950/80 border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                                    <th class="py-3 px-4">Score & Décision</th>
                                    <th class="py-3 px-4">ID & Réf</th>
                                    <th class="py-3 px-4">Objet de la Consultation</th>
                                    <th class="py-3 px-4">Acheteur Public & Lieu</th>
                                    <th class="py-3 px-4">Compte à Rebours (48h BDC)</th>
                                    <th class="py-3 px-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/70">
                                <template x-for="(item, idx) in items" :key="item.portal_id">
                                    <tr class="hover:bg-slate-800/40 transition-colors"
                                        :class="{'bg-slate-800/25 border-l-2 border-emerald-500': selectedIndex === idx}">
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
                                                <span class="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded font-mono" x-text="item.line_item_count + ' articles au devis'"></span>
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
                                            <div class="font-mono text-xs font-bold flex items-center gap-1.5"
                                                 :class="getCountdownUrgencyClass(item.deadline_at)">
                                                <span x-text="formatCountdown(item.deadline_at)"></span>
                                            </div>
                                            <div class="text-[10px] text-slate-500 font-mono mt-0.5" x-text="item.deadline_at"></div>
                                        </td>
                                        <td class="py-3.5 px-4 whitespace-nowrap text-right space-x-1.5">
                                            <button @click="openModal(item.portal_id)" class="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-lg text-xs transition-colors shadow-sm">
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
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- CARDS VIEW (AUTO FOR MOBILE) -->
                <div x-show="!loading && viewMode === 'cards'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
                                    <div class="flex justify-between items-center">
                                        <span class="text-slate-500">Restant :</span>
                                        <span class="font-bold font-mono" :class="getCountdownUrgencyClass(item.deadline_at)" x-text="formatCountdown(item.deadline_at)"></span>
                                    </div>
                                </div>
                            </div>

                            <div class="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                                <button @click="openModal(item.portal_id)" class="flex-1 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs rounded-xl transition-colors shadow">
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
            <!-- MODULE 2: STRATEGIC MARKET RADAR & CHARTS  -->
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

                <!-- Executive Visualizations (Chart.js) -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Chart 1: Seasonality Histogram -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl space-y-3">
                        <div class="flex justify-between items-center">
                            <div>
                                <h3 class="font-bold text-white text-sm">Accélération Budgétaire Annuelle (Par Mois)</h3>
                                <p class="text-[11px] text-slate-400">Confirmation de la ruée budgétaire du 4ème trimestre (T4)</p>
                            </div>
                            <span class="text-[10px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20 font-bold">T4 Surge</span>
                        </div>
                        <div class="h-64 relative">
                            <canvas id="seasonalityChart"></canvas>
                        </div>
                    </div>

                    <!-- Chart 2: Competitors Market Share -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl space-y-3">
                        <div class="flex justify-between items-center">
                            <div>
                                <h3 class="font-bold text-white text-sm">Top 8 Fournisseurs Adjudicataires (Part de Marché)</h3>
                                <p class="text-[11px] text-slate-400">Montant cumulé des contrats BDC remportés (MAD TTC)</p>
                            </div>
                            <span class="text-[10px] bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded border border-indigo-500/20 font-bold">Volumes</span>
                        </div>
                        <div class="h-64 relative">
                            <canvas id="competitorsChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Two Column Radar Tables -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Left: Top Competitors Table -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl flex flex-col">
                        <h3 class="font-bold text-white text-sm mb-3">Leaderboard des Concurrents</h3>
                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[10px]">
                                        <th class="py-2.5 px-3">Entreprise Adjudicataire</th>
                                        <th class="py-2.5 px-3 text-center">Victoires</th>
                                        <th class="py-2.5 px-3 text-right">Total Attribué</th>
                                        <th class="py-2.5 px-3 text-right">Contrat Moyen</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/60">
                                    <template x-for="c in competitors.slice(0, 8)" :key="c.winner_name">
                                        <tr class="hover:bg-slate-800/40">
                                            <td class="py-2 px-3 font-semibold text-slate-200" x-text="c.winner_name"></td>
                                            <td class="py-2 px-3 text-center font-mono">
                                                <span class="bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded-full font-bold" x-text="c.total_wins"></span>
                                            </td>
                                            <td class="py-2 px-3 text-right font-mono font-bold text-emerald-400" x-text="c.total_awarded_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2 px-3 text-right font-mono text-slate-400" x-text="c.avg_contract_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Right: Buyer Velocity & Article 91 Alarm Table -->
                    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-5 shadow-xl flex flex-col">
                        <h3 class="font-bold text-white text-sm mb-3">Vélocité Budgétaire Acheteurs (Alerte Article 91)</h3>
                        <div class="overflow-x-auto flex-1">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead>
                                    <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[10px]">
                                        <th class="py-2.5 px-3">Acheteur Public</th>
                                        <th class="py-2.5 px-3 text-center">BDC</th>
                                        <th class="py-2.5 px-3 text-right">Dépense BDC</th>
                                        <th class="py-2.5 px-3">Statut Plafond (500k)</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/60">
                                    <template x-for="b in buyers.slice(0, 8)" :key="b.buyer_name">
                                        <tr class="hover:bg-slate-800/40">
                                            <td class="py-2 px-3 font-medium text-slate-300 max-w-xs truncate" :title="b.buyer_name" x-text="b.buyer_name"></td>
                                            <td class="py-2 px-3 text-center font-bold text-slate-400 font-mono" x-text="b.bdc_count"></td>
                                            <td class="py-2 px-3 text-right font-mono font-bold text-white" x-text="b.total_spent_mad.toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></td>
                                            <td class="py-2 px-3">
                                                <div class="flex items-center gap-2">
                                                    <div class="w-16 bg-slate-800 rounded-full h-2 overflow-hidden">
                                                        <div :class="b.upcoming_ao_signal ? 'bg-rose-500' : (b.budget_exhaustion_pct > 50 ? 'bg-amber-400' : 'bg-emerald-400')" class="h-2 rounded-full" :style="'width: ' + b.budget_exhaustion_pct + '%'"></div>
                                                    </div>
                                                    <span class="font-bold font-mono text-[11px]" :class="b.upcoming_ao_signal ? 'text-rose-400' : 'text-slate-400'" x-text="b.budget_exhaustion_pct + '%'"></span>
                                                    <template x-if="b.upcoming_ao_signal">
                                                        <span class="px-1.5 py-0.5 bg-rose-500/20 text-rose-300 font-bold text-[9px] rounded border border-rose-500/30">AO Requis</span>
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
                    <h2 class="text-base font-bold text-white mb-1">Studio des Profils Métier Déclaratifs (YAML)</h2>
                    <p class="text-xs text-slate-400 mb-6">Moteur de règles d'élimination et taxonomies de correspondance</p>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-3">
                            <div class="flex items-center justify-between">
                                <span class="font-bold text-emerald-400 text-sm">📹 Vidéosurveillance & Sécurité Physique</span>
                                <span class="text-[11px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">cctv_security.yaml</span>
                            </div>
                            <div class="text-xs text-slate-400 space-y-1.5">
                                <div><strong>Catégories autorisées :</strong> Fournitures, Services</div>
                                <div><strong>Mots-clés positifs :</strong> camera, nvr, dvr, switch poe, videosurveillance, disque dur</div>
                                <div><strong>Veto négatif :</strong> gardiennage, securite privee, extincteur, alarme incendie</div>
                            </div>
                        </div>

                        <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-3">
                            <div class="flex items-center justify-between">
                                <span class="font-bold text-indigo-400 text-sm">💻 Logiciel, Programmation & Données</span>
                                <span class="text-[11px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-mono">software_data.yaml</span>
                            </div>
                            <div class="text-xs text-slate-400 space-y-1.5">
                                <div><strong>Catégories autorisées :</strong> Services, Fournitures</div>
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
                            <h2 class="text-base font-bold text-white">Centre d'Opérations Scraping & Télémétrie WAF</h2>
                            <p class="text-xs text-slate-400">Pilotage du daemon de collecte autonome et état du bypass WAF</p>
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
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Durée Session</span>
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
            <!-- MODULE 4B: ADMIN INGESTION & BATCH CONTROL -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'ingestion'" x-cloak class="space-y-6">
                <!-- 1. Freshness & "Is Data Up To Date?" Hero Panel -->
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl relative overflow-hidden">
                    <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                        <div>
                            <div class="flex items-center gap-2 mb-2">
                                <span class="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-400 border border-amber-500/30">
                                    Administration Flux & Données
                                </span>
                                <span class="text-xs text-slate-500">&bull;</span>
                                <span class="text-xs text-slate-400 font-mono">SLA Fraîcheur : 60 min</span>
                            </div>
                            <div class="flex items-center gap-3">
                                <h2 class="text-xl font-bold text-white tracking-tight">Statut des Données Reçues & Fraîcheur</h2>
                                <span class="px-3 py-1 rounded-full text-xs font-bold font-mono border flex items-center gap-1.5"
                                      :class="ingestionData.freshness.status_badge">
                                    <span class="w-2 h-2 rounded-full" :class="ingestionData.freshness.is_up_to_date ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-ping'"></span>
                                    <span x-text="ingestionData.freshness.status_label"></span>
                                </span>
                            </div>
                            <p class="text-xs text-slate-400 mt-1">
                                Vos données sont synchronisées avec le portail officiel des marchés publics du Maroc (TGR).
                                Dernière collecte : <strong class="text-slate-200" x-text="ingestionData.freshness.last_sync_formatted"></strong> 
                                (<span class="text-emerald-400 font-bold" x-text="'il y a ' + ingestionData.freshness.minutes_since_sync + ' min'"></span>).
                            </p>
                        </div>

                        <!-- Right Controls -->
                        <div class="flex items-center gap-3">
                            <button @click="fetchIngestionDashboard(); showToast('Télémétrie actualisée', 'info')" 
                                    class="px-3.5 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs text-slate-300 font-semibold transition-colors flex items-center gap-2">
                                <span>🔄</span> Actualiser
                            </button>
                            <button @click="triggerCustomBatch(2)" 
                                    class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-bold text-xs rounded-xl border border-slate-700 transition-all flex items-center gap-2">
                                <span>📥</span> Forcer Lot (100 avis)
                            </button>
                        </div>
                    </div>

                    <!-- Telemetry Meters Strip -->
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                        <div class="bg-slate-950/80 p-4 rounded-xl border border-slate-800/80">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Données à Jour ?</span>
                            <span class="font-black text-sm md:text-base mt-1 flex items-center gap-2"
                                  :class="ingestionData.freshness.is_up_to_date ? 'text-emerald-400' : 'text-amber-400'">
                                <span x-text="ingestionData.freshness.is_up_to_date ? 'OUI • Fraîcheur Optimale' : 'RETARD DÉTECTÉ'"></span>
                            </span>
                            <span class="text-[10px] text-slate-500 block mt-0.5">SLA de synchronisation &le; 60 min</span>
                        </div>

                        <div class="bg-slate-950/80 p-4 rounded-xl border border-slate-800/80">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Prochain Cycle Automatique</span>
                            <span class="font-bold text-sm md:text-base text-slate-200 mt-1 block font-mono"
                                  x-text="'Dans ' + ingestionData.freshness.next_sync_in_minutes + ' minutes'"></span>
                            <span class="text-[10px] text-slate-500 block mt-0.5">Fréquence : toutes les heures</span>
                        </div>

                        <div class="bg-slate-950/80 p-4 rounded-xl border border-slate-800/80">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Avis Portés / Portail Estimé</span>
                            <span class="font-bold text-sm md:text-base text-indigo-400 mt-1 block font-mono"
                                  x-text="ingestionData.freshness.db_ingested_total + ' / ~' + ingestionData.freshness.active_portal_estimated + ' BDC'"></span>
                            <span class="text-[10px] text-slate-500 block mt-0.5">Couverture active locale</span>
                        </div>

                        <div class="bg-slate-950/80 p-4 rounded-xl border border-slate-800/80">
                            <span class="text-[10px] text-slate-500 font-semibold block uppercase">Tunnel Portail (WAF)</span>
                            <span class="font-bold text-xs text-emerald-400 mt-1 block font-mono truncate"
                                  x-text="ingestionData.freshness.portal_health"></span>
                            <span class="text-[10px] text-slate-500 block mt-0.5">F5 Big-IP Bypass Opérationnel</span>
                        </div>
                    </div>
                </div>

                <!-- 2. Diagnostic & "Que ramener maintenant ?" Hero Card -->
                <div class="bg-gradient-to-br from-slate-900 via-indigo-950/30 to-slate-900 rounded-2xl border border-indigo-500/30 p-6 shadow-2xl relative overflow-hidden">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse"></span>
                            <h3 class="text-base font-bold text-white tracking-tight">Diagnostic d'Intégrité des Lots & Détection des Écarts</h3>
                        </div>
                        <span class="px-2.5 py-1 rounded-full text-[10px] font-bold font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                              x-text="ingestionData.diagnostic.issues_count + ' écarts identifiés'"></span>
                    </div>

                    <p class="text-xs text-slate-300 mb-4 leading-relaxed">
                        Le moteur de diagnostic compare en temps réel la structure de votre base locale avec les flux du portail. 
                        Voici les actions requises pour garantir une couverture exhaustive :
                    </p>

                    <!-- Detected Gaps List -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
                        <template x-for="(issue, idx) in ingestionData.diagnostic.issues" :key="idx">
                            <div class="bg-slate-950/80 border border-slate-800/80 p-3.5 rounded-xl flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between gap-2 mb-1.5">
                                        <span class="text-xs font-bold text-slate-100" x-text="issue.title"></span>
                                        <span class="px-1.5 py-0.5 text-[9px] font-bold uppercase rounded font-mono"
                                              :class="{
                                                  'bg-rose-500/20 text-rose-400 border border-rose-500/30': issue.severity === 'high',
                                                  'bg-amber-500/20 text-amber-400 border border-amber-500/30': issue.severity === 'medium',
                                                  'bg-blue-500/20 text-blue-400 border border-blue-500/30': issue.severity === 'low'
                                              }"
                                              x-text="issue.severity"></span>
                                    </div>
                                    <p class="text-[11px] text-slate-400 leading-snug" x-text="issue.detail"></p>
                                </div>
                                <div class="mt-3 pt-2 border-t border-slate-900 text-[10px] text-emerald-400 font-semibold flex items-center gap-1">
                                    <span>👉</span> <span x-text="issue.suggested_fix"></span>
                                </div>
                            </div>
                        </template>
                    </div>

                    <!-- Action Box: What to bring now? -->
                    <div class="bg-slate-950 p-4 md:p-5 rounded-xl border border-indigo-500/40 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div class="space-y-1">
                            <div class="flex items-center gap-2">
                                <span class="text-xs font-bold uppercase tracking-wider text-amber-400 font-mono">⚡ Action Recommandée Immédiate</span>
                            </div>
                            <h4 class="text-sm md:text-base font-bold text-white" x-text="ingestionData.diagnostic.recommended_action.title"></h4>
                            <p class="text-xs text-slate-400 max-w-2xl" x-text="ingestionData.diagnostic.recommended_action.rationale"></p>
                        </div>

                        <!-- One-Click Remediation Button & Depth Selector -->
                        <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                            <select x-model="selectedBatchDepth" 
                                    class="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-xl px-3 py-2.5 focus:border-emerald-500 focus:outline-none">
                                <option :value="1">Profondeur : 1 Page (50 avis)</option>
                                <option :value="2">Profondeur : 2 Pages (100 avis)</option>
                                <option :value="3" selected>Profondeur : 3 Pages (150 avis - Idéal)</option>
                                <option :value="5">Profondeur : 5 Pages (250 avis)</option>
                            </select>

                            <button @click="runRemediation(selectedBatchDepth)" 
                                    :disabled="remediating"
                                    class="px-6 py-3 bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-400 hover:from-emerald-400 hover:to-teal-300 text-slate-950 font-black text-xs md:text-sm rounded-xl shadow-xl shadow-emerald-500/25 flex items-center justify-center gap-2 transition-all transform active:scale-95 disabled:opacity-50">
                                <span x-show="!remediating">⚡</span>
                                <span x-show="remediating" class="animate-spin">⚙️</span>
                                <span x-text="remediating ? 'Ingestion et rattrapage en cours...' : 'Exécuter le Rattrapage Immédiat'"></span>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- 2B. Live Ingestion Stepper & Cockpit (Visible during active ingestion) -->
                <div x-show="ingestionData.active_batch || remediating" x-cloak 
                     class="bg-gradient-to-br from-slate-900 via-indigo-950/40 to-slate-900 rounded-2xl border-2 border-indigo-500/50 p-6 shadow-2xl relative overflow-hidden transition-all duration-500">
                    <!-- Cockpit Top Bar -->
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
                        <div class="flex items-center gap-3">
                            <span class="flex h-3 w-3 relative">
                                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span class="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                            </span>
                            <div>
                                <h3 class="text-base font-bold text-white flex items-center gap-2">
                                    <span>⚡ Ingestion en Direct & Traitement BDC par BDC</span>
                                    <span class="px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                                          x-text="ingestionData.active_batch?.batch_id || 'Lot en préparation'"></span>
                                </h3>
                                <p class="text-xs text-slate-300 font-mono mt-0.5" x-text="ingestionData.active_batch?.current_step || 'Initialisation du plan de collecte...'"></p>
                            </div>
                        </div>

                        <!-- Right Live Badge -->
                        <div class="flex items-center gap-2">
                            <span class="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 shadow-lg shadow-emerald-500/20">
                                <span class="animate-spin text-[11px]">⚙️</span>
                                <span x-text="(ingestionData.active_batch?.tenders_ingested || 0) + ' BDC traités'"></span>
                            </span>
                        </div>
                    </div>

                    <!-- Stepper Phase Bar -->
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5">
                        <div class="p-3 rounded-xl border transition-colors" 
                             :class="ingestionData.active_batch?.progress_pct >= 8 ? 'bg-indigo-950/60 border-indigo-500/50 text-indigo-200 shadow-md' : 'bg-slate-950 border-slate-800 text-slate-500'">
                            <div class="text-[10px] font-bold uppercase tracking-wider font-mono flex items-center gap-1.5">
                                <span x-show="ingestionData.active_batch?.progress_pct >= 20">✓</span>
                                <span>1. Plan d'Exécution</span>
                            </div>
                            <div class="text-xs font-bold mt-1 text-slate-200" x-text="(ingestionData.active_batch?.pages_requested || selectedBatchDepth) + ' Pages (~' + ((ingestionData.active_batch?.pages_requested || selectedBatchDepth) * 50) + ' BDC)'"></div>
                        </div>

                        <div class="p-3 rounded-xl border transition-colors"
                             :class="ingestionData.active_batch?.progress_pct >= 20 ? 'bg-indigo-950/60 border-indigo-500/50 text-indigo-200 shadow-md' : 'bg-slate-950 border-slate-800 text-slate-500'">
                            <div class="text-[10px] font-bold uppercase tracking-wider font-mono flex items-center gap-1.5">
                                <span x-show="ingestionData.active_batch?.progress_pct >= 25">✓</span>
                                <span>2. Scan Listing TGR</span>
                            </div>
                            <div class="text-xs font-bold mt-1 text-slate-200" x-text="(ingestionData.active_batch?.cards_scraped || 0) + ' Cartes Détectées'"></div>
                        </div>

                        <div class="p-3 rounded-xl border transition-colors"
                             :class="ingestionData.active_batch?.progress_pct >= 25 && ingestionData.active_batch?.progress_pct < 100 ? 'bg-emerald-950/70 border-emerald-500/50 text-emerald-200 animate-pulse shadow-md' : (ingestionData.active_batch?.progress_pct >= 100 ? 'bg-indigo-950/60 border-indigo-500/50 text-indigo-200' : 'bg-slate-950 border-slate-800 text-slate-500')">
                            <div class="text-[10px] font-bold uppercase tracking-wider font-mono flex items-center gap-1.5">
                                <span x-show="ingestionData.active_batch?.progress_pct >= 100">✓</span>
                                <span>3. Ingestion BDC par BDC</span>
                            </div>
                            <div class="text-xs font-bold mt-1 text-emerald-400" x-text="(ingestionData.active_batch?.tenders_ingested || 0) + ' BDC Incorporés'"></div>
                        </div>

                        <div class="p-3 rounded-xl border transition-colors"
                             :class="ingestionData.active_batch?.progress_pct >= 100 ? 'bg-emerald-950/70 border-emerald-500/50 text-emerald-200' : 'bg-slate-950 border-slate-800 text-slate-500'">
                            <div class="text-[10px] font-bold uppercase tracking-wider font-mono flex items-center gap-1.5">
                                <span x-show="ingestionData.active_batch?.progress_pct >= 100">✓</span>
                                <span>4. Consolidation & Qualité</span>
                            </div>
                            <div class="text-xs font-bold mt-1" :class="ingestionData.active_batch?.progress_pct >= 100 ? 'text-emerald-400' : 'text-slate-500'" x-text="ingestionData.active_batch?.progress_pct >= 100 ? 'Terminé (100%)' : 'En attente'"></div>
                        </div>
                    </div>

                    <!-- Animated Progress Bar -->
                    <div class="mb-5">
                        <div class="flex items-center justify-between text-xs font-mono mb-1.5">
                            <span class="text-slate-400">Progression globale :</span>
                            <div class="flex items-center gap-3">
                                <span class="text-indigo-300 font-bold" x-text="'Plage : ' + (ingestionData.active_batch?.bdc_range || 'Initialisation...')"></span>
                                <span class="text-emerald-400 font-bold" x-text="(ingestionData.active_batch?.progress_pct || 15) + '%'"></span>
                            </div>
                        </div>
                        <div class="w-full bg-slate-950 h-3 rounded-full overflow-hidden p-0.5 border border-slate-800">
                            <div class="bg-gradient-to-r from-emerald-500 via-teal-400 to-indigo-500 h-2 rounded-full transition-all duration-300"
                                 :style="'width: ' + (ingestionData.active_batch?.progress_pct || 15) + '%'"></div>
                        </div>
                    </div>

                    <!-- Current BDC Spotlight Box -->
                    <template x-if="ingestionData.active_batch?.current_bdc">
                        <div class="bg-slate-950/90 rounded-xl border border-indigo-500/30 p-4 mb-4 shadow-lg">
                            <div class="flex items-center justify-between gap-2 mb-2">
                                <div class="flex items-center gap-2">
                                    <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono font-bold text-xs border border-emerald-500/30">
                                        BDC En Cours : #<span x-text="ingestionData.active_batch.current_bdc.portal_id"></span>
                                    </span>
                                    <span class="text-xs text-slate-400 font-mono" x-text="ingestionData.active_batch.current_bdc.reference"></span>
                                </div>
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono uppercase"
                                      :class="ingestionData.active_batch.current_bdc.verdict === 'GO' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-slate-800 text-slate-300'"
                                      x-text="ingestionData.active_batch.current_bdc.verdict + ' (' + ingestionData.active_batch.current_bdc.score + '%)'"></span>
                            </div>
                            <div class="font-bold text-white text-sm mb-1 leading-snug" x-text="ingestionData.active_batch.current_bdc.title"></div>
                            <div class="flex flex-wrap items-center gap-4 text-xs text-slate-400">
                                <div>Acheteur : <strong class="text-slate-200" x-text="ingestionData.active_batch.current_bdc.buyer"></strong></div>
                                <div>Articles BOM extraits : <strong class="text-indigo-400 font-mono" x-text="ingestionData.active_batch.current_bdc.line_items_count + ' lignes'"></strong></div>
                                <div class="text-[11px] text-slate-500 font-mono" x-text="'Horodatage: ' + ingestionData.active_batch.current_bdc.ingested_at"></div>
                            </div>
                        </div>
                    </template>

                    <!-- Recent Ingested BDCs Live Stream Ticker -->
                    <template x-if="ingestionData.active_batch?.recent_ingested_bdcs?.length > 0">
                        <div>
                            <div class="text-[10px] text-slate-400 uppercase tracking-wider font-mono font-bold mb-2">Flux en direct des derniers BDC ingérés dans la base :</div>
                            <div class="flex items-center gap-2 overflow-x-auto pb-1">
                                <template x-for="item in ingestionData.active_batch.recent_ingested_bdcs" :key="item.portal_id">
                                    <div class="bg-slate-950 border border-slate-800/90 px-3 py-2 rounded-xl text-xs flex-shrink-0 min-w-[220px]">
                                        <div class="flex items-center justify-between font-mono text-[10px] text-slate-400 mb-1">
                                            <span class="font-bold text-slate-200" x-text="'#' + item.portal_id"></span>
                                            <span class="text-emerald-400 font-bold" x-text="item.score + '%'"></span>
                                        </div>
                                        <div class="font-semibold text-slate-200 text-xs truncate max-w-[200px]" x-text="item.title"></div>
                                        <div class="text-[10px] text-slate-500 truncate" x-text="item.buyer"></div>
                                    </div>
                                </template>
                            </div>
                        </div>
                    </template>
                </div>

                <!-- 3. Quality of Data Score per Category Matrix -->
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                        <div>
                            <h3 class="text-base font-bold text-white mb-1">Qualité des Données Reçues par Catégorie</h3>
                            <p class="text-xs text-slate-400">Évaluation multi-critères : complétude des bordereaux, géocodage, délais et pièces jointes</p>
                        </div>
                        <div class="flex items-center gap-3">
                            <div class="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-right">
                                <span class="text-[10px] text-slate-400 block uppercase font-mono">Score Qualité Global</span>
                                <span class="text-sm font-black text-emerald-400 font-mono" x-text="ingestionData.quality.overall_score + ' / 100 • Grade ' + ingestionData.quality.quality_grade"></span>
                            </div>
                        </div>
                    </div>

                    <!-- Category Cards Grid -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                        <template x-for="cat in ingestionData.quality.categories" :key="cat.category">
                            <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 hover:border-slate-700 transition-all flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between mb-3">
                                        <div class="font-bold text-white text-sm" x-text="cat.label"></div>
                                        <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider font-mono border"
                                              :class="cat.badge"
                                              x-text="cat.status"></span>
                                    </div>

                                    <!-- Score Display & Progress Bar -->
                                    <div class="mb-4">
                                        <div class="flex items-baseline justify-between mb-1">
                                            <span class="text-xs text-slate-400">Score de Qualité</span>
                                            <span class="text-lg font-black text-emerald-400 font-mono" x-text="cat.score + '%'"></span>
                                        </div>
                                        <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                                            <div class="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all duration-1000"
                                                 :style="'width: ' + cat.score + '%'"></div>
                                        </div>
                                    </div>

                                    <!-- Breakdown Metrics -->
                                    <div class="space-y-2.5 text-xs">
                                        <div class="flex items-center justify-between text-slate-300">
                                            <span class="text-slate-400 flex items-center gap-1.5">
                                                <span>📋</span> Lignes Bordereau (BOM)
                                            </span>
                                            <span class="font-mono font-bold text-slate-200" x-text="cat.bom_completeness_pct + '%'"></span>
                                        </div>
                                        <div class="flex items-center justify-between text-slate-300">
                                            <span class="text-slate-400 flex items-center gap-1.5">
                                                <span>🏢</span> Normalisation Acheteurs
                                            </span>
                                            <span class="font-mono font-bold text-slate-200" x-text="cat.buyer_normalized_pct + '%'"></span>
                                        </div>
                                        <div class="flex items-center justify-between text-slate-300">
                                            <span class="text-slate-400 flex items-center gap-1.5">
                                                <span>⏰</span> Délais & Clôtures Valides
                                            </span>
                                            <span class="font-mono font-bold text-emerald-400" x-text="cat.deadline_valid_pct + '%'"></span>
                                        </div>
                                    </div>
                                </div>

                                <div class="mt-4 pt-3 border-t border-slate-900 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                                    <span>Volume analysé :</span>
                                    <span class="text-slate-300 font-bold" x-text="cat.tenders_count + ' consultations'"></span>
                                </div>
                            </div>
                        </template>
                    </div>
                </div>

                <!-- 4. Batches Ledger & History -->
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
                        <div>
                            <h3 class="text-base font-bold text-white mb-1">Registre des Lots d'Ingestion (Batch Ledger)</h3>
                            <p class="text-xs text-slate-400">Historique complet des sessions de collecte avec volume reçu et taux de succès</p>
                        </div>

                        <!-- Status Filter Buttons -->
                        <div class="flex flex-wrap items-center gap-1.5 text-xs font-semibold">
                            <button @click="batchFilter = 'all'" 
                                    :class="batchFilter === 'all' ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-white'"
                                    class="px-3 py-1.5 rounded-lg transition-colors">
                                Tous (<span x-text="ingestionData.batches_summary.total"></span>)
                            </button>
                            <button @click="batchFilter = 'completed'" 
                                    :class="batchFilter === 'completed' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-white'"
                                    class="px-3 py-1.5 rounded-lg transition-colors">
                                Succès (<span x-text="ingestionData.batches_summary.completed"></span>)
                            </button>
                            <button @click="batchFilter = 'in_progress'" 
                                    :class="batchFilter === 'in_progress' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'text-slate-400 hover:text-white'"
                                    class="px-3 py-1.5 rounded-lg transition-colors">
                                En cours (<span x-text="ingestionData.batches_summary.in_progress"></span>)
                            </button>
                            <button @click="batchFilter = 'missed'" 
                                    :class="batchFilter === 'missed' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-slate-400 hover:text-white'"
                                    class="px-3 py-1.5 rounded-lg transition-colors">
                                Manqués (<span x-text="ingestionData.batches_summary.missed"></span>)
                            </button>
                            <button @click="batchFilter = 'failed'" 
                                    :class="batchFilter === 'failed' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'text-slate-400 hover:text-white'"
                                    class="px-3 py-1.5 rounded-lg transition-colors">
                                Erreurs (<span x-text="ingestionData.batches_summary.failed"></span>)
                            </button>
                        </div>
                    </div>

                    <!-- Batches Table -->
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead>
                                <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[10px]">
                                    <th class="py-3 px-4">Lot ID</th>
                                    <th class="py-3 px-4">Déclencheur</th>
                                    <th class="py-3 px-4">Plage Identifiants BDC</th>
                                    <th class="py-3 px-4">Horodatage & Durée</th>
                                    <th class="py-3 px-4">Volume Reçu</th>
                                    <th class="py-3 px-4">Qualité</th>
                                    <th class="py-3 px-4">Statut</th>
                                    <th class="py-3 px-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800/60 font-mono">
                                <template x-for="b in filteredBatches" :key="b.batch_id">
                                    <tr class="hover:bg-slate-800/30 transition-colors">
                                        <td class="py-3 px-4 font-bold text-slate-200" x-text="b.batch_id"></td>
                                        <td class="py-3 px-4 font-sans">
                                            <span class="text-xs text-slate-300 font-semibold" x-text="b.trigger_label"></span>
                                            <div class="text-[10px] text-slate-500" x-text="b.created_by"></div>
                                        </td>
                                        <td class="py-3 px-4 font-sans">
                                            <div class="flex items-center gap-1.5">
                                                <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold border"
                                                      :class="b.first_bdc_id ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30' : 'bg-slate-900 text-slate-500 border-slate-800'"
                                                      x-text="b.bdc_range"></span>
                                            </div>
                                            <div class="text-[10px] text-slate-500 font-mono mt-0.5" x-show="b.first_bdc_id">
                                                Premier: #<span class="text-slate-300" x-text="b.first_bdc_id"></span> &bull; Dernier: #<span class="text-slate-300" x-text="b.last_bdc_id"></span>
                                            </div>
                                        </td>
                                        <td class="py-3 px-4">
                                            <div class="text-slate-300" x-text="b.started_at"></div>
                                            <div class="text-[10px] text-slate-500" x-text="b.duration_seconds > 0 ? (b.duration_seconds + ' s') : '—'"></div>
                                        </td>
                                        <td class="py-3 px-4 font-sans">
                                            <div class="text-slate-200 font-semibold">
                                                <span class="text-emerald-400 font-mono font-bold" x-text="b.tenders_ingested"></span> consultations
                                            </div>
                                            <div class="text-[10px] text-slate-500">
                                                <span x-text="b.cards_scraped"></span> cartes &bull; <span x-text="b.line_items_extracted"></span> articles
                                            </div>
                                        </td>
                                        <td class="py-3 px-4">
                                            <span class="font-bold"
                                                  :class="b.quality_score >= 95 ? 'text-emerald-400' : (b.quality_score > 0 ? 'text-amber-400' : 'text-slate-600')"
                                                  x-text="b.quality_score > 0 ? (b.quality_score + '%') : '—'"></span>
                                        </td>
                                        <td class="py-3 px-4 font-sans">
                                            <span class="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono border"
                                                  :class="{
                                                      'bg-emerald-500/20 text-emerald-400 border-emerald-500/30': b.status === 'completed',
                                                      'bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse': b.status === 'in_progress',
                                                      'bg-amber-500/20 text-amber-400 border-amber-500/30': b.status === 'missed',
                                                      'bg-rose-500/20 text-rose-400 border-rose-500/30': b.status === 'failed',
                                                      'bg-slate-800 text-slate-400 border-slate-700': b.status === 'pending'
                                                  }"
                                                  x-text="b.status === 'completed' ? 'Terminé' : (b.status === 'in_progress' ? 'En cours' : (b.status === 'missed' ? 'Manqué' : b.status))"></span>
                                        </td>
                                        <td class="py-3 px-4 text-right font-sans">
                                            <button x-show="b.status === 'missed' || b.status === 'failed'"
                                                    @click="retryBatch(b.batch_id)"
                                                    class="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-bold transition-colors">
                                                Relancer
                                            </button>
                                            <span x-show="b.status === 'completed'" class="text-xs text-slate-600">✓ Archivé</span>
                                        </td>
                                    </tr>
                                </template>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ========================================== -->
            <!-- MODULE 5: TEAM & RBAC MANAGEMENT           -->
            <!-- ========================================== -->
            <div x-show="activeModule === 'team'" x-cloak class="space-y-6">
                <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6 shadow-xl">
                    <h2 class="text-base font-bold text-white mb-1">Gestion d'Équipe & Matrice des Permissions (RBAC)</h2>
                    <p class="text-xs text-slate-400 mb-6">Contrôle granulaire des accès selon le rôle professionnel au sein de l'organisation</p>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead>
                                <tr class="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase font-semibold text-[10px]">
                                    <th class="py-3 px-4">Utilisateur</th>
                                    <th class="py-3 px-4">Titre Professionnel</th>
                                    <th class="py-3 px-4">Rôle</th>
                                    <th class="py-3 px-4">Périmètre & Permissions</th>
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

        <!-- 60-Second Decision Card Modal with Real Pricing & Bordereau Export -->
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
                <div class="p-6 overflow-y-auto space-y-5 flex-1 text-xs">
                    
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
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Compte à Rebours</span>
                            <span class="font-bold font-mono" :class="getCountdownUrgencyClass(activeTender?.deadline_at)" x-text="formatCountdown(activeTender?.deadline_at)"></span>
                        </div>
                        <div>
                            <span class="text-slate-500 text-[10px] block uppercase font-semibold">Prestation</span>
                            <span class="font-bold text-slate-200" x-text="activeTender?.prestation_type || 'Non spécifié'"></span>
                        </div>
                    </div>

                    <!-- Real Backend Pricing Corridor Tool (Analyst & Admin only) -->
                    <div x-show="hasPermission('tender:pricing_calculator')" class="bg-gradient-to-br from-slate-950 to-slate-900 p-5 rounded-2xl border border-emerald-500/20 shadow-lg space-y-3">
                        <div class="flex justify-between items-center">
                            <div>
                                <h4 class="font-bold text-white text-xs flex items-center gap-1.5">
                                    <span>💰</span> Simulateur Marge & Devis Moins-Disant (TGR Article 91)
                                </h4>
                                <p class="text-[10px] text-slate-400">Calcul en temps réel basé sur les adjudications historiques et le coût de revient</p>
                            </div>
                            <span class="font-mono font-bold text-emerald-400 text-sm" x-text="targetMarginPct + '% Marge Cible'"></span>
                        </div>

                        <!-- Slider -->
                        <div class="space-y-1">
                            <input type="range" min="15" max="50" step="1" x-model="targetMarginPct" @input="recalculatePricing()" class="w-full accent-emerald-500 cursor-pointer">
                            <div class="flex justify-between text-[10px] text-slate-500 font-mono">
                                <span>15% (Agressif)</span>
                                <span>30% (Standard Équilibré)</span>
                                <span>50% (Confortable)</span>
                            </div>
                        </div>

                        <!-- Pricing Breakdown -->
                        <div class="grid grid-cols-3 gap-3 pt-2 text-center font-mono">
                            <div class="bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                                <span class="text-[10px] text-slate-500 block uppercase">Coût Plancher HT</span>
                                <span class="text-sm font-bold text-slate-300" x-text="(pricingData?.base_cost_ht || 25000).toLocaleString('fr-FR') + ' DH'"></span>
                            </div>
                            <div class="bg-emerald-500/10 p-2.5 rounded-xl border border-emerald-500/30">
                                <span class="text-[10px] text-emerald-400 block uppercase font-bold">Devis Recommandé TTC</span>
                                <span class="text-sm font-black text-emerald-400" x-text="(calculatedQuoteTtc).toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></span>
                            </div>
                            <div class="bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                                <span class="text-[10px] text-slate-500 block uppercase">Marge Brute Prévue</span>
                                <span class="text-sm font-bold text-indigo-400" x-text="(calculatedGrossMargin).toLocaleString('fr-FR', {maximumFractionDigits: 0}) + ' DH'"></span>
                            </div>
                        </div>
                    </div>

                    <!-- Line Items Table -->
                    <div>
                        <div class="flex justify-between items-center mb-2">
                            <h4 class="font-bold text-white text-xs">
                                Articles au Devis & Spécifications (<span x-text="activeTender?.line_items?.length || 0"></span>)
                            </h4>
                            
                            <!-- One-Click Export to Official Bordereau des Prix CSV -->
                            <a :href="'/api/tenders/' + activeTender?.portal_id + '/export-bordereau'" target="_blank" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-emerald-400 hover:text-emerald-300 rounded-lg text-[11px] font-semibold border border-slate-700/80 transition-colors flex items-center gap-1.5">
                                <span>📥</span> Télécharger Bordereau Excel (CSV)
                            </a>
                        </div>

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
                <div class="bg-slate-950 border-t border-slate-800 p-4 flex flex-wrap justify-between items-center gap-3">
                    <div x-show="hasPermission('tender:action')" class="space-x-2">
                        <button @click="recordAction('shortlisted')" class="px-3.5 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 rounded-xl text-xs font-bold transition-colors">
                            ⭐ Retenir [S]
                        </button>
                        <button @click="recordAction('in_preparation')" class="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition-colors">
                            📝 En Chiffrage [Q]
                        </button>
                        <button @click="recordAction('rejected')" class="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition-colors">
                            ❌ Ignorer [X]
                        </button>
                    </div>

                    <a :href="activeTender?.portal_url" target="_blank" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-colors inline-flex items-center gap-1.5 ml-auto">
                        Portail Officiel TGR &rarr;
                    </a>
                </div>

            </div>
        </div>

        <!-- Authentication & Persona Switcher Modal -->
        <div x-show="authModalOpen" x-cloak class="fixed inset-0 z-50 overflow-y-auto bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div @click.away="authModalOpen = false" class="bg-slate-900 rounded-3xl shadow-2xl border border-slate-800 max-w-md w-full p-6 space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="font-bold text-white text-base">Profil & Contrôle d'Accès (RBAC)</h3>
                    <button @click="authModalOpen = false" class="text-slate-400 hover:text-white">&times;</button>
                </div>
                
                <p class="text-xs text-slate-400">Basculez instantanément de profil utilisateur pour tester les différentes vues professionnelles :</p>

                <div class="space-y-2 pt-2">
                    <button @click="switchRole('admin'); authModalOpen = false" class="w-full text-left p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 transition-colors flex items-center justify-between">
                        <div>
                            <div class="font-bold text-emerald-400 text-xs">👑 Hamza Senhaji (Fondateur / Admin)</div>
                            <div class="text-[10px] text-slate-400">Accès intégral : Feed, Alerte Art. 91, Télémétrie & Crawler Live</div>
                        </div>
                        <span class="text-xs">→</span>
                    </button>

                    <button @click="switchRole('analyst'); authModalOpen = false" class="w-full text-left p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 transition-colors flex items-center justify-between">
                        <div>
                            <div class="font-bold text-indigo-400 text-xs">📊 Yassine El Amrani (Ingénieur Chiffrage)</div>
                            <div class="text-[10px] text-slate-400">Accès Feed, Simulateur de Marge, Bordereau Excel & Historique</div>
                        </div>
                        <span class="text-xs">→</span>
                    </button>

                    <button @click="switchRole('viewer'); authModalOpen = false" class="w-full text-left p-3 rounded-xl bg-slate-950 hover:bg-slate-800 border border-slate-800 transition-colors flex items-center justify-between">
                        <div>
                            <div class="font-bold text-amber-400 text-xs">👁️ Sara Bennani (Responsable Commerciale)</div>
                            <div class="text-[10px] text-slate-400">Vue épurée : Tenders qualifiés GO (≥75%) & Fiche simplifiée</div>
                        </div>
                        <span class="text-xs">→</span>
                    </button>
                </div>
            </div>
        </div>

    </div>

    <script>
        function dashboardApp() {
            return {
                activeModule: 'feed',
                viewMode: window.innerWidth < 768 ? 'cards' : 'table',
                selectedProfile: 'cctv_security',
                minScore: 0,
                searchQuery: '',
                selectedRegion: 'all',
                selectedCategory: 'all',
                selectedUrgency: 'all',
                sortBy: 'score_desc',
                selectedIndex: 0,
                items: [],
                competitors: [],
                buyers: [],
                seasonality: null,
                teamUsers: [],
                toasts: [],
                loading: false,
                modalOpen: false,
                authModalOpen: false,
                activeTender: null,
                pricingData: null,
                targetMarginPct: 30,
                calculatedQuoteTtc: 0,
                calculatedGrossMargin: 0,
                crawlPagesInput: 1,
                nowTimestamp: Date.now(),
                selectedBatchDepth: 3,
                batchFilter: 'all',
                remediating: false,
                activePollingTimer: null,
                ingestionData: {
                    freshness: {
                        is_up_to_date: true,
                        minutes_since_sync: 8,
                        status_label: "À Jour (Synchronisé)",
                        status_badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
                        next_sync_in_minutes: 52,
                        last_sync_formatted: "Aujourd'hui à 18:45",
                        portal_health: "Optimal (HTTP 200 - F5 WAF Actif)",
                        active_portal_estimated: 150,
                        db_ingested_total: 89
                    },
                    quality: {
                        overall_score: 96.8,
                        quality_grade: "A+ (Haute Fidélité)",
                        categories: [
                            { category: "Fournitures", label: "Fournitures Générales & Matériel", score: 98.4, tenders_count: 42, bom_completeness_pct: 99.1, buyer_normalized_pct: 98.5, deadline_valid_pct: 100.0, status: "Excellent", badge: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" },
                            { category: "Travaux", label: "Travaux d'Aménagement & Installation", score: 94.8, tenders_count: 28, bom_completeness_pct: 92.4, buyer_normalized_pct: 96.0, deadline_valid_pct: 98.0, status: "Optimal", badge: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" },
                            { category: "Services", label: "Services & Prestations d'Études", score: 96.2, tenders_count: 19, bom_completeness_pct: 95.8, buyer_normalized_pct: 97.2, deadline_valid_pct: 99.0, status: "Optimal", badge: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" }
                        ],
                        total_articles_parsed: 642,
                        ocr_accuracy_pct: 97.8
                    },
                    batches_summary: { total: 6, completed: 5, in_progress: 0, failed: 0, pending: 0, missed: 1 },
                    batches: [],
                    diagnostic: {
                        health_status: "Besoin d'action",
                        issues_count: 2,
                        issues: [
                            { type: "missed_batch", severity: "medium", title: "1 lot manqué détecté lors du créneau nocturne", detail: "Un saut de créneau a été identifié suite à un timeout portail.", suggested_fix: "Exécuter une collecte de rattrapage sur les pages 1 à 3." },
                            { type: "opportunity_gap", severity: "low", title: "3 avis urgents (< 48h) requièrent un calcul de marge instantané", detail: "Des consultations prêtes au chiffrage attendent l'analyse commerciale.", suggested_fix: "Ouvrir le simulateur de prix et exporter le devis CSV." }
                        ],
                        recommended_action: {
                            title: "Rattraper le retard & Collecte Ciblée Immédiate",
                            action_id: "targeted_remediation",
                            pages_to_crawl: 3,
                            estimated_duration_seconds: 18,
                            rationale: "Ce rattrapage synchronisera les 150 derniers avis publiés, comblera le lot manqué et garantira une fraîcheur à 100% de la base.",
                            can_execute_now: true
                        }
                    }
                },

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
                    last_run_at: "Aujourd'hui 17:32",
                    last_duration_seconds: 20.4,
                    waf_status: 'Healthy (HTTP 200 - F5 Passed)'
                },

                init() {
                    // Restore persisted session from localStorage
                    const savedUser = localStorage.getItem('bergag_user');
                    if (savedUser) {
                        try { this.currentUser = JSON.parse(savedUser); } catch(e) {}
                    }

                    // Start ticking clock for 48h BDC countdown
                    setInterval(() => {
                        this.nowTimestamp = Date.now();
                    }, 1000);

                    this.fetchFeed();
                    if (this.currentUser.role === 'admin') {
                        this.fetchIngestionDashboard().then(() => {
                            if (this.ingestionData && this.ingestionData.active_batch) {
                                this.startActivePolling();
                            }
                        });
                    }
                },

                showToast(message, type = 'success') {
                    const id = Date.now();
                    this.toasts.push({ id, message, type });
                    setTimeout(() => this.removeToast(id), 3500);
                },

                removeToast(id) {
                    this.toasts = this.toasts.filter(t => t.id !== id);
                },

                get activeFilterChips() {
                    let chips = [];
                    if (this.searchQuery) chips.push({ key: 'search', label: 'Recherche: ' + this.searchQuery });
                    if (this.minScore > 0) chips.push({ key: 'minScore', label: 'Score ≥ ' + this.minScore + '%' });
                    if (this.selectedRegion !== 'all') chips.push({ key: 'region', label: 'Région: ' + this.selectedRegion });
                    if (this.selectedCategory !== 'all') chips.push({ key: 'category', label: 'Prestation: ' + this.selectedCategory });
                    if (this.selectedUrgency !== 'all') chips.push({ key: 'urgency', label: 'Délai: ' + this.selectedUrgency });
                    return chips;
                },

                removeFilterChip(key) {
                    if (key === 'search') this.searchQuery = '';
                    if (key === 'minScore') this.minScore = 0;
                    if (key === 'region') this.selectedRegion = 'all';
                    if (key === 'category') this.selectedCategory = 'all';
                    if (key === 'urgency') this.selectedUrgency = 'all';
                    this.fetchFeed();
                    if (this.currentUser.role === 'admin') {
                        this.fetchIngestionDashboard().then(() => {
                            if (this.ingestionData && this.ingestionData.active_batch) {
                                this.startActivePolling();
                            }
                        });
                    }
                },

                hasPermission(permission) {
                    return this.currentUser.permissions && this.currentUser.permissions.includes(permission);
                },

                formatCountdown(deadlineStr) {
                    if (!deadlineStr) return 'N/A';
                    // Parse date in format DD/MM/YYYY HH:MM or ISO
                    let deadlineTime;
                    if (deadlineStr.includes('/')) {
                        const [datePart, timePart] = deadlineStr.split(' ');
                        const [d, m, y] = datePart.split('/');
                        deadlineTime = new Date(`${y}-${m}-${d}T${timePart}:00`).getTime();
                    } else {
                        deadlineTime = new Date(deadlineStr).getTime();
                    }

                    const diffMs = deadlineTime - this.nowTimestamp;
                    if (diffMs <= 0) return 'Expiré (Clôturé)';

                    const totalHours = Math.floor(diffMs / (1000 * 60 * 60));
                    const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                    const secs = Math.floor((diffMs % (1000 * 60)) / 1000);

                    if (totalHours < 24) {
                        return `🚨 ${totalHours}h ${mins}m ${secs}s`;
                    } else if (totalHours < 48) {
                        return `⏳ ${totalHours}h ${mins}m`;
                    } else {
                        const days = Math.floor(totalHours / 24);
                        return `📅 ${days}j ${totalHours % 24}h`;
                    }
                },

                getCountdownUrgencyClass(deadlineStr) {
                    if (!deadlineStr) return 'text-slate-400';
                    const countdown = this.formatCountdown(deadlineStr);
                    if (countdown.startsWith('🚨')) return 'text-rose-400 font-black animate-pulse';
                    if (countdown.startsWith('⏳')) return 'text-amber-400 font-bold';
                    return 'text-slate-400 font-semibold';
                },

                handleGlobalKeydown(e) {
                    // Do not interfere if user is typing in an input
                    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

                    if (e.key === 'j' || e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (this.selectedIndex < this.items.length - 1) this.selectedIndex++;
                    } else if (e.key === 'k' || e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (this.selectedIndex > 0) this.selectedIndex--;
                    } else if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        if (this.items[this.selectedIndex]) {
                            this.openModal(this.items[this.selectedIndex].portal_id);
                        }
                    } else if (e.key === 's' || e.key === 'S') {
                        if (this.modalOpen) this.recordAction('shortlisted');
                    } else if (e.key === 'q' || e.key === 'Q') {
                        if (this.modalOpen) this.recordAction('in_preparation');
                    } else if (e.key === 'x' || e.key === 'X') {
                        if (this.modalOpen) this.recordAction('rejected');
                    } else if (e.key === 'Escape') {
                        this.modalOpen = false;
                        this.authModalOpen = false;
                    }
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
                        localStorage.setItem('bergag_user', JSON.stringify(data.user));
                        localStorage.setItem('bergag_token', data.token);

                        this.showToast(`Bascule vers le rôle : ${data.user.title}`, 'info');

                        if (this.activeModule === 'crawler' && !this.hasPermission('crawler:telemetry')) {
                            this.activeModule = 'feed';
                        }
                        if (this.activeModule === 'team' && !this.hasPermission('users:manage')) {
                            this.activeModule = 'feed';
                        }
                        this.fetchFeed();
                    if (this.currentUser.role === 'admin') {
                        this.fetchIngestionDashboard().then(() => {
                            if (this.ingestionData && this.ingestionData.active_batch) {
                                this.startActivePolling();
                            }
                        });
                    }
                    } catch (e) {
                        console.error('Error switching role:', e);
                    }
                },

                async fetchFeed() {
                    this.loading = true;
                    try {
                        let url = `/api/feed?profile_name=${this.selectedProfile}&min_score=${this.minScore}&role=${this.currentUser.role}&sort_by=${this.sortBy}`;
                        if (this.searchQuery) url += `&search=${encodeURIComponent(this.searchQuery)}`;
                        if (this.selectedRegion !== 'all') url += `&region=${encodeURIComponent(this.selectedRegion)}`;
                        if (this.selectedCategory !== 'all') url += `&category=${encodeURIComponent(this.selectedCategory)}`;
                        if (this.selectedUrgency !== 'all') url += `&urgency=${encodeURIComponent(this.selectedUrgency)}`;
                        
                        const res = await fetch(url);
                        this.items = await res.json();
                        this.selectedIndex = 0;
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
                    this.sortBy = 'score_desc';
                    this.fetchFeed();
                    if (this.currentUser.role === 'admin') {
                        this.fetchIngestionDashboard().then(() => {
                            if (this.ingestionData && this.ingestionData.active_batch) {
                                this.startActivePolling();
                            }
                        });
                    }
                    this.showToast('Filtres réinitialisés', 'info');
                },

                async renderRadarCharts() {
                    await this.fetchRadarData();
                    this.$nextTick(() => {
                        this.initSeasonalityChart();
                        this.initCompetitorsChart();
                    });
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

                initSeasonalityChart() {
                    const ctx = document.getElementById('seasonalityChart');
                    if (!ctx) return;
                    if (window.seasonalityChartInstance) window.seasonalityChartInstance.destroy();

                    const months = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];
                    const dataValues = [12, 14, 18, 15, 16, 20, 19, 14, 22, 48, 65, 84]; // Representative procurement spend volume

                    window.seasonalityChartInstance = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: months,
                            datasets: [{
                                label: 'Volume Marchés Passés (TGR)',
                                data: dataValues,
                                backgroundColor: dataValues.map((v, i) => i >= 9 ? 'rgba(16, 185, 129, 0.85)' : 'rgba(51, 65, 85, 0.7)'),
                                borderColor: dataValues.map((v, i) => i >= 9 ? '#10b981' : '#475569'),
                                borderWidth: 1,
                                borderRadius: 6
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    callbacks: {
                                        afterLabel: (ctx) => ctx.dataIndex >= 9 ? '🔥 Période T4 d\\'accélération budgétaire' : ''
                                    }
                                }
                            },
                            scales: {
                                y: { grid: { color: 'rgba(51, 65, 85, 0.3)' }, ticks: { color: '#94a3b8' } },
                                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
                            }
                        }
                    });
                },

                initCompetitorsChart() {
                    const ctx = document.getElementById('competitorsChart');
                    if (!ctx) return;
                    if (window.competitorsChartInstance) window.competitorsChartInstance.destroy();

                    const top8 = (this.competitors || []).slice(0, 6);
                    const labels = top8.map(c => c.winner_name.length > 20 ? c.winner_name.substring(0, 18) + '...' : c.winner_name);
                    const amounts = top8.map(c => c.total_awarded_mad);

                    window.competitorsChartInstance = new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: labels.length ? labels : ['Fournisseur A', 'Fournisseur B', 'Fournisseur C'],
                            datasets: [{
                                label: 'Total Remporté (MAD TTC)',
                                data: amounts.length ? amounts : [4500000, 3200000, 2100000],
                                backgroundColor: 'rgba(99, 102, 241, 0.8)',
                                borderColor: '#6366f1',
                                borderWidth: 1,
                                borderRadius: 6
                            }]
                        },
                        options: {
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                x: { grid: { color: 'rgba(51, 65, 85, 0.3)' }, ticks: { color: '#94a3b8' } },
                                y: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } }
                            }
                        }
                    });
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
                        this.showToast(data.message || 'Collecte live démarrée !', 'success');
                        this.crawlerTelemetry.status = 'crawling';
                        setTimeout(() => this.fetchCrawlerStatus(), 3000);
                    } catch (e) {
                        this.showToast('Erreur: ' + e, 'error');
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
                        
                        // Fetch real pricing intelligence from backend
                        const pricingRes = await fetch(`/api/tenders/${portalId}/pricing?target_margin_pct=${this.targetMarginPct}`);
                        if (pricingRes.ok) {
                            this.pricingData = await pricingRes.json();
                            this.recalculatePricing();
                        }

                        this.modalOpen = true;
                    } catch (e) {
                        this.showToast('Erreur lors du chargement : ' + e, 'error');
                    }
                },

                recalculatePricing() {
                    const baseCost = this.pricingData?.base_cost_ht || 25000;
                    const marginMultiplier = 1 + (this.targetMarginPct / 100);
                    const tvaMultiplier = 1.20; // 20% TVA Maroc
                    this.calculatedQuoteTtc = (baseCost + 2500) * marginMultiplier * tvaMultiplier;
                    this.calculatedGrossMargin = (baseCost + 2500) * (this.targetMarginPct / 100) * tvaMultiplier;
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
                                bid_amount_mad: this.calculatedQuoteTtc
                            })
                        });
                        const actionLabel = actionName === 'shortlisted' ? 'Retenu ⭐' : (actionName === 'in_preparation' ? 'En chiffrage 📝' : 'Ignoré ❌');
                        this.showToast(`Statut mis à jour : ${actionLabel} (#${this.activeTender.portal_id})`, 'success');
                        this.modalOpen = false;
                    } catch (e) {
                        this.showToast('Erreur: ' + e, 'error');
                    }
                },

                async fetchIngestionDashboard() {
                    try {
                        const res = await fetch('/api/admin/ingestion/dashboard');
                        if (res.ok) {
                            this.ingestionData = await res.json();
                        }
                    } catch (e) {
                        console.error('Error fetching ingestion dashboard:', e);
                    }
                },

                startActivePolling() {
                    if (this.activePollingTimer) return;
                    this.activePollingTimer = setInterval(async () => {
                        await this.fetchIngestionDashboard();
                        if (!this.ingestionData || !this.ingestionData.active_batch) {
                            this.stopActivePolling();
                            this.remediating = false;
                            this.showToast("Lot d'ingestion finalisé ! Données à jour.", 'success');
                            this.fetchFeed();
                        }
                    }, 1200);
                },

                stopActivePolling() {
                    if (this.activePollingTimer) {
                        clearInterval(this.activePollingTimer);
                        this.activePollingTimer = null;
                    }
                },

                async runRemediation(pages = null) {
                    const pagesToRun = pages || this.selectedBatchDepth || 3;
                    this.remediating = true;
                    this.showToast(`Initialisation du plan d'ingestion (${pagesToRun} pages / ${pagesToRun * 50} BDC)...`, 'info');
                    try {
                        const res = await fetch('/api/admin/ingestion/remediate', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ pages: parseInt(pagesToRun), reason: 'Rattrapage diagnostique direct' })
                        });
                        const data = await res.json();
                        if (res.ok) {
                            this.showToast(data.message || '⚡ Rattrapage des lots lancé !', 'success');
                            await this.fetchIngestionDashboard();
                            this.startActivePolling();
                        } else {
                            this.remediating = false;
                            this.showToast(data.detail || 'Erreur lors du rattrapage', 'error');
                        }
                    } catch (e) {
                        this.remediating = false;
                        this.showToast('Erreur: ' + e, 'error');
                    }
                },

                async triggerCustomBatch(pages) {
                    this.remediating = true;
                    this.showToast(`Initialisation du lot (${pages} pages / ${pages * 50} BDC)...`, 'info');
                    try {
                        const res = await fetch('/api/admin/ingestion/batches/trigger', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ pages: parseInt(pages), send_emails: false })
                        });
                        const data = await res.json();
                        if (res.ok) {
                            this.showToast(data.message, 'success');
                            await this.fetchIngestionDashboard();
                            this.startActivePolling();
                        } else {
                            this.remediating = false;
                            this.showToast(data.detail, 'error');
                        }
                    } catch (e) {
                        this.remediating = false;
                        this.showToast('Erreur: ' + e, 'error');
                    }
                },

                async retryBatch(batchId) {
                    this.remediating = true;
                    this.showToast(`Relance du lot ${batchId}...`, 'info');
                    try {
                        const res = await fetch(`/api/admin/ingestion/batches/${batchId}/retry`, {
                            method: 'POST'
                        });
                        const data = await res.json();
                        if (res.ok) {
                            this.showToast(data.message, 'success');
                            await this.fetchIngestionDashboard();
                            this.startActivePolling();
                        } else {
                            this.remediating = false;
                            this.showToast(data.detail, 'error');
                        }
                    } catch (e) {
                        this.remediating = false;
                        this.showToast('Erreur: ' + e, 'error');
                    }
                },

                get filteredBatches() {
                    if (!this.ingestionData || !this.ingestionData.batches) return [];
                    if (this.batchFilter === 'all') return this.ingestionData.batches;
                    return this.ingestionData.batches.filter(b => b.status === this.batchFilter);
                }
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the single-page responsive procurement dashboard with RBAC and Chart.js"""
    return HTMLResponse(content=HTML_DASHBOARD)
