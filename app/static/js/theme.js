document.addEventListener("DOMContentLoaded", function () {
  const themeIcon = document.getElementById("theme-active-icon");
  const themeText = document.getElementById("theme-active-text");
  const themeButtons = document.querySelectorAll("[data-bs-theme-value]");

  const metaMap = {
    light: { icon: "☀️", label: "Light" },
    dark: { icon: "🌙", label: "Dark" },
    auto: { icon: "🌗", label: "Auto" }
  };

  function applyTheme(themeChoice) {
    localStorage.setItem("fpl_theme", themeChoice);

    const effectiveTheme =
      themeChoice === "auto"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : themeChoice;

    document.documentElement.setAttribute("data-bs-theme", effectiveTheme);

    const info = metaMap[themeChoice] || metaMap.dark;
    if (themeIcon) themeIcon.textContent = info.icon;
    if (themeText) themeText.textContent = info.label;

    themeButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-bs-theme-value") === themeChoice);
    });
  }

  const currentStored = localStorage.getItem("fpl_theme") || "dark";
  applyTheme(currentStored);

  themeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.getAttribute("data-bs-theme-value");
      applyTheme(val);
    });
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((localStorage.getItem("fpl_theme") || "dark") === "auto") {
      applyTheme("auto");
    }
  });
});