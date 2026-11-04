(function () {
  "use strict";

  const topbar = document.querySelector(".topbar");
  if (!topbar || !window.Auth || !Auth.current()) return;

  const t = (key, values) => window.I18N ? I18N.t(key, values) : key;
  const menu = document.createElement("div");
  menu.className = "notification-menu";
  menu.innerHTML = `
    <button class="notification-trigger" id="notificationTrigger" type="button"
      aria-label="${t("notification.open")}" aria-expanded="false" aria-controls="notificationTray">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        <path d="M10 21h4" />
      </svg>
      <span class="notification-count" id="notificationCount" hidden></span>
    </button>
    <section class="notification-tray" id="notificationTray" aria-label="${t("notification.title")}" hidden>
      <div class="notification-tray-header">
        <strong>${t("notification.title")}</strong>
        <button class="notification-close" type="button" aria-label="${t("notification.close")}">&times;</button>
      </div>
      <div class="notification-list" id="notificationList" aria-live="polite"></div>
    </section>
  `;
  topbar.appendChild(menu);

  const trigger = menu.querySelector("#notificationTrigger");
  const tray = menu.querySelector("#notificationTray");
  const list = menu.querySelector("#notificationList");
  const count = menu.querySelector("#notificationCount");
  let loading = false;
  let knownNotificationIds = null;
  let appointmentSnapshot = JSON.stringify(Auth.getAppointments());
  let toastTimer;

  const toast = document.createElement("div");
  toast.className = "notification-toast";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  document.body.append(toast);

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("show"), 5000);
  }

  function showMessage(message) {
    const row = document.createElement("p");
    row.className = "notification-empty";
    row.textContent = message;
    list.replaceChildren(row);
  }

  function render(data) {
    count.hidden = data.unread_count < 1;
    count.textContent = data.unread_count > 99 ? "99+" : String(data.unread_count);
    list.replaceChildren();
    if (!data.notifications.length) {
      showMessage(t("notification.empty"));
      return;
    }

    data.notifications.forEach((notification) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `notification-item${notification.read ? "" : " unread"}`;
      const messageKey = {
        appointment_confirmed: "notification.confirmed",
        appointment_cancelled: "notification.cancelled",
        appointment_unavailable: "notification.unavailableSlot"
      }[notification.type] || "notification.title";
      const message = document.createElement("span");
      message.textContent = t(messageKey, {
        doctor: notification.doctor_name,
        date: notification.date,
        time: notification.time,
        reason: notification.reason || ""
      });
      item.append(message);
      if (!notification.read) {
        const indicator = document.createElement("span");
        indicator.className = "notification-unread-dot";
        indicator.setAttribute("aria-hidden", "true");
        item.append(indicator);
      }
      item.addEventListener("click", async () => {
        if (notification.read) return;
        item.disabled = true;
        try {
          const response = await fetch(`/api/notifications/${notification.id}/read`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
            cache: "no-store"
          });
          if (!response.ok) throw new Error(`Notification read request failed (${response.status}).`);
          await refresh();
        } catch (error) {
          console.error("Could not mark notification as read:", error);
          item.disabled = false;
        }
      });
      list.append(item);
    });
  }

  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      const user = await Auth.refreshAsync();
      if (!user) return;
      const response = await fetch("/api/notifications", { cache: "no-store" });
      if (!response.ok) throw new Error(`Notification request failed (${response.status}).`);
      const data = await response.json();
      if (!data.ok || !Array.isArray(data.notifications) || !Number.isInteger(data.unread_count)) {
        throw new Error("The notification response was invalid.");
      }
      const appointments = Array.isArray(user.data?.appointments) ? user.data.appointments : [];
      const nextAppointmentSnapshot = JSON.stringify(appointments);
      if (appointmentSnapshot !== null && appointmentSnapshot !== nextAppointmentSnapshot) {
        window.dispatchEvent(new CustomEvent("appointments:updated", { detail: appointments }));
      }
      appointmentSnapshot = nextAppointmentSnapshot;
      const currentIds = new Set(data.notifications.map(notification => notification.id));
      if (knownNotificationIds) {
        const newUnread = data.notifications.find(notification =>
          !notification.read && !knownNotificationIds.has(notification.id)
        );
        if (newUnread) {
          const messageKey = {
            appointment_confirmed: "notification.confirmed",
            appointment_cancelled: "notification.cancelled",
            appointment_unavailable: "notification.unavailableSlot"
          }[newUnread.type];
          if (messageKey) {
            showToast(t(messageKey, {
              doctor: newUnread.doctor_name,
              date: newUnread.date,
              time: newUnread.time,
              reason: newUnread.reason || ""
            }));
          }
        }
      }
      knownNotificationIds = currentIds;
      render(data);
    } catch (error) {
      console.error("Could not load notifications:", error);
      if (!list.childElementCount) showMessage(t("notification.unavailable"));
    } finally {
      loading = false;
    }
  }

  function setOpen(open) {
    tray.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (open) refresh();
  }

  trigger.addEventListener("click", () => setOpen(tray.hidden));
  menu.querySelector(".notification-close").addEventListener("click", () => setOpen(false));
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !tray.hidden) {
      setOpen(false);
      trigger.focus();
    }
  });

  refresh();
  window.setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, 3000);
})();
