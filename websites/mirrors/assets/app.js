const API='/mirrors/api';
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function badge(p){return '<span class="proto-badge">'+esc(p)+'</span>'}
async function go(){
  try{
    const r=await fetch(API);
    if(r.status===503){document.getElementById('content').innerHTML='<p class="spinner">checking servers...</p>';setTimeout(go,3000);return}
    const j=await r.json();
    render(j.data);
    const u=new Date(j.last_updated*1000).toISOString().replace('T',' ').slice(0,16)+' UTC';
    setInterval(()=>{
      const s=Math.max(0,Math.round((j.next_update*1000-Date.now())/1000));
      const m=Math.floor(s/60),ss=s%60;
      document.getElementById('ts').textContent='Updated '+u+' · refresh in '+(s>0?m+':'+String(ss).padStart(2,'0'):'updating...')
    },1000)
  }catch(e){document.getElementById('content').innerHTML='<p class="spinner">error: '+e.message+'</p>';setTimeout(go,10000)}
}
function render(d){
  let h='';
  h+='<div class="section"><h2>Binaries</h2>';
  h+='<p class="subtitle">pkg_add · iso · firmware</p>';
  if(d.binaries[0])h+='<div class="cmd-block"><div class="cmd-line">PKG_PATH='+esc(d.binaries[0].best_url)+' pkg_add &lt;package&gt;</div></div>';
  h+='<div class="card"><table><thead><tr><th></th><th>Host</th><th>Country</th><th>Proto</th><th>ms</th></tr></thead><tbody>';
  d.binaries.forEach(m=>{h+='<tr class="ok"><td><span class="status-dot dot-ok">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td>'+m.protos.map(badge).join('')+'</td><td class="ms">'+m.ms+'</td></tr>'});
  d.binary_dead.forEach(m=>{h+='<tr class="dead"><td><span class="status-dot dot-dead">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td></td><td></td></tr>'});
  h+='</tbody></table></div></div>';
  h+='<div class="section"><h2>CVS (anoncvs)</h2>';
  h+='<p class="subtitle">src · ports · xenocara</p>';
  if(d.cvs_cmds)d.cvs_cmds.forEach(c=>{h+='<div class="cmd-block"><div class="cmd-line">'+esc(c)+'</div></div>'});
  h+='<div class="card"><table><thead><tr><th></th><th>Host</th><th>Country</th><th>Proto</th><th>ms</th></tr></thead><tbody>';
  d.cvs.forEach(m=>{const p=m.port!==22&&m.port!==2401?':'+m.port:'';h+='<tr class="ok"><td><span class="status-dot dot-ok">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td>'+badge(m.proto+p)+'</td><td class="ms">'+m.ms+'</td></tr>'});
  d.cvs_dead.forEach(m=>{h+='<tr class="dead"><td><span class="status-dot dot-dead">●</span></td><td>'+esc(m.host)+'</td><td>'+esc(m.country)+'</td><td></td><td></td></tr>'});
  h+='</tbody></table></div></div>';
  document.getElementById('content').innerHTML=h;
}
go();
