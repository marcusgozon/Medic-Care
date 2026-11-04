const sidebar = document.getElementById('sidebar');
const scrim = document.getElementById('scrim');
const menuBtn = document.getElementById('menuBtn');
const closeSidebar = document.getElementById('closeSidebar');
let dashboardInitialized = false;
let dataLoading = false;
let pendingDenialAppointmentId = null;
const adminNotificationTrigger = document.getElementById('adminNotificationTrigger');
const adminNotificationTray = document.getElementById('adminNotificationTray');
const adminNotificationList = document.getElementById('adminNotificationList');
const adminNotificationCount = document.getElementById('adminNotificationCount');

function createPatientAvatar(name, userId, className = 'patient-list-avatar') {
    const avatar = document.createElement('span');
    avatar.className = className;
    const nameParts = String(name || '').trim().split(/\s+/).filter(Boolean);
    avatar.textContent = nameParts.length > 1
        ? `${nameParts[0][0]}${nameParts[nameParts.length - 1][0]}`.toUpperCase()
        : (nameParts[0] || 'P').slice(0, 2).toUpperCase();

    if (userId) {
        const image = document.createElement('img');
        image.alt = '';
        image.addEventListener('load', () => {
            avatar.textContent = '';
            avatar.append(image);
        }, { once: true });
        image.src = `/api/admin/users/${encodeURIComponent(userId)}/photo?v=${Date.now()}`;
    }

    return avatar;
}

function setAdminNotificationTray(open) {
    adminNotificationTray.hidden = !open;
    adminNotificationTrigger.setAttribute('aria-expanded', String(open));
}

function renderAdminNotifications(appointments) {
    const pending = appointments.filter(appointment => appointment.status === 'Pending');
    adminNotificationCount.hidden = pending.length === 0;
    adminNotificationCount.textContent = pending.length > 99 ? '99+' : String(pending.length);
    adminNotificationList.replaceChildren();

    if (!pending.length) {
        const empty = document.createElement('p');
        empty.className = 'notification-empty';
        empty.textContent = 'No appointments are waiting for approval.';
        adminNotificationList.append(empty);
        return;
    }

    pending.forEach(appointment => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'notification-item unread';
        item.append(
            createPatientAvatar(appointment.patient_name, appointment.user_id, 'patient-list-avatar notification-avatar')
        );
        const details = document.createElement('span');
        details.className = 'notification-item-details';
        details.textContent = `${appointment.patient_name} · ${appointment.doctor_name} · ${appointment.date} ${appointment.time}`;
        item.append(details);
        item.addEventListener('click', () => {
            setAdminNotificationTray(false);
            showSection('appointments', document.querySelector('.desktop-nav a[data-section="appointments"]'));
        });
        adminNotificationList.append(item);
    });
}

adminNotificationTrigger.addEventListener('click', () => {
    setAdminNotificationTray(adminNotificationTray.hidden);
});
document.getElementById('adminNotificationClose').addEventListener('click', () => setAdminNotificationTray(false));
document.addEventListener('click', event => {
    if (!adminNotificationTray.parentElement.contains(event.target)) setAdminNotificationTray(false);
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !adminNotificationTray.hidden) {
        setAdminNotificationTray(false);
        adminNotificationTrigger.focus();
    }
});

document.getElementById('denyBookingForm').addEventListener('submit', async event => {
    event.preventDefault();
    const reasonInput = document.getElementById('denyBookingReason');
    const error = document.getElementById('denyBookingError');
    const reason = reasonInput.value.trim();
    if (!reason) {
        error.textContent = 'Enter a reason for denying this appointment.';
        error.hidden = false;
        reasonInput.focus();
        return;
    }

    error.hidden = true;
    const submitted = await updateApptStatus(pendingDenialAppointmentId, 'Cancelled', reason, 'Pending');
    if (submitted) {
        pendingDenialAppointmentId = null;
        reasonInput.value = '';
        closeModal('denyBookingModal');
    }
});

function toggleMenu(open) {
    sidebar.classList.toggle('open', open);
    scrim.classList.toggle('open', open);
}

menuBtn.addEventListener('click', () => toggleMenu(true));
closeSidebar.addEventListener('click', () => toggleMenu(false));
scrim.addEventListener('click', () => toggleMenu(false));

function showSection(id, el) {
    if (document.body.classList.contains('not-logged-in')) {
        return;
    }

    document.querySelectorAll('main').forEach(m => m.classList.add('hidden'));
    document.getElementById(id + 'View').classList.remove('hidden');
    
    document.querySelectorAll('.sidebar nav a, .desktop-nav a').forEach(a => a.classList.remove('active'));
    if (el) el.classList.add('active');
    const desktopLink = document.querySelector(`.desktop-nav a[data-section="${id}"]`);
    if (desktopLink) desktopLink.classList.add('active');

    toggleMenu(false); 
}

async function loadDashboardData() {
    let resUsers;
    let dataUsers;
    try {
        resUsers = await fetch('/api/admin/users', { cache: 'no-store' });
        dataUsers = await resUsers.json();
    } catch (error) {
        console.error("Could not load admin dashboard data:", error);
        window.location.replace('/pages/login.html?tab=admin');
        return;
    }
    
    if(!dataUsers.ok) {
        document.body.classList.add('not-logged-in');
        window.location.replace('/pages/login.html?tab=admin');
        return;
    }
    
    document.body.classList.remove('not-logged-in');
    if (!dashboardInitialized) {
        document.querySelectorAll('.admin-layout main').forEach(main => main.classList.add('hidden'));
        document.getElementById("dashboardView").classList.remove("hidden");
        dashboardInitialized = true;
    }

    document.getElementById("statUsers").innerText = dataUsers.users.length;
    
    const patientTbody = document.getElementById("patientTableBody");
    const adminTbody = document.getElementById("adminTableBody");
    patientTbody.innerHTML = "";
    adminTbody.innerHTML = "";
    
    dataUsers.users.forEach(u => {
        const isBanned = u.status === 'banned';
        const statusBadge = isBanned 
            ? `<span class="status-badge status-banned">Banned</span>` 
            : `<span class="status-badge status-active">Active</span>`;
            
        const banBtn = isBanned 
            ? `<button class="btn-success" style="padding: 6px 12px; font-size: 12px;" onclick="toggleStatus(${u.id}, 'active')">Unban</button>`
            : `<button class="btn-warning" style="padding: 6px 12px; font-size: 12px;" onclick="toggleStatus(${u.id}, 'banned')">Ban</button>`;

        if (u.role === 'admin') {
            adminTbody.innerHTML += `
                <tr>
                    <td>${u.id}</td>
                    <td>${u.name}</td>
                    <td>${u.login_id}</td>
                    <td>${statusBadge}</td>
                    <td>${u.created_at}</td>
                    <td><button class="btn-primary" style="padding: 6px 12px; font-size: 12px;" onclick="openEditModal(${JSON.stringify(u).replace(/"/g, '&quot;')})">Edit</button></td>
                </tr>
            `;
        } else {
            patientTbody.innerHTML += `
                <tr>
                    <td>${u.id}</td>
                    <td>${u.name}</td>
                    <td>${u.login_id}</td>
                    <td>${statusBadge}</td>
                    <td>${u.created_at}</td>
                    <td style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <button class="btn-primary" style="padding: 6px 12px; font-size: 12px;" onclick="openEditModal(${JSON.stringify(u).replace(/"/g, '&quot;')})">Edit</button>
                        ${banBtn}
                        <button class="btn-danger" style="padding: 6px 12px; font-size: 12px;" onclick="deleteUser(${u.id})">Delete</button>
                    </td>
                </tr>
            `;
        }
    });

    const resAppts = await fetch('/api/admin/appointments', { cache: 'no-store' });
    const dataAppts = await resAppts.json();
    
    const apptsTbody = document.getElementById("appointmentsTableBody");
    const recentTbody = document.getElementById("recentApptsBody");
    
    if(dataAppts.ok) {
        const appts = dataAppts.appointments;
        renderAdminNotifications(appts);
        document.getElementById("statAppts").innerText = appts.length;

        let pending = 0;
        let confirmed = 0;
        appts.forEach(a => {
            if (a.status === 'Pending') pending++;
            if (a.status === 'Confirmed') confirmed++;
        });
        
        document.getElementById("statPending").innerText = pending;
        document.getElementById("statConfirmed").innerText = confirmed;

        apptsTbody.innerHTML = "";
        if (appts.length === 0) {
            apptsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 20px; color: #6b7794;">No appointments found in the database.</td></tr>`;
        } else {
            appts.forEach(a => {
                const badgeClass = a.status === 'Confirmed' ? 'status-confirmed' : 
                                   a.status === 'Pending' ? 'status-pending' : 
                                   a.status === 'Completed' ? 'status-completed' : 'status-cancelled';
                const allowedStatuses = a.status === 'Pending'
                    ? ['Pending', 'Confirmed', 'Cancelled']
                    : a.status === 'Confirmed'
                        ? ['Confirmed', 'Completed', 'Cancelled']
                        : [a.status];
                const statusOptions = allowedStatuses.map(status =>
                    `<option value="${status}" ${a.status === status ? 'selected' : ''}>${status === 'Cancelled' && a.status === 'Pending' ? 'Deny request' : status}</option>`
                ).join('');
                                  
                const apptJson = JSON.stringify(a).replace(/"/g, '&quot;');

                apptsTbody.innerHTML += `
                    <tr>
                        <td>#${a.id}</td>
                        <td>${a.patient_name}<br><small style="color:#6b7794">${a.patient_email}</small></td>
                        <td>${a.doctor_name}<br><small style="color:#6b7794">${a.spec}</small></td>
                        <td>${a.date}<br><small style="color:#6b7794">${a.time}</small></td>
                        <td><span class="status-badge ${badgeClass}">${a.status}</span></td>
                        <td style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <button class="btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="openViewApptModal(${apptJson})">View</button>
                            <select onchange="updateApptStatus(${a.id}, this.value, undefined, '${a.status}')" style="padding: 6px; font-size: 13px; width: auto;">${statusOptions}</select>
                        </td>
                    </tr>
                `;
            });
        }

        recentTbody.innerHTML = "";
        if (appts.length === 0) {
            recentTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: #6b7794;">No recent appointments.</td></tr>`;
        } else {
            appts.slice(0, 5).forEach(a => {
                const badgeClass = a.status === 'Confirmed' ? 'status-confirmed' : 
                                   a.status === 'Pending' ? 'status-pending' : 
                                   a.status === 'Completed' ? 'status-completed' : 'status-cancelled';
                const row = document.createElement('tr');
                const patientCell = document.createElement('td');
                const patientIdentity = document.createElement('div');
                patientIdentity.className = 'recent-patient-identity';
                patientIdentity.append(createPatientAvatar(a.patient_name, a.user_id));
                const patientName = document.createElement('span');
                patientName.textContent = a.patient_name || '';
                patientIdentity.append(patientName);
                patientCell.append(patientIdentity);

                const doctorCell = document.createElement('td');
                doctorCell.textContent = a.doctor_name || '';

                const dateCell = document.createElement('td');
                dateCell.append(document.createTextNode(a.date || ''));
                const time = document.createElement('small');
                time.textContent = a.time || '';
                dateCell.append(document.createElement('br'), time);

                const statusCell = document.createElement('td');
                const status = document.createElement('span');
                status.className = `status-badge ${badgeClass}`;
                status.textContent = a.status || '';
                statusCell.append(status);

                row.append(patientCell, doctorCell, dateCell, statusCell);
                recentTbody.append(row);
            });
        }
    } else {
        apptsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 20px; color: #ef4444;">Error loading appointments: ${dataAppts.error || 'Unknown Error'}</td></tr>`;
        recentTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: #ef4444;">Error loading appointments.</td></tr>`;
    }
}

async function loadData() {
    if (dataLoading) return;
    dataLoading = true;
    try {
        await loadDashboardData();
    } finally {
        dataLoading = false;
    }
}

async function updateApptStatus(id, newStatus, reason, currentStatus) {
    if (newStatus === 'Cancelled' && currentStatus === 'Pending' && reason === undefined) {
        pendingDenialAppointmentId = id;
        document.getElementById('denyBookingReason').value = '';
        document.getElementById('denyBookingError').hidden = true;
        document.getElementById('denyBookingModal').classList.add('show');
        document.getElementById('denyBookingReason').focus();
        return false;
    }

    try {
        const res = await fetch(`/api/admin/appointments/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ status: newStatus, reason: reason || '' })
        });
        if (res.ok) {
            loadData();
            return true;
        }
        const data = await res.json();
        alert(data.error === 'slot_unavailable'
            ? 'This doctor and schedule are no longer available. The patient was not confirmed.'
            : data.error === 'reason_required'
                ? 'Enter a reason before denying the appointment.'
                : 'Could not update the appointment status.');
        loadData();
    } catch (error) {
        console.error('Could not update appointment status:', error);
        alert('Could not reach the server. The appointment was not updated.');
    }
    return false;
}

async function toggleStatus(id, newStatus) {
    let action = newStatus === 'banned' ? 'BAN' : 'UNBAN';
    if(!confirm(`Are you sure you want to ${action} this user?`)) return;
    
    const res = await fetch(`/api/admin/users/${id}/status`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status: newStatus })
    });
    if(res.ok) loadData();
    else alert("Failed to update user status.");
}

async function deleteUser(id) {
    if(!confirm("Are you sure you want to permanently delete this user and all their appointments?")) return;
    await fetch(`/api/admin/users/${id}`, { method: 'DELETE' });
    loadData();
}

function openEditModal(user) {
    document.getElementById('editUserId').value = user.id;
    document.getElementById('editUserName').value = user.name;
    document.getElementById('editUserEmail').value = user.login_id;
    document.getElementById('editUserRole').value = user.role;
    document.getElementById('editUserModal').classList.add('show');
}

async function saveUserEdit() {
    const id = document.getElementById('editUserId').value;
    const name = document.getElementById('editUserName').value;
    const email = document.getElementById('editUserEmail').value;
    const role = document.getElementById('editUserRole').value;

    const res = await fetch(`/api/admin/users/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name, email, role })
    });
    const data = await res.json();
    
    if (data.ok) {
        closeModal('editUserModal');
        loadData();
    } else {
        alert("Failed to update user.");
    }
}

function openViewApptModal(appt) {
    let fullName = `${appt.patient_first || ''} ${appt.patient_middle || ''} ${appt.patient_last || ''} ${appt.patient_suffix || ''}`.replace(/\s+/g, ' ').trim();
    if (!fullName) fullName = appt.patient_name;

    const patientAvatar = document.getElementById('apptPatientAvatar');
    const nameParts = String(fullName || '').trim().split(/\s+/).filter(Boolean);
    patientAvatar.textContent = nameParts.length > 1
        ? `${nameParts[0][0]}${nameParts[nameParts.length - 1][0]}`.toUpperCase()
        : (nameParts[0] || 'P').slice(0, 2).toUpperCase();
    const patientImage = document.createElement('img');
    patientImage.alt = '';
    patientImage.addEventListener('load', () => {
        patientAvatar.textContent = '';
        patientAvatar.append(patientImage);
    }, { once: true });
    patientImage.src = `/api/admin/users/${encodeURIComponent(appt.user_id)}/photo?v=${Date.now()}`;

    document.getElementById('apptPatientName').innerText = fullName;
    document.getElementById('apptPatientDob').innerText = appt.patient_dob || "N/A";
    document.getElementById('apptPatientSex').innerText = appt.patient_sex || "N/A";
    document.getElementById('apptPatientPhone').innerText = appt.patient_phone || "N/A";
    document.getElementById('apptPatientEmail').innerText = appt.patient_email || "N/A";

    document.getElementById('apptService').innerText = appt.service || "N/A";
    document.getElementById('apptSpecific').innerText = appt.specific_service || "N/A";
    document.getElementById('apptDoctor').innerText = `${appt.doctor_name} (${appt.spec})`;
    document.getElementById('apptDateTime').innerText = `${appt.date} | ${appt.time}`;

    const deleteBtn = document.getElementById('deleteApptBtn');
    const newDeleteBtn = deleteBtn.cloneNode(true);
    deleteBtn.parentNode.replaceChild(newDeleteBtn, deleteBtn);
    
    newDeleteBtn.addEventListener('click', async () => {
        if(!confirm("Are you sure you want to permanently delete this appointment?")) return;
        await fetch(`/api/admin/appointments/${appt.id}`, { method: 'DELETE' });
        closeModal('viewApptModal');
        loadData();
    });

    document.getElementById('viewApptModal').classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal(overlay.id);
    });
});

// --- THE FIXED LOGOUT FUNCTION ---
async function logout(e) {
    if (e) e.preventDefault(); 

    // 1. Instantly hide UI to prevent any clicks
    document.body.classList.add('not-logged-in');
    document.querySelectorAll('main').forEach(m => m.classList.add('hidden'));
    
    // 2. Wait for the server to clear the session cookie
    try {
        // Added the required JSON headers and body so the backend accepts the request
        await fetch('/api/logout', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
            cache: 'no-store' 
        });
    } catch (err) {
        console.log("Network error during logout, forcing reload anyway.");
    }
    
    // 3. Force a hard redirect with a random cache-buster parameter
    window.location.replace('/pages/login.html?tab=admin');
}

// --- BFCACHE PROTECTION ---
window.addEventListener('pageshow', function(event) {
    if (event.persisted || (typeof performance !== 'undefined' && performance.getEntriesByType("navigation")[0].type === "back_forward")) {
        window.location.reload();
    }
});

window.onload = async () => {
    await loadData();
    window.setInterval(() => {
        if (document.visibilityState === 'visible') loadData();
    }, 3000);
};
