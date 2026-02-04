// Tab Navigation Logic
function openTab(tabId) {
	document
		.querySelectorAll(".tab-content")
		.forEach((el) => el.classList.remove("active"));
	document
		.querySelectorAll(".tab-btn")
		.forEach((el) => el.classList.remove("active"));

	const targetContent = document.getElementById(tabId);
	if (targetContent) {
		targetContent.classList.add("active");
	}

	if (event && event.currentTarget) {
		event.currentTarget.classList.add("active");
	}
}

// Modal Helpers
function closeModal(modalId) {
	document.getElementById(modalId).style.display = "none";
}

function openModal(modalId) {
	document.getElementById(modalId).style.display = "flex";
}

function openEditGroup(pk, name, parentPks) {
	const form = document.getElementById("form-edit-group");
	const inputName = document.getElementById("edit-group-name");
	const selectParents = document.getElementById("edit-group-parents"); // [BARU]

	if (form && inputName) {
		form.action = "/group/edit/" + pk;
		inputName.value = name;

		// [LOGIK BARU] Handle Multiple Selection
		if (selectParents) {
			// 1. Reset selection
			for (let i = 0; i < selectParents.options.length; i++) {
				selectParents.options[i].selected = false;
				selectParents.options[i].disabled = false; // Reset disabled status
			}

			// 2. Disable opsi "Diri Sendiri" agar tidak loop
			for (let i = 0; i < selectParents.options.length; i++) {
				if (selectParents.options[i].value === pk) {
					selectParents.options[i].disabled = true;
				}
			}

			// 3. Select parents yang sudah ada
			if (parentPks && Array.isArray(parentPks)) {
				for (let i = 0; i < selectParents.options.length; i++) {
					if (parentPks.includes(selectParents.options[i].value)) {
						selectParents.options[i].selected = true;
					}
				}
			}
		}

		openModal("modal-edit-group");
	}
}

function openEditApp(pk, name, url, redirectUris, boundGroupIds) {
	const form = document.getElementById("form-edit-app");
	const inputName = document.getElementById("edit-app-name");
	const inputUrl = document.getElementById("edit-app-url");
	const inputRedirects = document.getElementById("edit-app-redirects");
	const selectGroups = document.getElementById("edit-app-groups"); // Input baru

	if (form) {
		// 1. Set Action URL & Text Inputs
		form.action = "/app/edit/" + pk;
		if (inputName) inputName.value = name;
		if (inputUrl) inputUrl.value = url;
		if (inputRedirects) inputRedirects.value = redirectUris || "";

		// 2. Handle Group Selection (Multi-select Logic)
		if (selectGroups) {
			// Reset semua pilihan terlebih dahulu
			for (let i = 0; i < selectGroups.options.length; i++) {
				selectGroups.options[i].selected = false;
			}

			// Jika ada data boundGroupIds (array), pilih opsi yang sesuai
			if (boundGroupIds && Array.isArray(boundGroupIds)) {
				for (let i = 0; i < selectGroups.options.length; i++) {
					// Jika value option ada di dalam array boundGroupIds, set selected=true
					if (boundGroupIds.includes(selectGroups.options[i].value)) {
						selectGroups.options[i].selected = true;
					}
				}
			}
		}

		openModal("modal-edit-app");
	}
}

// Edit User Handler
function openEditUser(pk, name, email) {
	const form = document.getElementById("form-edit-user");
	const inputName = document.getElementById("edit-name");
	const inputEmail = document.getElementById("edit-email");

	if (form) {
		form.action = "/user/edit/" + pk;
		if (inputName) inputName.value = name;
		if (inputEmail) inputEmail.value = email;
		openModal("modal-edit-user");
	}
}

// Close modal if clicked outside content
window.onclick = function (event) {
	if (event.target.classList.contains("modal")) {
		event.target.style.display = "none";
	}
};

// Default Tab on Load
document.addEventListener("DOMContentLoaded", () => {
	if (!document.querySelector(".tab-content.active")) {
		openTab("tab-users");
	}
});

function openAppInfo(name, clientId, clientSecret, issuer, authUrl, tokenUrl) {
	document.getElementById("info-app-name").value = name;
	document.getElementById("info-client-id").value = clientId;
	document.getElementById("info-client-secret").value = clientSecret;
	document.getElementById("info-issuer").value = issuer;
	document.getElementById("info-auth-url").value = authUrl;
	document.getElementById("info-token-url").value = tokenUrl;

	openModal("modal-app-info");
}

function copyToClipboard(elementId) {
	const copyText = document.getElementById(elementId);
	copyText.select();
	copyText.setSelectionRange(0, 99999); // Untuk mobile

	try {
		navigator.clipboard.writeText(copyText.value);

		// Efek visual tombol berubah jadi centang sebentar
		const btn = copyText.nextElementSibling;
		const originalHtml = btn.innerHTML;
		btn.innerHTML = '<i class="fas fa-check" style="color: green;"></i>';
		setTimeout(() => {
			btn.innerHTML = originalHtml;
		}, 1500);
	} catch (err) {
		console.error("Failed to copy", err);
	}
}
