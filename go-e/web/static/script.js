/**
 * Go-e Smart Home Bridge - Dashboard JavaScript
 * Handles UI interactions and API communication
 */

// ==================== Constants ====================

const API_BASE = '/api';
const REFRESH_INTERVAL = 15000; // 10 seconds
const OVERRIDE_CHECK_INTERVAL = 30000; // 30 seconds

// ==================== Global State ====================

let currentUser = null;
let overrideActive = false;
let modeState = null;

// ==================== Time Picker Setup ====================

function initializeTimePickerOptions() {
    const timeSelect = document.getElementById('overrideTime');

    // Generate time options in 15-minute intervals
    const now = new Date();
    for (let hour = now.getHours(); hour < 24; hour++) {
        for (let minute = (hour === now.getHours() ? Math.ceil(now.getMinutes() / 15) * 15 : 0); minute < 60; minute += 15) {
            const option = document.createElement('option');
            const timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
            option.value = timeStr;
            option.textContent = timeStr;
            timeSelect.appendChild(option);
        }
    }
}

function initializeOverrideDatePicker() {
    const dateInput = document.getElementById('overrideDate');

    // Set minimum date to today
    const today = new Date();
    const dateStr = today.toISOString().split('T')[0];
    dateInput.min = dateStr;
    dateInput.value = dateStr;
}

// ==================== API Functions ====================

async function fetchLiveValues() {
    try {
        const response = await fetch(`${API_BASE}/live`);
        if (response.status === 401) {
            redirectToLogin();
            return null;
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching live values:', error);
        return null;
    }
}

async function setMode(mode) {
    try {
        const response = await fetch(`${API_BASE}/mode/set`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ mode })
        });

        if (response.status === 401) {
            redirectToLogin();
            return false;
        }

        if (response.ok) {
            modeState = mode;
            updateModeDisplay(mode);
            return true;
        }
        return false;
    } catch (error) {
        console.error('Error setting mode:', error);
        return false;
    }
}

async function setOverride() {
    const dateInput = document.getElementById('overrideDate');
    const timeInput = document.getElementById('overrideTime');

    if (!dateInput.value || !timeInput.value) {
        showMessage('Bitte Datum und Uhrzeit wählen', 'error', 'overrideMessage');
        return;
    }

    const dateStr = dateInput.value; // YYYY-MM-DD
    const timeStr = timeInput.value; // HH:MM
    const endDateTime = new Date(`${dateStr}T${timeStr}`);

    if (isNaN(endDateTime.getTime())) {
        showMessage('Ungültiges Datum/Zeit Format', 'error', 'overrideMessage');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/override/set`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                end_time: endDateTime.toISOString()
            })
        });

        if (response.status === 401) {
            redirectToLogin();
            return;
        }

        if (response.ok) {
            const data = await response.json();
            showMessage('Override erfolgreich gesetzt', 'success', 'overrideMessage');
            updateOverrideStatus(data.override);
        } else {
            showMessage('Fehler beim Setzen des Override', 'error', 'overrideMessage');
        }
    } catch (error) {
        console.error('Error setting override:', error);
        showMessage('Fehler beim Setzen des Override: ' + error.message, 'error', 'overrideMessage');
    }
}

async function clearOverride() {
    try {
        const response = await fetch(`${API_BASE}/override`, {
            method: 'DELETE'
        });

        if (response.status === 401) {
            redirectToLogin();
            return;
        }

        if (response.ok) {
            showMessage('Override aufgehoben', 'success', 'overrideMessage');
            updateOverrideStatus(null);
        } else {
            showMessage('Fehler beim Aufheben des Override', 'error', 'overrideMessage');
        }
    } catch (error) {
        console.error('Error clearing override:', error);
        showMessage('Fehler beim Aufheben des Override: ' + error.message, 'error', 'overrideMessage');
    }
}

async function logout() {
    try {
        await fetch(`${API_BASE}/logout`, { method: 'GET' });
        redirectToLogin();
    } catch (error) {
        console.error('Error logging out:', error);
        redirectToLogin();
    }
}

// ==================== UI Update Functions ====================

function updateLiveValues(data) {
    if (!data) return;

    // Power
    const powerValue = data.power || '--';
    document.getElementById('powerValue').textContent = powerValue + ' kW';

    // Phases
    const phasesValue = data.phases || '--';
    document.getElementById('phasesValue').textContent = phasesValue;

    // Source
    const sourceValueHomePV = data.HomePV || '--';
    document.getElementById('sourceValueHomePV').textContent = 'PV: ' + sourceValueHomePV + ' kW';
    const sourceValueHomeBat = data.HomeBat || '--';
    document.getElementById('sourceValueHomeBat').textContent = 'Akku: ' + sourceValueHomeBat + ' kW';
    const sourceValueHomeGrid = data.HomeGrid || '--';
    document.getElementById('sourceValueHomeGrid').textContent = 'Netz: ' + sourceValueHomeGrid + ' kW';

    // Mode
    const modeValue = data.mode || '--';
    document.getElementById('modeValue').textContent = modeValue;

    // Last update
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('de-DE');
}

function updateOverrideStatus(overrideInfo) {
    const statusDiv = document.getElementById('overrideStatus');
    const formDiv = document.getElementById('overrideForm');

    if (overrideInfo && overrideInfo.is_active) {
        overrideActive = true;
        statusDiv.style.display = 'block';
        formDiv.style.display = 'none';

        const endTime = new Date(overrideInfo.end_time);
        document.getElementById('overrideEndTime').textContent = endTime.toLocaleString('de-DE');
        document.getElementById('overrideRemaining').textContent = formatDuration(overrideInfo.remaining_seconds);
    } else {
        overrideActive = false;
        statusDiv.style.display = 'none';
        formDiv.style.display = 'block';
    }
}

function updateModeDisplay(mode) {
    const basicBtn = document.getElementById('basicBtn');
    const ecoBtn = document.getElementById('ecoBtn');

    basicBtn.classList.remove('active');
    ecoBtn.classList.remove('active');

    if (mode === 'BASIC') {
        basicBtn.classList.add('active');
    } else if (mode === 'ECO') {
        ecoBtn.classList.add('active');
    }
}

function updateMQTTStatus(connected) {
    const statusElement = document.getElementById('mqttStatus');
    if (connected) {
        statusElement.textContent = '● Verbunden';
        statusElement.className = 'status-indicator status-connected';
    } else {
        statusElement.textContent = '● Getrennt';
        statusElement.className = 'status-indicator status-disconnected';
    }
}

function updateUserDisplay(username) {
    const userElement = document.getElementById('userName');
    if (username) {
        userElement.textContent = `Benutzer: ${username}`;
    }
}

function showMessage(message, type, elementId) {
    const messageElement = document.getElementById(elementId);
    if (messageElement) {
        messageElement.textContent = message;
        messageElement.className = `status-message ${type}`;
        messageElement.style.display = 'block';

        // Auto-hide after 5 seconds
        setTimeout(() => {
            messageElement.style.display = 'none';
        }, 5000);
    }
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '--';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

// ==================== Event Listeners ====================

function setupEventListeners() {
    // Mode buttons
    document.getElementById('basicBtn').addEventListener('click', () => setMode('BASIC'));
    document.getElementById('ecoBtn').addEventListener('click', () => setMode('ECO'));

    // Override buttons
    document.getElementById('setOverrideBtn').addEventListener('click', setOverride);
    document.getElementById('clearOverrideBtn').addEventListener('click', clearOverride);

    // Logout button
    document.getElementById('logoutBtn').addEventListener('click', logout);
}

// ==================== Data Refresh ====================

async function refreshData() {
    // Fetch and update live values
    const liveValues = await fetchLiveValues();
    if (liveValues) {
        updateLiveValues(liveValues);
    }
}

function redirectToLogin() {
    window.location.href = '/login';
}

// ==================== Initialization ====================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Dashboard initializing...');

    // Setup UI
    initializeTimePickerOptions();
    initializeOverrideDatePicker();
    setupEventListeners();

    // Initial data refresh
    refreshData();

    // Set up periodic refresh
    setInterval(refreshData, REFRESH_INTERVAL);

    console.log('Dashboard ready');
});

