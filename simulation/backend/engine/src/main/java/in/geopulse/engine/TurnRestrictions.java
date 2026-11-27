package in.geopulse.engine;

import java.util.*;

/** Static rules on directed edge sequences. A movement may depend on the approach to a via road. */
public record TurnRestrictions(List<List<String>> forbidden, List<Only> only) {
    public static final TurnRestrictions NONE = new TurnRestrictions(List.of(),List.of());

    public record Only(List<String> after, List<String> allowed) {
        public Only {
            after=List.copyOf(after);
            allowed=List.copyOf(allowed);
            if(after.isEmpty())throw new IllegalArgumentException("Invalid required turn");
        }
    }

    public TurnRestrictions {
        forbidden=forbidden.stream().map(List::copyOf).toList();
        only=List.copyOf(only);
        if(forbidden.stream().anyMatch(path->path.size()<2))throw new IllegalArgumentException("Invalid forbidden turn");
    }

    void validate(Map<String,Graph.Edge> roads) {
        forbidden.forEach(path->validatePath(path,roads));
        for (var rule : only) {
            validatePath(rule.after(),roads);
            for (String edge : rule.allowed()) validatePath(append(rule.after(),edge),roads);
        }
    }

    private static void validatePath(List<String> path,Map<String,Graph.Edge> roads) {
        Graph.Edge previous=null;
        for (String id : path) {
            var edge=roads.get(id);
            if(edge==null||previous!=null&&!previous.to().equals(edge.from()))
                throw new IllegalArgumentException("Turn restriction must reference contiguous roads: "+path);
            previous=edge;
        }
    }

    public boolean empty() { return forbidden.isEmpty()&&only.isEmpty(); }

    boolean permits(List<String> context,String outgoing) {
        if(empty()||context.isEmpty())return true;
        for(var rule:only) {
            if(endsWith(context,rule.after())&&!rule.allowed().contains(outgoing))return false;
        }
        for(var path:forbidden) {
            int last=path.size()-1;
            if(outgoing.equals(path.get(last))&&endsWith(context,path.subList(0,last)))return false;
        }
        return true;
    }

    List<String> advance(List<String> context,String road) {
        if(empty())return List.of();
        var traversed=append(context,road);
        for(int length=traversed.size();length>0;length--) {
            var suffix=traversed.subList(traversed.size()-length,traversed.size());
            if(forbidden.stream().anyMatch(path->path.size()>suffix.size() && startsWith(path,suffix))
                    || only.stream().anyMatch(rule->startsWith(rule.after(),suffix)))
                return List.copyOf(suffix);
        }
        return List.of();
    }

    private static List<String> append(List<String> path,String road) {
        var joined=new ArrayList<>(path);
        joined.add(road);
        return joined;
    }

    private static boolean endsWith(List<String> path,List<String> suffix) {
        return path.size()>=suffix.size()&&path.subList(path.size()-suffix.size(),path.size()).equals(suffix);
    }

    private static boolean startsWith(List<String> path,List<String> prefix) {
        return path.size()>=prefix.size()&&path.subList(0,prefix.size()).equals(prefix);
    }
}
