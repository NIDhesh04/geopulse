import type {Snapshot,RunEvent} from './types';
export function newerSnapshot(current:Snapshot|null,next:Snapshot,runId:string):Snapshot|null {
 if(next.runId!==runId)return current;
 if(current&&current.runId===runId&&BigInt(next.stateRevision)<=BigInt(current.stateRevision))return current;
 return next;
}
export function mergeEvents(current:RunEvent[],incoming:RunEvent[]):RunEvent[]{
 const events=new Map(current.map(e=>[e.sequence,e]));for(const e of incoming)events.set(e.sequence,e);
 return [...events.values()].sort((a,b)=>BigInt(a.sequence)<BigInt(b.sequence)?-1:1);
}
