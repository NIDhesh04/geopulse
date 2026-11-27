import type {Coordinate, Node, Scenario} from './types';

export function mapCoordinate(node:Node):Coordinate {
  return node.lat!=null&&node.lng!=null?[node.lng,node.lat]:[75.78+node.x/100000,26.92-node.y/100000];
}

export function roadGeometry(scenario:Scenario) {
  const points=new Map(scenario.graph.nodes.map(node=>[node.id,mapCoordinate(node)]));
  return new Map(scenario.graph.edges.map(edge=>[
    edge.id, scenario.edgeGeometry?.[edge.id]??[points.get(edge.from)!,points.get(edge.to)!],
  ]));
}

function segments(line:Coordinate[]) {
  return line.slice(1).map((point,index)=>{
    const prev=line[index];
    const scale=Math.cos((point[1]+prev[1])*Math.PI/360);
    return Math.hypot((point[0]-prev[0])*scale,point[1]-prev[1]);
  });
}

export function sampleRoad(line:Coordinate[], share:number):Coordinate {
  const lengths=segments(line);
  let remaining=lengths.reduce((total,length)=>total+length,0)*Math.max(0,Math.min(1,share));
  for (const [index,length] of lengths.entries()) {
    if (remaining<=length) {
      const [a,b]=[line[index],line[index+1]];
      const mix=length?remaining/length:0;
      return [a[0]+(b[0]-a[0])*mix,a[1]+(b[1]-a[1])*mix];
    }
    remaining-=length;
  }
  return line[line.length-1];
}

export function queuedRoad(line:Coordinate[], share:number):Coordinate[] {
  const lengths=segments(line);
  let remaining=lengths.reduce((total,length)=>total+length,0)*Math.min(1,share);
  let boundary=lengths.length-1;
  while(boundary>0&&remaining>lengths[boundary]) remaining-=lengths[boundary--];
  return [sampleRoad(line,1-share),...line.slice(boundary+1)];
}
