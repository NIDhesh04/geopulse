import {useEffect,useState} from 'react';
import {api} from './api';
import {NetworkMap} from './NetworkMap';
import type {Scenario} from './types';
import {useRun} from './useRun';

const descriptions:Record<string,{label:string;description:string;incidents:string}> = {
  ROUTING_ONLY:{label:'Routing only',description:'Compare live and historical routing on an empty network.',incidents:'On-demand road closures'},
  TRAFFIC_SIGNALS:{label:'Traffic and signals',description:'Follow one ambulance through civilian queues and signal priority.',incidents:'On-demand closures, slowdowns, and demand changes'},
  FLEET_TRAFFIC:{label:'Ten ambulance conflict',description:'Coordinate ten ambulances competing for signal priority.',incidents:'Hidden incidents and operator-reviewed reports'},
  PREDICTABLE_CONGESTION:{label:'Predictable corridor congestion',description:'Use historical travel times to anticipate a demand surge beyond the live window.',incidents:'Scheduled civilian demand surge'},
};

export function Landing() {
  const run = useRun();
  const [scenarios,setScenarios] = useState<Scenario[]>([]);
  const [choice,setChoice] = useState('');
  const [error,setError] = useState('');
  useEffect(()=>{
    let active = true;
    api<Scenario[]>('/scenarios').then(items=>{
      if(!active)return;
      setScenarios(items);
      setChoice(items.find(item=>item.mode==='FLEET_TRAFFIC')?.id??items[0]?.id??'');
    }).catch(failure=>{if(active)setError(String(failure));});
    return ()=>{active=false;};
  },[]);
  const state = run.snapshot;
  const scenario = scenarios.find(item=>item.id===choice);
  const matching = state?.scenarioId===choice ? state : null;
  const fleet = matching?.fleet??(matching?[matching.ambulance]:[]);
  const driver = state?.fleet?.find(vehicle=>vehicle.activatedAt!==null)??state?.ambulance;
  const driverHref = state && driver ? `/driver?run=${encodeURIComponent(state.runId)}&ambulance=${encodeURIComponent(driver.id)}` : undefined;
  return <main className="landing">
    <header className="topbar"><a className="brand" href="/welcome"><span className="brand-mark" aria-hidden="true">G</span>GeoPulse</a></header>
    <div className="landing-body">
      <section className="landing-intro">
        <div>
          <h1>Simulate ambulance routing and signal priority</h1>
          <p>Choose a synthetic network to explore traffic queues, route changes, and obstruction review from the control room or the driver’s seat.</p>
          <div className="landing-actions">
            <a className="primary landing-link" href={choice?`/?scenario=${encodeURIComponent(choice)}&setup=1`:'/'}>Open Police Control Room</a>
            {driverHref&&<a className="secondary landing-link" href={driverHref}>Open Driver Navigation</a>}
          </div>
          {!driverHref&&<p>Driver Navigation is available once you create a run.</p>}
        </div>
        <figure className="panel landing-preview">
          <figcaption>{matching?(run.connected?'Live simulation preview':'Last confirmed simulation preview'):'Scenario network preview'}</figcaption>
          <div>{scenario&&<NetworkMap scenario={scenario} fleet={fleet} mode="operational" closures={matching?.reportedClosures??[]}
            signals={matching?.traffic?.signals} showNavigationControls={false} follow={false} locate={0}
            onDrag={()=>{}} onEdge={()=>{}} onAmbulance={()=>{}} onJunction={()=>{}}/>}</div>
        </figure>
      </section>
      <fieldset className="landing-scenarios">
        <legend>Choose a scenario</legend>
        {scenarios.map(item=>{
          const details=descriptions[item.mode];
          return <label className="panel scenario-option" key={item.id}>
            <span><input type="radio" name="landing-scenario" value={item.id} checked={choice===item.id}
              onChange={()=>setChoice(item.id)}/> <strong>{details?.label??item.name}</strong></span>
            <span className="mode-tag">Synthetic scenario</span>
            <span>{details?.description??item.name}</span>
            <span className="scenario-meta">{item.graph.nodes.length} junctions · {item.graph.edges.length} roads · {Object.keys(item.departureByAmbulance??{}).length||1} ambulance{item.departureByAmbulance?'s':''}</span>
            {details&&<span className="scenario-meta">{details.incidents}</span>}
          </label>;
        })}
        {error&&<p role="alert">{error}</p>}
        {!scenarios.length&&!error&&<p>Loading scenarios…</p>}
      </fieldset>
    </div>
  </main>;
}
