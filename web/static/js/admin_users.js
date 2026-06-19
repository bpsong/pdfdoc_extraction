(function () {
  function cookie(name) {
    return document.cookie.split("; ").find((item) => item.startsWith(name + "="))?.split("=")[1] || "";
  }
  document.querySelectorAll(".user-password-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const target = form.dataset.user;
      const payload = Object.fromEntries(new FormData(form).entries());
      const response = await fetch(`/api/admin/users/${target}/password`, {
        method: "PUT",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(cookie("csrf_token"))},
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      const message = document.getElementById("user-message");
      message.className = `alert ${response.ok ? "alert-success" : "alert-error"}`;
      message.textContent = response.ok ? `${target} password changed.` : (result.detail || "Password change failed.");
      if (response.ok) form.reset();
      if (response.ok && result.session_revoked) window.location.href = "/logout";
    });
  });
})();
