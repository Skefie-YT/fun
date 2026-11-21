(function () {
  const gamesGrid = document.getElementById('games-grid');
  const gameCountEl = document.getElementById('game-count');
  const resultsNoteEl = document.getElementById('results-note');
  const searchInput = document.getElementById('search-input');
  const categoryFilters = document.getElementById('category-filters');
  const randomGameBtn = document.getElementById('random-game-btn');
  const emptyStateEl = document.getElementById('empty-state');
  const resetFiltersBtn = document.getElementById('reset-filters-btn');

  let allGames = [];
  let activeCategory = 'all';
  let searchQuery = '';

  function getHighScore(slug) {
    try {
      const raw = localStorage.getItem('fun_arcade_highscore_' + slug);
      return raw ? Number(raw) : null;
    } catch {
      return null;
    }
  }

  function buildCategoryButtons(games) {
    const categories = Array.from(new Set(games.map((g) => g.category).filter(Boolean)));
    categoryFilters.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'filter-chip is-active';
    allBtn.dataset.category = 'all';
    allBtn.textContent = 'All';
    categoryFilters.appendChild(allBtn);

    categories.forEach((cat) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'filter-chip';
      btn.dataset.category = cat;
      btn.textContent = cat;
      categoryFilters.appendChild(btn);
    });
  }

  function renderGames() {
    const query = searchQuery.trim().toLowerCase();
    const filtered = allGames.filter((game) => {
      const matchesCat = activeCategory === 'all' || game.category === activeCategory;
      const matchesSearch =
        !query ||
        game.title.toLowerCase().includes(query) ||
        game.description.toLowerCase().includes(query) ||
        (game.category && game.category.toLowerCase().includes(query));
      return matchesCat && matchesSearch;
    });

    gamesGrid.innerHTML = '';

    if (filtered.length === 0) {
      emptyStateEl.hidden = false;
      resultsNoteEl.textContent = '0 games shown';
      return;
    }

    emptyStateEl.hidden = true;
    resultsNoteEl.textContent =
      filtered.length === allGames.length
        ? `${allGames.length} ${allGames.length === 1 ? 'game' : 'games'} ready`
        : `${filtered.length} of ${allGames.length} shown`;

    filtered.forEach((game, idx) => {
      const card = document.createElement('article');
      card.className = 'game-card';
      if (game.accent) {
        card.style.setProperty('--card-accent', game.accent);
      }

      const best = getHighScore(game.slug);
      const scoreHtml =
        best !== null && !Number.isNaN(best)
          ? `Best: <strong>${best}</strong>`
          : 'Not played yet';

      const gameNumber = String(idx + 1).padStart(2, '0');

      card.innerHTML = `
        <div>
          <div class="card-top">
            <span class="card-badge">${escapeHtml(game.category || 'Game')}</span>
            <span class="card-number">#${gameNumber}</span>
          </div>
          <h2 class="card-title">${escapeHtml(game.title)}</h2>
          <p class="card-desc">${escapeHtml(game.description)}</p>
        </div>
        <div class="card-footer">
          <span class="card-score">${scoreHtml}</span>
          <a class="play-link" href="games/${encodeURIComponent(game.slug)}/">
            Play <span aria-hidden="true">-&gt;</span>
          </a>
        </div>
      `;

      gamesGrid.appendChild(card);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  categoryFilters.addEventListener('click', (event) => {
    const btn = event.target.closest('.filter-chip');
    if (!btn) return;
    activeCategory = btn.dataset.category || 'all';
    categoryFilters.querySelectorAll('.filter-chip').forEach((chip) => {
      chip.classList.toggle('is-active', chip === btn);
    });
    renderGames();
  });

  searchInput.addEventListener('input', (event) => {
    searchQuery = event.target.value;
    renderGames();
  });

  resetFiltersBtn.addEventListener('click', () => {
    activeCategory = 'all';
    searchQuery = '';
    searchInput.value = '';
    categoryFilters.querySelectorAll('.filter-chip').forEach((chip) => {
      chip.classList.toggle('is-active', chip.dataset.category === 'all');
    });
    renderGames();
  });

  randomGameBtn.addEventListener('click', () => {
    if (!allGames.length) return;
    const pick = allGames[Math.floor(Math.random() * allGames.length)];
    window.location.href = `games/${encodeURIComponent(pick.slug)}/`;
  });

  async function loadGamesMenu() {
    try {
      const response = await fetch('games.json?t=' + Date.now(), { cache: 'no-store' });
      if (!response.ok) throw new Error('Failed to load games.json');
      const data = await response.json();
      allGames = Array.isArray(data) ? data : [];
      gameCountEl.textContent = String(allGames.length);
      buildCategoryButtons(allGames);
      renderGames();
    } catch (err) {
      console.error(err);
      resultsNoteEl.textContent = 'Could not load game menu.';
    }
  }

  // Make Game modal & GitHub Actions workflow trigger
  const makeGameBtn = document.getElementById('make-game-btn');
  const makeGameModal = document.getElementById('make-game-modal');
  const closeMakeModal = document.getElementById('close-make-modal');
  const makeGameForm = document.getElementById('make-game-form');
  const themeInput = document.getElementById('game-theme-input');
  const tokenInput = document.getElementById('gh-token-input');
  const statusBox = document.getElementById('make-game-status');
  const triggerBtn = document.getElementById('trigger-make-btn');
  const TOKEN_KEY = 'fun_arcade_gh_token';

  function setStatus(html) {
    statusBox.hidden = false;
    statusBox.innerHTML = html;
  }

  function openMakeModal() {
    try {
      const saved = localStorage.getItem(TOKEN_KEY);
      if (saved && !tokenInput.value) tokenInput.value = saved;
    } catch {}
    makeGameModal.hidden = false;
  }

  function hideMakeModal() {
    makeGameModal.hidden = true;
  }

  makeGameBtn.addEventListener('click', openMakeModal);
  closeMakeModal.addEventListener('click', hideMakeModal);
  makeGameModal.addEventListener('click', (e) => {
    if (e.target === makeGameModal) hideMakeModal();
  });

  async function pollRun(token, startedAt) {
    const headers = {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
    };
    for (let i = 0; i < 45; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      const res = await fetch(
        'https://api.github.com/repos/Skefie-YT/fun/actions/workflows/hourly-minigame.yml/runs?per_page=3',
        { headers, cache: 'no-store' }
      );
      if (!res.ok) continue;
      const data = await res.json();
      const run = (data.workflow_runs || []).find(
        (r) => new Date(r.created_at).getTime() >= startedAt - 15000
      );
      if (!run) continue;
      if (run.status !== 'completed') {
        setStatus(
          `Generating new game... (${escapeHtml(run.status)}) &bull; <a href="${escapeHtml(run.html_url)}" target="_blank" rel="noopener noreferrer">View run</a>`
        );
        continue;
      }
      if (run.conclusion === 'success') {
        setStatus('New game created! Waiting a few seconds for GitHub Pages to update...');
        await new Promise((r) => setTimeout(r, 8000));
        await loadGamesMenu();
        setStatus('Done! Your new game is in the Game Menu.');
        return;
      }
      setStatus(
        `Run finished with <strong>${escapeHtml(run.conclusion || 'error')}</strong>. <a href="${escapeHtml(run.html_url)}" target="_blank" rel="noopener noreferrer">Check logs</a>`
      );
      return;
    }
    setStatus('Still running in GitHub Actions—refresh the page in a minute to see your new game.');
  }

  makeGameForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = tokenInput.value.trim();
    const theme = themeInput.value.trim();
    if (!token) {
      setStatus('Paste a GitHub token with <strong>Actions: Read &amp; Write</strong> permission, or click <strong>Run on GitHub</strong>.');
      return;
    }
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {}

    triggerBtn.disabled = true;
    triggerBtn.textContent = 'Starting...';
    const startedAt = Date.now();
    setStatus('Triggering GitHub Actions workflow...');

    try {
      const res = await fetch(
        'https://api.github.com/repos/Skefie-YT/fun/actions/workflows/hourly-minigame.yml/dispatches',
        {
          method: 'POST',
          headers: {
            Accept: 'application/vnd.github+json',
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ ref: 'main', inputs: { theme } }),
        }
      );
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`GitHub API ${res.status}: ${err}`);
      }
      setStatus('Workflow queued! Waiting for AI game generator...');
      await pollRun(token, startedAt);
    } catch (err) {
      setStatus(`Could not trigger workflow: ${escapeHtml(err.message || String(err))}`);
    } finally {
      triggerBtn.disabled = false;
      triggerBtn.textContent = 'Generate Game';
    }
  });

  loadGamesMenu();
})();
