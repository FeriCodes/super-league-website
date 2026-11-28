document.addEventListener("DOMContentLoaded", function () {
  const table = document.getElementById("standings-table");
  if (!table) return;

  const headers = table.querySelectorAll(".sortable-th");
  const tbody = table.querySelector("tbody");

  let currentSort = "pts";
  let isDescending = true;

  headers.forEach((header) => {
    header.addEventListener("click", function () {
      const sortKey = this.getAttribute("data-sort");

      if (currentSort === sortKey) {
        isDescending = !isDescending;
      } else {
        currentSort = sortKey;
        isDescending = true;
      }

      headers.forEach((h) => {
        h.classList.remove("active-sort");
        h.querySelector(".sort-indicator").textContent = "⇅";
      });
      this.classList.add("active-sort");
      this.querySelector(".sort-indicator").textContent = isDescending ? "▼" : "▲";

      tbody.querySelectorAll("td[data-col]").forEach((td) => {
        td.classList.toggle("active-col-cells", td.getAttribute("data-col") === sortKey);
      });

      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort((a, b) => {
        const valA = parseInt(a.getAttribute(`data-${sortKey}`), 10);
        const valB = parseInt(b.getAttribute(`data-${sortKey}`), 10);

        if (valA !== valB) {
          return isDescending ? valB - valA : valA - valB;
        }

        const tie1Key = sortKey === "pts" ? "gd" : "pts";
        const tie1A = parseInt(a.getAttribute(`data-${tie1Key}`), 10);
        const tie1B = parseInt(b.getAttribute(`data-${tie1Key}`), 10);
        if (tie1A !== tie1B) {
          return tie1B - tie1A;
        }

        const totA = parseInt(a.getAttribute("data-tot"), 10);
        const totB = parseInt(b.getAttribute("data-tot"), 10);
        return totB - totA;
      });

      rows.forEach((row, index) => {
        row.querySelector(".col-pos").textContent = index + 1;
        tbody.appendChild(row);
      });
    });
  });
});