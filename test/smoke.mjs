// Node.js smoke test for the FastAPI auth API (Node 18+, no dependencies).
// Usage:  TEST_EMAIL=you@gmail.com TEST_PASSWORD=secret123 npm test
const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const email = process.env.TEST_EMAIL;
const password = process.env.TEST_PASSWORD;

if (!email || !password) {
  console.error("Set TEST_EMAIL and TEST_PASSWORD (a real address you control) before running.");
  process.exit(1);
}

let failed = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name} ${extra}`);
  if (!ok) failed++;
};

async function call(method, path, { body, token } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: res.status, data };
}

// Stage 2
let r = await call("GET", "/public/info");
check("GET /public/info -> 200", r.status === 200);
r = await call("GET", "/protected/profile");
check("GET /protected/profile (no token) -> 401", r.status === 401 && r.data?.error === "Access token required");

// Stage 1 validation
r = await call("POST", "/auth/signup", { body: { email } });
check("signup missing password -> 400", r.status === 400);
r = await call("POST", "/auth/login", { body: { password } });
check("login missing email -> 400", r.status === 400);

// Sign up (400 is fine if the account already exists), then log in
r = await call("POST", "/auth/signup", { body: { email, password } });
check("POST /auth/signup -> 201 (or 400 if already registered)", [201, 400].includes(r.status), `(got ${r.status})`);

r = await call("POST", "/auth/login", { body: { email, password: password + "x" } });
check("login wrong password -> 401", r.status === 401 && r.data?.error === "Invalid login credentials");

r = await call("POST", "/auth/login", { body: { email, password } });
check("POST /auth/login -> 200 + access_token", r.status === 200 && !!r.data?.access_token,
  r.status !== 200 ? `(got ${r.status}; is "Confirm email" disabled in Supabase?)` : "");
const token = r.data?.access_token;
if (!token) { console.log("Cannot continue without a token."); process.exit(1); }

// Stage 3 & 4
r = await call("GET", "/protected/profile", { token });
check("profile with valid token -> 200", r.status === 200 && r.data?.email === email.toLowerCase());
const tampered = token.slice(0, -1) + (token.endsWith("a") ? "b" : "a");
r = await call("GET", "/protected/profile", { token: tampered });
check("profile with tampered token -> 401", r.status === 401 && r.data?.error === "Invalid or expired token");
r = await call("GET", "/protected/dashboard", { token });
check("dashboard with valid token -> 200", r.status === 200);
r = await call("GET", "/protected/dashboard", { token: tampered });
check("dashboard with tampered token -> 401", r.status === 401);
r = await call("POST", "/auth/logout", { token });
check("POST /auth/logout -> 204", r.status === 204, `(got ${r.status})`);

console.log(failed ? `\n${failed} check(s) failed` : "\nAll checks passed");
process.exit(failed ? 1 : 0);
