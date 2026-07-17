
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
