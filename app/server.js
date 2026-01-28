require("dotenv").config({ path: "../.env" }); // Load .env dari root
const express = require("express");
const session = require("express-session");
const axios = require("axios");
const path = require("path");

// [UPDATE] Konfigurasi Dotenv Fleksibel
// 1. Coba load default (current dir) -> Untuk Docker (/app/.env)
require("dotenv").config();
// 2. Coba load parent dir -> Untuk Local Dev (../.env)
require("dotenv").config({ path: path.join(__dirname, "../.env") });

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API = process.env.PYTHON_API_URL || "http://127.0.0.1:5000";
const SESSION_SECRET = process.env.SESSION_SECRET || "unsafe-secret";

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, "public"))); // Serve HTML/CSS/JS

app.use(
	session({
		secret: SESSION_SECRET,
		resave: false,
		saveUninitialized: false,
		cookie: { secure: false, maxAge: 86400000 },
	}),
);

// Auth Middleware
function ensureAuthenticated(req, res, next) {
	if (req.session.user) {
		return next();
	}
	res.redirect("/login");
}
function ensureAdmin(req, res, next) {
	if (req.session.user?.role === "admin") return next();
	res.status(403).json({ error: "Access Denied: Admin only" });
}

function preventCache(req, res, next) {
	res.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
	res.set("Pragma", "no-cache");
	res.set("Expires", "0");
	next();
}

// --- ROUTES ---

// Halaman Login
app.get("/login", (req, res) => {
	if (req.session.user) {
		return res.redirect("/");
	}
	// Tambahkan preventCache juga di login agar saat back dari dashboard tidak kembali ke form login yang terisi
	res.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
	res.sendFile(path.join(__dirname, "public", "login.html"));
});

// Halaman Utama
app.get("/", ensureAuthenticated, preventCache, (req, res) => {
	res.sendFile(path.join(__dirname, "public", "dashboard.html"));
});

// API Auth (Login ke Backend LDAP)
app.post("/auth/login", async (req, res) => {
	try {
		const apiRes = await axios.post(`${PYTHON_API}/api/auth/login`, req.body);
		if (apiRes.data.success) {
			req.session.user = apiRes.data.user;
			res.json({ success: true });
		}
	} catch (e) {
		res.status(401).json(e.response?.data || { message: "Login Failed" });
	}
});

// Logout
app.get("/auth/logout", (req, res) => {
	req.session.destroy((err) => {
		if (err) {
			console.error("Logout error:", err);
			return res.redirect("/");
		}
		// Hapus cookie session di browser
		res.clearCookie("connect.sid");
		res.redirect("/login");
	});
});

// API Proxy Helper
const proxy = async (method, path, req, res) => {
	try {
		const response = await axios({
			method,
			url: `${PYTHON_API}${path}`,
			data: req.body,
		});
		res.json(response.data);
	} catch (e) {
		res.status(500).json({ error: "Backend Error" });
	}
};

// Proxies
app.get("/api/me", ensureAuthenticated, (req, res) =>
	res.json(req.session.user),
);
// ...
app.get("/api/alerts", ensureAuthenticated, (req, res) =>
	proxy("get", "/api/alerts", req, res),
);
app.post("/api/alerts/read", ensureAuthenticated, (req, res) =>
	proxy("post", "/api/alerts/read", req, res),
);
// ...
app.get("/api/status", ensureAuthenticated, (req, res) =>
	proxy("get", "/status", req, res),
);
app.post("/api/history", ensureAuthenticated, (req, res) =>
	proxy("post", "/api/history", req, res),
);
app.get("/api/users", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("get", "/api/users", req, res),
);
app.post("/api/add", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/add", req, res),
);
app.post("/api/edit", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/edit", req, res),
);
app.post("/api/remove", ensureAuthenticated, ensureAdmin, (req, res) =>
	proxy("post", "/remove", req, res),
);

app.listen(PORT, () => console.log(`Gateway running on port ${PORT}`));
