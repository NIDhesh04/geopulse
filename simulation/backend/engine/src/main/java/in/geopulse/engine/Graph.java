package in.geopulse.engine;
import java.util.*;
public record Graph(List<Node> nodes, List<Edge> edges, TurnRestrictions turnRestrictions) {
    public Graph(List<Node> nodes,List<Edge> edges) { this(nodes,edges,TurnRestrictions.NONE); }
    public record Node(String id,double x,double y,Double lat,Double lng) {
        public Node(String id,double x,double y){this(id,x,y,null,null);}
        public Node {if(id==null||id.isBlank()||!Double.isFinite(x)||!Double.isFinite(y))throw new IllegalArgumentException("Invalid junction");
            if((lat==null)!=(lng==null)||lat!=null&&(!Double.isFinite(lat)||!Double.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180))throw new IllegalArgumentException("Invalid geographic coordinates");}
    }
    public record Edge(String id,String from,String to,double length,double freeSpeed) {
        public Edge { if(id==null||from==null||to==null||!Double.isFinite(length)||length<=0||!Double.isFinite(freeSpeed)||freeSpeed<=0) throw new IllegalArgumentException("Invalid road"); }
    }
    public Graph {
        nodes=nodes.stream().sorted(Comparator.comparing(Node::id)).toList();
        edges=edges.stream().sorted(Comparator.comparing(Edge::id)).toList();
        Set<String> ids=new HashSet<>();for(Node n:nodes)if(!ids.add(n.id()))throw new IllegalArgumentException("Duplicate node");
        Map<String,Edge> byId=new HashMap<>();
        for(Edge e:edges)if(byId.put(e.id(),e)!=null||!ids.contains(e.from())||!ids.contains(e.to()))throw new IllegalArgumentException("Invalid graph edge");
        turnRestrictions=turnRestrictions==null?TurnRestrictions.NONE:turnRestrictions;
        turnRestrictions.validate(byId);
    }
    public Node node(String id){return nodes.stream().filter(n->n.id().equals(id)).findFirst().orElseThrow(()->new IllegalArgumentException("Unknown junction: "+id));}
    public Edge edge(String id){return edges.stream().filter(e->e.id().equals(id)).findFirst().orElseThrow(()->new IllegalArgumentException("Unknown road: "+id));}
    public List<Edge> outgoing(String node){return edges.stream().filter(e->e.from().equals(node)).toList();}
    public static Graph grid(int size){
        if(size<2||size>20)throw new IllegalArgumentException("Grid size must be 2..20");
        List<Node> ns=new ArrayList<>();List<Edge> es=new ArrayList<>();
        for(int row=0;row<size;row++)for(int col=0;col<size;col++)ns.add(new Node(id(row,col),col*100,row*100));
        for(int row=0;row<size;row++)for(int col=0;col<size;col++)for(int[] d:new int[][]{{0,1},{1,0},{0,-1},{-1,0}}){
            int rr=row+d[0],cc=col+d[1];if(rr>=0&&rr<size&&cc>=0&&cc<size){String a=id(row,col),b=id(rr,cc);es.add(new Edge(a+"_"+b,a,b,100,10));}
        }return new Graph(ns,es);
    }
    private static String id(int r,int c){return "n%02d_%02d".formatted(r,c);}
}
