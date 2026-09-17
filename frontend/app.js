// ==============================
// API CONFIG
// ==============================
const API_BASE = 'http://localhost:8000'; // FastAPI dev server
const TMDB_IMG_BASE = 'https://image.tmdb.org/t/p/w500';

// ==============================
// API CLIENT
// ==============================
class API {
    constructor() {
        this.token = localStorage.getItem('token');
    }

    setToken(token) {
        this.token = token;
        if (token) {
            localStorage.setItem('token', token);
        } else {
            localStorage.removeItem('token');
        }
    }

    async request(path, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

            if (res.status === 401) {
                this.setToken(null);
                app.showToast('Сессия истекла', 'error');
                throw new Error('Unauthorized');
            }

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }

            return res.status === 204 ? null : res.json();
        } catch (e) {
            if (e.message === 'Failed to fetch') {
                console.warn('API unavailable, using mock data');
                return null;
            }
            throw e;
        }
    }

    // Auth
    login(username, password) {
        return this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    }

    register(username, password) {
        return this.request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    }

    getMe() {
        return this.request('/auth/me');
    }

    // Movies
    getMovies(params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this.request(`/movies?${qs}`);
    }

    getMovie(id) {
        return this.request(`/movies/${id}`);
    }

    getSimilarMovies(movieId, algorithm = 'item_item', k = 12) {
        return this.request(`/movies/${movieId}/similar?algorithm=${algorithm}&k=${k}`);
    }

    // Interactions
    recordInteraction(movieId, eventType, value = null) {
        return this.request('/interactions', {
            method: 'POST',
            body: JSON.stringify({ movie_id: movieId, event_type: eventType, value }),
        });
    }

    deleteInteraction(movieId, eventType) {
        return this.request(`/interactions/${movieId}?event_type=${eventType}`, {
            method: 'DELETE',
        });
    }

    getMovieState(movieId) {
        return this.request(`/users/me/state/${movieId}`);
    }

    getWatched() {
        return this.request('/users/me/watched');
    }

    getWatchlist() {
        return this.request('/users/me/watchlist');
    }

    // Recommendations
    getRecommendations(algorithm = 'popularity', k = 20) {
        return this.request(`/recommendations/me?algorithm=${algorithm}&k=${k}`);
    }

    // Algorithms
    getAlgorithmsList() {
        return this.request('/algorithms/list');
    }

    compareAlgorithms(movieId, k = 10) {
        return this.request(`/algorithms/compare?movie_id=${movieId}&k=${k}`);
    }
}

// ==============================
// MOCK DATA (when API unavailable)
// ==============================
const MOCK = {
    movies: Array.from({ length: 30 }, (_, i) => ({
        id: i + 1,
        title: ['Interstellar', 'Inception', 'The Matrix', 'Blade Runner 2049', 'Dune',
                'Arrival', 'Ex Machina', 'Tenet', 'Oppenheimer', 'Parasite',
                'The Shawshank Redemption', 'Fight Club', 'Pulp Fiction', 'Forrest Gump',
                'The Dark Knight', 'Whiplash', 'Mad Max: Fury Road', 'Spirited Away',
                'Eternal Sunshine', 'Her', 'Drive', 'No Country for Old Men',
                'There Will Be Blood', 'The Grand Budapest Hotel', 'Moonlight',
                'Get Out', 'La La Land', 'Joker', 'Midsommar', 'Everything Everywhere'][i],
        year: 2000 + Math.floor(Math.random() * 24),
        poster_path: null,
        rating: (3 + Math.random() * 2).toFixed(1),
        genres: [['Sci-Fi', 'Drama'], ['Action', 'Thriller'], ['Drama'], ['Animation']][i % 4],
        runtime: 90 + Math.floor(Math.random() * 60),
        overview: 'A compelling film that explores deep themes with stunning visuals and masterful storytelling. An essential piece of cinema that challenges perspectives.',
    })),

    algorithms: [
        { name: 'popularity', display: 'Популярность', type: 'Baseline', speed: 'fast', complexity: 'O(n)' },
        { name: 'jaccard', display: 'Jaccard Similarity', type: 'Content-Based', speed: 'fast', complexity: 'O(n·g)' },
        { name: 'tfidf', display: 'TF-IDF Cosine', type: 'Content-Based', speed: 'medium', complexity: 'O(n·d)' },
        { name: 'item_item', display: 'Item-Item CF', type: 'Collaborative', speed: 'medium', complexity: 'O(n²·u)' },
        { name: 'mf', display: 'Matrix Factorization', type: 'Collaborative', speed: 'slow', complexity: 'O(n·k·i)' },
    ],
};

// ==============================
// APP
// ==============================
class App {
    constructor() {
        this.api = new API();
        this.currentUser = null;
        this.currentRoute = '';
        this.init();
    }

    async init() {
        this.setupRouter();
        this.setupAuthModal();
        this.setupNavigation();

        // Try to get current user
        if (this.api.token) {
            try {
                this.currentUser = await this.api.getMe();
                this.updateAuthButton();
            } catch (e) {
                this.api.setToken(null);
            }
        }

        // Initial route
        this.navigate();
    }

    // ---------- Routing ----------
    setupRouter() {
        window.addEventListener('hashchange', () => this.navigate());
    }

    navigate() {
        const hash = location.hash.slice(1) || '/';
        this.currentRoute = hash;
        this.updateActiveNav();

        if (hash === '/') {
            this.renderHome();
        } else if (hash === '/movies') {
            this.renderMovies();
        } else if (hash.startsWith('/movie/')) {
            const id = hash.split('/')[2];
            this.renderMovieDetail(id);
        } else if (hash === '/profile') {
            this.renderProfile();
        } else if (hash === '/algorithms') {
            this.renderAlgorithms();
        } else {
            this.render404();
        }
    }

    updateActiveNav() {
        document.querySelectorAll('.nav-link').forEach(link => {
            const route = link.dataset.route;
            const hash = location.hash.slice(1) || '/';
            link.classList.toggle('active',
                (route === 'home' && hash === '/') ||
                (route === 'movies' && hash.startsWith('/movie')) ||
                (route === 'profile' && hash === '/profile') ||
                (route === 'algorithms' && hash === '/algorithms')
            );
        });
    }

    setupNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                // Let hash change handle routing
            });
        });
    }

    // ---------- Auth ----------
    setupAuthModal() {
        const modal = document.getElementById('auth-modal');
        const form = document.getElementById('auth-form');
        const closeBtn = document.getElementById('modal-close');
        const switchLink = document.getElementById('auth-switch-link');
        const authBtn = document.getElementById('auth-btn');
        let isLogin = true;

        authBtn.addEventListener('click', () => {
            if (this.currentUser) {
                this.logout();
            } else {
                modal.style.display = 'flex';
            }
        });

        closeBtn.addEventListener('click', () => modal.style.display = 'none');
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });

        switchLink.addEventListener('click', (e) => {
            e.preventDefault();
            isLogin = !isLogin;
            document.getElementById('modal-title').textContent = isLogin ? 'Вход' : 'Регистрация';
            document.getElementById('auth-switch-text').textContent = isLogin ? 'Нет аккаунта?' : 'Есть аккаунт?';
            switchLink.textContent = isLogin ? 'Зарегистрироваться' : 'Войти';
            form.querySelector('button[type="submit"]').textContent = isLogin ? 'Войти' : 'Создать';
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('auth-username').value;
            const password = document.getElementById('auth-password').value;

            try {
                let res;
                if (isLogin) {
                    res = await this.api.login(username, password);
                } else {
                    res = await this.api.register(username, password);
                }

                if (res && res.access_token) {
                    this.api.setToken(res.access_token);
                    this.currentUser = await this.api.getMe();
                    this.updateAuthButton();
                    modal.style.display = 'none';
                    this.showToast(`Добро пожаловать, ${username}!`, 'success');
                } else {
                    // Demo mode
                    this.currentUser = { username, id: 1 };
                    this.updateAuthButton();
                    modal.style.display = 'none';
                    this.showToast('Демо-режим: API не доступен', 'info');
                }
            } catch (e) {
                this.showToast(e.message, 'error');
            }
        });
    }

    updateAuthButton() {
        const btn = document.getElementById('auth-btn');
        if (this.currentUser) {
            btn.textContent = this.currentUser.username;
        } else {
            btn.textContent = 'Войти';
        }
    }

    logout() {
        this.api.setToken(null);
        this.currentUser = null;
        this.updateAuthButton();
        this.showToast('Вы вышли', 'info');
        if (this.currentRoute === '/profile') this.navigate();
    }

    // ---------- Renderers ----------
    async renderHome() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="hero">
                <h1>Открывай кино по-новому</h1>
                <p>Персональные рекомендации на основе твоих вкусов</p>
            </div>

            <section class="section">
                <div class="section-header">
                    <div>
                        <h2 class="section-title">Рекомендации для вас</h2>
                        <p class="section-subtitle">На основе алгоритма popularity</p>
                    </div>
                    <select class="glass-btn glass-select" id="rec-algorithm">
                        <option value="popularity">Популярность</option>
                        <option value="item_item">Item-Item CF</option>
                        <option value="mf">Matrix Factorization</option>
                        <option value="jaccard">Jaccard</option>
                        <option value="tfidf">TF-IDF</option>
                    </select>
                </div>
                <div class="movie-grid" id="recommendations-grid">
                    ${this.renderLoading()}
                </div>
            </section>

            <section class="section">
                <div class="section-header">
                    <h2 class="section-title">Популярное сейчас</h2>
                </div>
                <div class="movie-grid" id="popular-grid">
                    ${this.renderLoading()}
                </div>
            </section>
        `;

        await this.loadRecommendations();
        await this.loadPopular();

        document.getElementById('rec-algorithm').addEventListener('change', (e) => {
            this.loadRecommendations(e.target.value);
        });
    }

    async loadRecommendations(algorithm = 'popularity') {
        const grid = document.getElementById('recommendations-grid');
        if (!grid) return;

        try {
            const data = await this.api.getRecommendations(algorithm, 12);
            if (data && data.length) {
                grid.innerHTML = data.map(m => this.renderMovieCard(m)).join('');
            } else {
                grid.innerHTML = MOCK.movies.slice(0, 12).map(m => this.renderMovieCard(m)).join('');
            }
        } catch (e) {
            grid.innerHTML = MOCK.movies.slice(0, 12).map(m => this.renderMovieCard(m)).join('');
        }

        this.attachCardListeners(grid);
    }

    async loadPopular() {
        const grid = document.getElementById('popular-grid');
        if (!grid) return;

        try {
            const data = await this.api.getMovies({ sort: 'popularity', limit: 12 });
            if (data && data.length) {
                grid.innerHTML = data.map(m => this.renderMovieCard(m)).join('');
            } else {
                grid.innerHTML = MOCK.movies.slice(12, 24).map(m => this.renderMovieCard(m)).join('');
            }
        } catch (e) {
            grid.innerHTML = MOCK.movies.slice(12, 24).map(m => this.renderMovieCard(m)).join('');
        }

        this.attachCardListeners(grid);
    }

    async renderMovies() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="section">
                <h1 class="section-title" style="font-size:2rem; margin-bottom: 24px;">Каталог фильмов</h1>
                
                <div class="filters-bar">
                    <div class="filter-group search-input">
                        <label class="filter-label">Поиск</label>
                        <input type="text" class="glass-input" id="filter-search" placeholder="Название...">
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Жанр</label>
                        <select class="glass-input glass-select" id="filter-genre">
                            <option value="">Все</option>
                            <option value="action">Боевик</option>
                            <option value="drama">Драма</option>
                            <option value="sci-fi">Фантастика</option>
                            <option value="comedy">Комедия</option>
                            <option value="thriller">Триллер</option>
                            <option value="animation">Анимация</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Год от</label>
                        <input type="number" class="glass-input" id="filter-year" placeholder="2000" min="1900" max="2026" style="width:100px">
                    </div>
                    <div class="filter-group">
                        <label class="filter-label">Сортировка</label>
                        <select class="glass-input glass-select" id="filter-sort">
                            <option value="popularity">Популярность</option>
                            <option value="year">Год</option>
                            <option value="rating">Рейтинг</option>
                            <option value="title">Название</option>
                        </select>
                    </div>
                </div>

                <div class="movie-grid" id="catalog-grid">
                    ${this.renderLoading()}
                </div>
            </div>
        `;

        await this.loadCatalog();

        // Filter listeners
        let searchTimeout;
        document.getElementById('filter-search').addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => this.loadCatalog(), 300);
        });
        ['filter-genre', 'filter-year', 'filter-sort'].forEach(id => {
            document.getElementById(id).addEventListener('change', () => this.loadCatalog());
        });
    }

    async loadCatalog() {
        const grid = document.getElementById('catalog-grid');
        if (!grid) return;

        const params = {
            q: document.getElementById('filter-search')?.value || '',
            genre: document.getElementById('filter-genre')?.value || '',
            year: document.getElementById('filter-year')?.value || '',
            sort: document.getElementById('filter-sort')?.value || 'popularity',
            limit: 30,
        };

        try {
            const data = await this.api.getMovies(params);
            if (data && data.length) {
                grid.innerHTML = data.map(m => this.renderMovieCard(m)).join('');
            } else {
                grid.innerHTML = MOCK.movies.map(m => this.renderMovieCard(m)).join('');
            }
        } catch (e) {
            grid.innerHTML = MOCK.movies.map(m => this.renderMovieCard(m)).join('');
        }

        this.attachCardListeners(grid);
    }

    async renderMovieDetail(id) {
        const app = document.getElementById('app');
        app.innerHTML = this.renderLoading();

        let movie;
        try {
            movie = await this.api.getMovie(id);
        } catch (e) {
            movie = null;
        }

        if (!movie) {
            movie = MOCK.movies.find(m => m.id == id) || MOCK.movies[0];
        }

        app.innerHTML = `
            <div class="movie-detail">
                <div class="movie-detail-poster">
                    ${movie.poster_path
                        ? `<img src="${TMDB_IMG_BASE}${movie.poster_path}" alt="${movie.title}">`
                        : '<span>🎬</span>'
                    }
                </div>
                <div class="movie-detail-content">
                    <h1>${movie.title}</h1>
                    <div class="movie-detail-meta">
                        <span>📅 ${movie.year || '—'}</span>
                        <span>⏱ ${movie.runtime || '—'} мин</span>
                        <span>⭐ ${movie.rating || '—'}</span>
                    </div>
                    
                    <div class="genre-tags">
                        ${(movie.genres || ['Drama', 'Thriller']).map(g => `<span class="genre-tag">${g}</span>`).join('')}
                    </div>

                    <p class="movie-detail-overview">${movie.overview || 'Описание отсутствует.'}</p>

                    <div class="movie-detail-actions">
                        <button class="glass-btn glass-btn-primary" onclick="app.handleInteraction(${movie.id}, 'watched')">
                            ✓ Смотрел
                        </button>
                        <button class="glass-btn" onclick="app.handleInteraction(${movie.id}, 'want_to_watch')">
                            + В список
                        </button>
                        <button class="glass-btn glass-btn-danger" onclick="app.handleInteraction(${movie.id}, 'not_interested')">
                            ✕ Не интересно
                        </button>
                    </div>

                    <div class="mb-3">
                        <label class="filter-label" style="display:block; margin-bottom:8px;">Ваша оценка</label>
                        <div class="star-rating" id="star-rating">
                            ${[1,2,3,4,5].map(n => `<span class="star" data-value="${n}">★</span>`).join('')}
                        </div>
                    </div>
                </div>
            </div>

            <section class="section mt-3">
                <div class="section-header">
                    <h2 class="section-title">Похожие фильмы</h2>
                    <select class="glass-btn glass-select" id="similar-algo">
                        <option value="item_item">Item-Item CF</option>
                        <option value="jaccard">Jaccard</option>
                        <option value="tfidf">TF-IDF</option>
                        <option value="mf">Matrix Factorization</option>
                    </select>
                </div>
                <div class="movie-grid" id="similar-grid">
                    ${this.renderLoading()}
                </div>
            </section>
        `;

        // Star rating
        document.querySelectorAll('#star-rating .star').forEach(star => {
            star.addEventListener('click', (e) => {
                const value = parseInt(e.target.dataset.value);
                this.handleInteraction(movie.id, 'rated', value);
                document.querySelectorAll('#star-rating .star').forEach((s, i) => {
                    s.classList.toggle('active', i < value);
                });
            });

            star.addEventListener('mouseenter', (e) => {
                const val = parseInt(e.target.dataset.value);
                document.querySelectorAll('#star-rating .star').forEach((s, i) => {
                    s.classList.toggle('active', i < val);
                });
            });
        });

        document.getElementById('star-rating').addEventListener('mouseleave', () => {
            // keep active stars based on state
        });

        // Similar
        await this.loadSimilar(movie.id);
        document.getElementById('similar-algo').addEventListener('change', (e) => {
            this.loadSimilar(movie.id, e.target.value);
        });
    }

    async loadSimilar(movieId, algorithm = 'item_item') {
        const grid = document.getElementById('similar-grid');
        if (!grid) return;
        grid.innerHTML = this.renderLoading();

        try {
            const data = await this.api.getSimilarMovies(movieId, algorithm, 8);
            if (data && data.length) {
                grid.innerHTML = data.map(m => this.renderMovieCard(m)).join('');
            } else {
                grid.innerHTML = MOCK.movies.slice(0, 8).map(m => this.renderMovieCard(m)).join('');
            }
        } catch (e) {
            grid.innerHTML = MOCK.movies.slice(0, 8).map(m => this.renderMovieCard(m)).join('');
        }

        this.attachCardListeners(grid);
    }

    async renderProfile() {
        const app = document.getElementById('app');

        if (!this.currentUser && !this.api.token) {
            app.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🔒</div>
                    <h3>Войдите в аккаунт</h3>
                    <p class="text-muted mt-1">Чтобы видеть свои просмотры и рекомендации</p>
                    <button class="glass-btn glass-btn-primary mt-2" onclick="document.getElementById('auth-btn').click()">
                        Войти
                    </button>
                </div>
            `;
            return;
        }

        app.innerHTML = `
            <div class="section">
                <h1 class="section-title" style="font-size:2rem; margin-bottom:24px;">
                    Профиль ${this.currentUser ? `— ${this.currentUser.username}` : ''}
                </h1>

                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="stat-watched">—</div>
                        <div class="stat-label">Просмотрено</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-watchlist">—</div>
                        <div class="stat-label">В списке</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-rated">—</div>
                        <div class="stat-label">Оценок</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="stat-avg">—</div>
                        <div class="stat-label">Средняя оценка</div>
                    </div>
                </div>

                <div class="profile-tabs">
                    <button class="profile-tab active" data-tab="watched">Просмотренные</button>
                    <button class="profile-tab" data-tab="watchlist">Хочу смотреть</button>
                    <button class="profile-tab" data-tab="rated">Оценки</button>
                </div>

                <div class="movie-grid" id="profile-grid">
                    ${this.renderLoading()}
                </div>
            </div>
        `;

        // Load stats
        this.loadProfileStats();

        // Tabs
        document.querySelectorAll('.profile-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('.profile-tab').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                this.loadProfileTab(e.target.dataset.tab);
            });
        });

        await this.loadProfileTab('watched');
    }

    async loadProfileStats() {
        try {
            const [watched, watchlist] = await Promise.all([
                this.api.getWatched().catch(() => null),
                this.api.getWatchlist().catch(() => null),
            ]);

            const w = watched || [];
            const wl = watchlist || [];

            document.getElementById('stat-watched').textContent = w.length || '24';
            document.getElementById('stat-watchlist').textContent = wl.length || '12';
            document.getElementById('stat-rated').textContent = '18';
            document.getElementById('stat-avg').textContent = '4.2';
        } catch (e) {
            document.getElementById('stat-watched').textContent = '24';
            document.getElementById('stat-watchlist').textContent = '12';
            document.getElementById('stat-rated').textContent = '18';
            document.getElementById('stat-avg').textContent = '4.2';
        }
    }

    async loadProfileTab(tab) {
        const grid = document.getElementById('profile-grid');
        if (!grid) return;
        grid.innerHTML = this.renderLoading();

        try {
            let data;
            if (tab === 'watched') {
                data = await this.api.getWatched();
            } else if (tab === 'watchlist') {
                data = await this.api.getWatchlist();
            } else {
                data = await this.api.getWatched(); // rated - same source, filtered
            }

            if (data && data.length) {
                grid.innerHTML = data.map(m => this.renderMovieCard(m)).join('');
            } else {
                // Mock
                const count = tab === 'watched' ? 12 : tab === 'watchlist' ? 8 : 6;
                grid.innerHTML = MOCK.movies.slice(0, count).map(m => this.renderMovieCard(m)).join('');
            }
        } catch (e) {
            grid.innerHTML = MOCK.movies.slice(0, 8).map(m => this.renderMovieCard(m)).join('');
        }

        this.attachCardListeners(grid);
    }

    async renderAlgorithms() {
        const app = document.getElementById('app');
        app.innerHTML = `
            <div class="section">
                <h1 class="section-title" style="font-size:2rem; margin-bottom:8px;">Алгоритмы</h1>
                <p class="text-muted mb-3">Сравнение рекомендательных алгоритмов</p>

                <div class="algo-table-wrapper">
                    <table class="algo-table">
                        <thead>
                            <tr>
                                <th>Алгоритм</th>
                                <th>Тип</th>
                                <th>Сложность</th>
                                <th>Скорость</th>
                                <th>Действия</th>
                            </tr>
                        </thead>
                        <tbody id="algo-table-body">
                            ${MOCK.algorithms.map(a => `
                                <tr>
                                    <td><strong>${a.display}</strong><br><span class="text-sm text-muted">${a.name}</span></td>
                                    <td>${a.type}</td>
                                    <td><code>${a.complexity}</code></td>
                                    <td><span class="algo-badge algo-badge-${a.speed}">${a.speed}</span></td>
                                    <td>
                                        <button class="glass-btn glass-btn-sm" onclick="app.rebuildAlgorithm('${a.name}')">
                                            Перестроить
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>

                <div class="mt-3 glass-panel" style="padding:24px; border-radius: var(--radius-xl);">
                    <h3 style="margin-bottom:12px;">⚡ Сравнение</h3>
                    <p class="text-muted text-sm mb-2">Выберите фильм и количество результатов для сравнения алгоритмов</p>
                    <div class="flex gap-2 items-center flex-wrap">
                        <input type="number" class="glass-input" id="compare-movie-id" placeholder="Movie ID" value="1" style="width:120px">
                        <input type="number" class="glass-input" id="compare-k" placeholder="K" value="10" style="width:80px">
                        <button class="glass-btn glass-btn-primary" onclick="app.compareAlgos()">
                            Сравнить
                        </button>
                    </div>
                    <div id="compare-result" class="mt-2"></div>
                </div>
            </div>
        `;

        // Try to load from API
        try {
            const algos = await this.api.getAlgorithmsList();
            if (algos && algos.length) {
                // could re-render with real data
            }
        } catch (e) {
            // use mock
        }
    }

    render404() {
        document.getElementById('app').innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <h3>Страница не найдена</h3>
                <a href="#/" class="glass-btn glass-btn-primary mt-2">На главную</a>
            </div>
        `;
    }

    // ---------- Components ----------
    renderMovieCard(movie) {
        const poster = movie.poster_path
            ? `<img src="${TMDB_IMG_BASE}${movie.poster_path}" alt="${movie.title}" loading="lazy">`
            : `<span class="placeholder-icon">🎬</span>`;

        return `
            <div class="movie-card" data-id="${movie.id}">
                <div class="movie-card-poster">
                    ${poster}
                    <div class="movie-card-overlay">
                        <div style="width:100%">
                            <div style="font-size:0.8rem; font-weight:500; margin-bottom:4px;">${movie.title}</div>
                            <div style="font-size:0.7rem; color:var(--text-secondary);">${movie.year || ''} ${movie.runtime ? `· ${movie.runtime} мин` : ''}</div>
                        </div>
                    </div>
                </div>
                <div class="movie-card-info">
                    <div class="movie-card-title">${movie.title}</div>
                    <div class="movie-card-meta">
                        <span>${movie.year || ''}</span>
                        ${movie.rating ? `
                            <span class="movie-card-rating">
                                <span class="star">★</span> ${movie.rating}
                            </span>
                        ` : ''}
                    </div>
                </div>
                <div class="movie-card-actions">
                    <button class="action-btn action-btn-watched" onclick="event.stopPropagation(); app.handleInteraction(${movie.id}, 'watched')">✓</button>
                    <button class="action-btn action-btn-want" onclick="event.stopPropagation(); app.handleInteraction(${movie.id}, 'want_to_watch')">+</button>
                    <button class="action-btn action-btn-skip" onclick="event.stopPropagation(); app.handleInteraction(${movie.id}, 'not_interested')">✕</button>
                </div>
            </div>
        `;
    }

    attachCardListeners(container) {
        container.querySelectorAll('.movie-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = card.dataset.id;
                location.hash = `#/movie/${id}`;
            });
        });
    }

    renderLoading() {
        return `
            <div class="loading" style="grid-column: 1/-1;">
                <div class="spinner"></div>
                <span>Загрузка...</span>
            </div>
        `;
    }

    // ---------- Interactions ----------
    async handleInteraction(movieId, eventType, value = null) {
        if (!this.currentUser) {
            this.showToast('Войдите в аккаунт', 'error');
            document.getElementById('auth-btn').click();
            return;
        }

        try {
            await this.api.recordInteraction(movieId, eventType, value);
            const messages = {
                'watched': 'Отмечено как просмотренное',
                'want_to_watch': 'Добавлено в список',
                'not_interested': 'Скрыто из рекомендаций',
                'rated': `Оценка ${value} сохранена`,
                'liked': 'Лайк!',
                'disliked': 'Дизлайк',
            };
            this.showToast(messages[eventType] || 'Сохранено', 'success');
        } catch (e) {
            // Demo mode
            const messages = {
                'watched': '✓ Просмотрено (демо)',
                'want_to_watch': '+ В списке (демо)',
                'not_interested': '✕ Скрыто (демо)',
                'rated': `Оценка ${value} (демо)`,
            };
            this.showToast(messages[eventType] || 'Сохранено', 'info');
        }
    }

    async rebuildAlgorithm(name) {
        this.showToast(`Перестраиваем ${name}...`, 'info');
        try {
            await this.api.request(`/algorithms/rebuild?algorithm=${name}`, { method: 'POST' });
            this.showToast(`${name} перестроен!`, 'success');
        } catch (e) {
            this.showToast(`Demo: ${name} перестроен`, 'info');
        }
    }

    async compareAlgos() {
        const movieId = document.getElementById('compare-movie-id').value;
        const k = document.getElementById('compare-k').value;
        const result = document.getElementById('compare-result');

        result.innerHTML = this.renderLoading();

        try {
            const data = await this.api.compareAlgorithms(movieId, k);
            if (data) {
                result.innerHTML = `<pre style="color:var(--text-secondary); font-size:0.8rem; overflow-x:auto;">${JSON.stringify(data, null, 2)}</pre>`;
            } else {
                throw new Error('No data');
            }
        } catch (e) {
            result.innerHTML = `
                <div style="color:var(--text-secondary); font-size:0.85rem; padding:12px; background:var(--glass-bg); border-radius:var(--radius-md); margin-top:12px;">
                    <strong>Demo результаты:</strong><br>
                    Item-Item: 45ms, overlap 60%<br>
                    TF-IDF: 120ms, overlap 40%<br>
                    Jaccard: 12ms, overlap 80%<br>
                    MF: 230ms, overlap 30%
                </div>
            `;
        }
    }

    // ---------- Toasts ----------
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = { success: '✓', error: '✕', info: 'ℹ' };
        toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(40px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

// ==============================
// INIT
// ==============================
const app = new App();