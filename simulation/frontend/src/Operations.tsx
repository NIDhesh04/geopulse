import {useState} from 'react';
import {clock, readable, type MapMode} from './controlRoom';
import type {RunEvent, Scenario, SimulationTruth, Snapshot} from './types';

type Act = (type:string, payload?:Record<string,unknown>)=>void;

export function RoadControls({mode,scenario,state,truth,events,road,setRoad,pending,act}:{
  mode:MapMode; scenario?:Scenario; state:Snapshot|null; truth?:SimulationTruth;
  events:RunEvent[]; road:string; setRoad:(road:string)=>void; pending:boolean; act:Act;
}) {
  const [effect,setEffect] = useState('ENTRY_CLOSED');
  if (mode === 'routing') return null;
  const physical = mode === 'truth';
  const roadTruth = physical ? truth?.roads[road] : undefined;
  const effects = physical ? truth?.physicalEffects[road] : undefined;
  const reviewTick = Math.max(-1,...Object.values(state?.reports??{})
    .filter(report=>report.status==='CONFIRMED'&&report.road===road).map(report=>report.reviewedAt??-1));
  const reportTick = events.reduce((latest,event)=>event.type==='ROAD_REPORT'
    &&event.data.message.startsWith(road+':')?Math.max(latest,event.time):latest,-1);
  const observedAt = Math.max(reviewTick,reportTick);
  const available = !!state && !pending && !!scenario?.graph.edges.some(edge=>edge.id===road);
  return <section className="inspector-section">
    <h3>{physical?'Simulator incident injection':'Operational road reports'}</h3>
    <label className="field-label" htmlFor="road">Road segment</label>
    <select id="road" value={road} onChange={event=>setRoad(event.target.value)}>
      {scenario?.graph.edges.map(edge=><option key={edge.id} value={edge.id}>{edge.from} → {edge.to}</option>)}
    </select>
    {physical ? <>
      {roadTruth && <p>Actual occupancy {roadTruth.occupancy.toFixed(1)} / {roadTruth.capacity} · Queue {roadTruth.queued.toFixed(1)} veh-eq</p>}
      <p>{effects?.length ? effects.map(readable).join(', ') : truth?'No active physical effect':'Waiting for simulation truth'}</p>
      <label className="field-label" htmlFor="effect">Physical effect</label>
      <select id="effect" value={effect} onChange={event=>setEffect(event.target.value)}>
        <option value="ENTRY_CLOSED">Entry closure</option><option value="IMPASSABLE">Fully impassable</option>
        <option value="SLOW">Slow to 2 m/s</option>
        {state?.traffic && <><option value="DISCHARGE_REDUCED">Reduce discharge</option><option value="DEMAND_SURGE">Increase boundary demand</option></>}
        <option value="OPEN">Restore road</option>
      </select>
      <button className="secondary full" disabled={!available} onClick={()=>act('INCIDENT',{edge:road,effect,reported:false})}>Apply road condition</button>
    </> : <>
      <p>{state?.reportedClosures.includes(road)?'Confirmed closure':'No confirmed closure'}
        {observedAt>=0&&` · Last confirmed at ${clock(observedAt)}`}</p>
      <div className="action-pair">
        <button className="secondary" disabled={!available} onClick={()=>act('REPORT_CLOSURE',{edge:road})}>Report closure</button>
        <button className="secondary" disabled={!available} onClick={()=>act('REPORT_REOPENING',{edge:road})}>Report reopening</button>
      </div>
    </>}
  </section>;
}

export function RunActivity({state,events,pending,act}:{
  state:Snapshot|null; events:RunEvent[]; pending:boolean; act:Act;
}) {
  const [tab,setTab] = useState<'alerts'|'events'>('alerts');
  const [seen,setSeen] = useState('0');
  const alerts = events.filter(event =>
    (event.type==='OPERATOR_ALERT'||event.type==='COMMAND_REJECTED'||event.type==='PRIORITY_DOWNSTREAM_BLOCKED')
    && state?.acknowledgements?.[event.sequence]===undefined);
  const reports = Object.values(state?.reports??{}).sort((a,b)=>a.submittedAt-b.submittedAt||a.id.localeCompare(b.id));
  const pendingReports = reports.filter(report=>report.status==='PENDING');
  const newEvents = events.filter(event=>BigInt(event.sequence)>BigInt(seen)).length;
  return <details className="event-panel panel" open>
    <summary>Run activity <span>{pendingReports.length} awaiting review · {alerts.length} unresolved</span></summary>
    <div className="event-toolbar" aria-label="Run activity view">
      <button className={tab==='alerts'?'tab active':'tab'} aria-pressed={tab==='alerts'} onClick={()=>setTab('alerts')}>Alerts</button>
      <button className={tab==='events'?'tab active':'tab'} aria-pressed={tab==='events'} onClick={()=>setTab('events')}>Events</button>
      {newEvents>0 && <button className="subtle new-events" onClick={()=>setSeen(events.at(-1)?.sequence??seen)}>{newEvents} new · Mark seen</button>}
    </div>
    <div className="events" hidden={tab!=='alerts'}>
      {pendingReports.map(report=><div className="review-row" key={report.id}>
        <time>{clock(report.submittedAt)}</time>
        <div><strong>{report.closure?'Obstruction report':'Reopening report'}</strong><p>{report.ambulanceId} · {report.road} · Awaiting operator review</p></div>
        <div className="action-pair"><button className="secondary" disabled={pending} onClick={()=>act('REVIEW_OBSTRUCTION',{reportId:report.id,confirmed:true})}>Confirm</button>
          <button className="secondary" disabled={pending} onClick={()=>act('REVIEW_OBSTRUCTION',{reportId:report.id,confirmed:false})}>Reject</button></div>
      </div>)}
      {alerts.map(event=><div className="review-row" key={event.sequence}><time>{clock(event.time)}</time>
        <div><strong>{readable(event.type)}</strong><p>{event.data.message}</p></div>
        <button className="secondary" disabled={!state||pending} onClick={()=>act('ACKNOWLEDGE_ALERT',{alertId:event.sequence})}>Acknowledge</button>
      </div>)}
      {!alerts.length&&!pendingReports.length&&<p className="empty-events">No unresolved alerts or pending reports.</p>}
    </div>
    <div className="events" role="log" tabIndex={0} aria-label="Recorded events" aria-live="off" hidden={tab!=='events'}>
      {events.map(event=><div className="event" key={event.sequence}><time>{clock(event.time)}</time>
        <span className="event-kind">{readable(event.type)}</span><span>{event.data.message}</span><small>#{event.sequence}</small>
      </div>)}
      {!events.length&&<p className="empty-events">No recorded events.</p>}
    </div>
  </details>;
}
