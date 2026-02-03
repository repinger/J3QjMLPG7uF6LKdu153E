// --- MAP INIT ---
const map = L.map("map", {
	center: [-2.5, 118.0],
	zoom: 5,
	minZoom: 4,
	maxBounds: [
		[-15.0, 90.0],
		[10.0, 145.0],
	],
	zoomControl: false,
});
L.control.zoom({ position: "bottomright" }).addTo(map);
L.tileLayer(
	"https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
	{ attribution: "&copy; OpenStreetMap" },
).addTo(map);
const markersLayer = L.markerClusterGroup({
	disableClusteringAtZoom: 15, // Naikkan threshold zoom untuk clustering
	spiderfyOnMaxZoom: true,
	showCoverageOnHover: false,
	maxClusterRadius: 60, // Kurangi radius cluster
	spiderfyDistanceMultiplier: 1.5,
	// Tambahkan chunked loading untuk performa
	chunkedLoading: true,
	chunkDelay: 100,
}).addTo(map);

// --- GLOBAL VARS ---
let currentMachines = [];
let markerMap = {};
let filteredMachines = [];
let tempClickMarker = null;
let listChartInstances = {};
let mapChartInstances = {};
let detailChartInstance = null;
let openedPopupId = null;
let currentDetailId = null;
let currentUserRole = "user";
let currentPage = 1;
let itemsPerPage = 6;
let currentViewMode = "normal";
let configLatency = 100; // Default
let configBandwidth = 10000; // Default

// --- AUTH CHECK & ROLE SETUP ---
async function fetchUserInfo() {
	try {
		const res = await fetch("/api/me");
		if (res.ok) {
			const user = await res.json();
			currentUserRole = user.role;

			// [FIX] Update Tampilan User & Role
			const nameEl = document.getElementById("nav-username");
			const roleEl = document.getElementById("nav-role");

			if (nameEl) nameEl.textContent = user.username || "User";
			if (roleEl) roleEl.textContent = user.role || "Member";

			// LOGIKA GANTI NAMA MENU & JUDUL
			const navListBtn = document.getElementById("nav-list");
			const pageTitle = document.querySelector("#view-list h2");
			const pageSubtitle = document.querySelector("#view-list .subtitle");

			if (currentUserRole === "admin") {
				// Tampilan ADMIN
				if (navListBtn)
					navListBtn.innerHTML = '<i class="fas fa-server"></i> Manage Nodes';
				if (pageTitle) pageTitle.textContent = "Manage Nodes";
				if (pageSubtitle)
					pageSubtitle.textContent = "Monitoring & Control Center";

				// Highlight Role Admin
				if (roleEl) {
					roleEl.style.color = "#f59e0b"; // Warna Orange/Emas untuk admin
					roleEl.innerHTML = '<i class="fas fa-shield-alt"></i> ADMIN';
				}
			} else {
				// Tampilan USER BIASA
				if (navListBtn)
					navListBtn.innerHTML =
						'<i class="fas fa-network-wired"></i> View Nodes';
				if (pageTitle) pageTitle.textContent = "Network Overview";
				if (pageSubtitle)
					pageSubtitle.textContent = "Real-time Infrastructure Status";

				document.body.classList.add("role-user");
			}

			document.body.classList.remove("auth-pending");
			renderList(currentMachines);
		} else {
			window.location.href = "/login";
		}
	} catch (e) {
		console.error("Auth check failed", e);
		document.body.classList.remove("auth-pending");
	}
}
fetchUserInfo();

// --- NOTIFICATIONS ---
window.toggleNotifications = function () {
	const dropdown = document.getElementById("notif-dropdown");
	dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
};

async function fetchNotifications() {
	try {
		const res = await fetch("/api/alerts");
		if (!res.ok) return;
		const data = await res.json();
		const badge = document.getElementById("notif-badge");
		badge.style.display = data.unread_count > 0 ? "block" : "none";
		const list = document.getElementById("notif-list");
		if (data.alerts.length === 0) {
			list.innerHTML = `<div style="padding:15px; text-align:center; color:#94a3b8; font-size:0.85rem;">Tidak ada notifikasi</div>`;
			return;
		}
		list.innerHTML = "";
		data.alerts.forEach((a) => {
			const icon =
				a.type === "down"
					? '<i class="fas fa-exclamation-circle" style="color:#ef4444"></i>'
					: '<i class="fas fa-tachometer-alt" style="color:#f59e0b"></i>';
			const html = `<div class="notif-item ${a.is_read ? "" : "unread"}"><div style="font-weight:700; margin-bottom:2px; font-size:0.8rem; display:flex; align-items:center; gap:6px;">${icon} ${a.machine_id}</div><div style="color:#334155;">${a.message}</div><span class="notif-time">${a.time}</span></div>`;
			list.insertAdjacentHTML("beforeend", html);
		});
	} catch (e) {
		console.error(e);
	}
}

window.markRead = async function () {
	await fetch("/api/alerts/read", { method: "POST" });
	fetchNotifications();
};

window.clearNotifications = async function () {
	// Konfirmasi agar tidak terhapus tidak sengaja
	if (!confirm("Hapus semua riwayat notifikasi?")) return;

	try {
		const res = await fetch("/api/alerts/clear", { method: "POST" });
		if (res.ok) {
			// Refresh list notifikasi (akan menjadi kosong)
			fetchNotifications();
			showToast("Notifikasi dihapus", "success");
		} else {
			showToast("Gagal menghapus", "error");
		}
	} catch (e) {
		console.error(e);
		showToast("Error koneksi", "error");
	}
};

// --- HELPERS ---
const AVAILABLE_ICONS = [
	"fa-server",
	"fa-network-wired",
	"fa-desktop",
	"fa-laptop",
	"fa-mobile-alt",
	"fa-wifi",
	"fa-video",
	"fa-print",
	"fa-database",
	"fa-cloud",
	"fa-microchip",
	"fa-hdd",
	"fa-gamepad",
	"fa-tv",
	"fa-robot",
	"fa-satellite-dish",
];

function renderIconSelector(c, i, s) {
	const container = document.getElementById(c);
	container.innerHTML = "";
	AVAILABLE_ICONS.forEach((icon) => {
		const div = document.createElement("div");
		div.className = `icon-option ${icon === s ? "selected" : ""}`;
		div.innerHTML = `<i class="fas ${icon}"></i>`;
		div.onclick = () => {
			container
				.querySelectorAll(".icon-option")
				.forEach((el) => el.classList.remove("selected"));
			div.classList.add("selected");
			document.getElementById(i).value = icon;
		};
		container.appendChild(div);
	});
}

window.toggleTypeInput = function (m) {
	const s = document.getElementById(`${m}TypeSelect`);
	const i = document.getElementById(`${m}TypeCustom`);
	if (s.value === "custom") {
		i.style.display = "block";
		i.focus();
	} else {
		i.style.display = "none";
	}
};

function getSafeValue(o, k, d = 0) {
	return o[k] !== null && o[k] !== undefined ? o[k] : d;
}

// --- VIEW & GRID ---
window.switchView = function (view) {
	document
		.querySelectorAll(".view-section")
		.forEach((el) => el.classList.remove("active-view"));
	document
		.querySelectorAll(".nav-item")
		.forEach((el) => el.classList.remove("active"));
	document.getElementById(`view-${view}`).classList.add("active-view");
	document.getElementById(`nav-${view}`).classList.add("active");
	if (view === "map") setTimeout(() => map.invalidateSize(), 200);
};

window.changeDensity = function (val) {
	itemsPerPage = parseInt(val);
	currentPage = 1;
	if (itemsPerPage <= 3) currentViewMode = "detailed";
	else if (itemsPerPage === 6) currentViewMode = "normal";
	else if (itemsPerPage <= 12) currentViewMode = "compact";
	else currentViewMode = "minimal";
	renderList(currentMachines);
};

// --- MAP LOGIC ---
map.on("click", function (e) {
	if (currentUserRole !== "admin") return;
	if (tempClickMarker) {
		map.removeLayer(tempClickMarker);
		tempClickMarker = null;
	}
	const lat = e.latlng.lat.toFixed(6),
		lng = e.latlng.lng.toFixed(6);
	const icon = L.divIcon({
		className: "",
		html: `<div class="marker-wrapper"><div class="pulse-ring" style="background:#2563eb; animation: pulsate 1.5s infinite;"></div><div class="marker-icon" style="background:#2563eb; border: 3px solid white;"><i class="fas fa-plus"></i></div></div>`,
		iconSize: [44, 44],
		iconAnchor: [22, 22],
		popupAnchor: [0, -26],
	});
	tempClickMarker = L.marker([lat, lng], { icon: icon, zIndexOffset: 9999 })
		.addTo(map)
		.bindPopup(
			`<div style="text-align:center; padding:12px; min-width:220px; font-family: 'Plus Jakarta Sans', sans-serif;"><div style="margin-bottom:10px;"><div style="font-weight:700; color:#1e293b; font-size:1rem;">Lokasi Terpilih</div><div style="color:#64748b; font-size:0.85rem; margin-top:4px;"><i class="fas fa-map-pin"></i> ${lat}, ${lng}</div></div><button onclick="openAddModal('${lat}', '${lng}')" style="width:100%; background:#2563eb; color:white; border:none; padding:10px 16px; border-radius:8px; cursor:pointer; font-weight:600; display:flex; align-items:center; justify-content:center; gap:8px;"><i class="fas fa-plus"></i> Tambah Node</button></div>`,
		)
		.openPopup();
});

map.on("popupopen", function (e) {
	const w = e.popup._contentNode.querySelector(".popup-content-data");
	if (!w) return;
	const id = w.getAttribute("data-id"),
		m = currentMachines.find((x) => x.id === id);
	if (m) {
		openedPopupId = id;
		setTimeout(() => drawPopupChart(m), 50);
	}
});

map.on("popupclose", function () {
	if (openedPopupId && mapChartInstances[openedPopupId]) {
		mapChartInstances[openedPopupId].destroy();
		delete mapChartInstances[openedPopupId];
		openedPopupId = null;
	}
});

async function loadStatus() {
	try {
		// [BARU] Load Settings dulu agar filter valid
		await loadSettings();

		const res = await fetch("/api/status");
		if (res.status === 401) window.location.reload();
		if (!res.ok) return;
		const data = await res.json();

		if (!Array.isArray(data)) return;

		// Sorting (Provinsi -> Kota -> ID)
		data.sort((a, b) => {
			const provA = a.province || "zzz";
			const provB = b.province || "zzz";
			if (provA !== provB) return provA.localeCompare(provB);
			const cityA = a.city || "zzz";
			const cityB = b.city || "zzz";
			if (cityA !== cityB) return cityA.localeCompare(cityB);
			return a.id.localeCompare(b.id);
		});

		currentMachines = data;
		updateFilters(data);
		applyFilters(false);
		renderMap(data);

		// Update detail chart if open
		if (openedPopupId) {
			const m = currentMachines.find((x) => x.id === openedPopupId);
			if (m && mapChartInstances[openedPopupId]) updateMapChart(m);
		}
	} catch (err) {
		console.error(err);
	}
}

// [BARU] Load Settings API
async function loadSettings() {
	try {
		const res = await fetch("/api/settings");
		if (res.ok) {
			const conf = await res.json();
			configLatency = conf.latency_threshold;
			configBandwidth = conf.bandwidth_threshold;
		}
	} catch (e) {
		console.error("Gagal load settings", e);
	}
}

// [BARU] Save Settings API
window.openSettingsModal = function () {
	document.getElementById("confLatency").value = configLatency;
	document.getElementById("confBandwidth").value = configBandwidth;
	document.getElementById("settingsModal").style.display = "flex";
};

window.saveSettings = async function () {
	const newLat = parseInt(document.getElementById("confLatency").value);
	const newBw = parseInt(document.getElementById("confBandwidth").value);

	try {
		const res = await fetch("/api/settings", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				latency_threshold: newLat,
				bandwidth_threshold: newBw,
			}),
		});

		if (res.ok) {
			configLatency = newLat;
			configBandwidth = newBw;
			closeModal("settingsModal");
			showToast("Konfigurasi tersimpan!", "success");
			applyFilters(); // Re-apply filter dengan nilai baru
		} else {
			showToast("Gagal menyimpan", "error");
		}
	} catch (e) {
		showToast("Error koneksi", "error");
	}
};

function updateFilters(data) {
	const typeSelect = document.getElementById("typeFilter");
	const provSelect = document.getElementById("provinceFilter");

	// A. Populate Tipe Perangkat (Label)
	const types = new Set();
	data.forEach((m) => {
		if (m.type) types.add(m.type);
	});

	// Helper untuk isi dropdown (biar tidak duplikat kode)
	const populateSelect = (selectEl, items, currentVal) => {
		selectEl.innerHTML = `<option value="all">Semua ${selectEl.id === "typeFilter" ? "Tipe" : "Provinsi"}</option>`;
		items.sort().forEach((item) => {
			const opt = document.createElement("option");
			opt.value = item;
			opt.textContent = item;
			selectEl.appendChild(opt);
		});
		if (items.includes(currentVal)) selectEl.value = currentVal;
	};

	populateSelect(typeSelect, Array.from(types), typeSelect.value);

	// B. Populate Provinsi
	const provinces = new Set();
	data.forEach((m) => {
		if (m.province) provinces.add(m.province);
	});
	populateSelect(provSelect, Array.from(provinces), provSelect.value);

	// C. Populate Kota (Inisialisasi awal)
	// Kita panggil fungsi khusus untuk kota agar sinkron dengan provinsi yang terpilih saat ini
	populateCityFilter(data, true);
}

window.onProvinceChange = function () {
	populateCityFilter(currentMachines, true); // Update opsi kota
	applyFilters(); // Terapkan filter
};

function populateCityFilter(data, forceUpdate = false) {
	const provFilter = document.getElementById("provinceFilter").value;
	const citySelect = document.getElementById("cityFilter");
	const currentCity = citySelect.value;

	// Filter data kota berdasarkan provinsi yang dipilih (jika bukan 'all')
	let relevantData = data;
	if (provFilter !== "all") {
		relevantData = data.filter((m) => m.province === provFilter);
	}

	const cities = new Set();
	relevantData.forEach((m) => {
		if (m.city) cities.add(m.city);
	});
	const sortedCities = Array.from(cities).sort();

	// Cek apakah perlu update DOM (Smart Render)
	const currentOpts = Array.from(citySelect.options)
		.map((o) => o.value)
		.filter((v) => v !== "all");

	if (
		forceUpdate ||
		JSON.stringify(currentOpts) !== JSON.stringify(sortedCities)
	) {
		citySelect.innerHTML = '<option value="all">Semua Kota</option>';
		sortedCities.forEach((c) => {
			const opt = document.createElement("option");
			opt.value = c;
			opt.textContent = c;
			citySelect.appendChild(opt);
		});

		// Restore pilihan jika masih valid
		if (sortedCities.includes(currentCity)) citySelect.value = currentCity;
		else citySelect.value = "all";
	}
}

function updateLocationFilterOptions(data) {
	const select = document.getElementById("locationFilter");
	const currentVal = select.value; // Simpan pilihan user saat ini

	// Ambil lokasi unik
	const locations = new Set();
	data.forEach((m) => {
		if (m.city || m.province) {
			const label =
				m.city && m.province
					? `${m.city}, ${m.province}`
					: m.city || m.province;
			locations.add(label);
		} else {
			locations.add("Lokasi Tidak Terdeteksi");
		}
	});

	// Render Option
	// Kita simpan opsi "Semua Lokasi" dulu
	select.innerHTML = '<option value="all">Semua Lokasi</option>';

	Array.from(locations)
		.sort()
		.forEach((loc) => {
			const option = document.createElement("option");
			option.value = loc;
			option.textContent = loc;
			select.appendChild(option);
		});

	// Kembalikan pilihan user jika opsi tersebut masih ada
	if ([...select.options].some((o) => o.value === currentVal)) {
		select.value = currentVal;
	}
}

window.applyFilters = function (resetPage = true) {
	const searchInput = document
		.getElementById("searchInput")
		.value.toLowerCase()
		.trim();

	// Ambil Value Dropdown
	const typeVal = document.getElementById("typeFilter").value;
	const provVal = document.getElementById("provinceFilter").value;
	const cityVal = document.getElementById("cityFilter").value;

	// Ambil Value Checkbox Issue (Multi-select)
	const checkedIssues = Array.from(
		document.querySelectorAll('input[name="issue"]:checked'),
	).map((cb) => cb.value);

	filteredMachines = currentMachines.filter((m) => {
		// 1. Search
		const matchSearch =
			!searchInput ||
			m.id.toLowerCase().includes(searchInput) ||
			m.host.toLowerCase().includes(searchInput);

		// 2. Dropdown Filters (Exact Match or All)
		const matchType = typeVal === "all" || m.type === typeVal;
		const matchProv = provVal === "all" || m.province === provVal;
		const matchCity = cityVal === "all" || m.city === cityVal;

		// 3. Issue Checkbox Logic (OR Logic antar issue)
		let matchIssue = true;
		if (checkedIssues.length > 0) {
			let hasIssue = false;
			if (checkedIssues.includes("offline") && !m.online) hasIssue = true;
			if (
				checkedIssues.includes("high_latency") &&
				m.online &&
				m.latency_ms > configLatency
			)
				hasIssue = true;
			if (
				checkedIssues.includes("high_traffic") &&
				m.online &&
				(m.rx_rate > configBandwidth || m.tx_rate > configBandwidth)
			)
				hasIssue = true;
			matchIssue = hasIssue;
		}

		return matchSearch && matchType && matchProv && matchCity && matchIssue;
	});

	const countEl = document.getElementById("resultCount");
	if (countEl)
		countEl.textContent = `Menampilkan ${filteredMachines.length} node`;

	if (resetPage) currentPage = 1;
	renderList(filteredMachines);
};

window.resetFilters = function () {
	document.getElementById("searchInput").value = "";
	document.getElementById("typeFilter").value = "all";
	document.getElementById("provinceFilter").value = "all";
	// Trigger onProvinceChange untuk reset kota juga
	onProvinceChange();

	document.querySelectorAll(".filter-cb").forEach((cb) => (cb.checked = false));
	applyFilters();
};

function renderCheckboxGroup(containerId, items, selectedItems) {
	const container = document.getElementById(containerId);
	// Simpan pilihan user saat ini jika selectedItems tidak disediakan
	// (Agar saat re-render karena search, centangan tidak hilang jika masih valid)
	const currentChecked =
		selectedItems ||
		Array.from(container.querySelectorAll("input:checked")).map(
			(cb) => cb.value,
		);

	container.innerHTML = "";

	if (items.length === 0) {
		container.innerHTML =
			'<div style="font-size:0.8rem; color:#94a3b8; padding:5px;">Tidak ada opsi</div>';
		return;
	}

	items.forEach((item) => {
		// Skip jika item kosong/null
		if (!item) return;

		const label = document.createElement("label");
		label.className = "cb-container";

		const isChecked = currentChecked.includes(item) ? "checked" : "";

		label.innerHTML = `
            <input type="checkbox" class="filter-cb" name="${containerId}" value="${item}" ${isChecked} onchange="applyFilters()">
            <span class="checkmark"></span>
            <span class="cb-label">${item}</span>
        `;
		container.appendChild(label);
	});
}

function renderMap(data) {
	const activeIds = new Set();
	data.forEach((m) => {
		if (m.lat && m.lng) {
			activeIds.add(m.id);

			// 1. DETEKSI ISU
			const isOnline = m.online;
			const isHighLat = isOnline && m.latency_ms > configLatency;
			const isHighTraf =
				isOnline &&
				(m.rx_rate > configBandwidth || m.tx_rate > configBandwidth);

			// 2. TENTUKAN WARNA MARKER & ANIMASI
			let markerClass = "status-online"; // Default Hijau
			let pulseClass = "pulse-ring"; // Default Hijau
			let latencyClass = "is-online";

			if (!isOnline) {
				// Prioritas 1: OFFLINE (Merah)
				markerClass = "status-offline";
				pulseClass = "pulse-ring offline";
				latencyClass = "is-offline";
			} else if (isHighLat) {
				// Prioritas 2: HIGH LATENCY (Oranye)
				markerClass = "status-warning";
				pulseClass = "pulse-ring warning";
			} else if (isHighTraf) {
				// Prioritas 3: HIGH TRAFFIC (Biru)
				markerClass = "status-traffic";
				pulseClass = "pulse-ring traffic";
			}

			// 3. GENERATE HTML MARKER
			const iconClass = m.icon || "fa-server";

			// Label bawah marker (Latency text)
			let latencyText = `${getSafeValue(m, "latency_ms")}ms`;
			if (!isOnline) latencyText = "Offline";
			else if (isHighLat) latencyText = `${m.latency_ms}ms (Slow)`;
			else if (isHighTraf) latencyText = `${m.latency_ms}ms (Busy)`;

			const nameHtml = `<div class="marker-name" onclick="openDetailModal('${m.id}', 'status')">${m.id}</div>`;
			const latencyHtml = `<div class="marker-latency ${latencyClass}" onclick="openDetailModal('${m.id}', 'latency')">
                <i class="fas ${isOnline ? "fa-bolt" : "fa-clock"}"></i> ${latencyText}
            </div>`;

			// Struktur HTML Marker
			const htmlContent = `
				<div class="marker-wrapper">
					<div class="${pulseClass}"></div>
					<div class="marker-icon ${markerClass}">
						<i class="fas ${iconClass}"></i>
					</div>
					${nameHtml}
					${latencyHtml}
				</div>`;

			// ... (Sisa logika markerMap & Popup tetap sama seperti sebelumnya) ...

			// [Popup Logic Simple Copy]
			const icon = L.divIcon({
				className: "custom-marker", // Class khusus untuk custom marker
				html: htmlContent,
				iconSize: [44, 44], // Pastikan ukuran sesuai dengan CSS
				iconAnchor: [22, 22], // Anchor di tengah marker
				popupAnchor: [0, -26], // Popup muncul di atas marker
			});

			// Popup HTML generation (Standard)
			const bwHtml =
				m.use_snmp && isOnline
					? `<div style="display:flex; gap:12px; font-size:0.85rem; font-weight:600; color:#475569; margin-bottom:12px; background:#f1f5f9; padding:8px 12px; border-radius:8px; justify-content:center;"><span><i class="fas fa-arrow-down" style="color:#10b981"></i> ${getSafeValue(m, "rx_rate")} K</span><span><i class="fas fa-arrow-up" style="color:#3b82f6"></i> ${getSafeValue(m, "tx_rate")} K</span></div>`
					: "";
			const popupHtml = `<div class="popup-content-data" data-id="${m.id}"><div class="popup-header"><div style="display:flex; justify-content:space-between; align-items:start; margin-bottom:10px;"><div><h4 style="margin:0; color:#0f172a; font-size:1.1rem; font-weight:700;">${m.id}</h4><p style="margin:2px 0 0; color:#64748b; font-size:0.85rem">${m.host}</p></div><div class="status-pill ${isOnline ? "online" : "offline"}">${isOnline ? "ONLINE" : "OFFLINE"}</div></div>${bwHtml}</div><div class="popup-body"><div style="height: 120px; width: 100%; position: relative;" onclick="openDetailModal('${m.id}')"><canvas id="popup-chart-${m.id}"></canvas></div></div></div>`;

			if (markerMap[m.id]) {
				const existing = markerMap[m.id];
				existing.setLatLng([m.lat, m.lng]);
				existing.setIcon(icon);
				if (!existing.getPopup().isOpen()) existing.setPopupContent(popupHtml);
			} else {
				const newMarker = L.marker([m.lat, m.lng], {
					icon: icon,
					// Tambahkan option untuk mencegah dragging jika tidak diperlukan
					draggable: false,
				})
					.bindPopup(popupHtml)
					.addTo(markersLayer);
				markerMap[m.id] = newMarker;
			}
		}
	});
	// Remove old markers
	Object.keys(markerMap).forEach((id) => {
		if (!activeIds.has(id)) {
			markersLayer.removeLayer(markerMap[id]);
			delete markerMap[id];
		}
	});
}

function renderList(data) {
	const container = document.getElementById("cards-container");

	if (data.length === 0) {
		container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #94a3b8;">
            <i class="fas fa-search" style="font-size: 2rem; margin-bottom: 10px;"></i>
            <p>Tidak ditemukan node yang cocok.</p>
        </div>`;
		renderPaginationControls(0, 0);
		return;
	}

	const totalItems = data.length;
	const totalPages = Math.ceil(totalItems / itemsPerPage);
	if (currentPage > totalPages && totalPages > 0) currentPage = totalPages;
	if (currentPage < 1) currentPage = 1;

	container.className = "card-grid";
	if (currentViewMode === "detailed") container.classList.add("view-detailed");
	if (currentViewMode === "compact") container.classList.add("view-compact");
	if (currentViewMode === "minimal") container.classList.add("view-minimal");

	const startIndex = (currentPage - 1) * itemsPerPage;
	const paginatedData = data.slice(startIndex, startIndex + itemsPerPage);

	const adminWrapper = document.getElementById("adminAddBtnWrapper");
	if (adminWrapper)
		adminWrapper.innerHTML =
			currentUserRole === "admin"
				? `<button class="btn-primary" onclick="openAddModal()" style="padding: 8px 12px;"><i class="fas fa-plus"></i></button>`
				: "";

	container.innerHTML = "";
	Object.keys(listChartInstances).forEach((id) => {
		if (listChartInstances[id]) {
			listChartInstances[id].destroy();
			delete listChartInstances[id];
		}
	});

	let lastGroupKey = null;

	paginatedData.forEach((m) => {
		const prov = m.province || "Lainnya";
		const city = m.city || "Tidak Diketahui";

		// Grouping Key: Gabungan Provinsi + Kota untuk mendeteksi perubahan
		const currentGroupKey = `${prov}-${city}`;

		if (currentGroupKey !== lastGroupKey) {
			// Tampilan Header
			const headerHtml = `
                <div style="grid-column: 1 / -1; margin: 20px 0 8px 0; display: flex; align-items: center; gap: 8px; color: #475569; padding-bottom: 4px; border-bottom: 2px solid #f1f5f9;">
                    <div style="font-weight: 700; font-size: 1rem;">${prov}</div>
                    <i class="fas fa-chevron-right" style="font-size: 0.7rem; color: #cbd5e1;"></i>
                    <div style="font-size: 0.95rem; color: #64748b;">${city}</div>
                </div>
            `;
			container.insertAdjacentHTML("beforeend", headerHtml);
			lastGroupKey = currentGroupKey;
		}

		const isOnline = m.online;
		const isHighLat = isOnline && m.latency_ms > configLatency;
		const isHighTraf =
			isOnline && (m.rx_rate > configBandwidth || m.tx_rate > configBandwidth);
		const iconClass = m.icon || "fa-server";
		let cardClass = "online";
		if (!isOnline) {
			cardClass = "offline";
		} else if (isHighLat) {
			cardClass = "issue-latency"; // Card jadi kuning/oranye
		} else if (isHighTraf) {
			cardClass = "issue-traffic"; // Card jadi biru
		}
		const statusHtml = isOnline
			? `<div class="status-pill online"><div class="dot-indicator"></div> ONLINE</div>`
			: `<div class="status-pill offline"><div class="dot-indicator"></div> OFFLINE</div>`;
		const latencyColor = isHighLat ? "#d97706" : "#eab308"; // Darker orange if issue
		const latencyText = isOnline
			? `<i class="fas fa-bolt" style="color:${latencyColor}"></i> ${getSafeValue(m, "latency_ms")} ms`
			: `<i class="fas fa-clock"></i> ${getSafeValue(m, "last_seen", "Never")}`;
		const telemetryHtml =
			m.use_snmp && isOnline
				? `<div class="net-stat" id="telemetry-${m.id}"><span><i class="fas fa-arrow-down" style="color:#10b981"></i> ${getSafeValue(m, "rx_rate")} K</span><span><i class="fas fa-arrow-up" style="color:#3b82f6"></i> ${getSafeValue(m, "tx_rate")} K</span></div>`
				: m.use_snmp
					? `<div class="monitoring-stopped">Stopped</div>`
					: `<div class="ping-only">Ping Only</div>`;
		const adminBtns =
			currentUserRole === "admin"
				? `<button class="btn-card-action" onclick="openEditModal('${m.id}')"><i class="fas fa-pen"></i></button><button class="btn-card-action btn-action-del" onclick="openDeleteModal('${m.id}')"><i class="fas fa-trash"></i></button>`
				: "";
		let issueBadgesHtml = "";
		if (isOnline) {
			if (isHighLat) {
				issueBadgesHtml += `<span class="badge-issue warning"><i class="fas fa-exclamation-triangle"></i> High Latency</span>`;
			}
			if (isHighTraf) {
				issueBadgesHtml += `<span class="badge-issue traffic"><i class="fas fa-tachometer-alt"></i> High Traffic</span>`;
			}
		}

		const html = `
    <div id="card-${m.id}" data-id="${m.id}" class="card card-node ${cardClass}">
        <div class="card-top">
            <div class="card-icon" id="icon-${m.id}"><i class="fas ${iconClass}"></i></div>
            <div class="card-info">
                <h4>${m.id}</h4>
                <p id="info-${m.id}">${m.type} - ${m.host}</p>
                <div class="issue-badges-container">${issueBadgesHtml}</div>
            </div>
        </div>
        <div class="metric-row">
            ${statusHtml}
            <span id="latency-${m.id}">${latencyText}</span>
        </div>
        <div id="telemetry-container">${telemetryHtml}</div>
        <div class="chart-wrapper" onclick="openDetailModal('${m.id}', 'latency')" title="Klik untuk perbesar">
            <canvas id="chart-${m.id}"></canvas>
        </div>
        <div class="card-actions">
            <button class="btn-card-action" onclick="openDetailModal('${m.id}', 'status')" style="color:#7c3aed; border-color:#7c3aed; background:#f5f3ff;"><i class="fas fa-history"></i></button>
            <button class="btn-card-action" onclick="openDetailModal('${m.id}', 'latency')" style="color:var(--primary); border-color:var(--primary); background:#eff6ff;"><i class="fas fa-chart-line"></i></button>
            ${adminBtns}
        </div>
    </div>`;

		container.insertAdjacentHTML("beforeend", html);
		if (currentViewMode !== "compact" && currentViewMode !== "minimal")
			initListChart(m);
	});

	renderPaginationControls(totalPages, totalItems);
}

function renderPaginationControls(pages, items) {
	const c = document.getElementById("pagination-controls");
	if (items === 0) {
		c.innerHTML = '<div class="pagination-info">Tidak ada data.</div>';
		return;
	}
	let h = `<button class="pagination-btn" onclick="changePage(${currentPage - 1})" ${currentPage === 1 ? "disabled" : ""}><i class="fas fa-chevron-left"></i></button>`;
	for (let i = 1; i <= pages; i++) {
		if (
			i === 1 ||
			i === pages ||
			(i >= currentPage - 1 && i <= currentPage + 1)
		)
			h += `<button class="pagination-btn ${i === currentPage ? "active" : ""}" onclick="changePage(${i})">${i}</button>`;
		else if (i === currentPage - 2 || i === currentPage + 2)
			h += `<span>...</span>`;
	}
	h += `<button class="pagination-btn" onclick="changePage(${currentPage + 1})" ${currentPage === pages ? "disabled" : ""}><i class="fas fa-chevron-right"></i></button>`;
	c.innerHTML = h;
}
window.changePage = function (p) {
	if (p < 1) return;
	currentPage = p;
	// PENTING: Render filteredMachines, bukan currentMachines (agar hasil search tidak hilang saat pindah hal)
	renderList(filteredMachines);
};

// --- CHARTS ---
function initListChart(m) {
	const el = document.getElementById(`chart-${m.id}`);
	if (!el) return;
	if (listChartInstances[m.id]) listChartInstances[m.id].destroy();
	const ctx = el.getContext("2d");
	let limit = currentViewMode === "normal" ? 10 : 30; // 30 DETIK (10 data)
	const d = m.history.slice(-limit);
	listChartInstances[m.id] = new Chart(ctx, {
		type: "line",
		data: {
			labels: d.map((h) => h.time.split(" ")[1]),
			datasets: [
				{
					label: "Latency",
					data: d.map((h) =>
						h.status === "OFFLINE" ? null : getSafeValue(h, "latency"),
					),
					borderColor: "#2563eb",
					backgroundColor: (c) => {
						const g = c.chart.ctx.createLinearGradient(0, 0, 0, 80);
						g.addColorStop(0, "rgba(37,99,235,0.15)");
						g.addColorStop(1, "rgba(37,99,235,0)");
						return g;
					},
					borderWidth: 2,
					pointRadius: 2.5,
					pointBackgroundColor: "#ffffff",
					pointBorderColor: "#2563eb",
					pointBorderWidth: 1.5,
					fill: true,
					tension: 0.4,
				},
			],
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			animation: false,
			plugins: {
				legend: { display: false },
				tooltip: {
					enabled: true,
					mode: "index",
					intersect: false,
					displayColors: false,
					callbacks: {
						title: () => null,
						label: (c) => `${c.formattedValue} ms`,
					},
				},
			},
			scales: {
				x: { display: false },
				y: { display: false, beginAtZero: true, suggestedMax: 100 },
			},
			layout: { padding: { left: -5, right: -5, bottom: -5, top: 5 } },
		},
	});
}
function drawPopupChart(m) {
	const el = document.getElementById(`popup-chart-${m.id}`);
	if (!el) return;
	const ctx = el.getContext("2d");
	const d = m.history.slice(-20);
	mapChartInstances[m.id] = new Chart(ctx, {
		type: "line",
		data: {
			labels: d.map((h) => h.time.split(" ")[1]),
			datasets: [
				{
					data: d.map((h) =>
						h.status === "OFFLINE" ? null : getSafeValue(h, "latency"),
					),
					borderColor: "#2563eb",
					borderWidth: 2,
					backgroundColor: "rgba(37,99,235,0.1)",
					pointRadius: 2,
					pointBackgroundColor: "#ffffff",
					pointBorderColor: "#2563eb",
					fill: true,
					tension: 0.4,
				},
			],
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			animation: false,
			layout: { padding: { top: 5 } },
			plugins: { legend: { display: false }, tooltip: { enabled: false } },
			scales: {
				x: {
					display: true,
					ticks: { maxTicksLimit: 4, font: { size: 8 } },
					grid: { display: false },
				},
				y: {
					display: true,
					ticks: { display: true, font: { size: 8 }, maxTicksLimit: 3 },
					grid: { drawBorder: false },
				},
			},
		},
	});
}
function updateMapChart(m) {
	const c = mapChartInstances[m.id];
	if (!c) return;
	const d = m.history.slice(-20);
	c.data.labels = d.map((h) => h.time.split(" ")[1]);
	c.data.datasets[0].data = d.map((h) =>
		h.status === "OFFLINE" ? null : getSafeValue(h, "latency"),
	);
	c.update("none");
}

// --- MODAL & CRUD ---
window.openDetailModal = async function (id, defaultMetric = "latency") {
	const m = currentMachines.find((x) => x.id === id);
	if (!m) return;
	currentDetailId = id;
	document.getElementById("detailTitle").textContent = `${m.id}`;
	document.getElementById("detailHost").textContent = `${m.host} (${m.type})`;
	const ms = document.getElementById("metricSelect");
	const bo = ms.querySelector('option[value="bandwidth"]');
	if (m.use_snmp) {
		bo.hidden = false;
		bo.disabled = false;
	} else {
		bo.hidden = true;
		bo.disabled = true;
		if (defaultMetric === "bandwidth") defaultMetric = "latency";
	}
	document.getElementById("detailModal").style.display = "flex";
	const rs = document.getElementById("rangeSelect");
	ms.value = defaultMetric;
	if (!rs.value) rs.value = "5";
	ms.disabled = true;
	rs.disabled = true;
	await updateDetailView();
	ms.disabled = false;
	rs.disabled = false;
};

window.updateDetailView = async function () {
	if (!currentDetailId) return;
	const metric = document.getElementById("metricSelect").value;
	const rangeMinutes = parseInt(document.getElementById("rangeSelect").value);
	const m = currentMachines.find((x) => x.id === currentDetailId);
	document.getElementById("chartLoading").style.display = "block";
	const cw = document.getElementById("chartWrapper");
	const tw = document.getElementById("historyListWrapper");
	const tb = document.getElementById("historyTableBody");
	const ctx = document.getElementById("detailChart").getContext("2d");
	if (metric === "status") {
		cw.style.display = "none";
		tw.style.display = "block";
		if (detailChartInstance) detailChartInstance.destroy();
	} else {
		cw.style.display = "block";
		tw.style.display = "none";
		if (detailChartInstance) detailChartInstance.clear();
	}
	try {
		const res = await fetch("/api/history", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ id: currentDetailId, minutes: rangeMinutes }),
		});
		const hData = await res.json();
		document.getElementById("chartLoading").style.display = "none";
		if (metric === "status") {
			tb.innerHTML = "";
			const distinct = [];
			let last = null;
			hData.forEach((h) => {
				if (h.status !== last) {
					distinct.push(h);
					last = h.status;
				}
			});
			const rev = distinct.reverse();
			if (rev.length === 0) {
				tb.innerHTML =
					'<tr><td colspan="3" style="text-align:center;">Belum ada perubahan.</td></tr>';
			} else {
				rev.forEach((h) => {
					const iso = h.status === "ONLINE";
					const cls = iso ? "log-online" : "log-offline";
					const lat = h.latency ? `${h.latency} ms` : "-";
					const det = iso
						? m.use_snmp
							? `Latency: ${lat} | DL: ${h.rx || 0}K / UL: ${h.tx || 0}K`
							: `Latency: ${lat}`
						: `Unreachable`;
					const row = `<tr><td>${h.time}</td><td><span class="log-badge ${cls}">${h.status}</span></td><td style="color:#64748b;">${det}</td></tr>`;
					tb.insertAdjacentHTML("beforeend", row);
				});
			}
			return;
		}
		if (detailChartInstance) detailChartInstance.destroy();
		const labels = hData.map((h) =>
			rangeMinutes > 1440 ? h.time : h.time.split(" ")[1],
		);
		const datasets = [];
		if (metric === "latency")
			datasets.push({
				label: "Latency",
				data: hData.map((h) =>
					h.status === "OFFLINE" ? null : getSafeValue(h, "latency"),
				),
				borderColor: "#2563eb",
				backgroundColor: "rgba(37,99,235,0.1)",
				fill: true,
				tension: 0.2,
				pointRadius: hData.length > 100 ? 0 : 3,
			});
		else if (metric === "bandwidth" && m.use_snmp) {
			datasets.push({
				label: "DL",
				data: hData.map((h) =>
					h.status === "OFFLINE" ? null : getSafeValue(h, "rx"),
				),
				borderColor: "#10b981",
				tension: 0.2,
				pointRadius: 0,
			});
			datasets.push({
				label: "UL",
				data: hData.map((h) =>
					h.status === "OFFLINE" ? null : getSafeValue(h, "tx"),
				),
				borderColor: "#8b5cf6",
				tension: 0.2,
				pointRadius: 0,
			});
		}
		detailChartInstance = new Chart(ctx, {
			type: "line",
			data: { labels, datasets },
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: "index", intersect: false },
				animation: false,
				scales: { x: { grid: { display: false } }, y: { beginAtZero: true } },
			},
		});
	} catch (e) {
		console.error(e);
		document.getElementById("chartLoading").textContent = "Gagal memuat.";
	}
};

window.openAddModal = function (lat = 0, lng = 0) {
	document.getElementById("addLat").value = parseFloat(lat).toFixed(6);
	document.getElementById("addLng").value = parseFloat(lng).toFixed(6);
	document.getElementById("addId").value = "";
	document.getElementById("addHost").value = "";
	document.getElementById("addTypeSelect").value = "Server";
	toggleTypeInput("add");
	renderIconSelector("addIconGrid", "addIcon", "fa-server");
	document.getElementById("addModal").style.display = "flex";
	if (tempClickMarker) {
		map.removeLayer(tempClickMarker);
		tempClickMarker = null;
	}
};
window.submitAdd = async function () {
	const id = document.getElementById("addId").value.trim(),
		host = document.getElementById("addHost").value.trim();

	if (!id || !host) {
		showToast("Isi Nama dan Host", "error");
		return;
	}

	const type =
		document.getElementById("addTypeSelect").value === "custom"
			? document.getElementById("addTypeCustom").value
			: document.getElementById("addTypeSelect").value;

	// Ambil value checkbox (1 atau 0)
	const notify_down = document.getElementById("addNotifyDown").checked ? 1 : 0;
	const notify_traffic = document.getElementById("addNotifyTraffic").checked
		? 1
		: 0;
	const notify_email = document.getElementById("addNotifyEmail").checked
		? 1
		: 0;

	const lat = document.getElementById("addLat").value || 0;
	const lng = document.getElementById("addLng").value || 0;

	try {
		const res = await fetch("/api/add", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				id,
				host,
				type,
				icon: document.getElementById("addIcon").value,
				use_snmp: document.getElementById("addUseSnmp").value,
				lat,
				lng,
				notify_down,
				notify_traffic,
				notify_email,
			}),
		});

		// [FIX] Baca respons JSON dari backend
		const data = await res.json();

		if (res.ok) {
			closeModal("addModal");
			showToast("Berhasil Menambahkan Node", "success");
			loadStatus();
		} else {
			// [FIX] Tampilkan pesan error spesifik (misal: "Node ID sudah ada")
			showToast(data.error || "Gagal menambahkan node", "error");
		}
	} catch (e) {
		console.error(e);
		showToast("Terjadi kesalahan koneksi", "error");
	}
};

window.openEditModal = function (id) {
	const m = currentMachines.find((x) => x.id === id);
	if (!m) return;
	document.getElementById("editId").value = m.id;
	document.getElementById("editHost").value = m.host;
	document.getElementById("editIcon").value = m.icon;
	document.getElementById("editUseSnmp").value = m.use_snmp ? "1" : "0";
	document.getElementById("editLat").value = m.lat;
	document.getElementById("editLng").value = m.lng;
	const sel = document.getElementById("editTypeSelect");
	if (["Server", "Router"].includes(m.type)) {
		sel.value = m.type;
	} else {
		sel.value = "custom";
		document.getElementById("editTypeCustom").value = m.type;
	}
	toggleTypeInput("edit");
	document.getElementById("editNotifyDown").checked = m.notify_down === 1;
	document.getElementById("editNotifyTraffic").checked = m.notify_traffic === 1;
	document.getElementById("editNotifyEmail").checked = m.notify_email === 1;
	renderIconSelector("editIconGrid", "editIcon", m.icon);
	document.getElementById("editModal").style.display = "flex";
};

window.submitEdit = async function () {
	const notify_down = document.getElementById("editNotifyDown").checked ? 1 : 0;
	const notify_traffic = document.getElementById("editNotifyTraffic").checked
		? 1
		: 0;
	const notify_email = document.getElementById("editNotifyEmail").checked
		? 1
		: 0;

	const type =
		document.getElementById("editTypeSelect").value === "custom"
			? document.getElementById("editTypeCustom").value
			: document.getElementById("editTypeSelect").value;

	const lat = document.getElementById("editLat").value || 0;
	const lng = document.getElementById("editLng").value || 0;

	try {
		const res = await fetch("/api/edit", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				id: document.getElementById("editId").value,
				host: document.getElementById("editHost").value,
				type,
				icon: document.getElementById("editIcon").value,
				use_snmp: document.getElementById("editUseSnmp").value,
				lat,
				lng,
				notify_down,
				notify_traffic,
				notify_email,
			}),
		});

		// [FIX] Baca respons JSON dari backend
		const data = await res.json();

		if (res.ok) {
			closeModal("editModal");
			showToast("Node Berhasil Diupdate", "success");
			loadStatus();
		} else {
			// [FIX] Tampilkan pesan error spesifik (misal: "IP Address sudah digunakan")
			showToast(data.error || "Gagal mengupdate node", "error");
		}
	} catch (e) {
		console.error(e);
		showToast("Terjadi kesalahan koneksi", "error");
	}
};

window.openDeleteModal = function (id) {
	document.getElementById("delTargetName").textContent = id;
	document.getElementById("delTargetId").value = id;
	document.getElementById("deleteModal").style.display = "flex";
};
window.submitDelete = async function () {
	try {
		await fetch("/api/remove", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				id: document.getElementById("delTargetId").value,
			}),
		});
		closeModal("deleteModal");
		showToast("Deleted", "success");
		loadStatus();
	} catch (e) {
		showToast("Gagal", "error");
	}
};

window.closeModal = function (id) {
	document.getElementById(id).style.display = "none";
	if (id === "detailModal") currentDetailId = null;
};
function showToast(m, t) {
	const d = document.createElement("div");
	d.className = `toast ${t}`;
	d.textContent = m;
	document.getElementById("toast-container").appendChild(d);
	setTimeout(() => d.remove(), 3000);
}
window.onclick = function (e) {
	if (e.target.classList.contains("modal")) {
		e.target.style.display = "none";
		if (e.target.id === "detailModal") currentDetailId = null;
	}
};

setInterval(() => {
	loadStatus();
	fetchNotifications();
}, 3000);
loadStatus();
fetchNotifications();
