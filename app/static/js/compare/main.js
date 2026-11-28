document.addEventListener("DOMContentLoaded", function () {
  const app = window.CompareApp || {};

  const popups = app.createPopupsController ? app.createPopupsController() : null;
  if (popups) popups.init();

  if (app.initCopyFeature) app.initCopyFeature();
  if (app.initCompareForm) {
    app.initCompareForm(function () {
      if (popups) popups.hideAll();
    });
  }
});