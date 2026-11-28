// GoatCounter Private Analytics
// Must load before count.js
if (window.location.hash === "#ignore-me") {
  localStorage.setItem("skipgc", "t");
  alert("✅ Owner Mode Activated! Visits from this browser will no longer be counted.");
}

window.goatcounter = {
  no_onload: localStorage.getItem("skipgc") === "t"
};