require("dotenv").config({ path: "../.env" });
const express = require("express");
const session = require("express-session");
const axios = require("axios");
const path = require("path");

require("dotenv").config();
require("dotenv").config({ path: path.join(__dirname, "../.env") });

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API = process.env.PYTHON_API_URL || "http://127.0.0.1:5000";
const SESSION_SECRET = process.env.SESSION_SECRET || "unsafe-secret";

// OIDC Config
const OIDC_AUTH_URL = process.env.OIDC_AUTH_URL;
const OIDC_CLIENT_ID = process.env.OIDC_CLIENT_ID;
const OIDC_REDIRECT_URI =
	process.env.OIDC_REDIRECT_URI || "http://localhost:3000/auth/callback";

const OIDC_LOGOUT_URL = process.env.OIDC_LOGOUT_URL;

// Turnstile Config
const TURNSTILE_SECRET_KEY = process.env.TURNSTILE_SECRET_KEY;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// [BARU] Middleware Cache Control yang Lebih Agresif
function preventCache(req, res, next) {
	res.set(
		"Cache-Control",
		"no-store, no-cache, must-revalidate, proxy-revalidate",
	);
	res.set("Pragma", "no-cache");
	res.set("Expires", "0");
	res.set("Surrogate-Control", "no-store");
	next();
}

// [PENTING] Blokir akses langsung ke file dashboard.html (Security Fix)
app.use("/dashboard.html", (req, res) => {
	res.redirect("/");
});

// Setup Static Folder
app.use(express.static(path.join(__dirname, "public")));

app.use(
	session({
		secret: SESSION_SECRET,
		resave: false,
		saveUninitialized: false,
		cookie: { secure: false, maxAge: 86400000 },
	}),
);

// Middleware Auth
function ensureAuthenticated(req, res, next) {
	if (req.session.user) return next();
	res.redirect("/login");
}
function ensureAdmin(req, res, next) {
	if (req.session.user?.role === "admin") return next();
	res.status(403).json({ error: "Access Denied" });
}

// --- ROUTES ---

// Route Login
app.get("/login", preventCache, (req, res) => {
	if (req.session.user) return res.redirect("/");
	res.sendFile(path.join(__dirname, "public", "login.html"));
});

app.post("/auth/start", async (req, res) => {
	const { turnstileToken } = req.body;
	if (!turnstileToken)
		return res.status(400).json({ success: false, message: "CAPTCHA missing" });

	try {
		const formData = new URLSearchParams();
		formData.append("secret", TURNSTILE_SECRET_KEY);
		formData.append("response", turnstileToken);

		const verifyRes = await axios.post(
			"https://challenges.cloudflare.com/turnstile/v0/siteverify",
			formData,
		);

		if (!verifyRes.data.success)
			return res
				.status(400)
				.json({ success: false, message: "CAPTCHA validation failed" });

		if (!OIDC_AUTH_URL || !OIDC_CLIENT_ID)
			return res
				.status(500)
				.json({ success: false, message: "Server config missing" });

		const params = new URLSearchParams({
			client_id: OIDC_CLIENT_ID,
			redirect_uri: OIDC_REDIRECT_URI,
			response_type: "code",
			scope: "openid profile email groups",
		});
		res.json({
			success: true,
			redirectUrl: `${OIDC_AUTH_URL}?${params.toString()}`,
		});
	} catch (e) {
		res.status(500).json({ success: false, message: "Internal Server Error" });
	}
});

app.get("/auth/callback", async (req, res) => {
	const { code, error } = req.query;
	if (error) return res.redirect(`/login?error=${encodeURIComponent(error)}`);
	if (!code) return res.redirect("/login?error=no_code");

	try {
		const apiRes = await axios.post(`${PYTHON_API}/api/auth/login`, { code });
		if (apiRes.data.success) {
			req.session.user = apiRes.data.user;
			res.redirect("/");
		} else {
			throw new Error("Backend rejected login");
		}
	} catch (e) {
		const msg = e.response?.data?.message || "Login Failed";
		res.redirect(`/login?error=${encodeURIComponent(msg)}`);
	}
});

app.get("/auth/logout", (req, res) => {
	req.session.destroy((err) => {
		res.clearCookie("connect.sid");

		res.set(
			"Cache-Control",
			"no-store, no-cache, must-revalidate, proxy-revalidate",
		);

		if (OIDC_LOGOUT_URL) {
			return res.redirect(OIDC_LOGOUT_URL);
		}

		res.redirect("/login");
	});
});

app.get("/", ensureAuthenticated, preventCache, (req, res) => {
	res.sendFile(path.join(__dirname, "public", "dashboard.html"));
});

const proxy = async (method, path, req, res) => {
	try {
		const headers = {};

		if (req.session.user) {
			headers["X-User-Role"] = req.session.user.role || "user";

			const groups = req.session.user.groups || [];
			headers["X-User-Groups"] = JSON.stringify(groups);

			headers["X-User-Name"] =
				req.session.user.preferred_username ||
				req.session.user.email ||
				req.session.user.sub ||
				"unknown";
		}

		const response = await axios({
			method,
			url: `${PYTHON_API}${path}`,
			data: req.body,
			headers: headers,
		});
		res.status(response.status).json(response.data);
	} catch (e) {
		// ... (error handling tetap sama)
		if (e.response) {
			res.status(e.response.status).json(e.response.data);
		} else {
			res.status(500).json({ error: "Gateway Error" });
		}
	}
};

app.get("/api/me", ensureAuthenticated, preventCache, (req, res) =>
	res.json(req.session.user),
);
app.get("/api/alerts", ensureAuthenticated, preventCache, (req, res) =>
	proxy("get", "/api/alerts", req, res),
);
app.post("/api/alerts/read", ensureAuthenticated, (req, res) =>
	proxy("post", "/api/alerts/read", req, res),
);
app.post("/api/alerts/clear", ensureAuthenticated, (req, res) =>
	proxy("post", "/api/alerts/clear", req, res),
);

app.get("/api/status", ensureAuthenticated, preventCache, (req, res) =>
	proxy("get", "/api/status", req, res),
);

// Route Proxy untuk HQ
app.get("/api/hq", ensureAuthenticated, preventCache, (req, res) =>
	proxy("get", "/api/hq", req, res),
);

app.post("/api/hq", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/api/hq", req, res),
);

app.post("/api/history", ensureAuthenticated, (req, res) =>
	proxy("post", "/api/history", req, res),
);
app.get(
	"/api/users",
	ensureAuthenticated,
	ensureAdmin,
	preventCache,
	(req, res) => proxy("get", "/api/users", req, res),
);
app.post("/api/add", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/api/add", req, res),
);
app.post("/api/edit", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/edit", req, res),
);
app.post("/api/remove", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/remove", req, res),
);
app.get("/api/settings", ensureAuthenticated, preventCache, (req, res) =>
	proxy("get", "/api/settings", req, res),
);

app.post("/api/settings", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/api/settings", req, res),
);

// --- [BARU] GEO RESTRICTION ROUTES ---
app.get(
	"/api/admin/authentik-groups",
	ensureAuthenticated,
	ensureAdmin,
	preventCache,
	(req, res) => proxy("get", "/api/admin/authentik-groups", req, res),
);
app.get(
	"/api/admin/provinces",
	ensureAuthenticated,
	ensureAdmin,
	preventCache,
	(req, res) => proxy("get", "/api/admin/provinces", req, res),
);
app.get(
	"/api/admin/province-rules",
	ensureAuthenticated,
	ensureAdmin,
	preventCache,
	(req, res) => proxy("get", "/api/admin/province-rules", req, res),
);
app.post(
	"/api/admin/province-rules",
	ensureAuthenticated,
	ensureAdmin,
	(req, res) => proxy("post", "/api/admin/province-rules", req, res),
);

app.listen(PORT, () => console.log(`Gateway running on port ${PORT}`));
