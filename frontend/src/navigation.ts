import type {Ambulance, Scenario, Signal} from './types';
import {readable} from './controlRoom';

export function duration(seconds:number) {
  const whole = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(whole / 60);
  const s = whole % 60;
  return m ? `${m}m ${s.toString().padStart(2,'0')}s` : `${s}s`;
}
export function arrivalClock(seconds:number) {
  const whole = Math.max(0, Math.ceil(seconds));
  return [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60]
    .map(part => part.toString().padStart(2,'0')).join(':');
}
export function stopReason(reason:string|null|undefined) {
  switch (reason) {
    case 'ALL_OUTGOING_BLOCKED': return 'All exits from this junction are blocked.';
    case 'DESTINATION_UNREACHABLE': return 'No feasible route to the destination.';
    case 'ROAD_IMPASSABLE': return 'The current road is impassable.';
    default: return reason ? readable(reason) : 'Waiting for a route estimate.';
  }
}

export function navigationEta(mission:Ambulance|undefined, tick:number) {
  if (mission?.arrivedAt != null && mission.activatedAt != null) {
    return {label:'Journey completed', measured:duration(mission.arrivedAt-mission.activatedAt)};
  }
  const arrival = mission?.estimatedArrival;
  if (arrival == null || mission?.status === 'STOPPED') {
    return {label:'ETA unavailable', reason:stopReason(mission?.reason)};
  }
  if (arrival <= tick) return {label:'Estimate exceeded', arrival:arrivalClock(arrival)};
  return {label:'Estimated arrival', remaining:duration(arrival-tick), arrival:arrivalClock(arrival)};
}

export function routeGuidance(mission:Ambulance|undefined, scenario:Scenario|undefined, incoming?:string) {
  if (!mission || !scenario) return {turn:'Awaiting mission', distance:null, junction:undefined, current:undefined};
  const byId = new Map(scenario.graph.edges.map(edge=>[edge.id,edge]));
  const position = mission.edge ? byId.get(mission.edge) : undefined;
  const current = position ?? (incoming ? byId.get(incoming) : undefined);
  const next = byId.get(mission.route[position && mission.route[0]===position.id ? 1 : 0]);
  const junction = position?.to ?? mission.node;
  const distance = mission.arrivedAt!==null ? 0 : mission.status==='STOPPED'||!mission.route.length ? null
    : Math.max(0,mission.route.reduce((sum,id)=>sum+(byId.get(id)?.length??0),0)-mission.progress);
  const stepDistance = position ? Math.max(0,position.length-mission.progress) : 0;
  if (mission.arrivedAt!==null) return {turn:'Destination reached',distance,junction,current};
  if (mission.status==='STOPPED') return {turn:'Stop safely',distance,junction,current};
  if (!next) return {turn:position?'Continue to destination':'Awaiting route',distance,junction,current,stepDistance};
  const node = new Map(scenario.graph.nodes.map(point=>[point.id,point]));
  const from = current && node.get(current.from);
  const pivot = node.get(next.from);
  const to = node.get(next.to);
  let turn = 'Continue';
  if (from && pivot && to) {
    const a = [pivot.x-from.x,pivot.y-from.y];
    const b = [to.x-pivot.x,to.y-pivot.y];
    const angle = Math.atan2(a[0]*b[1]-a[1]*b[0],a[0]*b[0]+a[1]*b[1]);
    turn = Math.abs(angle)>2.5 ? 'Make a U-turn' : angle>0.35 ? 'Turn right' : angle< -0.35 ? 'Turn left' : 'Continue straight';
  }
  return {turn,distance,junction,current,stepDistance,next};
}

export function signalMessage(signal:Signal|undefined, approach:string|undefined, waiting:boolean) {
  if (!signal || !approach || !signal.approaches.includes(approach)) return 'Signal information unavailable';
  if (signal.permissions[signal.approaches.indexOf(approach)]===1) return 'Green for your approach';
  if (waiting && signal.phase!=='AMBER') return 'Waiting at red light';
  return signal.phase==='AMBER' ? 'Signal clearance' : 'Red for your approach';
}
