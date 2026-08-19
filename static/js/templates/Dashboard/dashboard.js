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

  const categoryGroups = categoryFilter
    ? Array.from(categoryFilter.querySelectorAll("optgroup")).map((group) => ({
        type: group.dataset.projectCategoryType,
        label: group.label,
        options: Array.from(group.querySelectorAll("option")).map((option) => ({
          value: option.value,
          label: option.textContent,
        })),
      }))
    : [];

  function refreshCategoryOptions() {
    if (!categoryFilter) return;

    const previousValue = categoryFilter.value;
    categoryFilter.replaceChildren();

    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = currentCategory === "infra"
      ? "All Infrastructure Categories"
      : currentCategory === "noninfra"
        ? "All Non-Infrastructure Categories"
        : "All Categories";
    categoryFilter.appendChild(allOption);

    const availableValues = new Set(["all"]);
    categoryGroups.forEach((groupData) => {
      if (currentCategory !== "all" && groupData.type !== currentCategory) {
        return;
      }

      const group = document.createElement("optgroup");
      group.label = groupData.label;

      groupData.options.forEach((optionData) => {
        const option = document.createElement("option");
        option.value = optionData.value;
        option.textContent = optionData.label;
        group.appendChild(option);
        availableValues.add(optionData.value);
      });

      categoryFilter.appendChild(group);
    });

    categoryFilter.value = availableValues.has(previousValue)
      ? previousValue
      : "all";
    currentProjectCategory = categoryFilter.value;
  }

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
      refreshCategoryOptions();
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

  refreshCategoryOptions();
  applyFilters();
})();

