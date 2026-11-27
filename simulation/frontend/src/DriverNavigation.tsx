import {useEffect,useRef,useState,type FormEvent} from 'react';
import {api} from './api';
import {useProjection} from './useProjection';
import {useRun} from './useRun';
import {NetworkMap} from './NetworkMap';
import {navigationEta, routeGuidance, signalMessage, stopReason} from './navigation';
import type {MissionView, Scenario} from './types';
import './driver.css';

const params = new URLSearchParams(location.search);
const priorityLabels:Record<string,string> = {
  REQUESTED:'Priority requested', GRANTED:'Priority granted',
  DOWNSTREAM_BLOCKED:'Downstream blocked', NONE:'No priority request',
};

export function DriverNavigation() {
  const runId = params.get('run');
  const id = params.get('ambulance');
  const run = useRun(runId);
  const state = run.snapshot;
  const [scenarios,setScenarios] = useState<Scenario[]>([]);
  const [loadError,setLoadError] = useState('');
  const [follow,setFollow] = useState(true);
  const [locate,setLocate] = useState(0);
  const [reportOpen,setReportOpen] = useState(false);
  const [voice,setVoice] = useState(false);
  const lastSpoken = useRef('');
  const [road,setRoad] = useState('');
  const [roadEdited,setRoadEdited] = useState(false);
  const [reportId,setReportId] = useState<string>();
  const [accepted,setAccepted] = useState(false);
  const reportRoad = useRef<HTMLSelectElement>(null);
  const reportTrigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let current = true;
    api<Scenario[]>('/scenarios').then(items => {if(current)setScenarios(items);})
      .catch(error => {if(current)setLoadError(String(error));});
    return () => {current = false;};
  },[]);
  useEffect(() => {if(reportOpen)reportRoad.current?.focus();},[reportOpen]);
  const closeReport = () => {
    setReportOpen(false);
    requestAnimationFrame(()=>reportTrigger.current?.focus({preventScroll:true}));
  };

  const missionPath = state && id ? `/runs/${state.runId}/ambulances/${encodeURIComponent(id)}/snapshot` : null;
  const projection = useProjection<MissionView>(missionPath,state?.stateRevision);
  const scenario = scenarios.find(item=>item.id===state?.scenarioId);
  const selected = (state?.fleet ?? (state ? [state.ambulance] : [])).find(vehicle=>vehicle.id===id);
  const confirmed = useRef<MissionView|undefined>(undefined);
  if (run.connected && projection?.data?.ambulance.id===id) confirmed.current=projection.data;
  const mission = confirmed.current;
  const explanation = mission?.explanation;
  const guidance = routeGuidance(selected,scenario,explanation?.incoming);
  const currentRoad = guidance.current?.id;
  const nextRoadName=guidance.next?scenario?.roadNames?.[guidance.next.id]:undefined;
  const voiceAvailable='speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  const maneuver=nextRoadName?`${guidance.turn} onto ${nextRoadName}`:guidance.turn;
  const voiceCue=selected?.activatedAt!=null
    ? `${selected.reroutes}:${guidance.junction}:${guidance.next?.id}:${maneuver}` : '';
  useEffect(()=>{
    if(!voiceAvailable)return;
    if(!voice||!run.connected){
      if(lastSpoken.current)window.speechSynthesis.cancel();
      lastSpoken.current='';
      return;
    }
    if(voiceCue&&voiceCue!==lastSpoken.current){
      lastSpoken.current=voiceCue;
      window.speechSynthesis.cancel();
      const cue=new SpeechSynthesisUtterance(maneuver);
      cue.lang='en-IN';
      window.speechSynthesis.speak(cue);
    }
  },[voiceAvailable,voice,run.connected,voiceCue,maneuver]);
  useEffect(()=>()=>{if(lastSpoken.current)window.speechSynthesis.cancel();},[]);
  useEffect(() => {
    if (reportOpen && !roadEdited && !road && currentRoad) setRoad(currentRoad);
  },[reportOpen,roadEdited,road,currentRoad]);
  const eta = navigationEta(selected,state?.simulationTimeSeconds??0);
  const signal = guidance.junction ? state?.traffic?.signals[guidance.junction] : undefined;
  const approach = selected?.edge ?? guidance.current?.id ?? (guidance.junction ? 'station-entry:'+guidance.junction : undefined);
  const signalStatus = signalMessage(signal,approach,selected?.status==='AT_JUNCTION');
  const priority = !state?.priorityEnabled ? 'Priority disabled'
    : mission?.prioritySuspended ? 'Priority suspended' : priorityLabels[mission?.priority??'NONE'];
  const savedReport = reportId ? state?.reports?.[reportId] : undefined;
  const reportFeedback = savedReport?.status==='CONFIRMED'?'Report confirmed'
    : savedReport?.status==='REJECTED'?'Report rejected' : 'Awaiting operator review';

  const openReport = () => {
    setRoad(currentRoad??'');
    setRoadEdited(false);
    setAccepted(false);
    setReportId(undefined);
    setReportOpen(true);
  };
  async function submitReport(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!road || !id || !run.connected || run.pending) return;
    const submittedId = reportId ?? crypto.randomUUID();
    setReportId(submittedId);
    try {
      await run.send('SUBMIT_OBSTRUCTION',{reportId:submittedId,ambulanceId:id,edge:road,closure:true});
      setAccepted(true);
      closeReport();
    } catch {/* The command error stays visible with the form. */}
  }

  return <main className="driver">
    <header className="driver-top">
      <div><h1>Driver Navigation</h1><p>{id??'No ambulance selected'}</p></div>
      <div><span className={run.connected?'connection':'connection offline'}><i aria-hidden="true"/>
        {run.connected?'Connected':state?'Offline · Stale':'Connecting'}</span>
        <a href="/" className="driver-back">Police Control Room</a></div>
    </header>
    {(!runId||!id||state&&!selected) && <p className="driver-alert" role="alert">Open Driver Navigation from a selected ambulance in the Police Control Room.</p>}
    {(loadError||run.error||projection?.error) && <p className="driver-alert" role="alert">{loadError||run.error||projection?.error}</p>}
    <section className="driver-turn" aria-label="Next maneuver">
      <div><span className="eyebrow">Next maneuver</span><h2>{guidance.turn}</h2>
      <p>{nextRoadName??(guidance.next?`${guidance.next.from} → ${guidance.next.to}`:guidance.junction??'Route guidance will appear here')}</p></div>
      {guidance.stepDistance!==undefined&&<strong>{Math.ceil(guidance.stepDistance)} m</strong>}
    </section>
    <div className="driver-layout">
      <section className="driver-map panel">
        <div className="driver-map-toolbar"><span>{follow?'Following ambulance':'Map position unlocked'}</span>
          {voiceAvailable&&<button className="secondary driver-voice" aria-pressed={voice}
            onClick={()=>setVoice(current=>!current)}>Voice {voice?'on':'off'}</button>}
          {!follow&&<button className="secondary" onClick={()=>{setFollow(true);setLocate(n=>n+1);}}>Recenter</button>}
        </div>
        <div className="driver-map-canvas">
          {scenario&&selected?<NetworkMap scenario={scenario} fleet={[selected]} selected={selected} explanation={explanation}
            mode="routing" closures={state?.reportedClosures??[]} signals={state?.traffic?.signals} follow={follow} locate={locate}
            showNavigationControls={false} navigation
            onDrag={()=>setFollow(false)} onEdge={()=>{}} onAmbulance={()=>{}} onJunction={()=>{}}/>
            : <p className="map-empty">Waiting for mission map</p>}
        </div>
      </section>
      <aside className="driver-info">
        <section className="panel driver-card" aria-label="Journey and ETA">
          {state&&!run.connected&&<p className="stale-indicator" role="status">Stale · Last confirmed estimate</p>}
          <h2>{eta.label}</h2>
          <dl className="driver-eta">
            <div><dt>Remaining distance</dt><dd>{guidance.distance===null?'—':`${Math.ceil(guidance.distance)} m`}</dd></div>
            <div><dt>Remaining time</dt><dd>{eta.remaining??'—'}</dd></div>
            <div><dt>Arrival · simulation clock</dt><dd>{eta.arrival??'—'}</dd></div>
          </dl>
          {eta.reason&&<p>{eta.reason}</p>}
          {eta.measured&&<p>Measured journey time <strong>{eta.measured}</strong></p>}
          {selected&&<p>Destination {scenario?.nodeNames?.[selected.destination]??selected.destination}</p>}
        </section>
        <section className="panel driver-card" aria-label="Next junction">
          <h2>Next junction {guidance.junction??''}</h2><p>{signalStatus}</p>
          {currentRoad&&<p>Current road {currentRoad}</p>}
          <strong>{priority}</strong>
          {mission?.priority==='DOWNSTREAM_BLOCKED'&&!mission.prioritySuspended&&<p>Receiving lane is full. Wait for space.</p>}
        </section>
        {selected?.reason&&<p className="driver-alert" role="alert">{stopReason(selected.reason)}</p>}
        {!!selected?.reroutes&&<p className="driver-reroute" role="status">Route updated · Reroutes {selected.reroutes}</p>}
        <section className="panel driver-card" aria-label="Obstruction reports">
          {!reportOpen&&<button ref={reportTrigger} className="primary full" disabled={!selected||!scenario||!run.connected} onClick={openReport}>Report Obstruction</button>}
          {(accepted||savedReport)&&!reportOpen&&<p className="driver-reroute" role="status">{reportFeedback}</p>}
          {reportOpen&&<form onSubmit={event=>void submitReport(event)} onKeyDown={event=>{
            if(event.key==='Escape'&&!run.pending){event.preventDefault();closeReport();}
          }}>
            <h2>Report obstruction</h2>
            <label className="field-label" htmlFor="report-road">Road segment</label>
            <select id="report-road" ref={reportRoad} required value={road} onChange={event=>{setRoad(event.target.value);setRoadEdited(true);setReportId(undefined);}}>
              <option value="">Choose a road</option>
              {scenario?.graph.edges.map(edge=><option value={edge.id} key={edge.id}>{edge.from} → {edge.to}</option>)}
            </select>
            <div className="action-pair">
              <button className="primary" disabled={!road||!run.connected||!!run.pending} type="submit">{run.pending?'Submitting…':'Submit report'}</button>
              <button className="secondary" disabled={!!run.pending} type="button" onClick={closeReport}>Cancel</button>
            </div>
          </form>}
        </section>
      </aside>
    </div>
  </main>;
}
