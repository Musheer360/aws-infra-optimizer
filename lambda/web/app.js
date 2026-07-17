(function () {
  'use strict';

  var config = window.COSTOPT_CONFIG || { mode: 'cloud', apiEndpoint: '' };
  var isLocal = config.mode === 'local';
  var STORE_KEY = 'costoptimizer360.preferences.v3';

  var SERVICES = [
    { id: 'ec2', label: 'EC2 instances', group: 'Compute', hint: 'Rightsizing', icon: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h5"/>' },
    { id: 'stopped_ec2', label: 'Stopped EC2', group: 'Compute', hint: 'Attached waste', icon: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M9 9v6m6-6v6"/>' },
    { id: 'lambda', label: 'Lambda', group: 'Compute', hint: 'Memory tuning', icon: '<path d="m6 4 4 8-3 7h4l2-5 3 5h4L10 4z"/>' },
    { id: 'ebs', label: 'EBS volumes', group: 'Storage', hint: 'Orphaned & gp3', icon: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6m-14 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>' },
    { id: 'ebs_snapshot', label: 'EBS snapshots', group: 'Storage', hint: 'Age & orphans', icon: '<path d="M5 6h14v13H5zM8 3h8v3M9 10h6m-6 4h4"/>' },
    { id: 's3', label: 'S3 buckets', group: 'Storage', hint: 'Lifecycle hygiene', icon: '<path d="m12 3 7 4-7 4-7-4zM5 12l7 4 7-4M5 17l7 4 7-4"/>' },
    { id: 'rds', label: 'RDS databases', group: 'Data', hint: 'Rightsizing', icon: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>' },
    { id: 'dynamodb', label: 'DynamoDB', group: 'Data', hint: 'Capacity mode', icon: '<path d="M5 4h14v16H5zM9 4v16m6-16v16M5 9h14m-14 6h14"/>' },
    { id: 'eip', label: 'Public IPv4', group: 'Network', hint: 'Idle addresses', icon: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>' },
    { id: 'natgateway', label: 'NAT gateways', group: 'Network', hint: 'Idle & transfer', icon: '<path d="M4 8h16M4 16h16M8 4v16m8-16v16"/><path d="m5 5 3 3-3 3m14 2-3 3 3 3"/>' },
    { id: 'elb', label: 'Load balancers', group: 'Network', hint: 'Idle traffic', icon: '<path d="M4 12h16M8 7l-4 5 4 5m8-10 4 5-4 5"/><circle cx="12" cy="12" r="3"/>' },
    { id: 'commitments', label: 'Savings Plans', group: 'Rate', hint: 'Purchase options', icon: '<path d="M4 19V9m5 10V5m5 14v-7m5 7V3"/>' }
  ];

  var REGIONS = [
    ['us-east-1', 'US East (N. Virginia)', 'Americas'], ['us-east-2', 'US East (Ohio)', 'Americas'],
    ['us-west-1', 'US West (N. California)', 'Americas'], ['us-west-2', 'US West (Oregon)', 'Americas'],
    ['ca-central-1', 'Canada (Central)', 'Americas'], ['ca-west-1', 'Canada (Calgary)', 'Americas'],
    ['sa-east-1', 'South America (São Paulo)', 'Americas'], ['af-south-1', 'Africa (Cape Town)', 'Middle East & Africa'],
    ['il-central-1', 'Israel (Tel Aviv)', 'Middle East & Africa'], ['me-south-1', 'Middle East (Bahrain)', 'Middle East & Africa'],
    ['me-central-1', 'Middle East (UAE)', 'Middle East & Africa'], ['ap-east-1', 'Asia Pacific (Hong Kong)', 'Asia Pacific'],
    ['ap-south-1', 'Asia Pacific (Mumbai)', 'Asia Pacific'], ['ap-south-2', 'Asia Pacific (Hyderabad)', 'Asia Pacific'],
    ['ap-southeast-1', 'Asia Pacific (Singapore)', 'Asia Pacific'], ['ap-southeast-2', 'Asia Pacific (Sydney)', 'Asia Pacific'],
    ['ap-southeast-3', 'Asia Pacific (Jakarta)', 'Asia Pacific'], ['ap-southeast-4', 'Asia Pacific (Melbourne)', 'Asia Pacific'],
    ['ap-northeast-1', 'Asia Pacific (Tokyo)', 'Asia Pacific'], ['ap-northeast-2', 'Asia Pacific (Seoul)', 'Asia Pacific'],
    ['ap-northeast-3', 'Asia Pacific (Osaka)', 'Asia Pacific'], ['eu-central-1', 'Europe (Frankfurt)', 'Europe'],
    ['eu-central-2', 'Europe (Zurich)', 'Europe'], ['eu-west-1', 'Europe (Ireland)', 'Europe'],
    ['eu-west-2', 'Europe (London)', 'Europe'], ['eu-west-3', 'Europe (Paris)', 'Europe'],
    ['eu-south-1', 'Europe (Milan)', 'Europe'], ['eu-south-2', 'Europe (Spain)', 'Europe'],
    ['eu-north-1', 'Europe (Stockholm)', 'Europe']
  ];

  var PRESETS = {
    comprehensive: SERVICES.map(function (service) { return service.id; }),
    quick: ['stopped_ec2', 'ebs', 'ebs_snapshot', 'eip', 'elb'],
    compute: ['ec2', 'rds', 'lambda', 'dynamodb', 'commitments'],
    network: ['eip', 'natgateway', 'elb', 's3']
  };
  var COMMON_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'];
  var FORMAT_LABELS = { docx: 'Word (.docx)', xlsx: 'Excel (.xlsx)', html: 'HTML dashboard', json: 'JSON', csv: 'CSV' };
  var state = {
    services: new Set(PRESETS.comprehensive),
    regions: new Set(['us-east-1']),
    auth: isLocal ? 'credentials' : 'role',
    artifactUrl: '',
    artifactName: '',
    elapsedTimer: null,
    pollStopped: false,
    startedAt: 0,
    requestContext: null,
    toastTimer: null
  };

  var $ = function (selector, root) { return (root || document).querySelector(selector); };
  var $$ = function (selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); };
  var el = {
    setup: $('#setupView'), progress: $('#progressView'), results: $('#resultsView'), form: $('#scanForm'),
    serviceGrid: $('#serviceGrid'), regionGrid: $('#regionGrid'), selectedRegions: $('#selectedRegions'),
    regionSearch: $('#regionSearch'), errorSummary: $('#errorSummary'), progressBar: $('#progressBar'),
    progressTrack: $('#progressTrack'), progressStage: $('#progressStage'), progressTime: $('#progressTime'),
    progressScope: $('#progressScope'), dashboard: $('#dashboard'), download: $('#downloadBtn'), toast: $('#toast')
  };

  function safePreferences() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); } catch (ignore) { return {}; }
  }

  function loadPreferences() {
    var saved = safePreferences();
    if (typeof saved.clientName === 'string') $('#clientName').value = saved.clientName.slice(0, 80);
    if (Array.isArray(saved.services)) {
      var validServices = saved.services.filter(function (id) { return SERVICES.some(function (service) { return service.id === id; }); });
      if (validServices.length) state.services = new Set(validServices);
    }
    if (Array.isArray(saved.regions)) {
      var validRegions = saved.regions.filter(function (id) { return REGIONS.some(function (region) { return region[0] === id; }); });
      if (validRegions.length) state.regions = new Set(validRegions);
    }
    if (FORMAT_LABELS[saved.exportFormat]) {
      var radio = $('input[name="exportFormat"][value="' + saved.exportFormat + '"]');
      if (radio) radio.checked = true;
    }
    if (!isLocal && (saved.auth === 'role' || saved.auth === 'credentials')) state.auth = saved.auth;
  }

  function savePreferences() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({
        clientName: $('#clientName').value.trim(),
        services: Array.from(state.services),
        regions: Array.from(state.regions),
        exportFormat: $('input[name="exportFormat"]:checked').value,
        auth: state.auth
      }));
    } catch (ignore) { /* Preferences are optional. */ }
  }

  function renderServices() {
    el.serviceGrid.innerHTML = SERVICES.map(function (service) {
      var checked = state.services.has(service.id) ? ' checked' : '';
      return '<label class="service-option">' +
        '<input type="checkbox" value="' + service.id + '"' + checked + '>' +
        '<span class="service-symbol" aria-hidden="true"><svg viewBox="0 0 24 24">' + service.icon + '</svg></span>' +
        '<span class="service-copy"><strong>' + service.label + '</strong><small>' + service.group + ' · ' + service.hint + '</small></span>' +
        '<span class="checkmark" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="m3 8 3 3 7-7"/></svg></span></label>';
    }).join('');
    updateServiceSummary();
  }

  function updateServiceSummary() {
    $('#serviceCount').textContent = state.services.size + ' of ' + SERVICES.length + ' selected';
    $$('.preset').forEach(function (button) {
      var ids = PRESETS[button.dataset.preset];
      var isExact = ids.length === state.services.size && ids.every(function (id) { return state.services.has(id); });
      button.classList.toggle('active', isExact);
      button.setAttribute('aria-pressed', isExact ? 'true' : 'false');
    });
    updateReview();
  }

  function renderRegions() {
    var query = el.regionSearch.value.trim().toLowerCase();
    var rows = REGIONS.filter(function (region) {
      return !query || (region[0] + ' ' + region[1] + ' ' + region[2]).toLowerCase().indexOf(query) !== -1;
    });
    el.regionGrid.innerHTML = rows.length ? rows.map(function (region) {
      var checked = state.regions.has(region[0]) ? ' checked' : '';
      return '<label class="region-option"><input type="checkbox" value="' + region[0] + '"' + checked + '><span>' + region[1] + '</span><code>' + region[0] + '</code></label>';
    }).join('') : '<div class="region-empty">No regions match “' + escapeHtml(query) + '”.</div>';

    var selected = REGIONS.filter(function (region) { return state.regions.has(region[0]); });
    el.selectedRegions.innerHTML = selected.slice(0, 8).map(function (region) {
      return '<span class="region-chip">' + region[0] + '<button type="button" data-remove-region="' + region[0] + '" aria-label="Remove ' + region[1] + '">×</button></span>';
    }).join('') + (selected.length > 8 ? '<span class="region-chip">+' + (selected.length - 8) + ' more</span>' : '');
    $('#regionCount').textContent = state.regions.size + (state.regions.size === 1 ? ' selected' : ' selected');
    updateReview();
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  function setAuth(mode, focus) {
    if (isLocal) mode = 'credentials';
    state.auth = mode;
    $$('#authTabs [role="tab"]').forEach(function (tab) {
      var active = tab.dataset.auth === mode;
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.tabIndex = active ? 0 : -1;
      if (active && focus) tab.focus();
    });
    $('#rolePanel').hidden = mode !== 'role';
    $('#credentialsPanel').hidden = mode !== 'credentials';
    updateReview();
    savePreferences();
  }

  function selectedFormat() { return $('input[name="exportFormat"]:checked').value; }

  function updateReview() {
    var client = $('#clientName').value.trim();
    $('#reviewClient').textContent = client || 'Not named yet';
    $('#reviewCoverage').textContent = state.services.size + (state.services.size === 1 ? ' service' : ' services') + ' · ' + state.regions.size + (state.regions.size === 1 ? ' region' : ' regions');
    $('#reviewAuth').textContent = state.auth === 'role' ? 'IAM role' : 'Temporary credentials';
    $('#reviewFormat').textContent = FORMAT_LABELS[selectedFormat()];
    var units = state.services.size * Math.max(state.regions.size, 1);
    $('#scanEstimate').textContent = units <= 12 ? '1–2 min' : (units <= 48 ? '2–5 min' : '5–10 min');
  }

  function clearErrors() {
    el.errorSummary.hidden = true;
    el.errorSummary.innerHTML = '';
    ['clientName', 'roleArn', 'accessKeyId', 'secretAccessKey'].forEach(function (id) {
      $('#' + id).removeAttribute('aria-invalid');
    });
    ['clientError', 'servicesError', 'regionsError', 'roleArnError', 'accessKeyError', 'secretKeyError'].forEach(function (id) { $('#' + id).textContent = ''; });
  }

  function validate() {
    clearErrors();
    var errors = [];
    var add = function (id, errorId, message) {
      var control = $('#' + id);
      if (control) control.setAttribute('aria-invalid', 'true');
      if (errorId) $('#' + errorId).textContent = message;
      errors.push({ id: id, message: message });
    };
    if (!$('#clientName').value.trim()) add('clientName', 'clientError', 'Enter a name for this assessment.');
    if (!state.services.size) { $('#servicesError').textContent = 'Select at least one service.'; errors.push({ id: 'serviceGrid', message: 'Select at least one service.' }); }
    if (!state.regions.size) { $('#regionsError').textContent = 'Select at least one AWS region.'; errors.push({ id: 'regionSearch', message: 'Select at least one AWS region.' }); }
    if (state.auth === 'role') {
      var role = $('#roleArn').value.trim();
      if (!role) add('roleArn', 'roleArnError', 'Enter the cross-account role ARN.');
      else if (!/^arn:aws[a-z-]*:iam::\d{12}:role\/.+/.test(role)) add('roleArn', 'roleArnError', 'Use a valid IAM role ARN.');
    } else {
      if (!$('#accessKeyId').value.trim()) add('accessKeyId', 'accessKeyError', 'Enter an AWS access key ID.');
      if (!$('#secretAccessKey').value.trim()) add('secretAccessKey', 'secretKeyError', 'Enter the matching secret access key.');
    }
    if (errors.length) {
      el.errorSummary.innerHTML = '<strong>We need a few details before starting.</strong>' + errors.map(function (error) { return '<a href="#' + error.id + '">' + escapeHtml(error.message) + '</a>'; }).join('');
      el.errorSummary.hidden = false;
      el.errorSummary.focus();
      return false;
    }
    return true;
  }

  function buildRequest() {
    var regions = Array.from(state.regions);
    var body = {
      clientName: $('#clientName').value.trim(),
      services: Array.from(state.services),
      regions: regions,
      region: regions[0],
      exportFormat: selectedFormat()
    };
    if (state.auth === 'role') {
      body.roleArn = $('#roleArn').value.trim();
      if ($('#externalId').value.trim()) body.externalId = $('#externalId').value.trim();
    } else {
      body.accessKeyId = $('#accessKeyId').value.trim();
      body.secretAccessKey = $('#secretAccessKey').value.trim();
      if ($('#sessionToken').value.trim()) body.sessionToken = $('#sessionToken').value.trim();
    }
    if (isLocal) body.async = true;
    return body;
  }

  function clearSecretFields() {
    ['accessKeyId', 'secretAccessKey', 'sessionToken', 'externalId'].forEach(function (id) { $('#' + id).value = ''; });
    var secretInput = $('#secretAccessKey');
    secretInput.type = 'password';
    var revealButton = $('[data-reveal="secretAccessKey"]');
    if (revealButton) {
      revealButton.textContent = 'Show';
      revealButton.setAttribute('aria-label', 'Show secret access key');
    }
  }

  function showView(name) {
    el.setup.hidden = name !== 'setup';
    el.progress.hidden = name !== 'progress';
    el.results.hidden = name !== 'results';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function resetArtifact() {
    if (state.artifactUrl) URL.revokeObjectURL(state.artifactUrl);
    state.artifactUrl = '';
    state.artifactName = '';
    el.download.disabled = true;
    el.download.querySelector('span').textContent = 'Download report';
  }

  function startElapsedTimer() {
    stopElapsedTimer();
    state.startedAt = Date.now();
    var tick = function () {
      var seconds = Math.floor((Date.now() - state.startedAt) / 1000);
      el.progressTime.textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0') + ' elapsed';
    };
    tick();
    state.elapsedTimer = setInterval(tick, 1000);
  }

  function stopElapsedTimer() {
    if (state.elapsedTimer) clearInterval(state.elapsedTimer);
    state.elapsedTimer = null;
  }

  function beginProgress(context) {
    resetArtifact();
    state.requestContext = context;
    state.pollStopped = false;
    if (window.CostOpt360 && window.CostOpt360.clear) window.CostOpt360.clear();
    el.dashboard.innerHTML = '';
    el.progressScope.textContent = context.services.length + ' services across ' + context.regions.length + (context.regions.length === 1 ? ' region' : ' regions') + ' · ' + FORMAT_LABELS[context.exportFormat];
    el.progressStage.textContent = 'Establishing a secure connection…';
    el.progressBar.style.width = '';
    if (isLocal) {
      el.progressTrack.setAttribute('aria-valuenow', '0');
      el.progressBar.style.width = '0%';
    } else {
      el.progressTrack.removeAttribute('aria-valuenow');
    }
    $$('.process-steps span').forEach(function (step, index) { step.classList.toggle('active', index === 0); });
    showView('progress');
    $('#progressTitle').focus({ preventScroll: true });
    startElapsedTimer();
  }

  function updateProgress(percent, message, stageIndex) {
    var bounded = Math.max(0, Math.min(100, Number(percent) || 0));
    if (isLocal) {
      el.progressTrack.setAttribute('aria-valuenow', String(bounded));
      el.progressBar.style.width = bounded + '%';
    }
    el.progressStage.textContent = message;
    $$('.process-steps span').forEach(function (step, index) { step.classList.toggle('active', index <= stageIndex); });
  }

  async function submitAssessment(event) {
    event.preventDefault();
    if (!validate()) return;
    savePreferences();
    var body = buildRequest();
    var context = { clientName: body.clientName, services: body.services.slice(), regions: body.regions.slice(), exportFormat: body.exportFormat, auth: state.auth };
    beginProgress(context);

    if (!config.apiEndpoint || (!isLocal && config.apiEndpoint.indexOf('http') !== 0)) {
      clearSecretFields();
      showFailure('The cloud API is not configured yet.', 'Deploy the backend before running a live assessment, or explore the sample workspace now.');
      return;
    }

    try {
      var payload = JSON.stringify(body);
      var pending = fetch(config.apiEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload });
      clearSecretFields();
      body = null;
      payload = null;
      var response = await pending;
      var data = await parseResponse(response);
      if (!response.ok) throw new Error(data.message || data.error || ('Request failed with status ' + response.status));
      if (isLocal && data.scanId) await pollProgress(data.scanId);
      else if (data.file || data.recommendations) completeAssessment(data, context);
      else throw new Error('The scan completed without a usable result.');
    } catch (error) {
      clearSecretFields();
      showFailure('We could not complete the assessment.', sanitizeError(error));
    }
  }

  async function parseResponse(response) {
    var text = await response.text();
    if (!text) return {};
    try { return JSON.parse(text); } catch (ignore) { throw new Error('The server returned an unreadable response.'); }
  }

  async function pollProgress(scanId) {
    var failures = 0;
    while (!state.pollStopped) {
      try {
        var response = await fetch(config.progressEndpoint + '/' + encodeURIComponent(scanId), { cache: 'no-store' });
        var data = await parseResponse(response);
        if (response.status === 404 || data.status === 'not_found') throw new Error('This local scan could not be found. It may have expired or the server restarted.');
        if (!response.ok) throw new Error(data.error || 'Unable to read scan progress.');
        failures = 0;
        if (data.status === 'starting') updateProgress(data.progress || 2, 'Connecting to AWS…', 0);
        else if (data.status === 'scanning') updateProgress(data.progress || 8, data.current_service ? 'Analyzing ' + data.current_service : 'Analyzing AWS resources…', 2);
        else if (data.status === 'generating') updateProgress(data.progress || 98, 'Building your report and action plan…', 3);
        else if (data.status === 'complete') { completeAssessment(data.result || {}, state.requestContext); return; }
        else if (data.status === 'error') throw new Error(data.error || 'The local scan failed.');
      } catch (error) {
        failures += 1;
        if (failures >= 6) throw error;
        el.progressStage.textContent = failures >= 3 ? 'Connection interrupted; retrying safely…' : 'Checking assessment progress…';
      }
      await wait(Math.min(1000 + failures * 750, 5000));
    }
  }

  function wait(milliseconds) { return new Promise(function (resolve) { setTimeout(resolve, milliseconds); }); }
  function sanitizeError(error) {
    var message = error && error.message ? String(error.message) : 'An unexpected error occurred.';
    return message.replace(/AKIA[A-Z0-9]+/g, '[redacted access key]').slice(0, 600);
  }

  function showFailure(title, detail) {
    stopElapsedTimer();
    state.pollStopped = true;
    showView('setup');
    el.errorSummary.innerHTML = '<strong>' + escapeHtml(title) + '</strong><span>' + escapeHtml(detail) + '</span><a href="#accessHeading">Review the connection and try again.</a>';
    el.errorSummary.hidden = false;
    el.errorSummary.focus();
  }

  function base64Blob(base64, type) {
    var binary = atob(base64);
    var chunks = [];
    for (var offset = 0; offset < binary.length; offset += 65536) {
      var slice = binary.slice(offset, offset + 65536);
      var bytes = new Uint8Array(slice.length);
      for (var index = 0; index < slice.length; index += 1) bytes[index] = slice.charCodeAt(index);
      chunks.push(bytes);
    }
    return new Blob(chunks, { type: type });
  }

  function mimeType(filename) {
    var lower = String(filename || '').toLowerCase();
    if (lower.endsWith('.docx')) return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    if (lower.endsWith('.xlsx')) return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    if (lower.endsWith('.html') || lower.endsWith('.htm')) return 'text/html;charset=utf-8';
    if (lower.endsWith('.json')) return 'application/json;charset=utf-8';
    if (lower.endsWith('.csv')) return 'text/csv;charset=utf-8';
    return 'application/octet-stream';
  }

  function createResultContext(data, context, isDemo) {
    var container = $('#resultContext');
    container.innerHTML = '';
    var items = [
      ['<path d="M12 8v4l3 2"/><circle cx="12" cy="12" r="9"/>', isDemo ? 'Sample data' : ('Generated ' + formatDate(data.generatedAt))],
      ['<path d="M4 5h16v14H4zM8 3v4m8-4v4M4 9h16"/>', context.regions.length + (context.regions.length === 1 ? ' region' : ' regions')],
      ['<path d="M4 6h16M4 12h16M4 18h10"/>', context.services.length + ' checks requested'],
      ['<path d="M12 3 5 6v6c0 4.5 2.8 7.5 7 9 4.2-1.5 7-4.5 7-9V6z"/>', 'Read-only · estimates require validation']
    ];
    items.forEach(function (item, index) {
      var span = document.createElement('span');
      span.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24">' + item[0] + '</svg>';
      var text = document.createTextNode(item[1]);
      if (index === 0) { var strong = document.createElement('strong'); strong.appendChild(text); span.appendChild(strong); }
      else span.appendChild(text);
      container.appendChild(span);
    });
  }

  function formatDate(value) {
    if (!value) return 'just now';
    var date = new Date(value);
    return isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  function completeAssessment(data, context, isDemo) {
    stopElapsedTimer();
    state.pollStopped = true;
    updateProgress(100, 'Assessment complete', 3);
    resetArtifact();
    if (data.file && data.filename) {
      try {
        state.artifactName = data.filename;
        state.artifactUrl = URL.createObjectURL(base64Blob(data.file, mimeType(data.filename)));
        el.download.disabled = false;
        el.download.querySelector('span').textContent = 'Download ' + data.filename.split('.').pop().toUpperCase() + ' report';
      } catch (error) { showToast('The dashboard is ready, but the report file could not be prepared.', true); }
    } else if (isDemo) {
      state.artifactName = 'costoptimizer360-sample.json';
      state.artifactUrl = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' }));
      el.download.disabled = false;
      el.download.querySelector('span').textContent = 'Download sample JSON';
    }
    createResultContext(data, context, Boolean(isDemo));
    $('#resultsSubtitle').textContent = isDemo ? 'A realistic sample workspace showing how live findings become an implementation-ready plan.' : 'Review the highest-value moves, inspect the evidence, and export an implementation-ready plan.';
    try {
      if (!window.CostOpt360) throw new Error('Dashboard renderer unavailable.');
      window.CostOpt360.renderDashboard(data, el.dashboard, { clientName: context.clientName, requestedServices: context.services, requestedRegions: context.regions, demo: Boolean(isDemo) });
    } catch (error) {
      el.dashboard.innerHTML = '<div class="co-error-state"><strong>The report is ready, but the interactive view could not load.</strong><p>You can still download the generated report above.</p></div>';
    }
    showView('results');
    $('#resultsTitle').focus();
    showToast(isDemo ? 'Sample assessment loaded.' : 'Assessment complete. Your report is ready.');
  }

  function showToast(message, isError) {
    clearTimeout(state.toastTimer);
    el.toast.textContent = message;
    el.toast.classList.toggle('error', Boolean(isError));
    el.toast.hidden = false;
    state.toastTimer = setTimeout(function () { el.toast.hidden = true; }, 4200);
  }

  function downloadArtifact() {
    if (!state.artifactUrl) return;
    var link = document.createElement('a');
    link.href = state.artifactUrl;
    link.download = state.artifactName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    showToast('Download started: ' + state.artifactName);
  }

  function newAssessment() {
    if (window.CostOpt360 && window.CostOpt360.hasSelection && window.CostOpt360.hasSelection()) {
      if (!window.confirm('Start a new assessment? Your unexported action plan selection will be cleared.')) return;
    }
    resetArtifact();
    if (window.CostOpt360 && window.CostOpt360.clear) window.CostOpt360.clear();
    el.dashboard.innerHTML = '';
    showView('setup');
    $('#setupTitle').focus({ preventScroll: true });
  }

  function sampleRecommendation(overrides) {
    var base = { region: 'us-east-1', confidence: 'High', effort: 'Low', risk: 'Low', priority: 'Quick Win', priority_score: 93, savings_basis: 'on_demand', source: 'AWS telemetry', tags: { Environment: 'production', Owner: 'platform' } };
    Object.keys(overrides).forEach(function (key) { base[key] = overrides[key]; });
    base.annual_savings = Math.round((base.monthly_savings || 0) * 1200) / 100;
    return base;
  }

  function demoData() {
    var recommendations = {
      ec2: [sampleRecommendation({ instance_id: 'i-0a7f2c9b18d4e6f01', current_type: 'm5.2xlarge', recommended_type: 'm7i.large', monthly_savings: 1280, priority: 'High', priority_score: 98, effort: 'Medium', risk: 'Medium', performance_risk: 'Low', reason: 'CPU stayed below 12% at p95 during the 14-day lookback.', recommendation: 'Rightsize to m7i.large after load testing.', remediation: 'aws ec2 modify-instance-attribute --instance-id i-0a7f2c9b18d4e6f01 --instance-type "{\\"Value\\":\\"m7i.large\\"}"' })],
      stopped_ec2: [sampleRecommendation({ instance_id: 'i-042d8a14c2f7ab921', monthly_savings: 412, reason: 'Instance has been stopped for 46 days while 2.4 TiB of EBS remains attached.', recommendation: 'Snapshot required volumes, then terminate the instance and remove obsolete storage.', remediation: 'aws ec2 describe-volumes --filters Name=attachment.instance-id,Values=i-042d8a14c2f7ab921' })],
      ebs: [sampleRecommendation({ volume_id: 'vol-07de31b6f8c245ad9', current_type: 'gp2', recommended_type: 'gp3', monthly_savings: 286, reason: 'The volume can retain baseline performance on gp3 at a lower unit price.', recommendation: 'Migrate gp2 to gp3 with matched IOPS and throughput.', remediation: 'aws ec2 modify-volume --volume-id vol-07de31b6f8c245ad9 --volume-type gp3 --iops 3000 --throughput 125' })],
      ebs_snapshot: [sampleRecommendation({ snapshot_id: 'snap-0f89c3a3d45b2019e', age_days: 428, monthly_savings: 145, reason: 'Snapshot is 428 days old and is not referenced by an active AMI.', recommendation: 'Confirm retention policy, then delete the orphaned snapshot.', remediation: 'aws ec2 delete-snapshot --snapshot-id snap-0f89c3a3d45b2019e' })],
      rds: [sampleRecommendation({ db_id: 'orders-primary', current_class: 'db.r6g.2xlarge', recommended_class: 'db.r6g.xlarge', monthly_savings: 930, priority: 'High', priority_score: 96, effort: 'Medium', risk: 'Medium', reason: 'Average CPU is 8.7% with low connection pressure and healthy freeable memory.', recommendation: 'Test a one-size reduction during the next maintenance window.', remediation: 'aws rds modify-db-instance --db-instance-identifier orders-primary --db-instance-class db.r6g.xlarge --apply-immediately' })],
      lambda: [sampleRecommendation({ function_name: 'image-processing-worker', current_memory: 2048, recommended_memory: 1536, avg_duration: 312, monthly_savings: 118, priority: 'Medium', priority_score: 72, effort: 'Medium', reason: 'Duration and invocation profile indicate excess allocated memory.', recommendation: 'Power-tune at 1536 MB and compare latency before deployment.', remediation: 'aws lambda update-function-configuration --function-name image-processing-worker --memory-size 1536' })],
      eip: [sampleRecommendation({ ip_address: '18.211.42.17', allocation_id: 'eipalloc-07bd18ca3912d901f', monthly_savings: 29.2, reason: 'Public IPv4 address is allocated but not associated with a resource.', recommendation: 'Release the address if it is not reserved for an upcoming migration.', remediation: 'aws ec2 release-address --allocation-id eipalloc-07bd18ca3912d901f' })],
      natgateway: [sampleRecommendation({ nat_gateway_id: 'nat-038daf8f2e4c0d719', region: 'us-west-2', monthly_savings: 610, priority: 'High', priority_score: 91, effort: 'Medium', risk: 'Low', reason: 'Most processed bytes are S3 and DynamoDB traffic eligible for gateway endpoints.', recommendation: 'Route eligible traffic through free gateway VPC endpoints.', remediation: 'aws ec2 create-vpc-endpoint --vpc-id vpc-0123456789abcdef0 --service-name com.amazonaws.us-west-2.s3 --vpc-endpoint-type Gateway' })],
      dynamodb: [sampleRecommendation({ table_name: 'session-events', region: 'eu-west-1', monthly_savings: 214, priority: 'Medium', priority_score: 68, effort: 'Medium', reason: 'Provisioned capacity remained below the calculated on-demand break-even point.', recommendation: 'Evaluate PAY_PER_REQUEST for this variable workload.', remediation: 'aws dynamodb update-table --table-name session-events --billing-mode PAY_PER_REQUEST --region eu-west-1' })],
      elb: [sampleRecommendation({ load_balancer_name: 'legacy-staging-alb', region: 'us-west-2', monthly_savings: 162, reason: 'No meaningful requests were observed during the lookback window.', recommendation: 'Verify DNS and target dependencies, then remove the idle load balancer.', remediation: 'aws elbv2 delete-load-balancer --load-balancer-arn arn:aws:elasticloadbalancing:us-west-2:123456789012:loadbalancer/app/legacy-staging-alb/example' })],
      s3: [sampleRecommendation({ bucket_name: 'northstar-build-artifacts', region: 'us-east-1', monthly_savings: 0, priority: 'Medium', priority_score: 61, effort: 'Medium', reason: 'Old object versions and incomplete multipart uploads have no lifecycle policy.', recommendation: 'Add noncurrent-version expiry and abort incomplete multipart uploads.', remediation: 'aws s3api put-bucket-lifecycle-configuration --bucket northstar-build-artifacts --lifecycle-configuration file://lifecycle.json' })],
      savings_plan: [sampleRecommendation({ type: 'Compute Savings Plan', region: 'Global', monthly_savings: 1810, annual_savings: 21720, priority: 'Medium', priority_score: 66, effort: 'Medium', risk: 'Medium', savings_basis: 'commitment_purchase', reason: 'Stable eligible compute spend supports a 1-year partial-upfront commitment.', recommendation: 'Review the purchase recommendation and validate workload durability before committing.', remediation: 'Open AWS Cost Explorer → Savings Plans → Recommendations and review the 30-day lookback.' })]
    };
    return {
      totalMonthlySavings: 4186.2, totalAnnualSavings: 50234.4, commitmentMonthlySavings: 1810, commitmentAnnualSavings: 21720,
      quickWins: 5, highPriority: 3, generatedAt: new Date().toISOString(), regions: ['us-east-1', 'us-west-2', 'eu-west-1'],
      recommendationCounts: { ec2: 1, stopped_ec2: 1, ebs: 1, ebs_snapshot: 1, rds: 1, lambda: 1, eip: 1, natgateway: 1, dynamodb: 1, elb: 1, s3: 1, savings_plan: 1 },
      riSpCoverage: { ri_coverage_pct: 42, ri_coverage_hours_pct: 48.7, sp_coverage_pct: 63.4, sp_utilization_pct: 91.2 },
      forecast: { forecast_month: 48720, month_to_date: 23410 }, recommendations: recommendations
    };
  }

  function openDemo() {
    clearErrors();
    clearSecretFields();
    var context = { clientName: 'Northstar Commerce · Production', services: PRESETS.comprehensive.slice(), regions: ['us-east-1', 'us-west-2', 'eu-west-1'], exportFormat: 'json', auth: 'sample' };
    beginProgress(context);
    updateProgress(100, 'Sample workspace ready', 3);
    setTimeout(function () { completeAssessment(demoData(), context, true); }, 320);
  }

  function bindEvents() {
    el.form.addEventListener('submit', submitAssessment);
    $('#clientName').addEventListener('input', function () { updateReview(); savePreferences(); });
    el.serviceGrid.addEventListener('change', function (event) {
      if (!event.target.matches('input[type="checkbox"]')) return;
      if (event.target.checked) state.services.add(event.target.value); else state.services.delete(event.target.value);
      updateServiceSummary(); savePreferences();
    });
    $$('.preset').forEach(function (button) {
      button.addEventListener('click', function () { state.services = new Set(PRESETS[button.dataset.preset]); renderServices(); savePreferences(); });
    });
    el.regionGrid.addEventListener('change', function (event) {
      if (!event.target.matches('input[type="checkbox"]')) return;
      if (event.target.checked) state.regions.add(event.target.value); else state.regions.delete(event.target.value);
      renderRegions(); savePreferences();
    });
    el.selectedRegions.addEventListener('click', function (event) {
      var button = event.target.closest('[data-remove-region]');
      if (!button) return;
      state.regions.delete(button.dataset.removeRegion); renderRegions(); savePreferences();
    });
    el.regionSearch.addEventListener('input', renderRegions);
    $$('[data-region-action]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (button.dataset.regionAction === 'all') state.regions = new Set(REGIONS.map(function (region) { return region[0]; }));
        else if (button.dataset.regionAction === 'common') state.regions = new Set(COMMON_REGIONS);
        else state.regions.clear();
        renderRegions(); savePreferences();
      });
    });
    $$('#authTabs [role="tab"]').forEach(function (tab) {
      tab.addEventListener('click', function () { setAuth(tab.dataset.auth); });
      tab.addEventListener('keydown', function (event) {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault(); setAuth(state.auth === 'role' ? 'credentials' : 'role', true);
      });
    });
    $$('input[name="exportFormat"]').forEach(function (radio) { radio.addEventListener('change', function () { updateReview(); savePreferences(); }); });
    $$('.reveal-secret').forEach(function (button) {
      button.addEventListener('click', function () {
        var input = $('#' + button.dataset.reveal); var showing = input.type === 'text';
        input.type = showing ? 'password' : 'text'; button.textContent = showing ? 'Show' : 'Hide'; button.setAttribute('aria-label', (showing ? 'Show' : 'Hide') + ' secret access key');
      });
    });
    $('#demoBtn').addEventListener('click', openDemo);
    $('#summaryDemoBtn').addEventListener('click', openDemo);
    $('#newScanBtn').addEventListener('click', newAssessment);
    el.download.addEventListener('click', downloadArtifact);
    window.addEventListener('beforeunload', function () { state.pollStopped = true; resetArtifact(); });
  }

  function initialize() {
    loadPreferences();
    renderServices(); renderRegions(); bindEvents();
    if (isLocal) {
      $('#modeBadge').textContent = 'Local workspace';
      $('#authTabs').hidden = true;
      $('#rolePanel').hidden = true;
      $('#credentialsPanel').hidden = false;
      $('#accessIntro').textContent = 'Credentials are sent only to this local server and cleared as soon as the scan starts.';
    }
    setAuth(state.auth);
    updateReview();
  }

  initialize();
})();
