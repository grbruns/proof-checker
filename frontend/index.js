'use strict';

// ── Legacy repository data ─────────────────────────────────────────────────
const repositoryData = {
    userProofs: [],
    repoProofs: [],       // kept for backward compat; no longer displayed
    completedUserProofs: []
};
let adminUsers = [];

// ── Problem-set navigation state ───────────────────────────────────────────
let currentCourseId   = null;
let currentPsId       = null;
let currentPsName     = '';
let currentPsProblems = [];
let currentProblemSetProblem = null;  // the problem currently loaded from a PS

// ── Auth / User ────────────────────────────────────────────────────────────
function handleSignIn() {
    const email = document.getElementById('signin-email').value.trim();
    if (!email) return;
    $.getJSON('/backend/admins', (admins) => {
        try { adminUsers = admins['Admins']; } catch(e) { console.error(e); }
        new User(email).initializeDisplay().loadProofs();
    });
}

class User {
    constructor(email) {
        this.email = email;
        User._currentEmail = email;
        if (adminUsers.indexOf(this.email) > -1) {
            this.showAdminFunctionality();
        }
        return this;
    }

    initializeDisplay() {
        $('#user-email').text(this.email);
        $('#signin-form').hide();
        $('#load-container').show();
        $('#nameyourproof').show();
        return this;
    }

    showAdminFunctionality() {
        $('#adminLink').show();
        return this;
    }

    showInstructorLink() {
        $('#instructorLink').show();
        $('#saveToPsBtn').show();
        return this;
    }

    loadProofs() {
        loadUserProofs();
        loadCourses();
        // Show Instructor link if the user is an instructor
        $.ajax({
            url: '/backend/instructor/courses',
            method: 'GET',
            headers: { 'X-Auth-Token': this.email },
            dataType: 'json',
        }).then(() => this.showInstructorLink()).fail(() => {});
        return this;
    }

    static isSignedIn()     { return !!User._currentEmail; }
    static isAdministrator(){ return adminUsers.indexOf(User._currentEmail) > -1; }
    static getIdToken()     { return User._currentEmail; }
}

// ── Backend helpers ────────────────────────────────────────────────────────
function backendPOST(path_str, data_obj) {
    if (!User.isSignedIn()) {
        if (sessionStorage.getItem('loginPromptShown') == null) {
            alert('You are not signed in.\nTo save your work, please sign in and then try again.');
            sessionStorage.setItem('loginPromptShown', 'true');
        }
        return Promise.reject('Unauthenticated user');
    }
    return authenticatedBackendPOST(path_str, data_obj, User.getIdToken());
}

function authenticatedBackendPOST(path_str, data_obj, id_token) {
    return $.ajax({
        url: '/backend/' + path_str,
        method: 'POST',
        data: JSON.stringify(data_obj),
        dataType: 'json',
        contentType: 'application/json; charset=utf-8',
        headers: { 'X-Auth-Token': id_token }
    }).then(
        (data) => data,
        (jqXHR, textStatus, errorThrown) => { console.error(textStatus, errorThrown); }
    );
}

function backendGET(path_str) {
    if (!User.isSignedIn()) return Promise.reject('Unauthenticated');
    return $.ajax({
        url: '/backend/' + path_str,
        method: 'GET',
        dataType: 'json',
        headers: { 'X-Auth-Token': User.getIdToken() }
    });
}

// ── Legacy proof selector helpers ──────────────────────────────────────────
const prepareSelect = (selector, options) => {
    const el = document.querySelector(selector);
    $(el).empty();
    el.appendChild(Object.assign(new Option('Select...', null, true, true), { disabled: true }));
    (options || []).forEach(proof => el.appendChild(new Option(proof.ProofName, proof.Id)));
};

function loadUserProofs() {
    backendPOST('proofs', { selection: 'user' }).then((data) => {
        repositoryData.userProofs = data || [];
        prepareSelect('#userProofSelect', data);
        $('#userProofSelect').data('repositoryDataKey', 'userProofs');
        if (data && data.length > 0) {
            $('#legacyProofsWrap').show();
        }
    }, console.log);
}

// ── Course / Problem Set / Problem navigation ──────────────────────────────
function shortDate(dtStr) {
    if (!dtStr) return '';
    try {
        const d = new Date(dtStr.replace(' ', 'T'));
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch(e) { return dtStr.slice(0, 10); }
}

function loadCourses() {
    backendGET('student/courses').then(courses => {
        if (!courses || courses.length === 0) return;
        if (courses.length === 1) {
            currentCourseId = courses[0].id;
            loadProblemSets(courses[0].id);
        } else {
            $('#courseSelect').empty().append(
                $('<option>').val('').text('Select a course…').prop('disabled', true).prop('selected', true)
            );
            courses.forEach(c => $('#courseSelect').append(new Option(c.name, c.id)));
            $('#courseSelectWrap').show();
        }
    }).fail(() => {});  // not enrolled in any course — that's fine
}

function loadProblemSets(courseId) {
    currentCourseId = courseId;
    $('#psSelectWrap').hide();
    $('#problemSelectWrap').hide();
    $('#retryWrap').hide();

    backendGET('student/courses/' + courseId + '/problem_sets').then(psList => {
        if (!psList || psList.length === 0) return;
        const now = new Date().toISOString().slice(0, 19).replace('T', ' ');

        $('#psSelect').empty().append(
            $('<option>').val('').text('Select a problem set…').prop('disabled', true).prop('selected', true)
        );
        psList.forEach(ps => {
            let label = ps.name;
            const closed = ps.until && ps.until < now;
            if (closed) label += ' [Closed]';
            else if (ps.due_date) label += ' [Due: ' + shortDate(ps.due_date) + ']';
            const opt = new Option(label, ps.id);
            if (closed) opt.disabled = true;
            $('#psSelect').append(opt);
        });
        $('#psSelectWrap').show();
    });
}

function loadProblemList(psId) {
    currentPsId = psId;
    $('#problemSelectWrap').hide();
    $('#retryWrap').hide();

    // Store PS name for context display
    const psOpt = $('#psSelect option:selected');
    currentPsName = psOpt.length ? psOpt.text().replace(/\s*\[.*$/, '') : '';

    backendGET('student/problem_sets/' + psId + '/problems').then(problems => {
        if (!problems || problems.length === 0) return;
        currentPsProblems = problems;

        $('#problemSelect').empty().append(
            $('<option>').val('').text('Select a problem…').prop('disabled', true).prop('selected', true)
        );
        problems.forEach(p => {
            const icon = p.solved ? '● ' : (p.in_progress ? '◑ ' : '○ ');
            const pts  = p.points != null ? ' (' + p.points + 'pt)' : '';
            $('#problemSelect').append(new Option(icon + p.name + pts, p.id));
        });
        $('#problemSelectWrap').show();
    });
}

function selectProblem(problemId) {
    const problem = currentPsProblems.find(p => p.id === problemId);
    if (!problem) return;

    backendGET('student/problems/' + problemId + '/attempt')
        .then(attempt => loadProblem(problem, attempt))
        .fail(xhr => {
            // 404 = no attempt yet; anything else = still try to load fresh
            loadProblem(problem, null);
        });
}

function loadProblem(problem, savedAttempt) {
    currentProblemSetProblem = problem;

    // Set logic type
    predicateSettings = (problem.logic_type === 'fol');
    $('#folradio').prop('checked', predicateSettings);
    $('#tflradio').prop('checked', !predicateSettings);

    // Pre-load saved logic into proofContainer (createProb reads it from there)
    if (savedAttempt && savedAttempt.current_logic) {
        const raw = savedAttempt.current_logic;
        const logicArr = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (Array.isArray(logicArr) && logicArr.length > 0) {
            $('.proofContainer').data({ Logic: [JSON.stringify(logicArr)], Rules: [] });
        } else {
            $('.proofContainer').removeData();
        }
    } else {
        $('.proofContainer').removeData();
    }

    $('#proofName').val(problem.name);
    $('#probpremises').val((problem.premises || []).join(', '));
    $('#probconc').val(problem.conclusion);
    $('#repoProblem').val('false');

    $('#retryWrap').toggle(!!(savedAttempt && savedAttempt.solved));

    $('#createProb').click();

    // Show problem context beneath the proof title
    const pos = currentPsProblems.indexOf(problem) + 1;
    const total = currentPsProblems.length;
    $('#problemcontext').text(currentPsName + ' · Problem ' + pos + ' of ' + total).show();
}

function refreshProblemStatus(problemId, status) {
    const icons = { solved: '● ', in_progress: '◑ ', unsolved: '○ ' };
    const icon = icons[status] || '◑ ';
    const opt = $('#problemSelect option[value="' + problemId + '"]');
    if (opt.length) opt.text(icon + opt.text().replace(/^[○●◑]\s/, ''));
    const p = currentPsProblems.find(p => p.id === problemId);
    if (p) { p.solved = (status === 'solved'); p.in_progress = (status !== 'unsolved'); }
}

// ── Save-to-Problem-Set (instructor shortcut) ──────────────────────────────
function openSaveToPsModal() {
    const proofName  = $('#proofName').val() || $('.proofNameSpan').text() || '';
    const logicType  = $('#folradio').is(':checked') ? 'fol' : 'prop';

    $('#stpsNameInp').val(proofName);
    $('#stpsLogicInp').val(logicType === 'fol' ? 'First-Order' : 'Propositional');
    $('#stpsPointsInp').val('');
    $('#stpsCourseSelect').empty().append(
        $('<option>').val('').text('Loading…').prop('disabled', true).prop('selected', true)
    );
    $('#stpsPsSelect').empty();

    $.ajax({
        url: '/backend/instructor/courses', method: 'GET',
        headers: { 'X-Auth-Token': User.getIdToken() }, dataType: 'json',
    }).then(courses => {
        $('#stpsCourseSelect').empty().append(
            $('<option>').val('').text('Select course…').prop('disabled', true).prop('selected', true)
        );
        (courses || []).forEach(c => $('#stpsCourseSelect').append(new Option(c.name, c.id)));
    }).fail(() => {
        $('#stpsCourseSelect').empty().append($('<option>').text('Error loading courses'));
    });

    $('#saveToPsModal').modal('show');
}

// ── Document ready ─────────────────────────────────────────────────────────
$(document).ready(function () {

    // ── Check Proof event: save to legacy table + problem-set attempt ──────
    $('.proofContainer').on('checkProofEvent', (event) => {
        const proofData = event.detail.proofdata;
        const Premises  = proofData.filter(e => e.jstr === 'Pr').map(e => e.wffstr);
        const Logic     = [JSON.stringify(proofData)];
        const Rules     = [];
        const proofName  = $('.proofNameSpan').text() || 'n/a';
        const repoProblem = $('#repoProblem').val() || 'false';
        const proofType  = predicateSettings ? 'fol' : 'prop';
        const proofCompleted = event.detail.proofCompleted;
        const conclusion = event.detail.wantedConc;

        const postData = new Proof('proof', proofName, proofType, Premises, Logic, Rules,
                                   proofCompleted, conclusion, repoProblem);

        backendPOST('saveproof', postData).then((data) => {
            if (postData.proofCompleted === 'true') {
                // refresh legacy dropdown quietly
                backendPOST('proofs', { selection: 'user' }).then(d => {
                    repositoryData.userProofs = d || [];
                    prepareSelect('#userProofSelect', d);
                });
            }
        }, console.log);

        // Also save to problem-set attempt endpoint if a PS problem is loaded
        if (currentProblemSetProblem && User.isSignedIn()) {
            const solved = proofCompleted === 'true';
            $.ajax({
                url: '/backend/student/problems/' + currentProblemSetProblem.id + '/attempt',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ logic: proofData, proof_completed: solved }),
                headers: { 'X-Auth-Token': User.getIdToken() },
                dataType: 'json',
            }).then(() => {
                refreshProblemStatus(currentProblemSetProblem.id, solved ? 'solved' : 'in_progress');
                if (solved) $('#retryWrap').show();
            }).fail(xhr => {
                if (xhr.status === 403 || xhr.status === 429) {
                    alert(xhr.responseText || 'Submission rejected: past deadline or max attempts reached.');
                }
            });
        }
    });

    // ── Admin: toggle public/repo status ──────────────────────────────────
    $('.proofContainer').on('click', '#togglePublicButton', (event) => {
        let proofName = $('.proofNameSpan').text();
        if (!proofName) proofName = prompt('Please enter a name for your proof:');
        if (!proofName) return;
        if (!proofName.startsWith('Repository - ')) proofName = 'Repository - ' + proofName;
        $('.proofNameSpan').text(proofName);

        const publicStatus = $('#repoProblem').val() || 'false';
        if (publicStatus === 'false') {
            $('#repoProblem').val('true');
            $('#togglePublicButton').fadeOut().text('Make Private').fadeIn();
        } else {
            $('#repoProblem').val('false');
            $('#togglePublicButton').fadeOut().text('Make Public').fadeIn();
        }
        $('#checkButton').click();
    });

    // ── Legacy proof selector (userProofSelect only) ───────────────────────
    $('#userProofSelect').on('change', (event) => {
        const selectedId  = event.target.value;
        const dataSet     = repositoryData['userProofs'];
        const selectedProof = dataSet.filter(p => p.Id == selectedId)[0];
        if (!selectedProof) { console.error('Proof ID not found.'); return; }

        $('#repoProblem').val('false');
        if (Array.isArray(selectedProof.Logic) && Array.isArray(selectedProof.Rules)) {
            $('.proofContainer').data({ Logic: selectedProof.Logic, Rules: selectedProof.Rules });
        }

        predicateSettings = (selectedProof.ProofType !== 'prop');
        $('#folradio').prop('checked', predicateSettings);
        $('#tflradio').prop('checked', !predicateSettings);
        $('#proofName').val(selectedProof.ProofName);
        $('#probpremises').val(selectedProof.Premise.join(','));
        $('#probconc').val(selectedProof.Conclusion);

        // clear any PS context before loading legacy proof
        currentProblemSetProblem = null;
        $('#retryWrap').hide();
        $('#problemcontext').hide().text('');

        $('#createProb').click();
    });

    // ── Course / PS / Problem selects ─────────────────────────────────────
    $('#courseSelect').on('change', function () {
        const id = parseInt(this.value);
        if (!id) return;
        loadProblemSets(id);
    });

    $('#psSelect').on('change', function () {
        const id = parseInt(this.value);
        if (!id) return;
        loadProblemList(id);
    });

    $('#problemSelect').on('change', function () {
        const id = parseInt(this.value);
        if (!id) return;
        selectProblem(id);
    });

    // ── Retry button ───────────────────────────────────────────────────────
    $('#retryBtn').on('click', () => {
        if (!currentProblemSetProblem) return;
        loadProblem(currentProblemSetProblem, null);
    });

    // ── Create problem (premises/conclusion form) ─────────────────────────
    $('#createProb').on('click', function () {
        predicateSettings = document.getElementById('folradio').checked;
        createProb(
            document.getElementById('proofName').value,
            document.getElementById('probpremises').value,
            document.getElementById('probconc').value
        );
    });

    // ── Clear & start new proof ────────────────────────────────────────────
    $('.newProof').on('click', () => {
        resetProofUI();
        $('#repoProblem').val('false');
        currentProblemSetProblem = null;
        $('#retryWrap').hide();
        $('#problemcontext').hide().text('');
        $('.createProof').slideDown();
        $('.proofContainer').slideUp();
    });

    // ── Save to Problem Set modal ──────────────────────────────────────────
    $('#saveToPsBtn').on('click', openSaveToPsModal);

    $('#stpsCourseSelect').on('change', function () {
        const courseId = this.value;
        if (!courseId) return;
        $('#stpsPsSelect').empty().append(
            $('<option>').val('').text('Loading…').prop('disabled', true).prop('selected', true)
        );
        $.ajax({
            url: '/backend/instructor/courses/' + courseId + '/problem_sets', method: 'GET',
            headers: { 'X-Auth-Token': User.getIdToken() }, dataType: 'json',
        }).then(psList => {
            $('#stpsPsSelect').empty().append(
                $('<option>').val('').text('Select problem set…').prop('disabled', true).prop('selected', true)
            );
            (psList || []).forEach(ps => $('#stpsPsSelect').append(new Option(ps.name, ps.id)));
        });
    });

    $('#stpsSaveBtn').on('click', () => {
        const name    = $('#stpsNameInp').val().trim();
        const psId    = $('#stpsPsSelect').val();
        if (!name)  { alert('Problem name is required.');  return; }
        if (!psId)  { alert('Please select a problem set.'); return; }

        const premisesStr = $('#probpremises').val().trim();
        const premises = premisesStr
            ? premisesStr.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
            : [];
        const conclusion = $('#probconc').val().trim();
        if (!conclusion) { alert('Conclusion is required.'); return; }

        $.ajax({
            url: '/backend/instructor/problem_sets/' + psId + '/problems',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                name, premises, conclusion,
                logic_type: $('#folradio').is(':checked') ? 'fol' : 'prop',
                points: parseInt($('#stpsPointsInp').val()) || null,
            }),
            headers: { 'X-Auth-Token': User.getIdToken() },
            dataType: 'json',
        }).then(() => {
            $('#saveToPsModal').modal('hide');
            alert('Problem added to problem set!');
        }).fail(xhr => alert('Error: ' + (xhr.responseText || xhr.statusText)));
    });

});

// ── Proof UI helpers ───────────────────────────────────────────────────────
function resetProofUI() {
    $('#proofName').val('');
    $('#tflradio').prop('checked', true);
    $('#probpremises').val('');
    $('#probconc').val('');
    $('.proofNameSpan').text('');
    $('#theproof').empty();
    $('.proofContainer').removeData();
    // Reset only the legacy saved-proofs select, not the nav selects
    $('#userProofSelect option:first-child').prop('selected', true);
}

function createProb(proofName, premisesString, conclusionString) {
    const pstr = premisesString.replace(/^[,;\s]*/, '').replace(/[,;\s]*$/, '');
    const prems = pstr.split(/[,;\s]*[,;][,;\s]*/);

    const conc = fixWffInputStr(conclusionString);
    const cw   = parseIt(conc);
    if (!cw.isWellFormed) {
        alert('The conclusion ' + fixWffInputStr(conc) + ' is not well formed.');
        return false;
    }
    if (predicateSettings && cw.allFreeVars.length !== 0) {
        alert('The conclusion is not closed.');
        return false;
    }

    let proofdata = [];
    const containerData = $('.proofContainer').data();
    if (Object.prototype.hasOwnProperty.call(containerData, 'Logic')) {
        if (Array.isArray(containerData.Logic) && containerData.Logic.length > 0) {
            proofdata = JSON.parse(containerData.Logic[0]);
        }
    } else {
        for (let a = 0; a < prems.length; a++) {
            if (prems[a] !== '') {
                const w = parseIt(fixWffInputStr(prems[a]));
                if (!w.isWellFormed) {
                    alert('Premise ' + (a + 1) + ', ' + fixWffInputStr(prems[a]) + ', is not well formed.');
                    return false;
                }
                if (predicateSettings && w.allFreeVars.length !== 0) {
                    alert('Premise ' + (a + 1) + ' is not closed.');
                    return false;
                }
                proofdata.push({ wffstr: wffToString(w, false), jstr: 'Pr' });
            }
        }
    }

    $('.createProof').slideUp();
    resetProofUI();
    $('.proofContainer').show();
    $('.proofNameSpan').text(proofName);

    let probstr = '';
    for (let k = 0; k < prems.length; k++) {
        probstr += prettyStr(prems[k]);
        if (k + 1 < prems.length) probstr += ', ';
    }
    document.getElementById('proofdetails').innerHTML =
        'Construct a proof for the argument: ' + probstr + ' ∴ ' + wffToString(cw, true);

    makeProof(document.getElementById('theproof'), proofdata, wffToString(cw, false));
    return true;
}
