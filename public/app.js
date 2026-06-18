/* BharatWatch shared frontend helpers */

const CR = 1e7;
const fmtCr = (v) => "₹" + (v / CR).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " Cr";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const res = await fetch(path, opts);
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
    ["/", "Dashboard"], ["/explore", "Explore"], ["/overview", "National Overview"],
    ["/about", "About"], ["/admin", "Admin"],
  ];
  document.body.insertAdjacentHTML("afterbegin", `
    <header class="site">
      <a class="logo" href="/">Bharat<span>Watch</span></a>
      <nav class="main">${nav.map(([h, l]) =>
        `<a href="${h}" class="${h === active ? "active" : ""}">${l}</a>`).join("")}</nav>
      <div class="spacer"></div>
      <button class="ghost" id="themeBtn" title="Toggle dark/light mode">◐</button>
    </header>`);
  document.body.insertAdjacentHTML("beforeend", `
    <footer class="site">
      <strong>Disclaimer:</strong> For transparency and informational purposes only — not legal advice
      or an accusation of wrongdoing. All data is sourced exclusively from public portals (ECI, MCA,
      CPPP, GeM, PFMS, data.gov.in) and updated periodically. Patterns are statistical indicators that
      require human verification. This demo instance is seeded with <em>fictional</em> data.
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
