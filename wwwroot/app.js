// Setup Interop API
let api = null;

// Elements
const tabs = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const btnEnableWacom = document.getElementById('btn-enable-wacom');
const btnDisableWacom = document.getElementById('btn-disable-wacom');
const btnStartReal = document.getElementById('btn-start-real');
const btnStopReal = document.getElementById('btn-stop-real');
const chkToggleSidebar = document.getElementById('chk-toggle-sidebar');
const btnMinimize = document.getElementById('btn-minimize');
const btnClose = document.getElementById('btn-close');
const realStatusDot = document.getElementById('real-status-dot');
const realStatusText = document.getElementById('real-status-text');

// Cloud Elements
const btnCloudConnect = document.getElementById('btn-cloud-connect');
const btnCloudDisconnect = document.getElementById('btn-cloud-disconnect');
const cloudStatusDot = document.getElementById('cloud-status-dot');
const cloudStatusText = document.getElementById('cloud-status-text');
const inpCloudProject = document.getElementById('inp-cloud-project');
const inpCloudApiKey = document.getElementById('inp-cloud-apikey');
const dragRegion = document.getElementById('drag-region');

    // WuWa DB Variables
    let wuwaCharacters = [];
    const characterGrid = document.getElementById('character-grid');
    const detailModal = document.getElementById('character-detail-modal');
    const detailBody = document.getElementById('character-detail-body');
    const btnCloseModal = document.getElementById('btn-close-modal');
    const btnReloadDb = document.getElementById('btn-reload-db');

    // UI Event Listeners
    tabs.forEach(btn => {
        btn.addEventListener('click', () => {
            tabs.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const target = btn.dataset.tab;
            document.getElementById(`tab-${target}`).classList.add('active');

            // Load DB if WuWa tab is selected and DB is empty
            if (target === 'wuwa-db' && wuwaCharacters.length === 0) {
                loadWuWaDatabase();
            }
        });
    });

// Cloud Mockup logic
btnCloudConnect.addEventListener('click', async () => {
    btnCloudConnect.innerHTML = "Connecting...";
    
    // Save to Config
    if (window.chrome && window.chrome.webview) {
        await api.SetCloudProjectId(inpCloudProject.value);
        await api.SetCloudApiKey(inpCloudApiKey.value);
    }
    
    // Fake Connection Delay
    setTimeout(() => {
        btnCloudConnect.style.display = 'none';
        btnCloudDisconnect.style.display = 'block';
        cloudStatusDot.classList.add('green');
        cloudStatusText.innerText = 'Connected to Cloud';
        btnCloudConnect.innerHTML = "Connect";
        // Lock inputs
        inpCloudProject.disabled = true;
        inpCloudApiKey.disabled = true;
    }, 800);
});

btnCloudDisconnect.addEventListener('click', () => {
    btnCloudDisconnect.style.display = 'none';
    btnCloudConnect.style.display = 'block';
    cloudStatusDot.classList.remove('green');
    cloudStatusText.innerText = 'Not Connected';
    // Unlock inputs
    inpCloudProject.disabled = false;
    inpCloudApiKey.disabled = false;
});

// Init
window.onload = async () => {
    if (window.chrome && window.chrome.webview) {
        api = window.chrome.webview.hostObjects.api;
        
        // Window Controls
        btnMinimize.addEventListener('click', () => api.MinimizeToTray());
        btnClose.addEventListener('click', () => api.Shutdown());

        // Drag Region Fallback (if -webkit-app-region is flaky)
        dragRegion.addEventListener('mousedown', () => {
            window.chrome.webview.postMessage('dragWindow');
        });

        // API Calls
        btnEnableWacom.addEventListener('click', () => api.EnableWacom());
        btnDisableWacom.addEventListener('click', () => api.DisableWacom());
        btnStartReal.addEventListener('click', () => api.StartReal());
        btnStopReal.addEventListener('click', () => api.StopReal());
        chkToggleSidebar.addEventListener('change', () => api.ToggleSidebar());

        // Init Settings
        const closeToTray = await api.GetCloseToTray();
        document.getElementById('chk-close-to-tray').checked = closeToTray;
        document.getElementById('chk-close-to-tray').addEventListener('change', (e) => {
            api.SetCloseToTray(e.target.checked);
        });

        const hidePullTab = await api.GetHideSidebarPullTab();
        document.getElementById('chk-hide-pull-tab').checked = hidePullTab;
        
        const cloudProject = await api.GetCloudProjectId();
        const cloudApiKey = await api.GetCloudApiKey();
        if (cloudProject) inpCloudProject.value = cloudProject;
        if (cloudApiKey) inpCloudApiKey.value = cloudApiKey;
        
        if (cloudProject && cloudApiKey) {
             // Auto-connect if credentials exist
             btnCloudConnect.click();
        }

        document.getElementById('chk-hide-pull-tab').addEventListener('change', (e) => {
            api.SetHideSidebarPullTab(e.target.checked);
        });
    }

    // ----------------------------------------------------
    // WuWa Database Logic
    // ----------------------------------------------------
    async function loadWuWaDatabase() {
        try {
            // Load from local file
            const response = await fetch('data/wuwa_characters.json');
            if (response.ok) {
                wuwaCharacters = await response.json();
                renderCharacterGrid();
            } else {
                characterGrid.innerHTML = '<p>Failed to load database. File not found.</p>';
            }
        } catch (error) {
            console.error('Error loading DB:', error);
            characterGrid.innerHTML = `<p>Error loading database: ${error.message}</p>`;
        }
    }

    function renderCharacterGrid() {
        characterGrid.innerHTML = '';
        wuwaCharacters.forEach(char => {
            const card = document.createElement('div');
            card.className = `char-card rarity-${char.rarity}`;
            card.innerHTML = `
                <img src="${char.portrait}" alt="${char.name}" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzMzMyIvPjwvc3ZnPg=='" />
                <div class="char-name">${char.name}</div>
            `;
            card.addEventListener('click', () => showCharacterDetail(char));
            characterGrid.appendChild(card);
        });
    }

    function showCharacterDetail(char) {
        detailBody.innerHTML = `
            <div class="detail-layout">
                <div class="detail-portrait">
                    <img src="${char.portrait}" alt="${char.name}" style="border: 2px solid ${char.rarity === 5 ? '#ffd700' : '#a335ee'};" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzMzMyIvPjwvc3ZnPg=='" />
                </div>
                <div class="detail-info">
                    <h2>${char.name}</h2>
                    <p><strong>Element:</strong> ${char.element}</p>
                    <p><strong>Weapon:</strong> ${char.weapon}</p>
                    <p><strong>Rarity:</strong> ${char.rarity}★</p>
                    
                    <div class="stats-grid">
                        <div class="stat-item"><span>HP</span> <span>${char.stats_lvl90.hp}</span></div>
                        <div class="stat-item"><span>ATK</span> <span>${char.stats_lvl90.atk}</span></div>
                        <div class="stat-item"><span>DEF</span> <span>${char.stats_lvl90.def}</span></div>
                        <div class="stat-item"><span>Crit Rate</span> <span>${char.stats_lvl90.crit_rate}%</span></div>
                        <div class="stat-item"><span>Crit DMG</span> <span>${char.stats_lvl90.crit_dmg}%</span></div>
                    </div>
                </div>
            </div>

            <div class="build-section">
                <h3>Recommended Build</h3>
                <p><strong>Best Echo Set:</strong> ${char.build_recommendations.best_echo_set}</p>
                <p><strong>Main Echo:</strong> ${char.build_recommendations.best_echo_main}</p>
                <p><strong>Stat Priority:</strong> ${char.build_recommendations.stat_priority}</p>
                <p><strong>4-Cost:</strong> ${char.build_recommendations.cost_4_stat}</p>
                <p><strong>3-Cost:</strong> ${char.build_recommendations.cost_3_stat}</p>
                <p><strong>1-Cost:</strong> ${char.build_recommendations.cost_1_stat}</p>
            </div>

            <div class="build-section">
                <h3>Top Weapons</h3>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: var(--text-muted);">
                    ${char.best_weapons.map(w => `<li>${w}</li>`).join('')}
                </ul>
            </div>
        `;
        detailModal.style.display = 'flex';
    }

    btnCloseModal.addEventListener('click', () => {
        detailModal.style.display = 'none';
    });
    
    // Close modal on click outside
    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) detailModal.style.display = 'none';
    });

    btnReloadDb.addEventListener('click', () => {
        loadWuWaDatabase();
    });
};

// Update Handlers called from C#
window.updateRealStatus = (isRunning) => {
    if (isRunning) {
        realStatusDot.className = 'dot green';
        realStatusText.innerText = 'Running';
    } else {
        realStatusDot.className = 'dot red';
        realStatusText.innerText = 'Stopped';
    }
};

window.updateSidebarMode = (isSidebar) => {
    const container = document.getElementById('app-container');
    const titlebar = document.getElementById('titlebar');
    const pullTab = document.getElementById('pull-tab');
    
    if (isSidebar) {
        container.style.borderRadius = '0';
        container.style.borderRight = 'none';
        container.style.borderTop = 'none';
        container.style.borderBottom = 'none';
        titlebar.style.display = 'none';
        pullTab.style.display = 'flex';
        if(chkToggleSidebar) chkToggleSidebar.checked = true;
    } else {
        container.style.borderRadius = '8px';
        container.style.border = '1px solid var(--border)';
        titlebar.style.display = 'flex';
        pullTab.style.display = 'none';
        if(chkToggleSidebar) chkToggleSidebar.checked = false;
    }
};
