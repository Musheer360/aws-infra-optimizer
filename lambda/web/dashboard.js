(function () {
  'use strict';

  var SERVICE_LABELS = {
    ec2: 'EC2 rightsizing', stopped_ec2: 'Stopped EC2', ebs: 'EBS volumes', ebs_snapshot: 'EBS snapshots',
    rds: 'RDS databases', lambda: 'Lambda functions', eip: 'Public IPv4', natgateway: 'NAT gateways',
    dynamodb: 'DynamoDB', elb: 'Load balancers', s3: 'S3 buckets', savings_plan: 'Savings Plans'
  };
  var SERVICE_COLORS = {
    ec2: '#1677c8', stopped_ec2: '#5a8db7', ebs: '#7158b5', ebs_snapshot: '#9a72cb', rds: '#d17128',
    lambda: '#e49b24', eip: '#198e91', natgateway: '#0d7a91', dynamodb: '#1d8d68', elb: '#3b9f88',
    s3: '#788c2f', savings_plan: '#7c55b4'
  };
  var BASIS_LABELS = {
    on_demand: 'On-Demand estimate', after_discounts: 'After existing discounts', commitment_purchase: 'Commitment purchase estimate'
  };
  var PRIORITY_RANK = { 'Quick Win': 0, High: 1, Medium: 2, Low: 3, '-': 4 };
  var runtime = null;

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }
  function text(value) {
    if (value == null) return '';
    if (Array.isArray(value)) return value.map(text).filter(Boolean).join(', ');
    if (typeof value === 'object') return Object.keys(value).map(function (key) { return key + ': ' + text(value[key]); }).join(', ');
    return String(value);
  }
  function number(value) { var parsed = Number(value); return isFinite(parsed) ? parsed : 0; }
  function money(value) { return '$' + number(value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }); }
  function moneyPrecise(value) { return '$' + number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function percent(value) { return number(value).toLocaleString(undefined, { maximumFractionDigits: 1 }) + '%'; }
  function resourceId(rec) {
    return rec.instance_id || rec.volume_id || rec.db_id || rec.function_name || rec.snapshot_id || rec.load_balancer_name ||
      rec.nat_gateway_id || rec.table_name || rec.ip_address || rec.bucket_name || rec.allocation_id || rec.resource_id || rec.type || 'Resource';
  }
  function normalizePriority(rec) {
    if (rec.quick_win || rec.priority === 'Quick Win') return 'Quick Win';
    return ['High', 'Medium', 'Low'].indexOf(rec.priority) !== -1 ? rec.priority : 'Medium';
  }
  function tagText(tags) {
    if (!tags) return '';
    if (Array.isArray(tags)) return tags.map(text).join(' ');
    if (typeof tags === 'object') return Object.keys(tags).map(function (key) { return key + ' ' + text(tags[key]); }).join(' ');
    return text(tags);
  }
  function flatten(recommendations) {
    var rows = [];
    Object.keys(recommendations || {}).forEach(function (service) {
      var list = recommendations[service];
      if (!Array.isArray(list)) return;
      list.forEach(function (rec, index) {
        var monthly = number(rec.monthly_savings);
        rows.push({
          key: service + '-' + rows.length,
          order: rows.length,
          service: service,
          label: SERVICE_LABELS[service] || service,
          id: text(resourceId(rec)),
          region: text(rec.region || 'Global'),
          monthly: monthly,
          annual: number(rec.annual_savings || monthly * 12),
          priority: normalizePriority(rec),
          score: number(rec.priority_score),
          confidence: text(rec.confidence || 'Medium'),
          effort: text(rec.effort || 'Medium'),
          risk: text(rec.risk || 'Medium'),
          basis: text(rec.savings_basis || (service === 'savings_plan' ? 'commitment_purchase' : 'on_demand')),
          reason: text(rec.reason || rec.issue || rec.issues || 'No additional rationale was returned.'),
          recommendation: text(rec.recommendation || 'Review this opportunity with the owning team.'),
          remediation: text(rec.remediation || ''),
          tagsText: tagText(rec.tags),
          raw: rec,
          index: index
        });
      });
    });
    return rows;
  }
  function pill(value, type) {
    var normalized = String(value || '').toLowerCase();
    var tone = type === 'basis' ? 'purple' : (normalized.indexOf('quick') >= 0 ? 'quick' : (normalized.indexOf('high') >= 0 ? 'high' : (normalized.indexOf('low') >= 0 ? 'low' : (normalized.indexOf('medium') >= 0 ? 'medium' : 'neutral'))));
    return '<span class="co-pill ' + tone + '">' + escapeHtml(value || 'Not available') + '</span>';
  }
  function icon(path) { return '<svg aria-hidden="true" viewBox="0 0 24 24">' + path + '</svg>'; }

  function kpi(label, value, foot, modifier, path, filter) {
    var card = '<article class="co-kpi ' + (modifier || '') + '"><div class="co-kpi-top"><span class="co-kpi-label">' + escapeHtml(label) + '</span><span class="co-kpi-icon">' + icon(path) + '</span></div><div class="co-kpi-value">' + escapeHtml(value) + '</div><div class="co-kpi-foot">' + escapeHtml(foot) + '</div></article>';
    return filter ? '<button type="button" class="co-kpi-button" data-quick="' + filter + '" aria-label="Filter recommendations to ' + escapeHtml(label) + '">' + card + '</button>' : card;
  }

  function serviceBars(rows) {
    var totals = {};
    rows.forEach(function (row) { if (row.basis !== 'commitment_purchase' && row.monthly > 0) totals[row.service] = (totals[row.service] || 0) + row.monthly; });
    var entries = Object.keys(totals).map(function (service) { return [service, totals[service]]; }).sort(function (a, b) { return b[1] - a[1]; });
    if (!entries.length) return '<div class="co-empty-chart">No positive waste-reduction savings were returned for this scope.</div>';
    var top = entries.slice(0, 7); var max = top[0][1] || 1;
    return '<div class="co-bars">' + top.map(function (entry) {
      return '<button type="button" class="co-bar-button" data-service-bar="' + entry[0] + '"><span class="co-bar-label">' + escapeHtml(SERVICE_LABELS[entry[0]] || entry[0]) + '</span><span class="co-bar-track"><i class="co-bar-fill" style="width:' + Math.max(2, entry[1] / max * 100).toFixed(1) + '%;background:' + (SERVICE_COLORS[entry[0]] || '#0b6bcb') + '"></i></span><span class="co-bar-value">' + money(entry[1]) + '/mo</span></button>';
    }).join('') + '</div>';
  }

  function priorityPanel(rows) {
    if (!rows.length) return '<div class="co-empty-chart">No recommendations were returned, so there is no priority mix to display.</div>';
    var counts = { 'Quick Win': 0, High: 0, Medium: 0, Low: 0 };
    rows.forEach(function (row) { counts[row.priority] = (counts[row.priority] || 0) + 1; });
    var total = rows.length;
    var quick = counts['Quick Win'] / total * 100;
    var high = quick + counts.High / total * 100;
    var medium = high + counts.Medium / total * 100;
    var colors = { 'Quick Win': '#0b6bcb', High: '#b42318', Medium: '#d68400', Low: '#0d9878' };
    return '<div class="co-priority-wrap"><div class="co-priority-ring" style="--quick:' + quick + '%;--high:' + high + '%;--medium:' + medium + '%"><div class="co-ring-center"><strong>' + rows.length + '</strong><span>findings</span></div></div><div class="co-legend">' +
      Object.keys(counts).map(function (priority) { return '<button type="button" data-priority-bar="' + priority + '"><i class="co-legend-dot" style="background:' + colors[priority] + '"></i><span>' + priority + '</span><strong>' + counts[priority] + '</strong></button>'; }).join('') + '</div></div>';
  }

  function coveragePanel(coverage) {
    var riCoverage = coverage.ri_coverage_hours_pct != null ? coverage.ri_coverage_hours_pct :
      (coverage.ri_coverage_ce_pct != null ? coverage.ri_coverage_ce_pct : coverage.ri_coverage_pct);
    var metrics = [
      ['RI coverage', riCoverage],
      ['SP coverage', coverage.sp_coverage_pct], ['SP utilization', coverage.sp_utilization_pct]
    ].filter(function (metric) { return metric[1] != null; });
    if (!metrics.length) return '<div class="co-empty-chart">Coverage data was not returned. Cost Explorer permissions or usage history may be unavailable.</div>';
    return '<div class="co-metric-list">' + metrics.map(function (metric) {
      var value = Math.max(0, Math.min(100, number(metric[1])));
      return '<div class="co-metric-row"><span>' + metric[0] + '</span><div class="co-meter"><i style="width:' + value + '%"></i></div><strong>' + percent(value) + '</strong></div>';
    }).join('') + '</div><div class="co-callout">' + icon('<path d="M12 3 5 6v6c0 4.5 2.8 7.5 7 9 4.2-1.5 7-4.5 7-9V6z"/><path d="M12 8v4m0 3h.01"/>') + '<span>Coverage and utilization are context—not additive savings. Validate commitment recommendations against workload durability.</span></div>';
  }

  function forecastPanel(forecast) {
    if (forecast.forecast_month == null && forecast.month_to_date == null) return '<div class="co-empty-chart">No Cost Explorer forecast was returned for this assessment.</div>';
    return '<div class="co-forecast">' +
      '<div class="co-forecast-item"><span>Forecast AWS spend this month</span><strong>' + (forecast.forecast_month == null ? 'Not available' : money(forecast.forecast_month)) + '</strong></div>' +
      '<div class="co-forecast-item"><span>Month-to-date AWS spend</span><strong>' + (forecast.month_to_date == null ? 'Not available' : money(forecast.month_to_date)) + '</strong></div></div>' +
      '<div class="co-callout">' + icon('<path d="M4 18V9m5 9V5m5 13v-6m5 6V3"/>') + '<span>The forecast is expected spend, not savings. Potential savings remain estimates until changes are validated and implemented.</span></div>';
  }

  function optionList(values, label) {
    return '<option value="">' + label + '</option>' + values.map(function (value) { return '<option value="' + escapeHtml(value) + '">' + escapeHtml(value) + '</option>'; }).join('');
  }
  function unique(rows, field) {
    return rows.map(function (row) { return row[field]; }).filter(function (value, index, list) { return value && list.indexOf(value) === index; }).sort();
  }

  function buildDashboard(data, rows) {
    var coverage = data.riSpCoverage || {};
    var forecast = data.forecast || {};
    var totalMonthly = number(data.totalMonthlySavings);
    var totalAnnual = number(data.totalAnnualSavings || totalMonthly * 12);
    var commitment = number(data.commitmentMonthlySavings);
    var quickWins = data.quickWins != null ? number(data.quickWins) : rows.filter(function (row) { return row.priority === 'Quick Win'; }).length;
    var high = data.highPriority != null ? number(data.highPriority) : rows.filter(function (row) { return row.priority === 'High'; }).length;

    var kpis = kpi('Potential waste reduction', money(totalMonthly) + '/mo', money(totalAnnual) + ' annualized · excludes commitments', 'co-kpi--hero', '<path d="M4 18V9m5 9V5m5 13v-6m5 6V3"/>') +
      kpi('Quick wins', String(quickWins), 'Low-effort opportunities to validate first', '', '<path d="m4 11 5 5L20 5"/>', rows.length ? 'quick' : '') +
      kpi('High priority', String(high), 'Largest or most urgent findings', '', '<path d="M12 3 2.8 20h18.4z"/><path d="M12 9v5m0 3h.01"/>', rows.length ? 'high' : '') +
      kpi('Commitment opportunity', commitment ? money(commitment) + '/mo' : 'None returned', commitment ? money(number(data.commitmentAnnualSavings || commitment * 12)) + ' annualized · separate from waste' : 'No purchase recommendation in this scope', '', '<path d="M4 19V9m5 10V5m5 14v-7m5 7V3"/>', commitment && rows.length ? 'commitments' : '');

    return '<div class="co-overview">' +
      '<section class="co-kpi-grid" aria-label="Assessment summary">' + kpis + '</section>' +
      '<div class="co-insight-grid">' +
        '<section class="co-panel"><div class="co-panel-head"><div><h2>Where the opportunity lives</h2><p>Potential monthly waste reduction, ranked by service</p></div><span class="co-panel-meta">Click to filter</span></div>' + serviceBars(rows) + '</section>' +
        '<section class="co-panel"><div class="co-panel-head"><div><h2>Priority mix</h2><p>Sequence work by impact and effort</p></div><span class="co-panel-meta">' + rows.length + ' total</span></div>' + priorityPanel(rows) + '</section>' +
      '</div>' +
      '<div class="co-secondary-grid">' +
        '<section class="co-panel"><div class="co-panel-head"><div><h2>Commitment posture</h2><p>Returned RI and Savings Plans context</p></div></div>' + coveragePanel(coverage) + '</section>' +
        '<section class="co-panel"><div class="co-panel-head"><div><h2>Spend outlook</h2><p>Cost Explorer context for this month</p></div></div>' + forecastPanel(forecast) + '</section>' +
      '</div>' +
      buildWorkbench(rows) + '</div>';
  }

  function buildWorkbench(rows) {
    if (!rows.length) {
      return '<section class="co-panel co-workbench" id="coWorkbench" aria-labelledby="coWorkbenchTitle">' +
        '<div class="co-workbench-head"><div><h2 id="coWorkbenchTitle">Recommendation workbench</h2><p>No actionable recommendation rows were returned for this scope.</p></div></div>' +
        '<div class="co-no-results">' + icon('<path d="m5 12 4 4L19 6"/><circle cx="12" cy="12" r="9"/>') + '<strong>No optimization opportunities to prioritize.</strong><p>The selected resources may already meet scanner thresholds. Coverage and spend context above remain valid; review the downloadable report for scan assumptions, permissions, and unavailable metrics.</p></div>' +
        '</section>';
    }
    return '<section class="co-panel co-workbench" id="coWorkbench" aria-labelledby="coWorkbenchTitle">' +
      '<div class="co-workbench-head"><div><h2 id="coWorkbenchTitle">Recommendation workbench</h2><p>Filter the evidence, inspect each change, and shortlist an action plan.</p></div><div class="co-export-actions"><button type="button" class="co-button" data-export="filtered">' + icon('<path d="M12 3v12m-5-5 5 5 5-5M5 21h14"/>') + 'Export filtered CSV</button></div></div>' +
      '<div class="co-quick-filters" role="group" aria-label="Recommendation views"><button type="button" class="active" data-quick="all">All opportunities</button><button type="button" data-quick="quick">Quick wins</button><button type="button" data-quick="high">High priority</button><button type="button" data-quick="commitments">Commitments</button></div>' +
      '<div class="co-filters">' +
        '<label class="co-search"><span class="sr-only">Search recommendations</span>' + icon('<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>') + '<input id="coSearch" type="search" placeholder="Search resources, reasons, tags…"></label>' +
        '<label><span class="sr-only">Service</span><select id="coService">' + optionList(unique(rows, 'label'), 'All services') + '</select></label>' +
        '<label><span class="sr-only">Region</span><select id="coRegion">' + optionList(unique(rows, 'region'), 'All regions') + '</select></label>' +
        '<label><span class="sr-only">Priority</span><select id="coPriority">' + optionList(['Quick Win', 'High', 'Medium', 'Low'], 'All priorities') + '</select></label>' +
        '<label><span class="sr-only">Confidence</span><select id="coConfidence">' + optionList(unique(rows, 'confidence'), 'All confidence') + '</select></label>' +
        '<label><span class="sr-only">Effort</span><select id="coEffort">' + optionList(unique(rows, 'effort'), 'All effort') + '</select></label>' +
        '<label><span class="sr-only">Risk</span><select id="coRisk">' + optionList(unique(rows, 'risk'), 'All risk') + '</select></label>' +
        '<label><span class="sr-only">Savings basis</span><select id="coBasis"><option value="">All savings bases</option><option value="on_demand">On-Demand estimate</option><option value="after_discounts">After existing discounts</option><option value="commitment_purchase">Commitment purchase</option></select></label>' +
        '<label><span class="sr-only">Sort recommendations</span><select id="coSort"><option value="score">Sort: Recommended order</option><option value="monthly">Sort: Monthly savings</option><option value="annual">Sort: Annual savings</option><option value="service">Sort: Service</option><option value="priority">Sort: Priority</option><option value="confidence">Sort: Confidence</option></select></label>' +
      '</div>' +
      '<div class="co-active-filters" id="coActiveFilters"></div>' +
      '<div class="co-results-summary"><span id="coResultCount"><strong>0</strong> recommendations</span><div class="co-summary-money"><span>Waste: <b id="coFilteredWaste">$0</b>/mo</span><span>Commitments: <b id="coFilteredCommitment">$0</b>/mo</span></div></div>' +
      '<div class="co-table-wrap"><table class="co-table"><thead><tr><th><input class="co-select" id="coSelectPage" type="checkbox" aria-label="Select all recommendations on this page"></th><th><button type="button" class="co-sort" data-sort="score">Resource</button></th><th><button type="button" class="co-sort" data-sort="service">Service</button></th><th>Region</th><th><button type="button" class="co-sort" data-sort="monthly">Monthly</button></th><th><button type="button" class="co-sort" data-sort="priority">Priority</button></th><th><button type="button" class="co-sort" data-sort="confidence">Confidence</button></th><th>Effort / risk</th><th><span class="sr-only">Details</span></th></tr></thead><tbody id="coTableBody"></tbody></table></div>' +
      '<div class="co-mobile-list" id="coMobileList"></div>' +
      '<div class="co-no-results" id="coNoResults" hidden>' + icon('<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5M8 11h6"/>') + '<strong>No recommendations match these filters.</strong><p>Clear a filter or broaden your search to bring opportunities back into view.</p></div>' +
      '<div class="co-pagination" id="coPagination"><span id="coPageStatus"></span><div class="co-page-actions"><label class="sr-only" for="coPageSize">Rows per page</label><select id="coPageSize"><option>25</option><option selected>50</option><option>100</option></select><button type="button" id="coPrev" aria-label="Previous page">←</button><button type="button" id="coNext" aria-label="Next page">→</button></div></div>' +
      '</section>';
  }

  function renderDashboard(data, root, options) {
    if (typeof root === 'string') root = document.getElementById(root);
    if (!root) return;
    clear();
    var rows = flatten(data.recommendations || {});
    runtime = {
      root: root, data: data || {}, rows: rows, options: options || {}, selected: new Set(), page: 1, pageSize: 50,
      filters: { search: '', service: '', region: '', priority: '', confidence: '', effort: '', risk: '', basis: '', sort: 'score' },
      filtered: [], pageRows: [], drawerOpener: null, drawerKey: ''
    };
    root.classList.add('co-dash');
    root.innerHTML = buildDashboard(data || {}, rows);
    if (!rows.length) return;
    bindDashboard();
    draw();
  }

  function filteredRows() {
    var f = runtime.filters;
    var query = f.search.toLowerCase();
    var list = runtime.rows.filter(function (row) {
      if (f.service && row.label !== f.service) return false;
      if (f.region && row.region !== f.region) return false;
      if (f.priority && row.priority !== f.priority) return false;
      if (f.confidence && row.confidence !== f.confidence) return false;
      if (f.effort && row.effort !== f.effort) return false;
      if (f.risk && row.risk !== f.risk) return false;
      if (f.basis && row.basis !== f.basis) return false;
      if (query && (row.id + ' ' + row.label + ' ' + row.region + ' ' + row.reason + ' ' + row.recommendation + ' ' + row.tagsText).toLowerCase().indexOf(query) < 0) return false;
      return true;
    });
    list.sort(function (a, b) {
      if (f.sort === 'monthly') return b.monthly - a.monthly || a.order - b.order;
      if (f.sort === 'annual') return b.annual - a.annual || a.order - b.order;
      if (f.sort === 'service') return a.label.localeCompare(b.label) || b.monthly - a.monthly;
      if (f.sort === 'priority') return PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || b.monthly - a.monthly;
      if (f.sort === 'confidence') return a.confidence.localeCompare(b.confidence) || b.monthly - a.monthly;
      return b.score - a.score || PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || b.monthly - a.monthly || a.order - b.order;
    });
    return list;
  }

  function draw() {
    if (!runtime) return;
    closeDrawer(false);
    runtime.filtered = filteredRows();
    var maxPage = Math.max(1, Math.ceil(runtime.filtered.length / runtime.pageSize));
    runtime.page = Math.min(runtime.page, maxPage);
    var start = (runtime.page - 1) * runtime.pageSize;
    runtime.pageRows = runtime.filtered.slice(start, start + runtime.pageSize);
    drawSummary(); drawActiveFilters(); drawRows(); drawPagination(); drawPlan();
  }

  function drawSummary() {
    var waste = 0; var commitment = 0;
    runtime.filtered.forEach(function (row) { if (row.basis === 'commitment_purchase') commitment += row.monthly; else waste += row.monthly; });
    $('#coResultCount', runtime.root).innerHTML = '<strong>' + runtime.filtered.length + '</strong> of ' + runtime.rows.length + ' recommendations';
    $('#coFilteredWaste', runtime.root).textContent = money(waste);
    $('#coFilteredCommitment', runtime.root).textContent = money(commitment);
  }

  function drawActiveFilters() {
    var container = $('#coActiveFilters', runtime.root); var labels = { search: 'Search', service: 'Service', region: 'Region', priority: 'Priority', confidence: 'Confidence', effort: 'Effort', risk: 'Risk', basis: 'Basis' };
    var active = Object.keys(labels).filter(function (key) { return runtime.filters[key]; });
    container.innerHTML = active.map(function (key) { return '<span class="co-filter-chip">' + labels[key] + ': ' + escapeHtml(runtime.filters[key]) + '<button type="button" data-clear-filter="' + key + '" aria-label="Clear ' + labels[key] + ' filter">×</button></span>'; }).join('') + (active.length ? '<button type="button" class="co-filter-chip clear" data-clear-filter="all">Clear all</button>' : '');
  }

  function rowMarkup(row) {
    var effortRisk = escapeHtml(row.effort) + ' / ' + escapeHtml(row.risk);
    return '<tr><td><input class="co-select" type="checkbox" data-select="' + row.key + '" aria-label="Add ' + escapeHtml(row.id) + ' to action plan"' + (runtime.selected.has(row.key) ? ' checked' : '') + '></td>' +
      '<td><div class="co-resource"><strong title="' + escapeHtml(row.id) + '">' + escapeHtml(row.id) + '</strong><small>' + escapeHtml(shorten(row.reason, 72)) + '</small></div></td>' +
      '<td><span class="co-service" style="--service-color:' + (SERVICE_COLORS[row.service] || '#0b6bcb') + '"><i class="co-service-dot"></i>' + escapeHtml(row.label) + '</span></td>' +
      '<td>' + escapeHtml(row.region) + '</td><td class="co-money ' + (row.basis === 'commitment_purchase' ? 'commitment' : '') + '">' + (row.monthly > 0 ? moneyPrecise(row.monthly) : '—') + '</td>' +
      '<td>' + pill(row.priority) + '</td><td>' + pill(row.confidence) + '</td><td>' + effortRisk + '</td>' +
      '<td><button type="button" class="co-detail-button" data-open="' + row.key + '" aria-label="View details for ' + escapeHtml(row.id) + '">' + icon('<path d="m9 5 7 7-7 7"/>') + '</button></td></tr>';
  }

  function mobileMarkup(row) {
    return '<article class="co-mobile-card"><input class="co-select" type="checkbox" data-select="' + row.key + '" aria-label="Add ' + escapeHtml(row.id) + ' to action plan"' + (runtime.selected.has(row.key) ? ' checked' : '') + '><div class="co-mobile-main"><strong>' + escapeHtml(row.id) + '</strong><small>' + escapeHtml(row.label) + ' · ' + escapeHtml(row.region) + '</small><div class="co-mobile-meta">' + pill(row.priority) + pill(row.confidence) + '<span class="co-mobile-money">' + (row.monthly > 0 ? moneyPrecise(row.monthly) + '/mo' : 'Informational') + '</span></div></div><button type="button" class="co-detail-button" data-open="' + row.key + '" aria-label="View details for ' + escapeHtml(row.id) + '">' + icon('<path d="m9 5 7 7-7 7"/>') + '</button></article>';
  }

  function drawRows() {
    var body = $('#coTableBody', runtime.root); var mobile = $('#coMobileList', runtime.root); var empty = $('#coNoResults', runtime.root);
    body.innerHTML = runtime.pageRows.map(rowMarkup).join('');
    mobile.innerHTML = runtime.pageRows.map(mobileMarkup).join('');
    empty.hidden = runtime.filtered.length !== 0;
    $('.co-table-wrap', runtime.root).hidden = runtime.filtered.length === 0;
    mobile.hidden = runtime.filtered.length === 0;
    var selectPage = $('#coSelectPage', runtime.root);
    selectPage.checked = runtime.pageRows.length > 0 && runtime.pageRows.every(function (row) { return runtime.selected.has(row.key); });
    selectPage.indeterminate = !selectPage.checked && runtime.pageRows.some(function (row) { return runtime.selected.has(row.key); });
    $$('.co-sort', runtime.root).forEach(function (button) { button.classList.toggle('active', button.dataset.sort === runtime.filters.sort); });
  }

  function drawPagination() {
    var maxPage = Math.max(1, Math.ceil(runtime.filtered.length / runtime.pageSize));
    $('#coPageStatus', runtime.root).textContent = runtime.filtered.length ? ('Page ' + runtime.page + ' of ' + maxPage) : 'No pages';
    $('#coPrev', runtime.root).disabled = runtime.page <= 1;
    $('#coNext', runtime.root).disabled = runtime.page >= maxPage;
    $('#coPagination', runtime.root).hidden = runtime.filtered.length === 0;
  }

  function drawPlan() {
    var existing = document.getElementById('coPlanTray');
    if (existing) existing.remove();
    if (!runtime || !runtime.selected.size) return;
    var selectedRows = runtime.rows.filter(function (row) { return runtime.selected.has(row.key); });
    var waste = 0; var commitment = 0;
    selectedRows.forEach(function (row) { if (row.basis === 'commitment_purchase') commitment += row.monthly; else waste += row.monthly; });
    var tray = document.createElement('div');
    tray.id = 'coPlanTray'; tray.className = 'co-plan-tray';
    tray.innerHTML = '<div class="co-plan-copy"><span class="co-plan-count">' + selectedRows.length + '</span><div><strong>Action plan selection</strong><span>' + money(waste) + '/mo waste · ' + money(commitment) + '/mo commitments</span></div></div><div class="co-plan-actions"><button type="button" data-plan="clear">Clear</button><button type="button" class="primary" data-plan="export">Export plan CSV</button></div>';
    document.body.appendChild(tray);
    tray.addEventListener('click', function (event) {
      var action = event.target.closest('[data-plan]'); if (!action) return;
      if (action.dataset.plan === 'clear') { runtime.selected.clear(); drawRows(); drawPlan(); }
      else exportCsv(selectedRows, 'action-plan');
    });
  }

  function shorten(value, max) { var string = text(value); return string.length > max ? string.slice(0, max - 1) + '…' : string; }
  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }

  function applyQuickFilter(value) {
    runtime.filters.priority = '';
    runtime.filters.basis = '';
    if (value === 'quick') runtime.filters.priority = 'Quick Win';
    else if (value === 'high') runtime.filters.priority = 'High';
    else if (value === 'commitments') runtime.filters.basis = 'commitment_purchase';
    if (value === 'all') {
      runtime.filters.search = ''; runtime.filters.service = ''; runtime.filters.region = ''; runtime.filters.confidence = ''; runtime.filters.effort = ''; runtime.filters.risk = '';
      $('#coSearch', runtime.root).value = ''; $('#coService', runtime.root).value = ''; $('#coRegion', runtime.root).value = ''; $('#coConfidence', runtime.root).value = '';
      $('#coEffort', runtime.root).value = ''; $('#coRisk', runtime.root).value = ''; $('#coBasis', runtime.root).value = '';
    }
    $('#coPriority', runtime.root).value = runtime.filters.priority;
    runtime.page = 1;
    $$('.co-quick-filters button', runtime.root).forEach(function (button) { button.classList.toggle('active', button.dataset.quick === value); });
    draw();
    var count = $('#coResultCount', runtime.root); if (count) count.focus && count.focus();
    $('#coWorkbench', runtime.root).scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function bindDashboard() {
    var root = runtime.root;
    $('#coSearch', root).addEventListener('input', function (event) { runtime.filters.search = event.target.value; runtime.page = 1; draw(); });
    [['coService', 'service'], ['coRegion', 'region'], ['coPriority', 'priority'], ['coConfidence', 'confidence'], ['coEffort', 'effort'], ['coRisk', 'risk'], ['coBasis', 'basis'], ['coSort', 'sort']].forEach(function (binding) {
      $('#' + binding[0], root).addEventListener('change', function (event) { runtime.filters[binding[1]] = event.target.value; runtime.page = 1; draw(); });
    });
    root.addEventListener('click', function (event) {
      var quick = event.target.closest('[data-quick]'); if (quick) { applyQuickFilter(quick.dataset.quick); return; }
      var serviceBar = event.target.closest('[data-service-bar]'); if (serviceBar) { runtime.filters.service = SERVICE_LABELS[serviceBar.dataset.serviceBar] || serviceBar.dataset.serviceBar; $('#coService', root).value = runtime.filters.service; runtime.page = 1; draw(); $('#coWorkbench', root).scrollIntoView({ behavior: 'smooth' }); return; }
      var priorityBar = event.target.closest('[data-priority-bar]'); if (priorityBar) { runtime.filters.priority = priorityBar.dataset.priorityBar; $('#coPriority', root).value = runtime.filters.priority; runtime.page = 1; draw(); $('#coWorkbench', root).scrollIntoView({ behavior: 'smooth' }); return; }
      var clearFilter = event.target.closest('[data-clear-filter]'); if (clearFilter) { clearFilterValue(clearFilter.dataset.clearFilter); return; }
      var sort = event.target.closest('[data-sort]'); if (sort) { runtime.filters.sort = sort.dataset.sort; $('#coSort', root).value = runtime.filters.sort; draw(); return; }
      var open = event.target.closest('[data-open]'); if (open) { openDrawer(open.dataset.open, open); return; }
      var exportButton = event.target.closest('[data-export]'); if (exportButton) { exportCsv(runtime.filtered, 'filtered-recommendations'); return; }
      if (event.target.id === 'coPrev') { runtime.page = Math.max(1, runtime.page - 1); draw(); }
      if (event.target.id === 'coNext') { runtime.page += 1; draw(); }
    });
    root.addEventListener('change', function (event) {
      if (event.target.matches('[data-select]')) {
        if (event.target.checked) runtime.selected.add(event.target.dataset.select); else runtime.selected.delete(event.target.dataset.select);
        $$('[data-select="' + event.target.dataset.select + '"]', root).forEach(function (checkbox) { checkbox.checked = event.target.checked; });
        drawPlan(); return;
      }
      if (event.target.id === 'coSelectPage') {
        runtime.pageRows.forEach(function (row) { if (event.target.checked) runtime.selected.add(row.key); else runtime.selected.delete(row.key); });
        drawRows(); drawPlan(); return;
      }
      if (event.target.id === 'coPageSize') { runtime.pageSize = number(event.target.value) || 50; runtime.page = 1; draw(); }
    });
  }

  function clearFilterValue(key) {
    if (key === 'all') {
      Object.keys(runtime.filters).forEach(function (name) { if (name !== 'sort') runtime.filters[name] = ''; });
      $('#coSearch', runtime.root).value = '';
      ['coService', 'coRegion', 'coPriority', 'coConfidence', 'coEffort', 'coRisk', 'coBasis'].forEach(function (id) { $('#' + id, runtime.root).value = ''; });
    } else {
      runtime.filters[key] = '';
      var idMap = { search: 'coSearch', service: 'coService', region: 'coRegion', priority: 'coPriority', confidence: 'coConfidence', effort: 'coEffort', risk: 'coRisk', basis: 'coBasis' };
      if (idMap[key]) $('#' + idMap[key], runtime.root).value = '';
    }
    runtime.page = 1; draw();
  }

  function first(raw, keys) {
    for (var index = 0; index < keys.length; index += 1) if (raw[keys[index]] != null && raw[keys[index]] !== '') return text(raw[keys[index]]);
    return '';
  }
  function comparison(row) {
    var current = first(row.raw, ['current_type', 'current_class', 'current_memory', 'current_size', 'current_configuration', 'current_cost', 'current_resource_summary']);
    var target = first(row.raw, ['recommended_type', 'recommended_class', 'recommended_memory', 'recommended_size', 'recommended_configuration', 'recommended_resource_summary']);
    if (!current && !target) return '';
    return '<div class="co-compare"><div><span>Current</span><strong>' + escapeHtml(current || 'Not available') + '</strong></div>' + icon('<path d="m8 5 7 7-7 7"/>') + '<div><span>Recommended</span><strong>' + escapeHtml(target || 'See action below') + '</strong></div></div>';
  }
  function evidence(row) {
    var averageDuration = first(row.raw, ['avg_duration', 'avg_duration_ms']);
    var fields = [
      ['Source', first(row.raw, ['source', 'pricing_source'])], ['Performance risk', first(row.raw, ['performance_risk'])],
      ['Average CPU', first(row.raw, ['cpu_avg', 'avg_cpu', 'average_cpu'])], ['Peak / p99 CPU', first(row.raw, ['cpu_max', 'max_cpu', 'p99_cpu'])],
      ['Data points', first(row.raw, ['data_points', 'metric_count'])], ['Age', first(row.raw, ['age_days']) ? first(row.raw, ['age_days']) + ' days' : ''],
      ['Average duration', averageDuration ? averageDuration + ' ms' : ''],
      ['Current monthly cost', first(row.raw, ['current_cost', 'current_monthly_cost', 'monthly_cost'])], ['Savings percentage', first(row.raw, ['savings_percentage'])]
    ].filter(function (field) { return field[1]; });
    if (!fields.length) fields = [['Evidence', 'See the rationale and recommendation returned by the scanner.']];
    return '<div class="co-evidence">' + fields.slice(0, 8).map(function (field) { return '<div><span>' + field[0] + '</span><strong>' + escapeHtml(field[1]) + '</strong></div>'; }).join('') + '</div>';
  }
  function tags(row) {
    var source = row.raw.tags;
    if (!source) return '';
    var values = [];
    if (Array.isArray(source)) source.forEach(function (tag) { values.push(text(tag.Key || tag.key) + ': ' + text(tag.Value || tag.value)); });
    else if (typeof source === 'object') Object.keys(source).forEach(function (key) { values.push(key + ': ' + text(source[key])); });
    return values.length ? '<div class="co-tags">' + values.map(function (value) { return '<span class="co-tag">' + escapeHtml(value) + '</span>'; }).join('') + '</div>' : '';
  }
  function basisNote(basis) {
    if (basis === 'after_discounts') return 'Savings reflect estimated impact after existing discounts. Confirm coverage interactions before changing capacity.';
    if (basis === 'commitment_purchase') return 'This is a rate-optimization estimate and is intentionally separate from waste reduction. A commitment can reduce flexibility.';
    return 'Savings use an On-Demand estimate. Existing Reserved Instances or Savings Plans can change the realized amount.';
  }
  function consoleUrl(row) {
    var region = encodeURIComponent(row.region === 'Global' ? 'us-east-1' : row.region);
    var id = encodeURIComponent(row.id);
    if (row.service === 'ec2') return 'https://' + region + '.console.aws.amazon.com/ec2/home?region=' + region + '#InstanceDetails:instanceId=' + id;
    if (row.service === 'ebs') return 'https://' + region + '.console.aws.amazon.com/ec2/home?region=' + region + '#VolumeDetails:volumeId=' + id;
    if (row.service === 'ebs_snapshot') return 'https://' + region + '.console.aws.amazon.com/ec2/home?region=' + region + '#SnapshotDetails:snapshotId=' + id;
    if (row.service === 'rds') return 'https://' + region + '.console.aws.amazon.com/rds/home?region=' + region + '#database:id=' + id;
    if (row.service === 'lambda') return 'https://' + region + '.console.aws.amazon.com/lambda/home?region=' + region + '#/functions/' + id;
    if (row.service === 'dynamodb') return 'https://' + region + '.console.aws.amazon.com/dynamodbv2/home?region=' + region + '#table?name=' + id;
    if (row.service === 's3') return 'https://s3.console.aws.amazon.com/s3/buckets/' + id;
    return '';
  }

  function openDrawer(key, opener) {
    var row = runtime.rows.find(function (item) { return item.key === key; }); if (!row) return;
    closeDrawer(false); runtime.drawerOpener = opener; runtime.drawerKey = key;
    var backdrop = document.createElement('div'); backdrop.className = 'co-drawer-backdrop'; backdrop.id = 'coDrawerBackdrop';
    var drawer = document.createElement('aside'); drawer.className = 'co-drawer'; drawer.id = 'coDrawer'; drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true'); drawer.setAttribute('aria-labelledby', 'coDrawerTitle');
    var remediation = row.remediation ? '<div class="co-drawer-section"><h3>Implementation guidance</h3><div class="co-code-wrap"><pre class="co-code" id="coRemediation">' + escapeHtml(row.remediation) + '</pre><button type="button" class="co-copy" data-copy>Copy</button></div></div>' : '';
    var tagMarkup = tags(row); var comparisonMarkup = comparison(row); var url = consoleUrl(row);
    drawer.innerHTML = '<div class="co-drawer-head"><div><span class="co-drawer-service">' + escapeHtml(row.label) + ' · ' + escapeHtml(row.region) + '</span><h2 id="coDrawerTitle">' + escapeHtml(row.id) + '</h2></div><button type="button" class="co-drawer-close" data-close aria-label="Close recommendation details">×</button></div>' +
      '<div class="co-drawer-body"><div class="co-impact-card"><div><span>Potential monthly impact</span><strong>' + (row.monthly > 0 ? moneyPrecise(row.monthly) : 'Informational') + '</strong></div><div><span>Potential annual impact</span><strong>' + (row.annual > 0 ? moneyPrecise(row.annual) : '—') + '</strong></div></div>' +
      '<div class="co-drawer-chips">' + pill(row.priority) + pill(row.confidence) + pill(row.effort + ' effort') + pill(row.risk + ' risk') + pill(BASIS_LABELS[row.basis] || row.basis, 'basis') + '</div>' +
      (comparisonMarkup ? '<div class="co-drawer-section"><h3>Current → recommended</h3>' + comparisonMarkup + '</div>' : '') +
      '<div class="co-drawer-section"><h3>Why this was flagged</h3><p>' + escapeHtml(row.reason) + '</p></div>' +
      '<div class="co-drawer-section"><h3>Recommended action</h3><p>' + escapeHtml(row.recommendation) + '</p></div>' +
      '<div class="co-drawer-section"><h3>Evidence returned</h3>' + evidence(row) + '</div>' +
      (tagMarkup ? '<div class="co-drawer-section"><h3>Resource context</h3>' + tagMarkup + '</div>' : '') + remediation +
      '<div class="co-drawer-section"><div class="co-basis-note">' + icon('<path d="M12 3 5 6v6c0 4.5 2.8 7.5 7 9 4.2-1.5 7-4.5 7-9V6z"/><path d="M12 8v4m0 3h.01"/>') + '<span>' + escapeHtml(basisNote(row.basis)) + ' Validate in a non-production environment before applying any change.</span></div></div></div>' +
      '<div class="co-drawer-foot">' + (url ? '<a class="co-console-link" href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">Open in AWS Console ↗</a>' : '<span></span>') + '<button type="button" class="co-button primary" data-drawer-select="' + row.key + '">' + (runtime.selected.has(row.key) ? 'Remove from plan' : 'Add to action plan') + '</button></div>';
    document.body.appendChild(backdrop); document.body.appendChild(drawer); document.body.classList.add('co-drawer-open');
    backdrop.addEventListener('click', function () { closeDrawer(true); });
    drawer.addEventListener('click', function (event) {
      if (event.target.closest('[data-close]')) closeDrawer(true);
      var copy = event.target.closest('[data-copy]'); if (copy) copyText(row.remediation, copy);
      var select = event.target.closest('[data-drawer-select]'); if (select) { if (runtime.selected.has(row.key)) runtime.selected.delete(row.key); else runtime.selected.add(row.key); select.textContent = runtime.selected.has(row.key) ? 'Remove from plan' : 'Add to action plan'; drawRows(); drawPlan(); }
    });
    document.addEventListener('keydown', drawerKeydown);
    $('.co-drawer-close', drawer).focus();
  }

  function drawerKeydown(event) {
    var drawer = document.getElementById('coDrawer'); if (!drawer) return;
    if (event.key === 'Escape') { event.preventDefault(); closeDrawer(true); return; }
    if (event.key !== 'Tab') return;
    var focusable = $$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled])', drawer);
    if (!focusable.length) return;
    var first = focusable[0]; var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function closeDrawer(restoreFocus) {
    var drawer = document.getElementById('coDrawer'); var backdrop = document.getElementById('coDrawerBackdrop');
    if (drawer) drawer.remove(); if (backdrop) backdrop.remove();
    document.body.classList.remove('co-drawer-open'); document.removeEventListener('keydown', drawerKeydown);
    if (restoreFocus && runtime) {
      var focusTarget = runtime.drawerOpener && document.contains(runtime.drawerOpener) ? runtime.drawerOpener :
        (runtime.drawerKey && runtime.root ? $('[data-open="' + runtime.drawerKey + '"]', runtime.root) : null);
      if (focusTarget) focusTarget.focus();
    }
    if (runtime) { runtime.drawerOpener = null; runtime.drawerKey = ''; }
  }

  function copyText(value, button) {
    var finish = function () { button.textContent = 'Copied'; setTimeout(function () { button.textContent = 'Copy'; }, 1600); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(value).then(finish).catch(function () { fallbackCopy(value); finish(); });
    else { fallbackCopy(value); finish(); }
  }
  function fallbackCopy(value) {
    var area = document.createElement('textarea'); area.value = value; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.appendChild(area); area.select();
    try { document.execCommand('copy'); } catch (ignore) { /* Browser may block copying. */ } area.remove();
  }

  function csvCell(value) {
    var string = text(value).replace(/\r?\n/g, ' ');
    if (/^[=+\-@]/.test(string)) string = "'" + string;
    return '"' + string.replace(/"/g, '""') + '"';
  }
  function exportCsv(rows, suffix) {
    if (!rows || !rows.length) return;
    var columns = ['Service', 'Resource', 'Region', 'Reason', 'Recommendation', 'Monthly savings', 'Annual savings', 'Priority', 'Confidence', 'Effort', 'Risk', 'Savings basis', 'Remediation'];
    var csv = '\ufeff' + columns.map(csvCell).join(',') + '\r\n' + rows.map(function (row) {
      return [row.label, row.id, row.region, row.reason, row.recommendation, row.monthly, row.annual, row.priority, row.confidence, row.effort, row.risk, row.basis, row.remediation].map(csvCell).join(',');
    }).join('\r\n');
    var url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    var link = document.createElement('a');
    var client = text(runtime.options.clientName || 'costoptimizer360').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'costoptimizer360';
    link.href = url; link.download = client + '-' + suffix + '.csv'; document.body.appendChild(link); link.click(); link.remove(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function hasSelection() { return Boolean(runtime && runtime.selected.size); }
  function clear() {
    closeDrawer(false);
    var tray = document.getElementById('coPlanTray'); if (tray) tray.remove();
    if (runtime && runtime.root) runtime.root.innerHTML = '';
    runtime = null;
  }

  window.CostOpt360 = { renderDashboard: renderDashboard, hasSelection: hasSelection, clear: clear };
})();
