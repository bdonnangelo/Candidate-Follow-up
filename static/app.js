const el = (id) => document.getElementById(id);

const CLOSE_REASON_LABELS = {
  hired: "Contratado",
  hold: "En hold",
  position_closed: "Vacante cerrada",
  rejected: "No continúa",
};

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("es-UY", { day: "2-digit", month: "short", year: "numeric" });
}

function showToast(msg) {
  const t = el("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  t.style.opacity = "1";
  setTimeout(() => {
    t.style.opacity = "0";
    setTimeout(() => t.classList.add("hidden"), 200);
  }, 2200);
}

function attendeesLine(attendees) {
  if (!attendees || attendees.length === 0) return "";
  const names = attendees.map((a) => a.name || a.email).slice(0, 3).join(", ");
  return `Invitados: ${names}${attendees.length > 3 ? "…" : ""}`;
}

function closeReasonSelectHTML(eventId) {
  let options = '<option value="" selected disabled>Dejar de notificar…</option>';
  for (const [value, label] of Object.entries(CLOSE_REASON_LABELS)) {
    options += `<option value="${value}">${label}</option>`;
  }
  return `<select class="close-select" data-id="${eventId}">${options}</select>`;
}

function renderPending(items) {
  const list = el("pendingList");
  list.innerHTML = "";
  el("pendingCount").textContent = items.length;
  el("pendingEmpty").classList.toggle("hidden", items.length > 0);

  items.forEach((it) => {
    const div = document.createElement("div");
    div.className = "item overdue";
    const overdueBadge =
      it.weeks_overdue > 0
        ? `<span class="badge overdue">${it.weeks_overdue + 1} semana(s) de atraso</span>`
        : `<span class="badge overdue">Pendiente</span>`;
    div.innerHTML = `
      <input type="checkbox" data-id="${it.event_id}" />
      <div class="item-main">
        <div class="item-name">${it.candidate_name}</div>
        <div class="item-role">${it.position} · ${it.company}</div>
        <div class="item-meta">
          <span>Entrevista: ${fmtDate(it.interview_datetime)}</span>
          <span>${it.days_elapsed} día(s) desde la entrevista</span>
          <span>${attendeesLine(it.attendees)}</span>
        </div>
      </div>
      ${overdueBadge}
      ${closeReasonSelectHTML(it.event_id)}
    `;
    div.querySelector("input").addEventListener("change", (e) => completeFollowup(it.event_id, e.target));
    div.querySelector(".close-select").addEventListener("change", (e) => closeFollowup(it.event_id, e.target));
    list.appendChild(div);
  });
}

function renderUpcoming(items) {
  const list = el("upcomingList");
  list.innerHTML = "";
  el("upcomingCount").textContent = items.length;
  el("upcomingEmpty").classList.toggle("hidden", items.length > 0);

  items.forEach((it) => {
    const div = document.createElement("div");
    div.className = "item waiting";
    div.innerHTML = `
      <input type="checkbox" checked disabled />
      <div class="item-main">
        <div class="item-name">${it.candidate_name}</div>
        <div class="item-role">${it.position} · ${it.company}</div>
        <div class="item-meta">
          <span>Entrevista: ${fmtDate(it.interview_datetime)}</span>
          <span>Próximo recordatorio: ${fmtDate(it.next_reminder_date)}</span>
        </div>
      </div>
      <span class="badge waiting">Al día</span>
      ${closeReasonSelectHTML(it.event_id)}
    `;
    div.querySelector(".close-select").addEventListener("change", (e) => closeFollowup(it.event_id, e.target));
    list.appendChild(div);
  });
}

function renderHistory(items) {
  const list = el("historyList");
  list.innerHTML = "";
  el("historyCount").textContent = items.length;
  el("historyEmpty").classList.toggle("hidden", items.length > 0);

  items.forEach((it) => {
    const div = document.createElement("div");
    div.className = "item history";
    div.innerHTML = `
      <div class="item-main">
        <div class="item-name">${it.candidate_name}</div>
        <div class="item-role">${it.position} · ${it.company}</div>
        <div class="item-meta">
          <span>Entrevista: ${fmtDate(it.interview_datetime)}</span>
          <span>Seguimiento realizado: ${fmtDate(it.completed_at)}</span>
        </div>
      </div>
      <span class="badge done">Realizado</span>
    `;
    list.appendChild(div);
  });
}

function renderClosed(items) {
  const list = el("closedList");
  list.innerHTML = "";
  el("closedCount").textContent = items.length;
  el("closedEmpty").classList.toggle("hidden", items.length > 0);

  items.forEach((it) => {
    const div = document.createElement("div");
    div.className = "item closed";
    div.innerHTML = `
      <div class="item-main">
        <div class="item-name">${it.candidate_name}</div>
        <div class="item-role">${it.position} · ${it.company}</div>
        <div class="item-meta">
          <span>Entrevista: ${fmtDate(it.interview_datetime)}</span>
          <span>${it.status_changed_at ? "Archivado: " + fmtDate(it.status_changed_at) : ""}</span>
        </div>
      </div>
      <span class="badge closed">${it.status_reason_label || "Archivado"}</span>
      <button class="btn btn-secondary btn-small reactivate-btn" data-id="${it.event_id}">Reactivar</button>
    `;
    div.querySelector(".reactivate-btn").addEventListener("click", () => reactivateFollowup(it.event_id));
    list.appendChild(div);
  });
}

async function completeFollowup(eventId, checkbox) {
  checkbox.disabled = true;
  try {
    const res = await fetch(`/api/followups/${eventId}/complete`, { method: "POST" });
    if (!res.ok) throw new Error("failed");
    showToast("Follow-up marcado como realizado ✔ — vuelve a avisar en 7 días");
    await loadAll();
  } catch (e) {
    showToast("No se pudo marcar el follow-up. Probá de nuevo.");
    checkbox.disabled = false;
    checkbox.checked = false;
  }
}

async function closeFollowup(eventId, selectEl) {
  const reason = selectEl.value;
  if (!reason) return;
  selectEl.disabled = true;
  try {
    const res = await fetch(`/api/followups/${eventId}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) throw new Error("failed");
    showToast(`Dejaste de notificar a este candidato (${CLOSE_REASON_LABELS[reason]})`);
    await loadAll();
  } catch (e) {
    showToast("No se pudo archivar. Probá de nuevo.");
    selectEl.disabled = false;
    selectEl.value = "";
  }
}

async function reactivateFollowup(eventId) {
  try {
    const res = await fetch(`/api/followups/${eventId}/reactivate`, { method: "POST" });
    if (!res.ok) throw new Error("failed");
    showToast("Candidato reactivado — vuelve a la sección de seguimiento");
    await loadAll();
  } catch (e) {
    showToast("No se pudo reactivar. Probá de nuevo.");
  }
}

async function loadAll() {
  const [pending, upcoming, history, closed] = await Promise.all([
    fetch("/api/followups/pending").then((r) => r.json()),
    fetch("/api/followups/upcoming").then((r) => r.json()),
    fetch("/api/followups/history").then((r) => r.json()),
    fetch("/api/followups/closed").then((r) => r.json()),
  ]);
  renderPending(pending);
  renderUpcoming(upcoming);
  renderHistory(history);
  renderClosed(closed);
}

async function sync() {
  el("syncBtn").disabled = true;
  el("syncBtn").textContent = "Sincronizando…";
  try {
    const since = el("syncSince").value; // "YYYY-MM-DD"
    const res = await fetch("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ since }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "error");
    showToast(`Sincronizado: ${data.new_tracked} entrevista(s) nueva(s) detectada(s)`);
    await loadAll();
  } catch (e) {
    showToast("Error al sincronizar con Google Calendar.");
  } finally {
    el("syncBtn").disabled = false;
    el("syncBtn").textContent = "Sincronizar calendario";
  }
}

function defaultSyncSince() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10); // "YYYY-MM-DD"
}

async function logout() {
  await fetch("/logout", { method: "POST" });
  window.location.reload();
}

async function init() {
  const me = await fetch("/api/auth/me").then((r) => r.json());
  if (me.logged_in && me.connected) {
    el("userEmail").textContent = me.email;
    el("userEmail").classList.remove("hidden");
    el("syncSince").value = defaultSyncSince();
    el("syncSinceLabel").classList.remove("hidden");
    el("syncBtn").classList.remove("hidden");
    el("logoutBtn").classList.remove("hidden");
    el("app").classList.remove("hidden");
    el("disconnected").classList.add("hidden");
    await loadAll();
  } else {
    el("connectBtn").classList.remove("hidden");
    el("disconnected").classList.remove("hidden");
    el("app").classList.add("hidden");
  }
}

el("syncBtn").addEventListener("click", sync);
el("logoutBtn").addEventListener("click", logout);
init();
