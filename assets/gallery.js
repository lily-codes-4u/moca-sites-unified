/* AutoGallery pages: open a deep-linked image (#image-12, or the old ?Image=12 links) and run the slideshow. */
(function () {
  var d = document;
  function openN(n) {
    var f = d.getElementById("image-" + n);
    if (!f) return;
    f.scrollIntoView({ block: "center" });
    var a = f.querySelector("a.zoom"); if (a) setTimeout(function () { a.click(); }, 50);
  }
  var m = location.hash.match(/^#image-(\d+)/) || location.search.match(/[?&]image=(\d+)/i);
  if (m) openN(m[1]);
  var play = d.getElementById("play"), lb = d.getElementById("lb");
  if (!play || !lb) return;
  var timer = null, i = 0, all = d.querySelectorAll("#gallery a.zoom");
  function show() {
    var a = all[i % all.length];
    var img = lb.querySelector("img"), fig = a.closest("figure");
    img.src = a.getAttribute("data-full") || a.href;
    img.alt = (a.querySelector("img") || {}).alt || "";
    lb.querySelector(".cap").textContent = (fig.querySelector("figcaption") || {}).textContent + "  (" + (i % all.length + 1) + " of " + all.length + ")";
    lb.querySelector(".orig").href = a.href;
    var next = all[(i + 1) % all.length]; if (next) { var pre = new Image(); pre.src = next.getAttribute("data-full"); }
    i++;
  }
  function stop() { clearInterval(timer); timer = null; play.textContent = "▶ Play slideshow"; }
  play.addEventListener("click", function () {
    if (timer) return stop();
    i = 0; show(); lb.showModal();
    timer = setInterval(show, (parseFloat(play.getAttribute("data-timer")) || 4) * 1000);
    play.textContent = "❚❚ Stop slideshow";
  });
  lb.addEventListener("close", stop);
})();
