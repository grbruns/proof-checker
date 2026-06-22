'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let email = null;
let currentCourse = null;
let courseModalMode = 'create';
let psModalMode = 'create';
let psModalEditId = null;
let addProbPsId = null;

// ── API ────────────────────────────────────────────────────────────────────
function api(method, path, data) {
    const opts = {
        url: '/backend' + path,
        method,
        headers: { 'X-Auth-Token': email },
        dataType: 'json',
    };
    if (data !== undefined) {
        opts.contentType = 'application/json';
        opts.data = JSON.stringify(data);
    }
    return $.ajax(opts);
}

// ── Utilities ──────────────────────────────────────────────────────────────
function esc(s) {
    return $('<div>').text(s == null ? '' : String(s)).html();
}

function toLocalDt(utcStr) {
    if (!utcStr) return '';
    return utcStr.slice(0, 16).replace(' ', 'T');
}

function fromLocalDt(str) {
    if (!str) return null;
    return str.replace('T', ' ') + ':00';
}

function psStatusBadge(ps) {
    if (!ps.published) return '<span class="ui grey small label">Unpublished</span>';
    const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
    if (ps.until && ps.until < now) return '<span class="ui red small label">Closed</span>';
    if (ps.available_from && ps.available_from > now) return '<span class="ui yellow small label">Scheduled</span>';
    return '<span class="ui green small label">Open</span>';
}

function formatProof(logic, depth) {
    depth = depth || 0;
    if (typeof logic === 'string') {
        try { logic = JSON.parse(logic); } catch (e) { return logic; }
    }
    if (!Array.isArray(logic)) return String(logic);
    const pad = '   '.repeat(depth);
    return logic.map((line, i) => {
        if (Array.isArray(line)) {
            return pad + '┌─ subproof\n' + formatProof(line, depth + 1) + '\n' + pad + '└─';
        }
        return pad + String(i + 1).padStart(2) + '. ' + (line.wffstr || '').padEnd(30) + '  ' + (line.jstr || '');
    }).join('\n');
}

// ── Tabs ───────────────────────────────────────────────────────────────────
function activateTab(tabId) {
    $('.course-tab-menu .item').removeClass('active');
    $(`.course-tab-menu .item[data-tab="${tabId}"]`).addClass('active');
    $('.course-tab').removeClass('active');
    $(`.course-tab[data-tab="${tabId}"]`).addClass('active');
}

// ── Sign-in ────────────────────────────────────────────────────────────────
function handleSignIn() {
    const val = $('#signinEmail').val().trim();
    if (!val) return;
    email = val;
    sessionStorage.setItem('userEmail', email);

    api('GET', '/instructor/courses').then(courses => {
        $('#signinRow').hide();
        $('#userEmail').text(email);
        $('#main').show();
        renderCourseList(courses);
    }).fail(xhr => {
        email = null;
        if (xhr.status === 403) {
            $('#notAuthorized').show();
        } else {
            alert('Sign-in failed. Check the console for details.');
            console.error(xhr);
        }
    });
}

// ── Courses ────────────────────────────────────────────────────────────────
function renderCourseList(courses) {
    const el = $('#courseList').empty();
    if (!courses || courses.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No courses yet.</p>');
        return;
    }
    courses.forEach(c => {
        $('<div class="course-item">')
            .attr('data-id', c.id)
            .text(c.name)
            .toggleClass('selected', !!(currentCourse && currentCourse.id === c.id))
            .on('click', () => selectCourse(c, courses))
            .appendTo(el);
    });
}

function loadCourses() {
    return api('GET', '/instructor/courses').then(renderCourseList);
}

function selectCourse(course, courses) {
    currentCourse = course;
    renderCourseList(courses || [course]);
    $('#noCourseMsg').hide();
    $('#courseDetail').show();
    $('#courseDetailName').text(course.name);
    activateTab('tab-ps');
    loadProblemSets();
    loadStudents();
    loadTas();
    $('#tasViewSolutionsChk').prop('checked', !!course.tas_can_view_solutions);
}

// Course modal
function openCourseModal(mode) {
    courseModalMode = mode;
    if (mode === 'create') {
        $('#courseModalTitle').text('New Course');
        $('#courseNameInp').val('');
        $('#courseDescInp').val('');
        $('#courseMaxInp').val(200);
    } else {
        $('#courseModalTitle').text('Edit Course');
        $('#courseNameInp').val(currentCourse.name);
        $('#courseDescInp').val(currentCourse.description || '');
        $('#courseMaxInp').val(currentCourse.max_students || 200);
    }
    $('#courseModal').modal('show');
}

function saveCourseModal() {
    const name = $('#courseNameInp').val().trim();
    if (!name) { alert('Course name is required.'); return; }
    const data = {
        name,
        description: $('#courseDescInp').val(),
        max_students: parseInt($('#courseMaxInp').val()) || 200,
    };
    const req = courseModalMode === 'create'
        ? api('POST', '/instructor/courses', data)
        : api('PATCH', `/instructor/courses/${currentCourse.id}`, data);

    req.then(updated => {
        $('#courseModal').modal('hide');
        if (courseModalMode === 'edit') {
            currentCourse = { ...currentCourse, ...data };
            $('#courseDetailName').text(currentCourse.name);
        }
        loadCourses();
    }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
}

// ── Problem Sets ──────────────────────────────────────────────────────────
function loadProblemSets() {
    if (!currentCourse) return;
    api('GET', `/instructor/courses/${currentCourse.id}/problem_sets`).then(renderProblemSets);
}

function renderProblemSets(psList) {
    const el = $('#problemSetList').empty();
    if (!psList || psList.length === 0) {
        el.html('<p style="color:#888;">No problem sets yet.</p>');
        return;
    }
    psList.forEach(ps => el.append(buildPsCard(ps)));
}

function buildPsCard(ps) {
    const card = $('<div class="ps-card">');

    const header = $(`
        <div class="ps-card-header">
            <span style="flex:1; font-weight:bold;">${esc(ps.name)}</span>
            ${psStatusBadge(ps)}
            <span style="color:#999; font-size:.85em; margin-left:.25rem;">▼</span>
        </div>
    `).appendTo(card);

    const body = $(`<div class="ps-card-body" id="ps-body-${ps.id}">`).appendTo(card);

    $(`<div style="display:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:1rem;">
        <button class="ui small button ps-edit-btn" data-psid="${ps.id}">Edit Settings</button>
        <button class="ui small red basic button ps-delete-btn" data-psid="${ps.id}">Delete</button>
        <button class="ui small primary button ps-addprob-btn" data-psid="${ps.id}">+ Add Problem</button>
        <button class="ui small teal button ps-download-btn" data-psid="${ps.id}">Download Attempts</button>
    </div>`).appendTo(body);

    $(`<div id="ps-problems-${ps.id}"><em style="color:#888;">Click to load problems…</em></div>`)
        .appendTo(body);

    header.on('click', function (e) {
        if ($(e.target).is('button') || $(e.target).closest('button').length) return;
        const open = body.hasClass('open');
        body.toggleClass('open', !open);
        header.find('span:last-child').text(open ? '▼' : '▲');
        if (!open) loadProblems(ps.id);
    });

    return card;
}

// Problem Set modal
function openPsModal(mode, ps) {
    psModalMode = mode;
    psModalEditId = (mode === 'edit') ? ps.id : null;
    if (mode === 'create') {
        $('#psModalTitle').text('New Problem Set');
        $('#psNameInp').val('');
        $('#psPublishedInp').prop('checked', false);
        ['psAvailFromInp','psDueDateInp','psUntilInp','psRelSolInp','psTimeLimitInp','psMaxAttInp']
            .forEach(id => $('#' + id).val(''));
    } else {
        $('#psModalTitle').text('Edit Problem Set');
        $('#psNameInp').val(ps.name);
        $('#psPublishedInp').prop('checked', !!ps.published);
        $('#psAvailFromInp').val(toLocalDt(ps.available_from));
        $('#psDueDateInp').val(toLocalDt(ps.due_date));
        $('#psUntilInp').val(toLocalDt(ps.until));
        $('#psRelSolInp').val(toLocalDt(ps.release_solutions_at));
        $('#psTimeLimitInp').val(ps.time_limit_minutes || '');
        $('#psMaxAttInp').val(ps.max_attempts_per_problem || '');
    }
    $('#psModal').modal('show');
}

function savePsModal() {
    const name = $('#psNameInp').val().trim();
    if (!name) { alert('Name is required.'); return; }
    const data = {
        name,
        published:               $('#psPublishedInp').is(':checked') ? 1 : 0,
        available_from:          fromLocalDt($('#psAvailFromInp').val()),
        due_date:                fromLocalDt($('#psDueDateInp').val()),
        until:                   fromLocalDt($('#psUntilInp').val()),
        release_solutions_at:    fromLocalDt($('#psRelSolInp').val()),
        time_limit_minutes:      parseInt($('#psTimeLimitInp').val()) || null,
        max_attempts_per_problem: parseInt($('#psMaxAttInp').val()) || null,
    };
    const req = psModalMode === 'create'
        ? api('POST', `/instructor/courses/${currentCourse.id}/problem_sets`, data)
        : api('PATCH', `/instructor/problem_sets/${psModalEditId}`, data);

    req.then(() => {
        $('#psModal').modal('hide');
        loadProblemSets();
    }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
}

// ── Problems ──────────────────────────────────────────────────────────────
function loadProblems(psId) {
    api('GET', `/instructor/problem_sets/${psId}/problems`).then(problems => {
        renderProblems(problems, psId);
    });
}

function renderProblems(problems, psId) {
    const el = $(`#ps-problems-${psId}`).empty();
    if (!problems || problems.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No problems yet.</p>');
        return;
    }
    const tbody = $('<tbody>');
    problems.forEach(p => {
        $(`<tr>
            <td>${p.position}</td>
            <td>${esc(p.name)}</td>
            <td>${p.points != null ? p.points : '—'}</td>
            <td>${p.logic_type === 'fol' ? 'FOL' : 'Prop'}</td>
            <td>
              <button class="ui mini button prob-sol-btn"
                data-probid="${p.id}" data-probname="${esc(p.name)}">Solution</button>
              <button class="ui mini red basic button prob-del-btn"
                data-probid="${p.id}" data-psid="${psId}">Delete</button>
            </td>
        </tr>`).appendTo(tbody);
    });
    el.append($(`
        <table class="ui small compact table">
          <thead><tr><th>#</th><th>Name</th><th>Pts</th><th>Type</th><th>Actions</th></tr></thead>
        </table>
    `).append(tbody));
}

// Add Problem modal
function openProblemModal(psId) {
    addProbPsId = psId;
    ['probNameInp','probPremisesInp','probConcInp','probPointsInp'].forEach(id => $('#' + id).val(''));
    $('#probLogicInp').val('prop');
    $('#problemModal').modal('show');
}

function saveProblemModal() {
    const name       = $('#probNameInp').val().trim();
    const conclusion = $('#probConcInp').val().trim();
    if (!name || !conclusion) { alert('Name and conclusion are required.'); return; }
    const premRaw  = $('#probPremisesInp').val().trim();
    const premises = premRaw
        ? premRaw.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
        : [];
    const data = {
        name, premises, conclusion,
        logic_type: $('#probLogicInp').val(),
        points: parseInt($('#probPointsInp').val()) || null,
    };
    api('POST', `/instructor/problem_sets/${addProbPsId}/problems`, data).then(() => {
        $('#problemModal').modal('hide');
        loadProblems(addProbPsId);
    }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
}

// ── Solutions ─────────────────────────────────────────────────────────────
function viewSolution(probId, probName) {
    api('GET', `/instructor/problems/${probId}/solution`).then(sol => {
        $('#solutionProbName').text(probName);
        if (!sol) {
            $('#solutionMeta').text('No solution saved for this problem yet.');
            $('#solutionContent').text('');
        } else {
            $('#solutionMeta').text(`Saved by ${sol.author_email} · ${sol.updated_at}`);
            $('#solutionContent').text(formatProof(sol.logic));
        }
        $('#solutionModal').modal('show');
    }).fail(xhr => {
        if (xhr.status === 403) alert('Access to this solution is not permitted.');
        else alert('Error: ' + (xhr.responseText || xhr.statusText));
    });
}

// ── Download Attempts ─────────────────────────────────────────────────────
function downloadAttempts(psId) {
    api('GET', `/instructor/problem_sets/${psId}/attempts`).then(data => {
        if (!data || data.length === 0) { alert('No attempt data yet.'); return; }
        const headers = Object.keys(data[0]).join(',');
        const rows = data.map(row =>
            Object.values(row).map(v =>
                '"' + (Array.isArray(v) ? JSON.stringify(v) : String(v ?? '')).replace(/"/g, '""') + '"'
            ).join(',')
        );
        const csv = [headers, ...rows].join('\n');
        const a   = document.createElement('a');
        a.href     = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
        a.download = `attempts_ps${psId}.csv`;
        a.click();
    }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
}

// ── Students ──────────────────────────────────────────────────────────────
function loadStudents() {
    if (!currentCourse) return;
    api('GET', `/instructor/courses/${currentCourse.id}/students`).then(renderStudents);
}

function renderStudents(students) {
    $('#studentCount').text(students ? students.length : 0);
    const el = $('#studentList').empty();
    if (!students || students.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No students enrolled.</p>');
        return;
    }
    const tbody = $('<tbody>');
    students.forEach(s => {
        $(`<tr><td>${esc(s)}</td><td>
            <button class="ui mini red basic button student-rm-btn" data-email="${esc(s)}">Remove</button>
        </td></tr>`).appendTo(tbody);
    });
    el.append($('<table class="ui small compact table"><thead><tr><th>Email</th><th></th></tr></thead></table>').append(tbody));
}

// ── TAs ───────────────────────────────────────────────────────────────────
function loadTas() {
    if (!currentCourse) return;
    api('GET', `/instructor/courses/${currentCourse.id}/tas`).then(renderTas);
}

function renderTas(tas) {
    const el = $('#taList').empty();
    if (!tas || tas.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No TAs added.</p>');
        return;
    }
    const tbody = $('<tbody>');
    tas.forEach(t => {
        $(`<tr><td>${esc(t)}</td><td>
            <button class="ui mini red basic button ta-rm-btn" data-email="${esc(t)}">Remove</button>
        </td></tr>`).appendTo(tbody);
    });
    el.append($('<table class="ui small compact table"><thead><tr><th>Email</th><th></th></tr></thead></table>').append(tbody));
}

// ── Document ready ────────────────────────────────────────────────────────
$(function () {

    // Sign in on Enter
    $('#signinEmail').on('keydown', e => { if (e.key === 'Enter') handleSignIn(); });

    // Auto sign-in if email was saved from another page
    const saved = sessionStorage.getItem('userEmail');
    if (saved) { $('#signinEmail').val(saved); handleSignIn(); }

    // Tabs
    $('.course-tab-menu').on('click', '.item', function () {
        activateTab(this.dataset.tab);
    });

    // ── Courses
    $('#newCourseBtn').on('click', () => openCourseModal('create'));
    $('#saveCourseBtn').on('click', saveCourseModal);
    $('#editCourseBtn').on('click', () => openCourseModal('edit'));
    $('#deleteCourseBtn').on('click', () => {
        if (!currentCourse) return;
        if (!confirm(`Delete "${currentCourse.name}"?\nThis also removes all problem sets and problems.`)) return;
        api('DELETE', `/instructor/courses/${currentCourse.id}`).then(() => {
            currentCourse = null;
            $('#courseDetail').hide();
            $('#noCourseMsg').show();
            loadCourses();
        }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });

    // ── Problem sets
    $('#newPsBtn').on('click', () => openPsModal('create', null));
    $('#savePsBtn').on('click', savePsModal);

    $('#problemSetList').on('click', '.ps-edit-btn', function () {
        const psId = parseInt(this.dataset.psid);
        api('GET', `/instructor/problem_sets/${psId}`).then(ps => openPsModal('edit', ps));
    });
    $('#problemSetList').on('click', '.ps-delete-btn', function () {
        const psId = parseInt(this.dataset.psid);
        if (!confirm('Delete this problem set? Student attempt records are preserved.')) return;
        api('DELETE', `/instructor/problem_sets/${psId}`)
            .then(loadProblemSets)
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
    $('#problemSetList').on('click', '.ps-addprob-btn', function () {
        openProblemModal(parseInt(this.dataset.psid));
    });
    $('#problemSetList').on('click', '.ps-download-btn', function () {
        downloadAttempts(parseInt(this.dataset.psid));
    });

    // ── Problems
    $('#saveProbBtn').on('click', saveProblemModal);

    $('#problemSetList').on('click', '.prob-del-btn', function () {
        const probId = parseInt(this.dataset.probid);
        const psId   = parseInt(this.dataset.psid);
        if (!confirm('Delete this problem?')) return;
        api('DELETE', `/instructor/problems/${probId}`)
            .then(() => loadProblems(psId))
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
    $('#problemSetList').on('click', '.prob-sol-btn', function () {
        viewSolution(parseInt(this.dataset.probid), this.dataset.probname);
    });

    // ── Students
    $('#addStudentsBtn').on('click', () => {
        if (!currentCourse) return;
        const raw = $('#studentEmailsInput').val().trim();
        if (!raw) return;
        const emails = raw.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
        api('POST', `/instructor/courses/${currentCourse.id}/students`, { emails })
            .then(() => { $('#studentEmailsInput').val(''); loadStudents(); })
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
    $('#studentList').on('click', '.student-rm-btn', function () {
        const s = this.dataset.email;
        if (!confirm(`Remove ${s} from this course?`)) return;
        api('DELETE', `/instructor/courses/${currentCourse.id}/students/${encodeURIComponent(s)}`)
            .then(loadStudents)
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
    $('#tasViewSolutionsChk').on('change', function () {
        if (!currentCourse) return;
        const val = this.checked ? 1 : 0;
        api('PATCH', `/instructor/courses/${currentCourse.id}`, { tas_can_view_solutions: val })
            .then(() => { currentCourse.tas_can_view_solutions = !!val; })
            .fail(xhr => { this.checked = !this.checked; alert('Error: ' + xhr.responseText); });
    });

    // ── TAs
    $('#addTaBtn').on('click', () => {
        if (!currentCourse) return;
        const t = $('#taEmailInput').val().trim();
        if (!t) return;
        api('POST', `/instructor/courses/${currentCourse.id}/tas`, { email: t })
            .then(() => { $('#taEmailInput').val(''); loadTas(); })
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
    $('#taEmailInput').on('keydown', e => { if (e.key === 'Enter') $('#addTaBtn').click(); });
    $('#taList').on('click', '.ta-rm-btn', function () {
        const t = this.dataset.email;
        if (!confirm(`Remove TA ${t}?`)) return;
        api('DELETE', `/instructor/courses/${currentCourse.id}/tas/${encodeURIComponent(t)}`)
            .then(loadTas)
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });
});
