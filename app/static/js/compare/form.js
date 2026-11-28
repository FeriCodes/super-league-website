(function () {
  window.CompareApp = window.CompareApp || {};

  function initCompareForm(onBeforeSubmit) {
    const form = document.getElementById("compare-form");
    const btn = document.getElementById("btn-submit");
    const selectA = document.getElementById("team_a_name");
    const selectB = document.getElementById("team_b_name");
    const errorBox = document.getElementById("client-error-box");

    if (form && btn) {
      form.addEventListener("submit", function (e) {
        if (selectA && selectB && selectA.value && selectA.value === selectB.value) {
          e.preventDefault();
          if (errorBox) {
            errorBox.style.display = "block";
            errorBox.scrollIntoView({
              behavior: "smooth",
              block: "nearest"
            });
          }
          return;
        }

        if (typeof onBeforeSubmit === "function") {
          onBeforeSubmit();
        }

        if (errorBox) errorBox.style.display = "none";
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Comparing... Please wait`;
      });
    }

    if (selectA && selectB && errorBox) {
      const hideErr = () => {
        errorBox.style.display = "none";
      };
      selectA.addEventListener("change", hideErr);
      selectB.addEventListener("change", hideErr);
    }
  }

  window.CompareApp.initCompareForm = initCompareForm;
})();