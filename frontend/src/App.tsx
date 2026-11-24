import {useEffect,useState} from 'react';
import {api} from './api';import {useRun} from './useRun';import {NetworkMap} from './NetworkMap';
import type {Scenario} from './types';
const clock=(seconds:number)=>`${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;
const readable=(text:string)=>text.toLowerCase().replaceAll('_',' ');
export function App(){
 const run=useRun();const [scenario,setScenario]=useState<Scenario|null>(null),[loadError,setLoadError]=useState('');
 const [horizon,setHorizon]=useState('2'),[selected,setSelected]=useState(true),[locate,setLocate]=useState(0),[follow,setFollow]=useState(false);
 const [road,setRoad]=useState(''),[effect,setEffect]=useState('ENTRY_CLOSED'),[reported,setReported]=useState(true),[tab,setTab]=useState<'alerts'|'events'>('events');
 useEffect(()=>{api<Scenario[]>('/scenarios').then(s=>{setScenario(s[0]);setRoad(s[0].graph.edges[0].id);}).catch(e=>setLoadError(String(e)));},[]);
 const state=run.snapshot,a=state?.ambulance;
 const act=(type:string,payload:Record<string,unknown>={})=>{void run.send(type,payload).catch(()=>{});};
 const eta=state&&!run.connected?'Stale':!a?'—':a.arrivedAt!==null?'Arrived':a.estimatedArrival===null?'ETA unavailable':a.estimatedArrival<(state?.simulationTimeSeconds??0)?'Estimate exceeded':`${Math.ceil(a.estimatedArrival-(state?.simulationTimeSeconds??0))}s`;
 const events=run.events.filter(e=>tab==='events'||e.type==='OPERATOR_ALERT'||e.type==='COMMAND_REJECTED');
 const remaining=scenario&&a?a.route.reduce((sum,id)=>sum+(scenario.graph.edges.find(e=>e.id===id)?.length??0),0)-a.progress:0;
 return <main className="app-shell">
  <header className="topbar"><a className="brand" href="#"><span className="brand-mark">G<span/></span><span>GeoPulse<small>TRAFFIC INTELLIGENCE</small></span></a>
   <div className="workspace-title"><span className="eyebrow">OPERATIONS / CENTRAL DISTRICT</span><strong>Control room</strong></div>
   <div className="top-status"><span className="tag">SYNTHETIC NETWORK</span><span className={run.connected?'connection':'connection offline'}><i/>{run.connected?'Connected':state?'Connection stale':'Not connected'}</span></div>
  </header>
  <section className="workspace-bar"><div><span className="eyebrow">ROUTING LABORATORY</span><h1>Every turn, explained.</h1><p>One ambulance. A changing network. A decision at every junction.</p></div><div className="clock"><span className="eyebrow">SIMULATION TIME</span><strong>{clock(state?.simulationTimeSeconds??0)}</strong><span>{state?readable(state.runStatus):'Ready to begin'}</span></div></section>
  {(run.error||loadError)&&<div className="error-banner" role="alert">{run.error||loadError}{loadError&&' · Start the backend and reload this page.'}</div>}
  <div className="workspace">
   <aside className="fleet-panel panel"><div className="panel-heading"><h2>Mission control</h2><span className="count">01</span></div>
    <div className="scenario-card"><span className="eyebrow">ACTIVE SCENARIO</span><h3>Central district</h3><p>5 × 5 synthetic grid</p><div className="scenario-stats"><span><b>25</b> junctions</span><span><b>80</b> road segments</span></div><span className="mode-tag">M1 · Routing only</span></div>
    <label className="field-label" htmlFor="horizon">Live information horizon</label><select id="horizon" value={horizon} onChange={e=>setHorizon(e.target.value)}><option value="0">Historical only · 0 hops</option><option value="2">Hybrid · 2 hops</option><option value="all">All reachable roads</option></select>
    <button className="secondary full" disabled={!!run.pending||!scenario} onClick={()=>{if(!state||confirm('Create a new run? The current run will be paused and its history retained.'))void run.create(horizon);}}>{state?'New run':'Create run'}</button>
    <div className="section-label">FLEET <span>1 ambulance</span></div>
    <button className={`ambulance-card ${selected?'selected':''}`} onClick={()=>setSelected(true)}><span className="vehicle-icon">✚</span><span><strong>AMB–001</strong><small>{a?readable(a.status):'Awaiting mission'}</small></span><span className="card-chevron">›</span></button>
    <div className="mission-details"><div><span className="point station"/><span><small>DEPARTURE</small>Station 01</span></div><div><span className="point hospital"/><span><small>DESTINATION</small>City Hospital</span></div></div>
    <button className="primary full" disabled={!state||!!run.pending||a?.status!=='IDLE'} onClick={()=>act('ACTIVATE',{origin:scenario?.origin,destination:scenario?.destination})}>Activate mission</button>
    <details className="scenario-tools"><summary>Scenario controls</summary><p>Change a physical road condition. Reporting makes a closure known to the router.</p><label className="field-label" htmlFor="road">Road segment</label><select id="road" value={road} onChange={e=>setRoad(e.target.value)}>{scenario?.graph.edges.map(e=><option key={e.id} value={e.id}>{e.from} → {e.to}</option>)}</select>
     <label className="field-label" htmlFor="effect">Physical effect</label><select id="effect" value={effect} onChange={e=>setEffect(e.target.value)}><option value="ENTRY_CLOSED">Entry closure</option><option value="IMPASSABLE">Fully impassable</option><option value="SLOW">Slow to 2 m/s</option><option value="OPEN">Restore road</option></select>
     <label className="check"><input type="checkbox" checked={reported} onChange={e=>setReported(e.target.checked)}/> Report closure / reopening</label><button className="secondary full" disabled={!state||!!run.pending} onClick={()=>act('INCIDENT',{edge:road,effect,reported})}>Apply road condition</button>
    </details>
    <div className="scope-note"><strong>Routing-only demonstration</strong><p>Junction waiting is explicitly zero. Background traffic and signal priority arrive in M2.</p></div>
   </aside>
   <section className="map-panel panel"><div className="map-top"><div><span className="eyebrow">NETWORK VIEW</span><strong>Ambulance routing</strong></div><div className="map-actions"><button className="subtle" disabled={!state} onClick={()=>setLocate(n=>n+1)}>Locate</button><button className={follow?'subtle active':'subtle'} disabled={!state} aria-pressed={follow} onClick={()=>setFollow(v=>!v)}>Follow</button></div></div>
    <div className="map-wrap">{scenario?<NetworkMap scenario={scenario} snapshot={state} locate={locate} follow={follow} onDrag={()=>setFollow(false)} onEdge={setRoad} onAmbulance={()=>setSelected(true)}/>:<div className="map-empty">{loadError?'Backend unavailable':'Loading network…'}</div>}
     <div className="map-caption"><span className="mode-tag">SYNTHETIC</span><span>{state?.explanation?`Routing decision at ${clock(state.explanation.time)}`:'Activate a mission to inspect live coverage'}</span></div>
     <div className="map-legend"><span><i className="legend-line live"/>Live</span><span><i className="legend-line historical"/>Historical</span><span><i className="legend-line route"/>Selected route</span></div>
    </div>
    <div className="playback"><div className="play-buttons"><button className="primary" disabled={!state||!!run.pending||a?.status==='ARRIVED'} onClick={()=>act(state?.paused?'PLAY':'PAUSE')}>{!state||state.paused?'▶ Play':'Ⅱ Pause'}</button><button className="secondary" disabled={!state||!state.paused||!!run.pending||a?.status==='ARRIVED'} onClick={()=>act('STEP')}>Step 1s</button></div><label className="speed-label">Playback<select aria-label="Playback speed" value={state?.speed??1} disabled={!state||!!run.pending} onChange={e=>act('SET_SPEED',{speed:Number(e.target.value)})}>{[1,5,10,30,60].map(s=><option key={s} value={s}>{s}×</option>)}</select></label><span className="revision">{run.pending?`Pending: ${readable(run.pending)}`:`Revision ${state?.stateRevision??'—'}`}</span></div>
   </section>
   <aside className="inspector panel"><div className="panel-heading"><h2>Mission inspector</h2><span className="small-tag">AMB–001</span></div>
    <div className="inspector-title"><span className="eyebrow">HOSPITAL-BOUND JOURNEY</span><h2>City Hospital</h2><p>{a?readable(a.status):'No active mission'}</p></div>
    <div className="metrics"><div><span>Estimated remaining</span><strong>{eta}</strong></div><div><span>Distance remaining</span><strong>{Math.max(0,remaining)}<small> m</small></strong></div></div>
    <div className="metric-strip"><span>Re-plans <b>{a?.replans??0}</b></span><span>Reroutes <b>{a?.reroutes??0}</b></span></div>
    {a?.reason&&<div className="stop-alert" role="status"><strong>{readable(a.reason)}</strong><button className="secondary full" disabled={!!a.edge||!!run.pending} onClick={()=>act('RETRY_ROUTE')}>Retry route</button></div>}
    <div className="why-heading"><span className="eyebrow">DECISION EXPLAINER</span><h2>Why this turn?</h2><p>{state?.explanation?`Decision ${state.explanation.routingRevision} at ${clock(state.explanation.time)} · ${state.horizon==='all'?'All-live':state.horizon+'-hop live window'}`:'The next routing decision will appear here.'}</p></div>
    <div className="candidate-list">{state?.explanation?.candidates.map(c=><details className={`candidate ${c.outcome==='SELECTED'?'winner':''}`} key={c.edge}><summary><span>{scenario?.graph.edges.find(e=>e.id===c.edge)?.to}<small>{c.road.source==='LIVE'?'Live observation':c.road.source==='HISTORICAL_FALLBACK'?'Historical fallback':c.road.status==='BLOCKED'?'Known closure':c.road.source==='UNKNOWN'?'Estimate unavailable':'Historical estimate'}</small></span><span className="candidate-cost">{c.pathSeconds!==null?`${c.pathSeconds}s`:readable(c.outcome)}<small>{c.outcome==='SELECTED'?'SELECTED':'PATH COST'}</small></span></summary><div className="candidate-breakdown"><span>Road traversal <b>{c.road.seconds??'—'}s</b></span><span>Junction waiting <b>{c.junction.seconds??'—'}s</b></span><p>Junction estimator: M1_ZERO_WAIT</p><p>{c.reason??c.road.reason??'Total path cost includes all remaining road and junction estimates.'}</p></div></details>)}</div>
    {!state?.explanation&&<div className="empty-explanation"><span>◇</span><p>Live nearby. Historical farther away.<br/>One complete route to the destination.</p></div>}
    {a?.arrivedAt!==null&&a?.arrivedAt!==undefined&&<div className="arrival"><strong>Journey completed</strong><span>{a.arrivedAt-(a.activatedAt??0)} seconds actual travel time</span></div>}
   </aside>
  </div>
  <details className="event-panel panel" open><summary>Run activity <span>{run.events.length} recorded events</span></summary><div className="event-toolbar"><button className={tab==='alerts'?'tab active':'tab'} onClick={()=>setTab('alerts')}>Alerts</button><button className={tab==='events'?'tab active':'tab'} onClick={()=>setTab('events')}>Events</button><span>Ordered by server sequence · no automatic scrolling</span></div><div className="events" role="log" aria-live="off">{events.length?events.map(e=><div className="event" key={e.sequence}><time>{clock(e.time)}</time><span className={e.type.includes('ALERT')||e.type.includes('REJECTED')?'event-kind warning':'event-kind'}>{readable(e.type)}</span><span>{e.data.message}</span><small>#{e.sequence}</small></div>):<p className="empty-events">{tab==='alerts'?'No alerts recorded.':'Create a run to begin recording its decisions.'}</p>}</div></details>
  <footer>GEOPULSE <span>Deterministic simulation · Seed 108 · No real traffic data</span><span>M1 / Routing laboratory</span></footer>
 </main>;
}
