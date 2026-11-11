/* MOCA site behaviour: menu, image viewer, search, Flash player. No dependencies. */
(function () {
  var d = document, $ = function (s, r) { return (r || d).querySelector(s); };
  // theme memory is not needed: we follow the OS setting.
  var menu = $("#menubtn"), nav = $("#nav");
  if (menu) {
    menu.addEventListener("click", function () { var o = nav.classList.toggle("open"); menu.setAttribute("aria-expanded", o); });
    d.addEventListener("keydown", function (e) { if (e.key === "Escape" && nav.classList.contains("open")) { nav.classList.remove("open"); menu.setAttribute("aria-expanded", false); menu.focus(); } });
  }

  // ---- image viewer
  var lb = $("#lb");
  d.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a.zoom");
    if (!a || !lb || !lb.showModal || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    var img = $("img", lb), fig = a.closest("figure"), cap = fig && $("figcaption", fig);
    img.removeAttribute("src");
    img.src = a.getAttribute("data-full") || a.href;
    img.alt = (a.querySelector("img") || {}).alt || "";
    $(".cap", lb).textContent = cap ? cap.textContent : "";
    $(".orig", lb).href = a.href;
    lb.showModal();
    lb._from = a;
  });
  if (lb) {
    lb.addEventListener("click", function (e) { if (e.target === lb || e.target.classList.contains("x")) lb.close(); });
    d.addEventListener("keydown", function (e) {
      if (!lb.open || !lb._from) return;
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var all = Array.prototype.slice.call(d.querySelectorAll("a.zoom")), i = all.indexOf(lb._from);
      var n = all[(i + (e.key === "ArrowRight" ? 1 : -1) + all.length) % all.length];
      if (n) { lb.close(); n.click(); }
    });
  }

  // ---- search (index loads only when used)
  var sd = $("#sd"), q = $("#q"), res = $("#res"), idx = null;
  function openSearch() {
    if (!sd || !sd.showModal) { location.href = "/archive.html"; return; }
    sd.showModal(); q.focus();
    if (!idx) fetch("/search.json").then(function (r) { return r.json(); }).then(function (j) { idx = j; run(); });
  }
  function norm(s) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }
  function run() {
    if (!idx) return;
    var t = norm(q.value.trim()); res.innerHTML = "";
    if (t.length < 2) return;
    var words = t.split(/\s+/), out = [];
    for (var i = 0; i < idx.length && out.length < 60; i++) {
      var h = norm(idx[i][0] + " " + idx[i][2] + " " + idx[i][1]);
      if (words.every(function (w) { return h.indexOf(w) > -1; })) out.push(idx[i]);
    }
    res.innerHTML = out.map(function (r) {
      var a = d.createElement("a"); a.href = r[1]; a.textContent = r[0];
      var s = d.createElement("span"); s.textContent = r[2]; a.appendChild(s);
      return "<li>" + a.outerHTML + "</li>";
    }).join("") || "<li style='padding:10px 12px;color:var(--muted)'>No matches</li>";
  }
  var sb = $("#searchbtn"); if (sb) sb.addEventListener("click", openSearch);
  if (q) {
    q.addEventListener("input", run);
    q.addEventListener("keydown", function (e) { if (e.key === "Enter") { var a = res.querySelector("a"); if (a) { e.preventDefault(); location.href = a.href; } } });
  }
  if (sd) sd.addEventListener("click", function (e) { if (e.target === sd || e.target.classList.contains("x")) sd.close(); });
  d.addEventListener("keydown", function (e) {
    if (e.key === "/" && !/input|textarea|select/i.test(d.activeElement.tagName)) { e.preventDefault(); openSearch(); }
  });

  // ---- Flash (.swf) via the Ruffle emulator, loaded only when a visitor presses play
  d.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".swf .play");
    if (!b) return;
    var box = b.parentNode, url = box.getAttribute("data-swf");
    b.textContent = "Loading player…";
    function go() {
      var r = window.RufflePlayer.newest(), p = r.createPlayer();
      box.innerHTML = ""; box.appendChild(p); p.load({ url: url, autoplay: "on", letterbox: "on" });
    }
    if (window.RufflePlayer && window.RufflePlayer.newest) return go();
    window.RufflePlayer = window.RufflePlayer || {};
    window.RufflePlayer.config = { publicPath: "/vendor/ruffle/", polyfills: false, contextMenu: "rightClickOnly" };
    var s = d.createElement("script"); s.src = "/vendor/ruffle/ruffle.js"; s.onload = go;
    s.onerror = function () { b.textContent = "Player could not load. Use the download link."; };
    d.head.appendChild(s);
  });
})();
