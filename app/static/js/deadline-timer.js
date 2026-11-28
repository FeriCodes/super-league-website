(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const box = document.getElementById("gw-deadline-box");
    const wrap = document.getElementById("gw-countdown-wrap");
    if (!box || !wrap) return;

    const targetMs = new Date(box.dataset.deadline).getTime();
    if (Number.isNaN(targetMs)) return;

    const daysEl = document.getElementById("cd-days");
    const hoursEl = document.getElementById("cd-hours");
    const minsEl = document.getElementById("cd-mins");
    const secsEl = document.getElementById("cd-secs");
    const pad = (n) => String(n).padStart(2, "0");

    function updateCountdown() {
      const diff = targetMs - Date.now();
      if (diff <= 0) {
        wrap.innerHTML = '<span class="deadline-passed-pill">Deadline Passed - Refresh Page</span>';
        return false;
      }

      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      const secs = Math.floor((diff % 60000) / 1000);

      if (daysEl) daysEl.textContent = pad(days);
      if (hoursEl) hoursEl.textContent = pad(hours);
      if (minsEl) minsEl.textContent = pad(mins);
      if (secsEl) secsEl.textContent = pad(secs);
      return true;
    }

    if (updateCountdown()) {
      const timerId = setInterval(function () {
        if (!updateCountdown()) {
          clearInterval(timerId);
        }
      }, 1000);
    }
  });
})();