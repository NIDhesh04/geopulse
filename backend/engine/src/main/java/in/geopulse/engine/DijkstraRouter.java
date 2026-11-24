package in.geopulse.engine;
import java.util.*;
public final class DijkstraRouter implements RoutingPolicy {
    private record State(String node,String incoming){}
    private record Entry(State state,double cost,List<String> path){}
    @Override
    public Route route(Graph g,String start,String incoming,String destination,RoutingSnapshot snapshot){
        return route(g,start,incoming,destination,snapshot,0);
    }
    private Route route(Graph g,String start,String incoming,String destination,RoutingSnapshot snapshot,double offset){
        g.node(start);g.node(destination);
        Comparator<Entry> order=Comparator.comparingDouble(Entry::cost).thenComparing(e->e.state().node()).thenComparing(e->e.state().incoming());
        PriorityQueue<Entry> queue=new PriorityQueue<>(order);Map<State,Double> best=new HashMap<>();
        State initial=new State(start,incoming);best.put(initial,offset);queue.add(new Entry(initial,offset,List.of()));
        while(!queue.isEmpty()){
            Entry cur=queue.remove();if(cur.cost()>best.get(cur.state()))continue;
            if(cur.state().node().equals(destination))return new Route(true,cur.path(),cur.cost());
            for(var edge:g.outgoing(cur.state().node())){
                double projected=snapshot.time()+cur.cost();
                Estimate road=snapshot.road(edge.id(),projected);if(!road.usable())continue;
                Estimate wait=snapshot.junction(cur.state().incoming(),edge.id(),projected);if(!wait.usable())continue;
                double cost=cur.cost()+road.seconds()+wait.seconds();if(!Double.isFinite(cost))continue;
                State next=new State(edge.to(),edge.id());
                if(cost<best.getOrDefault(next,Double.POSITIVE_INFINITY)){
                    best.put(next,cost);List<String> path=new ArrayList<>(cur.path());path.add(edge.id());queue.add(new Entry(next,cost,List.copyOf(path)));
                }
            }
        }return new Route(false,List.of(),null);
    }
    @Override
    public List<Candidate> explain(Graph g,String start,String incoming,String destination,RoutingSnapshot snapshot,Route selected){
        List<Candidate> out=new ArrayList<>();
        for(var e:g.outgoing(start)){
            Estimate road=snapshot.road(e.id(),snapshot.time());Estimate wait=road.usable()?snapshot.junction(incoming,e.id(),snapshot.time()):Estimate.unknown("Road unavailable");
            Double total=null;String reason=road.reason();String outcome=road.status();
            if(road.usable()&&wait.usable()){
                var tail=route(g,e.to(),e.id(),destination,snapshot,road.seconds()+wait.seconds());
                if(tail.reachable()){total=tail.seconds();outcome=!selected.edges().isEmpty()&&selected.edges().getFirst().equals(e.id())?"SELECTED":"ALTERNATIVE";reason=null;}
                else{outcome="UNREACHABLE";reason="No complete path from this movement";}
            }else if(road.usable()){outcome=wait.status();reason=wait.reason();}
            out.add(new Candidate(e.id(),road,wait,total,outcome,reason));
        }return List.copyOf(out);
    }
}
