export type Node = {id:string;x:number;y:number;lat?:number|null;lng?:number|null};
export type Edge = {id:string;from:string;to:string;length:number;freeSpeed:number};
export type Scenario = {id:string;name:string;graph:{nodes:Node[];edges:Edge[]};origin:string;destination:string};
export type Estimate = {status:string;seconds:number|null;source:string;reason:string|null};
export type Candidate = {edge:string;road:Estimate;junction:Estimate;pathSeconds:number|null;outcome:string;reason:string|null};
export type Snapshot = {
 runId:string;stateRevision:string;latestEventSequence:string;simulationTimeSeconds:number;paused:boolean;speed:number;horizon:string;runStatus:string;
 ambulance:{id:string;status:string;node:string;edge:string|null;progress:number;destination:string;route:string[];activatedAt:number|null;arrivedAt:number|null;replans:number;reroutes:number;reason:string|null;initialEta:number|null;estimatedArrival:number|null};
 explanation:{routingRevision:string;time:number;incoming:string;candidates:Candidate[];liveEdges:string[];roads:Record<string,Estimate>}|null;
 reportedClosures:string[];
};
export type RunEvent={sequence:string;time:number;type:string;data:{message:string;commandId?:string}};
