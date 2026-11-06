const ROOM_COORDINATES = {
    "306": { left: 36.4, top: 61.6, width: 21.2, height: 37.4 },
    "320": { left: 44.6, top: 1.0, width: 13.5, height: 39.0 },
    "321": { left: 58.1, top: 1.0, width: 12.9, height: 39.0 }
};

let roomsState = [], selectedRoom = null, currentUser = null, authToken = null;
const $ = (id) => document.getElementById(id);
const canUserBook = () => currentUser && (currentUser.role === "teacher" || currentUser.role === "admin");
const getTodayStr = () => new Date().toLocaleDateString("sv-SE");

function formatShortName(fullName) {
    if (!fullName) return "";
    const parts = fullName.trim().split(/\s+/);
    return parts.length === 1
        ? parts[0]
        : `${parts[0]}&nbsp;${parts.slice(1).map(p => `${p[0]}.`).join("&nbsp;")}`;
}

document.addEventListener("DOMContentLoaded", () => {
    $("filter-date").value = getTodayStr();
    restoreSession();
    initNavigation();
    initFilterEvents();
    initModalEvents();
    initAuthModal();
    loadRoomsData();
});

async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
    if (options.body) headers["Content-Type"] = "application/json";
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();

    if (res.status === 401 && authToken) {
        clearSession();
        $("booking-modal")?.classList.add("hidden");
        showToast("Термін дії сесії минув. Будь ласка, увійдіть у систему знову.", "warning");
    }
    return { ok: res.ok, status: res.status, data };
}

function showToast(message, type = "success") {
    let container = $("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = container.className = "toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;
    toast.innerHTML = `<span>${message}</span><button type="button" class="toast-close">&times;</button>`;

    const remove = () => {
        toast.classList.add("toast-hide");
        setTimeout(() => toast.remove(), 250);
    };
    toast.querySelector(".toast-close").onclick = remove;
    container.appendChild(toast);
    setTimeout(remove, 3800);
}

function restoreSession() {
    const savedUser = localStorage.getItem("pnu_user");
    const savedToken = localStorage.getItem("pnu_token");
    if (savedUser && savedToken) {
        currentUser = JSON.parse(savedUser);
        authToken = savedToken;
    }
    updateHeaderProfileUI();
}

function setActiveTab(isMap) {
    $("nav-map-btn")?.classList.toggle("active", isMap);
    $("nav-bookings-btn")?.classList.toggle("active", !isMap);
    $("view-map")?.classList.toggle("hidden", !isMap);
    $("view-bookings")?.classList.toggle("hidden", isMap);
}

function setSession(user, token) {
    currentUser = user;
    authToken = token;
    localStorage.setItem("pnu_user", JSON.stringify(user));
    localStorage.setItem("pnu_token", token);
    updateHeaderProfileUI();
    setActiveTab(true);
    loadRoomsData();
    if (canUserBook()) loadAllBookingsJournal();
}

function clearSession() {
    currentUser = null;
    authToken = null;
    localStorage.removeItem("pnu_user");
    localStorage.removeItem("pnu_token");
    updateHeaderProfileUI();
    setActiveTab(true);
    loadRoomsData();
    if ($("all-bookings-body")) $("all-bookings-body").innerHTML = "";
}

function updateHeaderProfileUI() {
    const roleNames = { admin: "Адміністратор", teacher: "Викладач", student: "Студент" };
    const isLogged = Boolean(currentUser);

    $("guest-panel").classList.toggle("hidden", isLogged);
    $("user-panel").classList.toggle("hidden", !isLogged);
    $("nav-bookings-btn")?.classList.toggle("hidden", !canUserBook());

    if (isLogged) {
        $("active-user-name").textContent = currentUser.full_name;
        $("active-user-role-badge").textContent = roleNames[currentUser.role] || currentUser.role;
    }
    if (!canUserBook()) setActiveTab(true);
}

async function loadRoomsData() {
    const dateVal = $("filter-date").value || getTodayStr();
    const slotSelect = $("filter-slot");
    const equipQuery = Array.from(document.querySelectorAll('input[name="equipment"]:checked'))
        .map(cb => cb.value).join(",");

    $("current-slot-label").textContent =
        `Дата: ${dateVal.split("-").reverse().join(".")} | ${slotSelect.options[slotSelect.selectedIndex].text}`;

    try {
        const params = new URLSearchParams({
            date: dateVal,
            slot: slotSelect.value,
            capacity: $("filter-capacity").value || 0,
            equipment: equipQuery
        });
        const { ok, data } = await apiFetch(`/api/rooms?${params}`);
        if (!ok) return;

        roomsState = data;
        renderMapOverlays(roomsState);
        renderRoomsTable(roomsState);
    } catch (e) {
        console.error("Помилка завантаження аудиторій:", e);
    }
}

function renderMapOverlays(rooms) {
    const container = $("map-overlays");
    container.innerHTML = "";
    const statusMap = { free: "Вільна", occupied: "Зайнята", closed: "Недоступна" };

    rooms.forEach(room => {
        const c = ROOM_COORDINATES[room.room_number] || { left: 10, top: 36, width: 10, height: 10.1 };
        const box = document.createElement("div");
        box.className = `room-overlay-box status-${room.status} ${room.matches_filter ? "" : "filtered-out"}`;
        Object.assign(box.style, { left: `${c.left}%`, top: `${c.top}%`, width: `${c.width}%`, height: `${c.height}%` });

        box.innerHTML = `
            <span class="room-num">Ауд. ${room.room_number}</span>
            <span class="room-cap">${room.capacity} місць</span>
            <span class="room-state-tag">${statusMap[room.status]}</span>
        `;
        box.title = `Аудиторія №${room.room_number} (${room.equipment_description})`;
        box.onclick = () => openBookingModal(room);
        container.appendChild(box);
    });
}

function renderRoomsTable(rooms) {
    const tbody = $("rooms-table-body");
    const filtered = rooms.filter(r => r.matches_filter);

    if (!filtered.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:16px; color:#6c757d;">За обраними критеріями аудиторій не знайдено.</td></tr>`;
        return;
    }

    const canBook = canUserBook();
    const isAdmin = currentUser?.role === "admin";
    tbody.innerHTML = "";

    filtered.forEach(room => {
        let badge = `<span class="badge-status badge-free">Вільна</span>`;
        let action = `<button class="btn-action-sm ${canBook ? "btn-book" : "btn-secondary-sm"}">${canBook ? "Бронювати" : "Деталі"}</button>`;

        if (room.status === "occupied") {
            const tName = room.current_booking?.teacher_name ? ` (${room.current_booking.teacher_name})` : "";
            badge = `<span class="badge-status badge-occupied">Зайнята${tName}</span>`;
            action = `<button class="btn-action-sm ${canBook ? "btn-queue" : "btn-secondary-sm"}">${canBook ? "Стати в чергу" : "Деталі"}</button>`;
        } else if (room.status === "closed") {
            badge = `<span class="badge-status badge-closed">Тимчасово недоступна</span>`;
            action = isAdmin
                ? `<button class="btn-action-sm btn-secondary-sm">Керувати</button>`
                : `<span style="color:#888; font-size:12px;">Недоступна</span>`;
        }

        let queueCell = "—";
        if (room.queue_count > 0) {
            const firstTeacher = room.first_in_queue
                ? `<div style="font-size:11.5px; color:#555; margin-top:2px; white-space:nowrap;" title="Перший у черзі: ${room.first_in_queue}">${formatShortName(room.first_in_queue)}</div>`
                : "";
            queueCell = `<div><strong>${room.queue_count} у черзі.</strong>${firstTeacher}</div>`;
        }

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>№ ${room.room_number}</strong></td>
            <td>${room.capacity} місць</td>
            <td>${room.equipment_description}</td>
            <td>${badge}</td>
            <td>${queueCell}</td>
            <td>${action}</td>
        `;
        const btn = tr.querySelector("button");
        if (btn) btn.onclick = () => openBookingModal(room);
        tbody.appendChild(tr);
    });
}

function openBookingModal(room) {
    selectedRoom = room;
    const canBook = canUserBook();
    const isAdmin = currentUser?.role === "admin";
    const formEl = $("booking-form");
    const submitBtn = $("modal-submit-btn");
    const occupancyEl = $("modal-occupancy-box");
    const adminControls = $("admin-room-controls");
    const toggleStatusBtn = $("btn-toggle-room-status");

    $("form-error-msg").classList.add("hidden");
    $("form-purpose").value = "";
    $("modal-title").textContent = `Аудиторія №${room.room_number}`;
    $("modal-room-details").innerHTML = `<strong>Місткість:</strong> ${room.capacity} місць &nbsp;|&nbsp; <strong>Обладнання:</strong> ${room.equipment_description}`;
    $("form-room-id").value = room.id;
    $("form-date-display").value = $("filter-date").value;
    $("form-slot-display").value = $("filter-slot").value;

    if (adminControls && toggleStatusBtn) {
        adminControls.classList.toggle("hidden", !isAdmin);
        if (isAdmin) {
            const isClosed = room.status === "closed" || room.is_active === 0;
            toggleStatusBtn.textContent = isClosed ? "Відкрити аудиторію" : "Закрити на тех. обслуговування";
            toggleStatusBtn.className = `btn-action-sm ${isClosed ? "btn-book" : "btn-queue"}`;
        }
    }

    if (room.status === "closed") {
        occupancyEl.className = "occupancy-alert badge-closed";
        occupancyEl.innerHTML = `<strong>Статус: Тимчасово недоступна.</strong><br>`;
        formEl.classList.add("hidden");
    } else if (room.status === "occupied") {
        occupancyEl.className = "occupancy-alert badge-occupied";
        occupancyEl.innerHTML = room.current_booking
            ? `<strong>Статус: Зайнята на обрану пару.</strong><br>Викладач: <strong>${room.current_booking.teacher_name}</strong><br>Призначення: ${room.current_booking.purpose}<br>У черзі очікування: <strong>${room.queue_count}</strong>`
            : `<strong>Статус: Зайнята на обрану пару.</strong><br><em>Для перегляду ПІБ викладача, дисципліни та групи увійдіть з корпоративною поштою.</em>`;
        formEl.classList.toggle("hidden", !canBook);
        submitBtn.textContent = "Стати в чергу очікування";
        submitBtn.className = "btn-action-sm btn-queue";
    } else {
        occupancyEl.className = "occupancy-alert badge-free";
        occupancyEl.innerHTML = `<strong>Статус: Вільна на обрану пару.</strong><br>${canBook ? "Аудиторія доступна для миттєвого бронювання." : "Аудиторія вільна."}`;
        formEl.classList.toggle("hidden", !canBook);
        submitBtn.textContent = "Підтвердити бронювання";
        submitBtn.className = "btn-primary-pnu";
    }
    $("booking-modal").classList.remove("hidden");
}

function initModalEvents() {
    const closeModal = () => $("booking-modal").classList.add("hidden");
    $("modal-close-btn").onclick = closeModal;
    $("modal-cancel-btn").onclick = closeModal;

    const toggleBtn = $("btn-toggle-room-status");
    if (toggleBtn) {
        toggleBtn.onclick = async () => {
            if (!selectedRoom || currentUser?.role !== "admin") return;
            const newState = (selectedRoom.status === "closed" || selectedRoom.is_active === 0) ? 1 : 0;

            try {
                const { ok, status, data } = await apiFetch(`/api/rooms/${selectedRoom.id}/status`, {
                    method: "PATCH",
                    body: JSON.stringify({ is_active: newState })
                });
                if (!ok) {
                    if (status === 401) return;
                    return showToast(data.error || "Не вдалося змінити статус аудиторії.", "error");
                }
                showToast(
                    newState === 1
                        ? `Аудиторію №${selectedRoom.room_number} відкрито для бронювання!`
                        : `Аудиторію №${selectedRoom.room_number} зачинено на тех. обслуговування.`,
                    newState === 1 ? "success" : "warning"
                );
                closeModal();
                loadRoomsData();
            } catch {
                showToast("Не вдалося з'єднатися з сервером.", "error");
            }
        };
    }

    $("booking-form").onsubmit = async (e) => {
        e.preventDefault();
        const errorEl = $("form-error-msg");
        const purpose = $("form-purpose").value.trim();

        if (purpose.length < 5) {
            errorEl.textContent = "Помилка: вкажіть назву дисципліни та групу (щонайменше 5 символів).";
            return errorEl.classList.remove("hidden");
        }

        const dateVal = $("filter-date").value;
        const [startT, endT] = $("filter-slot").value.split("-");

        try {
            const { ok, status, data } = await apiFetch("/api/bookings", {
                method: "POST",
                body: JSON.stringify({
                    room_id: selectedRoom.id,
                    user_id: currentUser.id,
                    purpose,
                    start_time: `${dateVal} ${startT}:00`,
                    end_time: `${dateVal} ${endT}:00`
                })
            });
            if (!ok) {
                if (status === 401) return;
                errorEl.textContent = data.error || "Помилка збереження.";
                return errorEl.classList.remove("hidden");
            }
            showToast(data.message, data.status === "queued" ? "warning" : "success");
            closeModal();
            loadRoomsData();
        } catch {
            errorEl.textContent = "Не вдалося з'єднатися з сервером.";
            errorEl.classList.remove("hidden");
        }
    };
}

function initFilterEvents() {
    const setDateSlot = (date, slot) => {
        $("filter-date").value = date;
        if (slot) $("filter-slot").value = slot;
        loadRoomsData();
    };

    $("filter-form").onsubmit = (e) => { e.preventDefault(); loadRoomsData(); };
    $("filter-date").onchange = loadRoomsData;
    $("filter-slot").onchange = loadRoomsData;
    $("btn-date-today").onclick = () => setDateSlot(getTodayStr());

    $("btn-reset-filters").onclick = () => {
        $("filter-capacity").value = "";
        document.querySelectorAll('input[name="equipment"]').forEach(cb => (cb.checked = false));
        setDateSlot(getTodayStr(), "09:00-10:20");
    };
}

function initNavigation() {
    $("nav-map-btn").onclick = () => { setActiveTab(true); loadRoomsData(); };
    $("nav-bookings-btn").onclick = () => { setActiveTab(false); loadAllBookingsJournal(); };
}

async function loadAllBookingsJournal() {
    const tbody = $("all-bookings-body");
    if (!tbody || !canUserBook()) return;

    try {
        const { ok, status, data: bookings } = await apiFetch("/api/bookings");
        if (status === 401) return;
        tbody.innerHTML = "";

        if (!ok || !bookings.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:16px; color:#6c757d;">У профілю <strong>${currentUser.full_name}</strong> поки немає активних бронювань чи записів у черзі.</td></tr>`;
            return;
        }

        bookings.forEach(b => {
            const badge = b.status === "confirmed"
                ? `<span class="badge-status badge-free">Підтверджено (confirmed)</span>`
                : `<span class="badge-status badge-queued">В черзі (queued)</span>`;
            const canCancel = currentUser.role === "admin" || currentUser.id === b.user_id;

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>Ауд. ${b.room_number}</strong></td>
                <td>${b.teacher_name}</td>
                <td>${b.purpose}</td>
                <td>${b.start_time.slice(0, 16)} – ${b.end_time.slice(11, 16)}</td>
                <td>${badge}</td>
                <td>${canCancel ? `<button class="btn-action-sm btn-queue">Скасувати</button>` : "—"}</td>
            `;

            const delBtn = tr.querySelector("button");
            if (delBtn) {
                delBtn.onclick = async () => {
                    const { ok, status, data } = await apiFetch(`/api/bookings/${b.id}`, { method: "DELETE" });
                    if (status === 401) return;
                    showToast(ok ? data.message : (data.error || "Помилка"), ok ? "success" : "error");
                    loadAllBookingsJournal();
                    loadRoomsData();
                };
            }
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Помилка завантаження журналу:", e);
    }
}

function initAuthModal() {
    const modal = $("auth-modal");
    const closeModal = () => modal.classList.add("hidden");

    const switchTab = (isLogin) => {
        $("login-error-msg").classList.add("hidden");
        $("reg-error-msg").classList.add("hidden");
        $("tab-login-btn").className = isLogin ? "btn-primary-pnu" : "btn-outline-pnu";
        $("tab-register-btn").className = !isLogin ? "btn-primary-pnu" : "btn-outline-pnu";
        $("login-form").classList.toggle("hidden", !isLogin);
        $("register-form").classList.toggle("hidden", isLogin);
    };

    $("open-login-btn").onclick = () => { $("login-form").reset(); switchTab(true); modal.classList.remove("hidden"); };
    $("open-register-btn").onclick = () => { $("register-form").reset(); switchTab(false); modal.classList.remove("hidden"); };
    $("logout-btn").onclick = () => { clearSession(); showToast("Ви вийшли з облікового запису.", "warning"); };
    $("tab-login-btn").onclick = () => switchTab(true);
    $("tab-register-btn").onclick = () => switchTab(false);
    $("auth-close-btn").onclick = closeModal;
    $("login-cancel-btn").onclick = closeModal;
    $("register-cancel-btn").onclick = closeModal;

    const handleAuthSubmit = async (url, payload, errorEl, isLogin) => {
        errorEl.classList.add("hidden");
        try {
            const { ok, data } = await apiFetch(url, { method: "POST", body: JSON.stringify(payload) });
            if (!ok) {
                errorEl.textContent = data.error || "Помилка авторизації.";
                return errorEl.classList.remove("hidden");
            }
            setSession(data.user, data.token);
            showToast(isLogin ? `Вітаємо, ${data.user.full_name}!` : data.message, "success");
            closeModal();
        } catch {
            errorEl.textContent = "Не вдалося з'єднатися з сервером.";
            errorEl.classList.remove("hidden");
        }
    };

    $("login-form").onsubmit = (e) => {
        e.preventDefault();
        handleAuthSubmit("/api/auth/login", {
            email: $("login-email").value.trim(),
            password: $("login-password").value
        }, $("login-error-msg"), true);
    };

    $("register-form").onsubmit = (e) => {
        e.preventDefault();
        handleAuthSubmit("/api/auth/register", {
            full_name: $("reg-fullname").value.trim(),
            email: $("reg-email").value.trim(),
            password: $("reg-password").value,
            role: $("reg-role").value
        }, $("reg-error-msg"), false);
    };
}