let currentTab = "infra";
let currentFilter = "all";
let lastFocusedElement = null;

function scrollToRegistry() {
  document.getElementById("project-registry").scrollIntoView({ behavior: "smooth", block: "start" });
}

function switchTab(tab) {
  currentTab = tab;
  ["infra", "noninfra"].forEach(name => {
    const button = document.getElementById(`tab-${name}`);
    button.setAttribute("aria-selected", String(name === tab));
  });
  applyFilters();
}

function setFilter(status) {
  currentFilter = status;
  document.querySelectorAll(".filter-button").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.filter === status));
  });
  applyFilters();
}

function applyFilters() {
  const locVal = document.getElementById("location-select").value;
  const records = document.querySelectorAll(".project-row, .mobile-project");
  const visibleIds = new Set();

  records.forEach(record => {
    const categoryMatches = record.dataset.category === currentTab;
    const statusMatches = currentFilter === "all" || record.dataset.status === currentFilter;

    let locMatches = true;
    if (locVal !== "all") {
      locMatches = record.dataset.search.includes(locVal);
      if (locVal === "school") {
        locMatches = record.dataset.search.includes("school") || record.dataset.search.includes("deped") || record.dataset.search.includes("education");
      } else if (locVal === "remote") {
        locMatches = record.dataset.search.includes("remote") || record.dataset.search.includes("health");
      }
    }

    const shouldShow = categoryMatches && statusMatches && locMatches;
    record.classList.toggle("hidden", !shouldShow);
    if (shouldShow) visibleIds.add(record.dataset.record);
  });

  document.getElementById("visible-count").textContent = String(visibleIds.size);
  document.getElementById("empty-state").classList.toggle("hidden", visibleIds.size !== 0);
}

function openDetails(id) {
  lastFocusedElement = document.activeElement;
  document.querySelectorAll(".detail-view").forEach(view => {
    view.classList.toggle("hidden", view.dataset.detail !== id);
  });
  const overlay = document.getElementById("detail-overlay");
  overlay.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  document.querySelector('[data-template-id="detail-close-button"]').focus();
}

function closeDetails() {
  document.getElementById("detail-overlay").classList.add("hidden");
  document.body.style.overflow = "";
  if (lastFocusedElement) lastFocusedElement.focus();
}

document.getElementById("filter-form").addEventListener("submit", event => event.preventDefault());
document.getElementById("location-select").addEventListener("change", applyFilters);
document.querySelectorAll(".filter-button").forEach(button => {
  button.addEventListener("click", () => setFilter(button.dataset.filter));
});

document.getElementById("detail-overlay").addEventListener("click", event => {
  if (event.target.id === "detail-overlay") closeDetails();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !document.getElementById("detail-overlay").classList.contains("hidden")) {
    closeDetails();
  }
});

lucide.createIcons();
applyFilters();
