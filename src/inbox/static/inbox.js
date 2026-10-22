(function () {
  var drawer = document.getElementById("drawer");
  var body = document.getElementById("drawer-body");
  if (!drawer || !body) {
    return;
  }

  function closeDrawer() {
    drawer.hidden = true;
    body.innerHTML = "";
  }

  function openDrawer(url) {
    fetch(url, { headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Could not open card");
        }
        return response.text();
      })
      .then(function (html) {
        body.innerHTML = html;
        drawer.hidden = false;
        var closeBtn = drawer.querySelector("[data-close-drawer]");
        if (closeBtn) {
          closeBtn.focus();
        }
      })
      .catch(function () {
        window.location.href = url.replace("/fragment", "");
      });
  }

  document.addEventListener("click", function (event) {
    var close = event.target.closest("[data-close-drawer]");
    if (close) {
      event.preventDefault();
      closeDrawer();
      return;
    }
    if (event.target === drawer) {
      closeDrawer();
      return;
    }
    var link = event.target.closest("[data-drawer-url]");
    if (!link) {
      return;
    }
    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      return;
    }
    event.preventDefault();
    openDrawer(link.getAttribute("data-drawer-url"));
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !drawer.hidden) {
      closeDrawer();
    }
  });
})();
