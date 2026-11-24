package in.geopulse.engine;
public record Estimate(String status,Double seconds,String source,String reason) {
    public Estimate {
        if(!java.util.Set.of("AVAILABLE","BLOCKED","UNKNOWN").contains(status))throw new IllegalArgumentException("Unknown estimate status");
        if(status.equals("AVAILABLE")&&(seconds==null||!Double.isFinite(seconds)||seconds<0)){status="UNKNOWN";seconds=null;reason="Invalid travel-time estimate";}
        if(!status.equals("AVAILABLE"))seconds=null;
    }
    public static Estimate available(double seconds,String source){return new Estimate("AVAILABLE",seconds,source,null);}
    public static Estimate blocked(String reason){return new Estimate("BLOCKED",null,"KNOWN",reason);}
    public static Estimate unknown(String reason){return new Estimate("UNKNOWN",null,"UNKNOWN",reason);}
    public boolean usable(){return status.equals("AVAILABLE");}
}
