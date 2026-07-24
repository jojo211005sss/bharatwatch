/* BharatWatch shared frontend helpers */

const CR = 1e7;
const fmtCr = (v) => "₹" + (v / CR).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " Cr";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function isApproved() {
  return localStorage.getItem("bw_approved") === "1";
}

async function api(path, opts) {
  let url = path;
  if (url.startsWith("/api/") && !url.includes("approved=")) {
    const sep = url.includes("?") ? "&" : "?";
    url += sep + "approved=" + (isApproved() ? "1" : "0");
  }
  const res = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function riskBadge(risk) {
  const cls = risk >= 70 ? "risk-high" : risk >= 40 ? "risk-med" : "risk-low";
  return `<span class="badge ${cls}">${risk}% risk</span>`;
}

function renderHeader(active) {
  const nav = [
    ["/", "Dashboard", `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`],
    ["/explore", "Explore", `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`],
    ["/overview", "Overview", `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`],
    ["/about", "About", `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`]
  ];
  const appState = isApproved();
  document.body.insertAdjacentHTML("afterbegin", `
    <header class="site">
      <div class="header-left">
        <a class="logo" href="/">Bharat<span>Watch</span></a>
        <label class="approved-toggle" title="When OFF (default), displays only the Approved Nitin Gadkari case. Toggle ON to view all research cases.">
          <span class="approved-text">Approved</span>
          <input type="checkbox" id="approvedToggle" ${appState ? "checked" : ""}>
          <span class="toggle-switch"></span>
          <span class="toggle-status">${appState ? "ON" : "OFF"}</span>
        </label>
      </div>
      <nav class="main">${nav.map(([h, l]) =>
        `<a href="${h}" class="${h === active ? "active" : ""}">${l}</a>`).join("")}</nav>
      <div class="spacer"></div>
      <button class="ghost" id="themeBtn" title="Toggle dark/light mode">◐</button>
    </header>
    <nav class="mobile-bottom-nav">
      ${nav.map(([h, l, svg]) => `
        <a href="${h}" class="${h === active ? "active" : ""}">
          ${svg}
          <span>${l}</span>
        </a>
      `).join("")}
    </nav>`);

  const toggleInput = document.getElementById("approvedToggle");
  if (toggleInput) {
    toggleInput.addEventListener("change", (e) => {
      localStorage.setItem("bw_approved", e.target.checked ? "1" : "0");
      location.reload();
    });
  }

  document.body.insertAdjacentHTML("beforeend", `
    <footer class="site">
      <strong>Disclaimer:</strong> For transparency and informational purposes only — not legal advice
      or an accusation of wrongdoing. All data is sourced exclusively from public portals (ECI, MCA,
      CPPP, GeM, PFMS, data.gov.in) and updated periodically. Patterns are statistical indicators that
      require human verification.
    </footer>`);
  const saved = localStorage.getItem("bw-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = saved;
  document.getElementById("themeBtn").onclick = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("bw-theme", next);
  };
}

function attachSearch(inputEl, resultsEl) {
  let timer;
  inputEl.addEventListener("input", () => {
    clearTimeout(timer);
    const q = inputEl.value.trim();
    if (!q) { resultsEl.innerHTML = ""; return; }
    timer = setTimeout(async () => {
      const rows = await api("/api/search?q=" + encodeURIComponent(q));
      resultsEl.innerHTML = rows.map((r) => `
        <a href="/entity?id=${r.id}">
          <span><strong>${esc(r.name)}</strong>
            <span class="sub">${esc(r.type)}${r.constituency ? " · " + esc(r.constituency) : ""}${r.state ? ", " + esc(r.state) : ""}</span>
          </span>
          ${r.risk ? riskBadge(r.risk) : ""}
        </a>`).join("") || `<a>No matches</a>`;
    }, 180);
  });
  document.addEventListener("click", (e) => {
    if (!resultsEl.contains(e.target) && e.target !== inputEl) resultsEl.innerHTML = "";
  });
}
