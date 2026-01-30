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

// Edit Group Handler
function openEditGroup(pk, name) {
	const form = document.getElementById("form-edit-group");
	const inputName = document.getElementById("edit-group-name");

	if (form && inputName) {
		form.action = "/group/edit/" + pk;
		inputName.value = name;
		openModal("modal-edit-group");
	}
}

function openEditApp(pk, name, url, redirectUris) {
	const form = document.getElementById("form-edit-app");
	const inputName = document.getElementById("edit-app-name");
	const inputUrl = document.getElementById("edit-app-url");
	const inputRedirects = document.getElementById("edit-app-redirects");

	if (form) {
		form.action = "/app/edit/" + pk;
		if (inputName) inputName.value = name;
		if (inputUrl) inputUrl.value = url;
		if (inputRedirects) inputRedirects.value = redirectUris || "";

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
