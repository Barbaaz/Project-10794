// The page the service worker shows offline (static/offline.html); saved at install (sw.js PRECACHE).
applyI18n();
document.getElementById("retry").addEventListener("click", () => location.reload());
