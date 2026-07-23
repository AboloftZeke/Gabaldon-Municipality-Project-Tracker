(function () {
  const categoryFilter = document.getElementById("category-filter");
  const locationFilter = document.getElementById("location-filter");
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  const statusButtons = Array.from(document.querySelectorAll(".status-btn"));
  const visibleCount = document.getElementById("visible-count");
  const rows = Array.from(document.querySelectorAll(".project-row"));

  let currentCategory = "all";
  let currentProjectCategory = "all";
  let currentStatus = "all";

  if (!rows.length) {
    if (visibleCount) {
      visibleCount.textContent = "0";
    }
    return;
  }

  function applyFilters() {
    const projectCategory = categoryFilter ? categoryFilter.value : "all";
    const location = locationFilter ? locationFilter.value : "all";
    let shown = 0;

    rows.forEach((row) => {
      const matchesCategory = currentCategory === "all" || row.dataset.category === currentCategory;
      const matchesProjectCategory = projectCategory === "all" || row.dataset.projectCategory === projectCategory;
      const matchesStatus = currentStatus === "all" || row.dataset.status === currentStatus;
      const matchesLocation = location === "all" || row.dataset.location === location;
      const show = matchesCategory && matchesProjectCategory && matchesStatus && matchesLocation;
      row.classList.toggle("hidden-row", !show);
      if (show) {
        shown += 1;
      }
    });

    if (visibleCount) {
      visibleCount.textContent = String(shown);
    }
  }

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      currentCategory = button.dataset.category || "all";
      tabButtons.forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      applyFilters();
    });
  });

  if (categoryFilter) {
    categoryFilter.addEventListener("change", () => {
      currentProjectCategory = categoryFilter.value || "all";
      applyFilters();
    });
  }

  statusButtons.forEach((button) => {
    button.addEventListener("click", () => {
      currentStatus = button.dataset.status || "all";
      statusButtons.forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      applyFilters();
    });
  });

  if (locationFilter) {
    locationFilter.addEventListener("change", applyFilters);
  }

  applyFilters();
})();