package in.geopulse.engine;
import java.util.*;
public final class DijkstraRouter implements RoutingPolicy {
    private record State(String node,String incoming,List<String> turnContext){}
    private record Entry(State state,double cost,List<String> path){}
    @Override
    public Route route(Graph g,String start,String incoming,String destination,RoutingSnapshot snapshot){
        return route(g,new State(start,incoming,snapshot.turnContext(incoming)),destination,snapshot,0);
    }
    private Route route(Graph g,State initial,String destination,RoutingSnapshot snapshot,double offset){
        g.node(initial.node());g.node(destination);
        Comparator<Entry> order=Comparator.comparingDouble(Entry::cost).thenComparing(e->e.state().node())
                .thenComparing(e->e.state().incoming()).thenComparing(e->String.join("\n",e.state().turnContext()));
        PriorityQueue<Entry> queue=new PriorityQueue<>(order);Map<State,Double> best=new HashMap<>();
        best.put(initial,offset);queue.add(new Entry(initial,offset,List.of()));
        while(!queue.isEmpty()){
            Entry cur=queue.remove();if(cur.cost()>best.get(cur.state()))continue;
            if(cur.state().node().equals(destination))return new Route(true,cur.path(),cur.cost());
            for(var edge:g.outgoing(cur.state().node())){
                if(!g.turnRestrictions().permits(cur.state().turnContext(),edge.id())) continue;
                double projected=snapshot.time()+cur.cost();
                Estimate road=snapshot.road(edge.id(),projected);if(!road.usable())continue;
                Estimate wait=snapshot.junction(cur.state().incoming(),edge.id(),projected);if(!wait.usable())continue;
                double cost=cur.cost()+road.seconds()+wait.seconds();if(!Double.isFinite(cost))continue;
                State next=new State(edge.to(),edge.id(),g.turnRestrictions().advance(cur.state().turnContext(),edge.id()));
                if(cost<best.getOrDefault(next,Double.POSITIVE_INFINITY)){
                    best.put(next,cost);List<String> path=new ArrayList<>(cur.path());path.add(edge.id());queue.add(new Entry(next,cost,List.copyOf(path)));
                }
            }
        }return new Route(false,List.of(),null);
    }
    @Override
    public List<Candidate> explain(Graph g,String start,String incoming,String destination,RoutingSnapshot snapshot,Route selected){
        List<Candidate> out=new ArrayList<>();
        var turnContext=snapshot.turnContext(incoming);
        for(var e:g.outgoing(start)){
            Estimate road=snapshot.road(e.id(),snapshot.time());
            if(!g.turnRestrictions().permits(turnContext,e.id())) {
                String reason="Turn prohibited by imported road rules";
                out.add(new Candidate(e.id(),road,Estimate.unknown(reason),null,"TURN_RESTRICTED",reason));
                continue;
            }
            Estimate wait=road.usable()?snapshot.junction(incoming,e.id(),snapshot.time()):Estimate.unknown("Road unavailable");
            Double total=null;String reason=road.reason();String outcome=road.status();
            if(road.usable()&&wait.usable()){
                var downstream=new State(e.to(),e.id(),g.turnRestrictions().advance(turnContext,e.id()));
                var tail=route(g,downstream,destination,snapshot,road.seconds()+wait.seconds());
                if(tail.reachable()){total=tail.seconds();outcome=!selected.edges().isEmpty()&&selected.edges().getFirst().equals(e.id())?"SELECTED":"ALTERNATIVE";reason=null;}
                else{outcome="UNREACHABLE";reason="No complete path from this movement";}
            }else if(road.usable()){outcome=wait.status();reason=wait.reason();}
            out.add(new Candidate(e.id(),road,wait,total,outcome,reason));
        }return List.copyOf(out);
    }
}
