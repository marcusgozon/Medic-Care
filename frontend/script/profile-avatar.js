(function () {
  "use strict";

  const topbar = document.querySelector(".topbar");
  const bookingHeader = document.body.dataset.page === "booking"
    ? document.getElementById("main-header")
    : null;
  const target = topbar || bookingHeader;
  if (!target || target.querySelector(".profile-nav-avatar")) return;

  function initials(name) {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "U";
    return parts.length === 1
      ? parts[0].slice(0, 2).toUpperCase()
      : (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  async function addAvatar() {
    try {
      const response = await fetch("/api/me", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.ok || !data.user) return;

      const profile = data.user.profile || {};
      const isAdmin = document.body.dataset.page === "admin";
      const avatar = document.createElement(isAdmin ? "div" : "a");
      avatar.className = "profile-nav-avatar";
      if (!isAdmin) avatar.href = "/pages/profile.html";
      avatar.setAttribute("aria-label", profile.name ? `Profile: ${profile.name}` : "Profile");
      avatar.title = profile.name || "Profile";
      avatar.textContent = initials(profile.name);

      const image = document.createElement("img");
      image.alt = "";
      image.src = `/api/profile/photo?v=${Date.now()}`;
      image.addEventListener("load", () => {
        avatar.textContent = "";
        avatar.appendChild(image);
      }, { once: true });

      image.addEventListener("error", () => image.remove(), { once: true });
      target.appendChild(avatar);
    } catch (error) {
      console.error("Could not load the signed-in profile avatar.", error);
    }
  }

  addAvatar();
})();
