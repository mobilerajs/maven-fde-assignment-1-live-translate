// Paste this into DevTools console on any permissive page (e.g. books.toscrape.com)
// for the video demo — loads the widget FROM the deployed gateway, pointed at it.
document.querySelectorAll(".fde-fab, .fde-panel").forEach(e => e.remove()); // clear extension copy if present
window.FDE_CONFIG = { API_URL: "https://raj-livetranslate-gw.fly.dev" };
var s = document.createElement("script");
s.src = "https://raj-livetranslate-gw.fly.dev/widget.js";
document.body.appendChild(s);
