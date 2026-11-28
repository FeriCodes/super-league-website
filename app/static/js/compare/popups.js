(function () {
  window.CompareApp = window.CompareApp || {};

  function createPopupsController() {
    const popupBoxes = Array.from(document.querySelectorAll('[data-player-popup="true"]'));
    const instances = [];

    function hideAll(exceptEl = null) {
      popupBoxes.forEach(function (el) {
        if (el !== exceptEl) {
          const inst = bootstrap.Tooltip.getInstance(el);
          if (inst) inst.hide();
          el.classList.remove("popup-open");
        }
      });
    }

    function init() {
      popupBoxes.forEach(function (el) {
        const tpl = el.querySelector("template.popup-template");
        const htmlContent = tpl ? tpl.innerHTML.trim() : "";

        const inst = new bootstrap.Tooltip(el, {
          html: true,
          sanitize: false,
          trigger: "manual",
          placement: "top",
          boundary: "window",
          container: "body",
          title: htmlContent
        });
        instances.push(inst);

        el.addEventListener("click", function (e) {
          e.stopPropagation();
          const isOpen = el.classList.contains("popup-open");
          hideAll(el);
          if (isOpen) {
            inst.hide();
            el.classList.remove("popup-open");
          } else {
            inst.show();
            el.classList.add("popup-open");
          }
        });

        el.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            el.click();
          }
        });
      });

      document.addEventListener("click", function (e) {
        if (e.target.closest(".tooltip")) return;
        if (!e.target.closest('[data-player-popup="true"]')) {
          hideAll();
        }
      });

      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          hideAll();
        }
      });
    }

    return { init, hideAll };
  }

  window.CompareApp.createPopupsController = createPopupsController;
})();