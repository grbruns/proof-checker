'use strict';

let email = null;

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

// ── Sign-in ────────────────────────────────────────────────────────────────
function handleSignIn() {
    const val = $('#signinEmail').val().trim();
    if (!val) return;
    email = val;

    api('GET', '/admin/instructors').then(instructors => {
        $('#signinRow').hide();
        $('#userEmail').text(email);
        $('#main').show();
        renderInstructors(instructors);
        loadCourses();
    }).fail(xhr => {
        email = null;
        if (xhr.status === 403 || xhr.status === 401) {
            $('#notAuthorized').show();
        } else {
            alert('Sign-in failed: ' + (xhr.responseText || xhr.statusText));
        }
    });
}

// ── Instructors ────────────────────────────────────────────────────────────
function loadInstructors() {
    api('GET', '/admin/instructors').then(renderInstructors);
}

function renderInstructors(instructors) {
    const el = $('#instructorList').empty();
    if (!instructors || instructors.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No instructors yet.</p>');
        return;
    }
    instructors.forEach(e => {
        $(`<div class="instructor-row">
            <span>${esc(e)}</span>
            <button class="ui mini red basic button rm-instructor-btn" data-email="${esc(e)}">Remove</button>
          </div>`).appendTo(el);
    });
}

// ── Courses ────────────────────────────────────────────────────────────────
function loadCourses() {
    api('GET', '/admin/courses').then(renderCourses);
}

function renderCourses(courses) {
    const el = $('#courseList').empty();
    if (!courses || courses.length === 0) {
        el.html('<p style="color:#888; font-size:.9em;">No courses yet.</p>');
        return;
    }

    // Group by instructor_email
    const byInstructor = {};
    courses.forEach(c => {
        if (!byInstructor[c.instructor_email]) byInstructor[c.instructor_email] = [];
        byInstructor[c.instructor_email].push(c);
    });

    Object.entries(byInstructor).forEach(([instructor, courseList]) => {
        const group = $('<div class="course-group">');
        group.append(`<div class="course-group-label">${esc(instructor)}</div>`);
        const tbody = $('<tbody>');
        courseList.forEach(c => {
            $(`<tr>
                <td>${esc(c.name)}</td>
                <td style="color:#888;">${esc(c.description || '')}</td>
                <td style="color:#aaa; text-align:right;">${c.max_students} max</td>
              </tr>`).appendTo(tbody);
        });
        group.append(
            $('<table class="ui small compact table">').append(
                '<thead><tr><th>Course</th><th>Description</th><th></th></tr></thead>',
                tbody
            )
        );
        el.append(group);
    });
}

// ── CSV download (legacy admin function) ───────────────────────────────────
function downloadCsv() {
    $.ajax({
        url: '/backend/proofs',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ selection: 'downloadrepo' }),
        headers: { 'X-Auth-Token': email },
        dataType: 'json',
    }).then(data => {
        if (!Array.isArray(data) || data.length < 1) {
            alert('No student proof data found.');
            return;
        }
        const headers = Object.keys(data[0]).join(',');
        const rows = data.map(row =>
            Object.values(row).map(v =>
                '"' + (Array.isArray(v) ? v.join('|') : String(v ?? '')).replace(/"/g, '""') + '"'
            ).join(',')
        );
        const csv = [headers, ...rows].join('\n');
        const a   = document.createElement('a');
        a.href     = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
        a.download = 'Student_Problems.csv';
        a.click();
    }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
}

// ── Document ready ─────────────────────────────────────────────────────────
$(function () {
    $('#signinEmail').on('keydown', e => { if (e.key === 'Enter') handleSignIn(); });

    $('#addInstructorBtn').on('click', () => {
        const val = $('#newInstructorEmail').val().trim();
        if (!val) return;
        api('POST', '/admin/instructors', { email: val }).then(() => {
            $('#newInstructorEmail').val('');
            loadInstructors();
        }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });

    $('#newInstructorEmail').on('keydown', e => {
        if (e.key === 'Enter') $('#addInstructorBtn').click();
    });

    $('#instructorList').on('click', '.rm-instructor-btn', function () {
        const target = this.dataset.email;
        if (!confirm(`Remove instructor ${target}?\nTheir courses and data are preserved.`)) return;
        api('DELETE', '/admin/instructors/' + encodeURIComponent(target))
            .then(loadInstructors)
            .fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });

    $('#downloadCsvBtn').on('click', downloadCsv);
});
