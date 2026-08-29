// Export & Insights functions
function exportJSON(){
  const btn=document.getElementById('export-json-btn');
  btn.disabled=true;btn.textContent='Exporting...';
  fetch('/api/export').then(r=>r.json()).then(data=>{
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='routingmagic-usage-'+new Date().toISOString().slice(0,10)+'.json';
    a.click();URL.revokeObjectURL(url);
    btn.disabled=false;btn.textContent='Export JSON';
  }).catch(e=>{btn.disabled=false;btn.textContent='Export JSON';alert('Export failed: '+e);});
}

function exportCSV(){
  const btn=document.getElementById('export-csv-btn');
  btn.disabled=true;btn.textContent='Exporting...';
  fetch('/api/export/csv').then(r=>r.text()).then(csv=>{
    const blob=new Blob([csv],{type:'text/csv'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='routingmagic-sessions-'+new Date().toISOString().slice(0,10)+'.csv';
    a.click();URL.revokeObjectURL(url);
    btn.disabled=false;btn.textContent='Export CSV';
  }).catch(e=>{btn.disabled=false;btn.textContent='Export CSV';alert('Export failed: '+e);});
}

function showInsights(){
  document.getElementById('insights-modal').classList.add('open');
  document.getElementById('insights-loading').style.display='inline-flex';
  document.getElementById('insights-content').style.display='none';
  fetch('/api/insights').then(r=>r.json()).then(data=>{
    renderInsights(data);
    document.getElementById('insights-loading').style.display='none';
    document.getElementById('insights-content').style.display='block';
  }).catch(e=>{
    document.getElementById('insights-loading').style.display='none';
    document.getElementById('insights-content').innerHTML='<div style="color:var(--red);padding:16px;">Error loading insights: '+e+'</div>';
    document.getElementById('insights-content').style.display='block';
  });
  document.getElementById('insights-modal').classList.add('open');
}

function closeInsights(){
  document.getElementById('insights-modal').classList.remove('open');
}

function renderInsights(data){
  const container=document.getElementById('insights-content');
  if(!data.insights || data.insights.length===0){
    container.innerHTML='<div style="padding:20px;color:var(--muted);text-align:center;">No insights available</div>';
    return;
  }
  let html='';
  data.insights.forEach(insight=>{
    html+='<div class="insight-card" style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;">';
    html+='<h4 style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--accent);">'+esc(insight.title)+'</h4>';
    if(insight.type==='top_cost_models' || insight.type==='top_projects' || insight.type==='model_efficiency'){
      html+='<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>';
      const keys=Object.keys(insight.data[0]||{});
      keys.forEach(k=>html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">'+esc(k)+'</th>');
      html+='</tr></thead><tbody>';
      insight.data.forEach(row=>{
        html+='<tr>';
        keys.forEach(k=>{
          let v=row[k];
          if(k==='cost' || k==='cost_per_dollar')v=typeof v==='number'?'$'+v.toFixed(2):v;
          if(k==='tokens_per_dollar')v=typeof v==='number'?v.toLocaleString():v;
          if(k==='tokens' || k==='free_tokens' || k==='paid_tokens')v=typeof v==='number'?v.toLocaleString():v;
          html+='<td style="padding:4px 8px;border-bottom:1px solid var(--border);">'+esc(v)+'</td>';
        });
        html+='</tr>';
      });
      html+='</tbody></table>';
    }else if(insight.type==='free_ratio'){
      const d=insight.data;
      html+='<div style="display:flex;gap:16px;margin-top:8px;">';
      html+='<div style="flex:1;background:rgba(110,224,163,0.1);border:1px solid var(--green);border-radius:8px;padding:12px;text-align:center;">';
      html+='<div style="font-size:24px;font-weight:700;color:var(--green);">'+d.free_pct+'%</div>';
      html+='<div style="font-size:11px;color:var(--muted);">Free Usage</div>';
      html+='<div style="font-size:12px;font-family:monospace;">'+d.free_tokens.toLocaleString()+' tokens</div>';
      html+='</div>';
      html+='<div style="flex:1;background:rgba(232,92,78,0.1);border:1px solid var(--red);border-radius:8px;padding:12px;text-align:center;">';
      html+='<div style="font-size:24px;font-weight:700;color:var(--red);">'+(100-d.free_pct).toFixed(1)+'%</div>';
      html+='<div style="font-size:11px;color:var(--muted);">Paid Usage</div>';
      html+='<div style="font-size:12px;font-family:monospace;">'+d.paid_tokens.toLocaleString()+' tokens</div>';
      html+='</div>';
      html+='</div>';
    }else if(insight.type==='daily_trend'){
      html+='<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Day</th>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Tokens</th>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Cost</th>';
      html+='</tr></thead><tbody>';
      insight.data.forEach(r=>html+='<tr><td style="padding:4px 8px;border-bottom:1px solid var(--border);">'+esc(r.day)+'</td><td style="padding:4px 8px;border-bottom:1px solid var(--border);font-family:monospace;">'+r.tokens.toLocaleString()+'</td><td style="padding:4px 8px;border-bottom:1px solid var(--border);color:var(--green);">$'+r.cost.toFixed(2)+'</td></tr>');
      html+='</tbody></table>';
    }else if(insight.type==='budget_health'){
      const statusColors={'healthy':'var(--green)','warning':'var(--amber)','critical':'var(--red)'};
      const c=statusColors[d.status]||'var(--muted)';
      html+='<div style="display:flex;align-items:center;gap:12px;">';
      html+='<div style="width:12px;height:12px;border-radius:50%;background:'+c+';"></div>';
      html+='<div><div style="font-size:14px;font-weight:600;color:'+c+';">'+d.status.toUpperCase()+'</div>';
      html+='<div style="font-size:12px;color:var(--muted);">Monthly: '+d.monthly_pct+'% | Daily: '+d.daily_pct+'%</div></div></div>';
    }
    html+='</div>';
  });
  document.getElementById('insights-content').innerHTML=html;
  document.getElementById('insights-content').style.display='block';
}
