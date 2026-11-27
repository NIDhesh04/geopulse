import {useEffect,useRef,useState} from 'react';
import {Client} from '@stomp/stompjs';
import {api} from './api';
import {mergeEvents,newerSnapshot} from './state';
import type {Snapshot,RunEvent} from './types';
export function useRun(initialRunId?:string|null){
 const [runId,setRunId]=useState<string|null>(()=>initialRunId===undefined?localStorage.getItem('geopulse.run'):initialRunId);
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[events,setEvents]=useState<RunEvent[]>([]);
 const [connected,setConnected]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState('');
 const idRef=useRef(runId);idRef.current=runId;
 useEffect(()=>{
  setSnapshot(null);setEvents([]);setConnected(false);if(!runId)return;
  let alive=true,cursor='0',fetching=false,lastSeen=0;
  const catchUp=async()=>{if(fetching)return;fetching=true;try{while(alive){const rows=await api<RunEvent[]>(`/runs/${runId}/events?after=${cursor}`);if(!alive)return;setEvents(old=>mergeEvents(old,rows));if(rows.length)cursor=rows[rows.length-1].sequence;if(rows.length<200)break;}}catch(e){if(alive)setError(String(e));}finally{fetching=false;}};
  const receive=(next:Snapshot)=>{if(!alive||!navigator.onLine)return;lastSeen=Date.now();setConnected(true);setSnapshot(old=>newerSnapshot(old,next,runId));if(BigInt(next.latestEventSequence)>BigInt(cursor))void catchUp();};
  const fetchSnapshot=()=>api<Snapshot>(`/runs/${runId}/snapshot`).then(receive).catch(e=>{if(alive){setError(String(e));setConnected(false);}});
  const client=new Client({brokerURL:`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`,reconnectDelay:2000,
   onConnect:()=>{
    client.subscribe(`/topic/runs/${runId}/state`,m=>receive(JSON.parse(m.body)));
    client.subscribe(`/topic/runs/${runId}/events`,m=>{if(alive){setEvents(old=>mergeEvents(old,[JSON.parse(m.body)]));void catchUp();}});
    void fetchSnapshot();void catchUp();
   },onWebSocketClose:()=>{if(alive)setConnected(false);},onStompError:()=>{if(alive)setConnected(false);}
  });
  client.activate();void fetchSnapshot();
  const disconnected=()=>setConnected(false);
  window.addEventListener('offline',disconnected);
  const timer=setInterval(()=>{if(Date.now()-lastSeen>5000)setConnected(false);},500);
  return()=>{alive=false;clearInterval(timer);window.removeEventListener('offline',disconnected);void client.deactivate();};
 },[runId]);
 async function send(type:string,payload:Record<string,unknown>={},handoffAction?:string){
  if(!runId)throw new Error('Create a run first');const target=runId;setPending(type);setError('');
  try{
   const commandId=crypto.randomUUID();
   const endpoint=handoffAction?`/test-integrations/emergency108/runs/${target}/handoffs/${handoffAction}`:`/runs/${target}/commands`;
   let result=await api<{status:string;reason?:string}>(endpoint,handoffAction?{commandId}:{commandId,type,payload});
   for(let count=0;result.status==='ACCEPTED'&&count<100;count++){await new Promise(r=>setTimeout(r,100));result=await api(`/runs/${target}/commands/${commandId}`);}
   if(result.status==='ACCEPTED')throw new Error('Command remains pending; reconnect to inspect its outcome');
   if(result.status==='REJECTED')throw new Error(result.reason??'Command rejected');
   // An applied command remains successful if the follow-up refresh loses its connection.
   try {
    const next=await api<Snapshot>(`/runs/${target}/snapshot`);if(idRef.current===target)setSnapshot(old=>newerSnapshot(old,next,target));
   } catch {
    if(idRef.current===target)setConnected(false);
   }
  }catch(e){setError(String(e));throw e;}finally{setPending('');}
 }
 async function create(horizon:string,scenarioId:string,priorityEnabled:boolean){setError('');try{if(snapshot&&!snapshot.paused)await send('PAUSE');const next=await api<Snapshot>('/runs',{horizon,seed:108,scenarioId,priorityEnabled});localStorage.setItem('geopulse.run',next.runId);setRunId(next.runId);}catch(e){setError(String(e));}}
 return{snapshot,events,connected,error,pending,send,create};
}
