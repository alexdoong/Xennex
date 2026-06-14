// Setup Interop API
let api = null;

// Elements
const tabs = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const btnEnableWacom = document.getElementById('btn-enable-wacom');
const btnDisableWacom = document.getElementById('btn-disable-wacom');
const btnStartReal = document.getElementById('btn-start-real');
const btnStopReal = document.getElementById('btn-stop-real');
const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
const btnMinimize = document.getElementById('btn-minimize');
const btnClose = document.getElementById('btn-close');
const realStatusDot = document.getElementById('real-status-dot');
const realStatusText = document.getElementById('real-status-text');
const dragRegion = document.getElementById('drag-region');

// Setup Tabs
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
    });
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
        btnToggleSidebar.addEventListener('click', () => api.ToggleSidebar());

        // Init Settings
        const closeToTray = await api.GetCloseToTray();
        document.getElementById('chk-close-to-tray').checked = closeToTray;
        document.getElementById('chk-close-to-tray').addEventListener('change', (e) => {
            api.SetCloseToTray(e.target.checked);
        });

        const hidePullTab = await api.GetHideSidebarPullTab();
        document.getElementById('chk-hide-pull-tab').checked = hidePullTab;
        document.getElementById('chk-hide-pull-tab').addEventListener('change', (e) => {
            api.SetHideSidebarPullTab(e.target.checked);
        });
    }
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
    } else {
        container.style.borderRadius = '8px';
        container.style.border = '1px solid var(--border)';
        titlebar.style.display = 'flex';
        pullTab.style.display = 'none';
    }
};
