import {useEffect, useState} from 'react';
import {api} from './api';
import {useRun} from './useRun';
import {NetworkMap} from './NetworkMap';
import {clock, filterFleet, modes, readable, zoneFor, type MapMode} from './controlRoom';
import {useProjection} from './useProjection';
import {RoadControls, RunActivity} from './Operations';
import type {MissionView, Scenario, SimulationTruth} from './types';
import {isDrawer, useWorkspaceDrawers, type Drawer} from './workspaceDrawers';

const scenarioLabels: Record<string,string> = {
  ROUTING_ONLY:'Routing only', TRAFFIC_SIGNALS:'Traffic and signals', FLEET_TRAFFIC:'Ten ambulance conflict',
  PREDICTABLE_CONGESTION:'Predictable corridor congestion',
};

export function App() {
  const run = useRun();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState(()=>new URLSearchParams(location.search).get('scenario')??'routing-only-5x5');
  const [priority, setPriority] = useState(true);
  const [horizon, setHorizon] = useState('2');
  const [loadError, setLoadError] = useState('');
  const [selectedId, setSelectedId] = useState('AMB-001');
  const [inspectedJunction, setInspectedJunction] = useState<string>();
  const [road, setRoad] = useState('');
  const [search, setSearch] = useState('');
  const [zone, setZone] = useState('All zones');
  const [mode, setMode] = useState<MapMode>('operational');
  const [locate, setLocate] = useState(0);
  const [follow, setFollow] = useState(false);
  const drawers = useWorkspaceDrawers();
  const showSetup = new URLSearchParams(location.search).has('setup');

  useEffect(()=>{
    if (showSetup && !isDrawer(drawers.layout,'fleet')) return;
    if (showSetup) drawers.show('fleet');
  },[showSetup,drawers.layout]);

  useEffect(() => {
    api<Scenario[]>('/scenarios').then(items => {
      setScenarios(items);
      setScenarioId(current=>items.some(item=>item.id===current)?current:items[0]?.id??'');
      setRoad(items[0]?.graph.edges[0]?.id ?? '');
    }).catch(error => setLoadError(String(error)));
  }, []);

  const state = run.snapshot;
  const scenario = scenarios.find(item => item.id === (state?.scenarioId ?? scenarioId)) ?? scenarios[0];
  const next = scenarios.find(item => item.id === scenarioId);
  const traffic = state?.traffic;
  const fleet = state?.fleet ?? (state ? [state.ambulance] : []);
  const filteredFleet = filterFleet(fleet,search,zone,scenario);
  const selected = fleet.find(vehicle => vehicle.id === selectedId) ?? fleet[0];
  const id = selected?.id;
  const missionPath = state && id && state.fleet ? `/runs/${state.runId}/ambulances/${id}/snapshot` : null;
  const mission = useProjection<MissionView>(missionPath, state?.stateRevision);
  const truthPath = state && mode === 'truth' ? `/runs/${state.runId}/simulation-truth` : null;
  const truthResult = useProjection<SimulationTruth>(truthPath, state?.stateRevision);
  const truth = mode === 'truth' ? truthResult?.data : undefined;
  const explanation = mode === 'routing' ? mission?.data?.explanation ?? state?.explanation : undefined;
  const junction = inspectedJunction ?? (selected?.edge
    ? scenario?.graph.edges.find(edge => edge.id === selected.edge)?.to : selected?.node);
  const signal = junction ? traffic?.signals[junction] : undefined;
  const departure = (id ? scenario?.departureByAmbulance?.[id] : undefined) ?? scenario?.origin;
  const elapsed = state?.simulationTimeSeconds ?? 0;
  const pending = Boolean(run.pending);
  const prioritySuspended = mission?.data?.prioritySuspended ?? (id === 'AMB-001' && state?.prioritySuspended);
  const priorityState = prioritySuspended ? 'suspended' : state?.priorityEnabled
    ? readable(mission?.data?.priority ?? (id === 'AMB-001' ? traffic?.priority : undefined) ?? 'NONE') : 'disabled';
  const eta = !selected || !run.connected || selected.estimatedArrival === null ? '—'
    : selected.arrivedAt !== null ? 'Arrived' : selected.estimatedArrival < elapsed ? 'Estimate exceeded'
    : `${Math.ceil(selected.estimatedArrival - elapsed)}s`;
  const act = (type:string, payload:Record<string,unknown> = {}) => {void run.send(type,payload).catch(() => {});};
  const select = (vehicleId:string) => {setSelectedId(vehicleId);setInspectedJunction(undefined);};
  const selectOnMap = (vehicleId:string) => {select(vehicleId);setSearch('');setZone('All zones');drawers.show('inspector');};
  const create = () => {
    if (state && !confirm('Create a new run? The current run will be paused and its history retained.')) return;
    setSelectedId('AMB-001');setInspectedJunction(undefined);setSearch('');setZone('All zones');setFollow(false);
    void run.create(horizon, scenarioId, priority);
  };
  const canAdvance = !!state && !pending && state.runStatus !== 'COMPLETED';
  const panels:Record<Drawer,string> = {fleet:'Fleet',inspector:'Inspector',activity:'Run activity'};
  const closeButton = (panel:Drawer) => isDrawer(drawers.layout,panel) && <button className="subtle drawer-close"
    ref={element=>drawers.closeRef(panel,element)} aria-label={`Close ${panels[panel].toLowerCase()}`}
    onClick={()=>drawers.close(panel)}>Close</button>;

  return <main className="app-shell" data-layout={drawers.layout}>
    <header className="topbar">
      <a className="brand" href="/welcome"><span className="brand-mark" aria-hidden="true">G</span>GeoPulse</a>
      <div className="workspace-title"><strong>Police Control Room</strong></div>
      <div className="top-status"><span className="tag">SYNTHETIC NETWORK</span>
        <span className={run.connected?'connection':'connection offline'}><i/>{run.connected?'Connected':state?'Connection stale':'Not connected'}</span>
      </div>
    </header>
    <section className="workspace-bar">
      <div><h1>Police Control Room</h1><p>{scenario?.name ?? 'Select a scenario to begin'}</p></div>
      <div className="clock"><span className="eyebrow">Simulation time</span><strong>{clock(elapsed)}</strong><span>{state?readable(state.runStatus):'Ready'}</span></div>
    </section>
    {(run.error || loadError) && <div className="error-banner" role="alert">{run.error || loadError}</div>}
    {drawers.layout!=='desktop'&&<nav className="drawer-toolbar" aria-label="Control room panels">
      {(Object.keys(panels) as Drawer[]).filter(panel=>isDrawer(drawers.layout,panel)).map(panel=><button type="button"
        key={panel} className="secondary" aria-controls={`panel-${panel}`} aria-expanded={drawers.active===panel}
        ref={element=>drawers.triggerRef(panel,element)} onClick={()=>drawers.toggle(panel)}>{panels[panel]}</button>)}
    </nav>}
    <div className="workspace" data-fleet-open={drawers.visible('fleet')}>
      <aside className="fleet-panel panel" id="panel-fleet" aria-labelledby="fleet-heading" hidden={!drawers.visible('fleet')}>
        <div className="panel-heading"><h2 id="fleet-heading">Mission control</h2>{closeButton('fleet')}</div>
        <label className="field-label" htmlFor="scenario">Scenario for next run</label>
        <select id="scenario" value={scenarioId} onChange={e=>setScenarioId(e.target.value)}>
          {scenarios.map(item=><option key={item.id} value={item.id}>{scenarioLabels[item.mode] ?? item.name}</option>)}
        </select>
        {next && next.mode !== 'ROUTING_ONLY' && <label className="check"><input type="checkbox" checked={priority} onChange={e=>setPriority(e.target.checked)}/> Ambulance signal priority</label>}
        <label className="field-label" htmlFor="horizon">Live information horizon</label>
        <select id="horizon" value={horizon} onChange={e=>setHorizon(e.target.value)}>
          <option value="0">Historical only</option><option value="2">Hybrid · 2 hops</option><option value="all">All reachable roads</option>
        </select>
        <button className="secondary full" disabled={pending || !scenarios.length} onClick={create}>{state?'New run':'Create run'}</button>

        <div className="section-label">FLEET <span>{fleet.length} {fleet.length===1?'ambulance':'ambulances'}</span></div>
        <label className="field-label" htmlFor="fleet-search">Search fleet</label>
        <input id="fleet-search" type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Ambulance ID"/>
        <label className="field-label" htmlFor="fleet-zone">Zone</label>
        <select id="fleet-zone" value={zone} onChange={e=>setZone(e.target.value)}>
          {['All zones','North','Central','South'].map(item=><option key={item}>{item}</option>)}
        </select>
        <div className="fleet-list">
          {filteredFleet.map(vehicle=><button key={vehicle.id}
            className={`ambulance-card ${vehicle.id===id?'selected':''}`} aria-pressed={vehicle.id===id} onClick={()=>select(vehicle.id)}>
            <span className="vehicle-icon" aria-hidden="true">✚</span><span><strong>{vehicle.id}</strong>
            <small>{readable(vehicle.status)} · {zoneFor(vehicle.node,scenario)}</small></span>
          </button>)}
          {fleet.length>0 && !filteredFleet.length && <p className="scope-note">No ambulances match these filters.</p>}
        </div>
        {selected && <>
          <div className="mission-details"><div><span className="point"/><span><small>DEPARTURE</small>{departure}</span></div>
          <div><span className="point hospital"/><span><small>DESTINATION</small>{selected.activatedAt===null?scenario?.destination:selected.destination}</span></div></div>
          <button className="primary full" disabled={pending || selected.status!=='IDLE' || !departure || !scenario} onClick={()=>
            act('ACTIVATE',{ambulanceId:id,origin:departure,destination:scenario?.destination})}>Activate mission</button>
          {state && <a className="secondary full driver-link" href={`/driver?run=${encodeURIComponent(state.runId)}&ambulance=${encodeURIComponent(selected.id)}`}>Open Driver Navigation</a>}
        </>}
      </aside>

      <section className="map-panel panel">
        <div className="map-top"><div className="mode-switch" aria-label="Map information mode">
          {(Object.keys(modes) as MapMode[]).map(item=><button key={item} className={`subtle ${mode===item?'active':''}`}
            aria-pressed={mode===item} onClick={()=>setMode(item)}>{modes[item]}</button>)}
        </div><div className="map-actions">
          <button className="subtle" disabled={!selected} onClick={()=>setLocate(n=>n+1)}>Locate</button>
          <button className="subtle" disabled={!selected} aria-pressed={follow} onClick={()=>setFollow(value=>!value)}>Follow</button>
        </div></div>
        <div className="map-wrap">
          {scenario && <NetworkMap scenario={scenario} fleet={fleet} selected={selected} mode={mode} explanation={explanation}
            closures={state?.reportedClosures??[]} signals={traffic?.signals} truth={truth} locate={locate} follow={follow}
            onDrag={()=>setFollow(false)} onEdge={edge=>{setRoad(edge);drawers.show('inspector');}} onAmbulance={selectOnMap}
            onJunction={node=>{setInspectedJunction(node);drawers.show('inspector');}}/>}
          <div className="map-caption"><span className="mode-tag">{mode==='truth'?'SIMULATOR VIEW':modes[mode]}</span>
            <span>{mode==='truth' ? truth ? `Actual state at ${clock(truth.simulationTimeSeconds)}` : truthResult?.error ?? 'Waiting for simulation truth'
              : mode==='routing' ? explanation ? `${id} · Decision ${explanation.routingRevision} at ${clock(explanation.time)}` : mission?.error ?? 'Activate a mission to see routing estimates'
              : `Confirmed reports and signal observations at ${clock(elapsed)}`}</span></div>
          <div className="map-legend" aria-label="Map legend">
            {mode==='routing' ? <><span><i className="legend-line live"/>Live</span><span><i className="legend-line historical"/>Historical</span>
              <span><i className="legend-line fallback"/>Fallback</span><span><i className="legend-line route"/>Selected route</span>
              <span><i className="legend-line exception"/>Known closure</span></>
              : mode==='truth' ? <><span><i className="legend-line congestion"/>Occupancy · low to high</span>
                <span><i className="legend-line queue"/>Queued vehicles</span><span><i className="legend-line exception"/>Physical effect</span></>
              : <><span><i className="legend-line live"/>Road network</span><span><i className="legend-line exception"/>Confirmed closure</span>
                {traffic && <span><i className="signal-key"/>Observed signal</span>}</>}
          </div>
        </div>
        <div className="playback"><div className="play-buttons">
          <button className="primary" disabled={!canAdvance} onClick={()=>act(state?.paused?'PLAY':'PAUSE')}>{!state||state.paused?'▶ Play':'Ⅱ Pause'}</button>
          <button className="secondary" disabled={!canAdvance||!state?.paused} onClick={()=>act('STEP')}>Step 1s</button>
        </div><label className="speed-label">Playback<select aria-label="Playback speed" value={state?.speed??1} disabled={!state||pending}
          onChange={e=>act('SET_SPEED',{speed:Number(e.target.value)})}>{[1,5,10,30,60].map(speed=><option key={speed} value={speed}>{speed}×</option>)}</select></label>
          <span className="revision">{run.pending?`Pending: ${readable(run.pending)}`:`Revision ${state?.stateRevision??'—'}`}</span>
        </div>
      </section>

      <aside className="inspector panel" id="panel-inspector" aria-labelledby="inspector-heading" hidden={!drawers.visible('inspector')}>
        <div className="panel-heading"><h2 id="inspector-heading">Inspector</h2>{id&&<span className="small-tag">{id}</span>}{closeButton('inspector')}</div>
        <label className="field-label" htmlFor="inspect-junction">Inspect junction</label>
        <select id="inspect-junction" value={inspectedJunction??''} onChange={event=>setInspectedJunction(event.target.value||undefined)}>
          <option value="">Selected ambulance’s next junction</option>
          {scenario?.graph.nodes.map(node=><option key={node.id} value={node.id}>{node.id}</option>)}
        </select>
        {selected && <>
          <div className="metrics"><div><span>ETA remaining</span><strong>{eta}</strong></div>
            <div><span>Mission status</span><strong className="mission-status">{readable(selected.status)}</strong></div></div>
          {selected.reason && <div className="stop-alert"><strong>{readable(selected.reason)}</strong>
            <button className="secondary full" disabled={pending || !!selected.edge} onClick={()=>act('RETRY_ROUTE',{ambulanceId:id})}>Retry route</button></div>}
          {traffic && <div className="scope-note"><strong>Priority {priorityState}</strong>
            <p>Junction wait {mission?.data?.junctionWait??(id==='AMB-001'? state?.ambulanceJunctionWait??0:0)}s</p>
            {state?.priorityEnabled && <button className="secondary full" disabled={pending}
              onClick={()=>act('SUSPEND_PRIORITY',{ambulanceId:id,suspended:!prioritySuspended})}>{prioritySuspended?'Resume priority':'Suspend priority'}</button>}
          </div>}
        </>}
        {signal && <section className="inspector-section"><h3>Junction {junction}</h3>
          <p>{readable(signal.phase)}{signal.recoveryGreen?' · Recovery green':''}
            {signal.startedAt!==undefined && signal.startedAt>=0 && ` · Since ${clock(signal.startedAt)}`}</p>
          {signal.permissions.includes(1)&&<p>Green approach {signal.approaches[signal.permissions.indexOf(1)]}</p>}
          <p>Active grant {signal.grantedAmbulance ?? '—'}</p>
          <p>Pending and competing requests</p>
          {Object.entries(signal.requests??{}).filter(([,status])=>status!=='GRANTED').length===0 ? <p>None</p>
            : <ul>{Object.entries(signal.requests??{}).filter(([,status])=>status!=='GRANTED').map(([vehicle,status])=>
              <li key={vehicle}>{vehicle} · {readable(status)}</li>)}</ul>}
        </section>}
        {junction&&!signal&&<section className="inspector-section"><h3>Junction {junction}</h3><p>No signal observations available.</p></section>}
        {mode==='routing' && <section className="inspector-section"><h3>Why this turn?</h3>
          <p>{explanation?`Decision ${explanation.routingRevision} at ${clock(explanation.time)} · ${state?.horizon==='all'?'All live':`${state?.horizon}-hop window`}`:'Awaiting a routing decision'}</p>
          <label className="field-label" htmlFor="route-road">Inspect road estimate</label>
          <select id="route-road" value={road} onChange={event=>setRoad(event.target.value)}>
            {scenario?.graph.edges.map(edge=><option key={edge.id} value={edge.id}>{edge.from} → {edge.to}</option>)}
          </select>
          {explanation?.roads[road]&&<p>{readable(explanation.roads[road].source)} · {readable(explanation.roads[road].status)}
            {explanation.roads[road].seconds!==null&&` · ${explanation.roads[road].seconds?.toFixed(1)}s`}
            {explanation.roads[road].reason&&` · ${explanation.roads[road].reason}`}</p>}
          {explanation?.candidates.map(candidate=><details className={`candidate ${candidate.outcome==='SELECTED'?'winner':''}`} key={candidate.edge}>
            <summary><span>{scenario?.graph.edges.find(edge=>edge.id===candidate.edge)?.to ?? candidate.edge}<small>{readable(candidate.road.source)}</small></span>
              <span className="candidate-cost">{candidate.pathSeconds!==null?`${candidate.pathSeconds.toFixed(1)}s`:readable(candidate.outcome)}</span></summary>
            <div className="candidate-breakdown"><p>Road travel {candidate.road.seconds?.toFixed(1)??'—'}s · Junction wait {candidate.junction.seconds?.toFixed(1)??'—'}s</p>
              {candidate.road.reason&&<p>Road estimate · {candidate.road.reason}</p>}
              <p>Junction estimate · {candidate.junction.reason ?? readable(candidate.junction.source)}</p>
              {candidate.reason&&candidate.reason!==candidate.road.reason&&candidate.reason!==candidate.junction.reason&&<p>{candidate.reason}</p>}</div>
          </details>)}
        </section>}
        <RoadControls mode={mode} scenario={scenario} state={state} truth={truth} events={run.events} road={road} setRoad={setRoad} pending={pending} act={act}/>
      </aside>
    </div>
    <section id="panel-activity" className="activity-wrapper" aria-label="Run activity" hidden={!drawers.visible('activity')}>
      {closeButton('activity')}
      <RunActivity key={state?.runId} state={state} events={run.events} pending={pending} act={act}/>
    </section>
  </main>;
}
