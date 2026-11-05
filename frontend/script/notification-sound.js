(function () {
  "use strict";

  const scriptUrl = document.currentScript && document.currentScript.src;
  if (!scriptUrl) {
    console.error("Could not locate the notification sound script.");
    return;
  }

  const audio = new Audio(new URL("../assets/notification.mp3", scriptUrl));
  const appointmentReminderAudio = new Audio(new URL("../assets/alert.mp3", scriptUrl));
  audio.preload = "auto";
  appointmentReminderAudio.preload = "auto";
  let audioUnlocked = false;
  let unlockInProgress = false;
  let pendingNotification = false;
  let pendingAppointmentReminder = false;

  function unlockAudio() {
    if (audioUnlocked || unlockInProgress) return;
    unlockInProgress = true;
    document.removeEventListener("pointerdown", unlockAudio);
    document.removeEventListener("keydown", unlockAudio);
    const sounds = [audio, appointmentReminderAudio];
    sounds.forEach(sound => {
      sound.muted = true;
    });

    Promise.all(sounds.map(sound => sound.play())).then(() => {
      sounds.forEach(sound => {
        sound.pause();
        sound.currentTime = 0;
        sound.muted = false;
      });
      audioUnlocked = true;
      if (pendingNotification) {
        pendingNotification = false;
        window.playNotificationSound();
      }
      if (pendingAppointmentReminder) {
        pendingAppointmentReminder = false;
        window.playAppointmentReminderSound();
      }
    }).catch(error => {
      sounds.forEach(sound => {
        sound.pause();
        sound.currentTime = 0;
        sound.muted = false;
      });
      unlockInProgress = false;
      console.error("Could not enable notification sound:", error);
      document.addEventListener("pointerdown", unlockAudio, { once: true });
      document.addEventListener("keydown", unlockAudio, { once: true });
    });
  }

  audio.addEventListener("error", () => {
    console.error("Could not load the notification sound.");
  });
  appointmentReminderAudio.addEventListener("error", () => {
    console.error("Could not load the appointment reminder sound.");
  });
  document.addEventListener("pointerdown", unlockAudio, { once: true });
  document.addEventListener("keydown", unlockAudio, { once: true });

  window.playNotificationSound = function () {
    if (!audioUnlocked) {
      pendingNotification = true;
      return;
    }

    audio.currentTime = 0;
    audio.play().catch(error => {
      console.error("Could not play the notification sound:", error);
    });
  };

  window.playAppointmentReminderSound = function () {
    if (!audioUnlocked) {
      pendingAppointmentReminder = true;
      return;
    }
    appointmentReminderAudio.currentTime = 0;
    appointmentReminderAudio.play().catch(error => {
      console.error("Could not play the appointment reminder sound:", error);
    });
  };
})();
