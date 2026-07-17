"""
CostOptimizer360 - shared interactive dashboard assets (CSS + JS).

A single source of truth for the results dashboard that renders:
  * KPI cards (savings, quick wins, coverage, forecast)
  * charts (savings by service / region / priority) via Chart.js
  * a filterable, sortable, searchable recommendations table with drill-down
    remediation snippets

Used by:
  * generate_html_report()  -> a self-contained downloadable .html dashboard
  * the web frontends (cloud + local): the static files frontend/dashboard.css,
    frontend/dashboard.js and local/web/dashboard.css, local/web/dashboard.js are
    GENERATED from DASHBOARD_CSS / DASHBOARD_JS below (single source of truth) and
    loaded via <link>/<script>. Regenerate them after editing this module with:
        python -c "import sys;sys.path.insert(0,'lambda');import dashboard_assets as d;\
[open(f'{t}/dashboard.css','w').write(d.DASHBOARD_CSS) or \
open(f'{t}/dashboard.js','w').write(d.DASHBOARD_JS) for t in ('frontend','local/web')]"
    The frontends then call CostOpt360.renderDashboard(data, rootEl).

The renderer consumes the object produced by scan_result_summary() plus a
clientName/generatedAt, so the same data powers the live UI and the export.
"""

DASHBOARD_CSS = r"""
.co-dash { --brand:#23649c; --brand-dark:#1a4d78; --ink:#20303f; --muted:#64748b;
  --good:#0f7b3f; --warn:#b45309; --bad:#b91c1c; --card:#ffffff; --line:#e2e8f0;
  color:var(--ink); font-family:'Open Sans','Amazon Ember',Arial,sans-serif; }
.co-dash *{box-sizing:border-box;}
.co-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:22px;}
.co-kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;
  box-shadow:0 1px 3px rgba(15,23,42,.06);}
.co-kpi .v{font-size:1.7rem;font-weight:700;line-height:1.1;}
.co-kpi .l{font-size:.8rem;color:var(--muted);margin-top:6px;text-transform:uppercase;letter-spacing:.04em;}
.co-kpi.good .v{color:var(--good);} .co-kpi.brand .v{color:var(--brand);}
.co-kpi.warn .v{color:var(--warn);} .co-kpi.bad .v{color:var(--bad);}
.co-charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-bottom:24px;}
.co-chartcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  box-shadow:0 1px 3px rgba(15,23,42,.06);}
.co-chartcard h4{margin:0 0 12px;font-size:.95rem;color:var(--brand-dark);}
.co-chartcard .cwrap{position:relative;height:240px;}
.co-controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px;}
.co-controls input,.co-controls select{padding:9px 12px;border:1px solid var(--line);border-radius:8px;
  font-size:.9rem;background:#fff;color:var(--ink);}
.co-controls input[type=search]{flex:1;min-width:200px;}
.co-tablewrap{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;
  box-shadow:0 1px 3px rgba(15,23,42,.06);}
.co-table{width:100%;border-collapse:collapse;font-size:.86rem;}
.co-table th{background:#f1f5f9;text-align:left;padding:11px 12px;font-weight:700;color:var(--brand-dark);
  cursor:pointer;white-space:nowrap;border-bottom:1px solid var(--line);user-select:none;}
.co-table th:hover{background:#e2e8f0;}
.co-table td{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
.co-table tr.co-row:hover{background:#f8fafc;cursor:pointer;}
.co-table tr.co-detail td{background:#f8fafc;color:var(--muted);font-size:.82rem;}
.co-table tr.co-detail pre{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:8px;overflow:auto;
  font-size:.8rem;white-space:pre-wrap;word-break:break-word;margin:8px 0 0;}
.co-money{font-weight:700;color:var(--good);white-space:nowrap;}
.co-pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.72rem;font-weight:700;}
.co-pill.High,.co-pill.h{background:#fee2e2;color:#991b1b;}
.co-pill.Medium,.co-pill.m{background:#fef3c7;color:#92400e;}
.co-pill.Low,.co-pill.l{background:#dcfce7;color:#166534;}
.co-pill.qw{background:#dbeafe;color:#1e40af;}
.co-empty{padding:40px;text-align:center;color:var(--muted);}
.co-sec-title{font-size:1.05rem;color:var(--brand-dark);font-weight:700;margin:4px 0 12px;}
@media print{.co-controls{display:none;} .co-table tr.co-detail{display:table-row!important;}}
"""

# Vanilla-JS renderer exposed as window.CostOpt360.renderDashboard(data, rootEl)
DASHBOARD_JS = r"""
(function(){
  var SERVICE_LABELS = {
    ec2:'EC2 Rightsizing', stopped_ec2:'Stopped EC2 (EBS waste)', ebs:'EBS Volumes',
    ebs_snapshot:'EBS Snapshots', rds:'RDS Databases', lambda:'Lambda Functions',
    eip:'Elastic IPs / Public IPv4', natgateway:'NAT Gateways', dynamodb:'DynamoDB',
    elb:'Load Balancers', s3:'S3 Buckets', savings_plan:'Savings Plans (rate)'
  };
  var charts = [];
  function fmt(n){ return '$'+(Number(n)||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}); }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function resId(r){
    return r.instance_id||r.volume_id||r.db_id||r.function_name||r.snapshot_id||
           r.load_balancer_name||r.nat_gateway_id||r.table_name||r.ip_address||
           r.bucket_name||(r.type||'resource');
  }
  function flatten(recs){
    var rows=[];
    Object.keys(recs||{}).forEach(function(svc){
      var list=recs[svc]; if(!Array.isArray(list))return;
      list.forEach(function(r){
        rows.push({
          service:svc, label:SERVICE_LABELS[svc]||svc, id:resId(r),
          region:r.region||'-', monthly:Number(r.monthly_savings||0),
          annual:Number(r.annual_savings|| (r.monthly_savings||0)*12),
          confidence:r.confidence||'Medium', priority:r.priority||'-',
          effort:r.effort||'-', risk:r.risk||'-', basis:r.savings_basis||'on_demand',
          reason:r.reason||r.issue||r.issues||'', rec:r.recommendation||'',
          remediation:r.remediation||''
        });
      });
    });
    return rows;
  }
  function kpi(v,l,cls){ return '<div class="co-kpi '+(cls||'')+'"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>'; }

  function renderDashboard(data, root){
    if(typeof root==='string') root=document.getElementById(root);
    if(!root) return;
    charts.forEach(function(c){ try{c.destroy();}catch(e){} }); charts=[];
    var rows = flatten(data.recommendations);
    var cov = data.riSpCoverage||{};
    var fc = data.forecast||{};

    // KPI header
    var kpis='';
    kpis+=kpi(fmt(data.totalMonthlySavings)+' /mo','Waste Elimination (monthly)','good');
    kpis+=kpi(fmt(data.totalAnnualSavings),'Annualized Savings','brand');
    if(data.commitmentMonthlySavings>0) kpis+=kpi(fmt(data.commitmentMonthlySavings)+' /mo','Savings Plans Opportunity','brand');
    kpis+=kpi(rows.length,'Recommendations','');
    kpis+=kpi(data.quickWins||0,'Quick Wins','good');
    kpis+=kpi(data.highPriority||0,'High Priority','bad');
    if(cov.ri_coverage_pct!=null) kpis+=kpi((cov.ri_coverage_pct||0)+'%','RI Coverage',(cov.ri_coverage_pct>=50?'good':'warn'));
    if(fc.forecast_month!=null) kpis+=kpi(fmt(fc.forecast_month),'Forecast (this month)','');

    // Aggregations for charts
    var byService={}, byRegion={}, byPriority={High:0,Medium:0,Low:0,'Quick Win':0};
    rows.forEach(function(r){
      // Exclude Savings Plans (rate optimization) from the waste-savings charts so
      // they reconcile with the "Waste Elimination" KPI; commitments stay in the table.
      if(r.monthly>0 && r.service!=='savings_plan'){ byService[r.label]=(byService[r.label]||0)+r.monthly; byRegion[r.region]=(byRegion[r.region]||0)+r.monthly; }
      if(byPriority[r.priority]!=null) byPriority[r.priority]+=1;
    });

    var html=''+
      '<div class="co-kpis">'+kpis+'</div>'+
      '<div class="co-charts">'+
        '<div class="co-chartcard"><h4>Monthly Savings by Service</h4><div class="cwrap"><canvas id="coChartSvc"></canvas></div></div>'+
        '<div class="co-chartcard"><h4>Monthly Savings by Region</h4><div class="cwrap"><canvas id="coChartReg"></canvas></div></div>'+
        '<div class="co-chartcard"><h4>Recommendations by Priority</h4><div class="cwrap"><canvas id="coChartPri"></canvas></div></div>'+
      '</div>'+
      '<div class="co-sec-title">Recommendations</div>'+
      '<div class="co-controls">'+
        '<input type="search" id="coSearch" placeholder="Search resource, reason, region...">'+
        '<select id="coSvc"><option value="">All services</option>'+
          Object.keys(SERVICE_LABELS).map(function(s){return '<option value="'+s+'">'+SERVICE_LABELS[s]+'</option>';}).join('')+
        '</select>'+
        '<select id="coPri"><option value="">All priorities</option><option>Quick Win</option><option>High</option><option>Medium</option><option>Low</option></select>'+
        '<select id="coConf"><option value="">All confidence</option><option>High</option><option>Medium</option><option>Low</option></select>'+
        '<select id="coSort"><option value="monthly">Sort: Monthly savings</option><option value="annual">Sort: Annual savings</option><option value="service">Sort: Service</option><option value="priority">Sort: Priority</option></select>'+
      '</div>'+
      '<div class="co-tablewrap"><table class="co-table"><thead><tr>'+
        '<th data-k="label">Service</th><th data-k="id">Resource</th><th data-k="region">Region</th>'+
        '<th data-k="monthly">Monthly</th><th data-k="annual">Annual</th><th data-k="priority">Priority</th>'+
        '<th data-k="confidence">Confidence</th><th data-k="effort">Effort</th><th data-k="risk">Risk</th>'+
      '</tr></thead><tbody id="coBody"></tbody></table></div>';
    root.innerHTML=html;

    var priRank={'Quick Win':0,'High':1,'Medium':2,'Low':3,'-':4};
    var state={search:'',svc:'',pri:'',conf:'',sort:'monthly'};
    function draw(){
      var body=root.querySelector('#coBody');
      var f=rows.filter(function(r){
        if(state.svc && r.service!==state.svc) return false;
        if(state.pri && r.priority!==state.pri) return false;
        if(state.conf && r.confidence!==state.conf) return false;
        if(state.search){ var q=state.search.toLowerCase();
          if((r.id+' '+r.reason+' '+r.rec+' '+r.region+' '+r.label).toLowerCase().indexOf(q)<0) return false; }
        return true;
      });
      f.sort(function(a,b){
        if(state.sort==='service') return a.label.localeCompare(b.label);
        if(state.sort==='priority') return (priRank[a.priority]-priRank[b.priority])|| (b.monthly-a.monthly);
        if(state.sort==='annual') return b.annual-a.annual;
        return b.monthly-a.monthly;
      });
      if(!f.length){ body.innerHTML='<tr><td colspan="9" class="co-empty">No recommendations match your filters.</td></tr>'; return; }
      body.innerHTML=f.map(function(r,i){
        var pill=r.priority==='Quick Win'?'qw':(r.priority==='High'?'High':(r.priority==='Low'?'Low':'Medium'));
        var detail='<tr class="co-detail" id="cod'+i+'" style="display:none"><td colspan="9">'+
          '<b>Why:</b> '+esc(r.reason||'-')+'<br><b>Action:</b> '+esc(r.rec||'-')+
          ' &nbsp; <b>Savings basis:</b> '+esc(r.basis)+
          (r.remediation?('<pre>'+esc(r.remediation)+'</pre>'):'')+'</td></tr>';
        return '<tr class="co-row" data-i="'+i+'">'+
          '<td>'+esc(r.label)+'</td><td>'+esc(r.id)+'</td><td>'+esc(r.region)+'</td>'+
          '<td class="co-money">'+ (r.monthly>0?fmt(r.monthly):'-') +'</td>'+
          '<td class="co-money">'+ (r.annual>0?fmt(r.annual):'-') +'</td>'+
          '<td><span class="co-pill '+pill+'">'+esc(r.priority)+'</span></td>'+
          '<td><span class="co-pill '+r.confidence+'">'+esc(r.confidence)+'</span></td>'+
          '<td>'+esc(r.effort)+'</td><td>'+esc(r.risk)+'</td></tr>'+detail;
      }).join('');
      Array.prototype.forEach.call(body.querySelectorAll('tr.co-row'),function(tr){
        tr.addEventListener('click',function(){ var d=body.querySelector('#cod'+tr.getAttribute('data-i'));
          if(d) d.style.display = d.style.display==='none'?'table-row':'none'; });
      });
    }
    root.querySelector('#coSearch').addEventListener('input',function(e){state.search=e.target.value;draw();});
    root.querySelector('#coSvc').addEventListener('change',function(e){state.svc=e.target.value;draw();});
    root.querySelector('#coPri').addEventListener('change',function(e){state.pri=e.target.value;draw();});
    root.querySelector('#coConf').addEventListener('change',function(e){state.conf=e.target.value;draw();});
    root.querySelector('#coSort').addEventListener('change',function(e){state.sort=e.target.value;draw();});
    Array.prototype.forEach.call(root.querySelectorAll('th[data-k]'),function(th){
      th.addEventListener('click',function(){ var k=th.getAttribute('data-k');
        state.sort=(k==='monthly'||k==='annual'||k==='service'||k==='priority')?k:state.sort; draw(); });
    });
    draw();

    // Charts (progressive enhancement - only if Chart.js loaded)
    if(window.Chart){
      var palette=['#23649c','#0066CC','#3399FF','#66B2FF','#99CCFF','#006699','#008080','#0f7b3f','#b45309','#7c3aed'];
      var svcL=Object.keys(byService), svcV=svcL.map(function(k){return Math.round(byService[k]*100)/100;});
      if(svcL.length) charts.push(new Chart(root.querySelector('#coChartSvc'),{type:'doughnut',
        data:{labels:svcL,datasets:[{data:svcV,backgroundColor:palette}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{boxWidth:12,font:{size:10}}}}}}));
      var regL=Object.keys(byRegion), regV=regL.map(function(k){return Math.round(byRegion[k]*100)/100;});
      if(regL.length) charts.push(new Chart(root.querySelector('#coChartReg'),{type:'bar',
        data:{labels:regL,datasets:[{label:'Monthly $',data:regV,backgroundColor:'#23649c'}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}}));
      var priL=Object.keys(byPriority), priV=priL.map(function(k){return byPriority[k];});
      charts.push(new Chart(root.querySelector('#coChartPri'),{type:'bar',
        data:{labels:priL,datasets:[{label:'Count',data:priV,backgroundColor:['#1e40af','#b91c1c','#b45309','#166534']}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{ticks:{precision:0}}}}}));
    }
  }
  window.CostOpt360={renderDashboard:renderDashboard};
})();
"""


def build_standalone_html(data_json, client_name):
    """Return a full self-contained HTML dashboard document (string)."""
    from datetime import datetime, timezone
    safe_client = (client_name or 'Client').replace('<', '').replace('>', '')
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    # Escape characters that could break out of the <script> block or be treated
    # as HTML when the JSON is embedded inline. These map to valid JSON unicode
    # escapes inside string values, so JSON.parse() restores the originals.
    safe_data = (data_json
                 .replace('<', '\\u003c')
                 .replace('>', '\\u003e')
                 .replace('&', '\\u0026')
                 .replace('\u2028', '\\u2028')
                 .replace('\u2029', '\\u2029'))
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CostOptimizer360 - {client}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<style>
  body{{margin:0;background:#f1f5f9;padding:24px;}}
  .co-head{{background:linear-gradient(135deg,#23649c,#1a4d78);color:#fff;border-radius:14px;padding:26px 30px;margin-bottom:22px;}}
  .co-head h1{{margin:0;font-size:1.8rem;}} .co-head p{{margin:6px 0 0;opacity:.9;}}
{css}
</style></head>
<body>
  <div class="co-head">
    <h1>CostOptimizer360 - AWS Cost Optimization</h1>
    <p>Client: {client} &nbsp;|&nbsp; Generated: {generated}</p>
  </div>
  <div class="co-dash" id="dashboard"></div>
<script>const DATA={data};</script>
<script>{js}</script>
<script>window.addEventListener('DOMContentLoaded',function(){{CostOpt360.renderDashboard(DATA,'dashboard');}});</script>
</body></html>""".format(
        client=safe_client,
        generated=generated,
        css=DASHBOARD_CSS,
        js=DASHBOARD_JS,
        data=safe_data,
    )
