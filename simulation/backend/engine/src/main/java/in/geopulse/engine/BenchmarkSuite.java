package in.geopulse.engine;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

/** Fixed-step evaluation entry point. This class needs no application or database. */
public final class BenchmarkSuite {
    static final int WARMUP = 600;
    static final int EVALUATION_END = WARMUP + 1800;
    static final int END = EVALUATION_END + 600;
    private static final int RECOVERY_SECONDS = 60;

    enum Fixture {
        ORDINARY(5, 1), PREDICTABLE(5, 1), LOCAL_OBSTRUCTION(5, 1), DISTANT_OBSTRUCTION(5, 1),
        RECEIVING_BLOCKED(5, 1), CONFLICT(8, 10), DISCONNECTED(5, 1), SCALE(10, 30);

        final int size;
        final int ambulanceCount;
        Fixture(int size, int ambulanceCount) { this.size = size; this.ambulanceCount = ambulanceCount; }

        Map<String,String> stations() {
            var stations = new TreeMap<String,String>();
            for (int i = 0; i < ambulanceCount; i++) {
                stations.put("AMB-%03d".formatted(i + 1), switch (i % 3) {
                    case 1 -> "n00_04";
                    case 2 -> "n04_00";
                    default -> "n00_00";
                });
            }
            return Collections.unmodifiableMap(stations);
        }
    }

    record Mission(int tick, String id, String origin, String destination) {}
    record Change(int tick, String road, String effect, String id, boolean report) {}
    record Schedule(List<Mission> missions, List<Change> changes) {}
    record Policy(int horizon, boolean priority, boolean reference) {}
    record GrantKey(String ambulance, JunctionService.Movement movement, long revision, long requestedAt) {
        GrantKey(JunctionService.Request request) {
            this(request.ambulanceId(), request.movement(), request.routeRevision(), request.requestedAt());
        }
    }
    record Delay(double boundary, double junction, double running) {
        static Delay between(TrafficWorld.Totals from, TrafficWorld.Totals to) {
            return new Delay(to.boundaryWaiting()-from.boundaryWaiting(), to.junctionWaiting()-from.junctionWaiting(),
                    to.runningExcess()-from.runningExcess());
        }
        double total() { return boundary+junction+running; }
    }
    record Outcome(String id, String status, Long actual, Double etaError, long replans, long reroutes,
                   long signalWait, long receivingWait, long impassableWait, long routeWait,
                   long requests, long grants, long unsuccessfulGrants) {}
    record Result(Policy policy, Delay evaluation, Delay followup, TrafficWorld.Totals start,
                  TrafficWorld.Totals end, List<Outcome> missions, double peakQueue, long fullRoadSeconds,
                  long forecasts, long elapsedNanos, double[] queues, double[] backlogs, int lastGrantEnd) {}

    private static final class MissionCounters {
        final Map<String, Long> waits = new HashMap<>();
        final Set<GrantKey> requests = new HashSet<>();
        long grants;
        long unsuccessful;
        boolean rejected;
    }

    static Schedule schedule(Fixture fixture, long seed) {
        var random = new SplittableRandom(seed);
        int tick = 680 + random.nextInt(10);
        var stations = fixture.stations();
        String destination = fixture.ambulanceCount > 1 ? "n04_04" : "n00_04";
        var missions = stations.entrySet().stream().map(station -> new Mission(tick + random.nextInt(4),
                station.getKey(), station.getValue(), destination)).sorted(Comparator.comparingInt(Mission::tick)
                .thenComparing(Mission::id)).toList();
        var changes = new ArrayList<Change>();
        switch (fixture) {
            case LOCAL_OBSTRUCTION -> incident(changes, tick - 5, tick + 90, "n00_00_n00_01", "ENTRY_CLOSED");
            case DISTANT_OBSTRUCTION -> {
                var road = CalibrationRunner.CORRIDOR;
                incident(changes, tick - 5, tick + 120, road, "ENTRY_CLOSED");
                changes.add(new Change(tick+55, road, "ENTRY_CLOSED", "scheduled", true));
                changes.add(new Change(tick+120, road, "OPEN", "scheduled", true));
            }
            case RECEIVING_BLOCKED -> {
                var road = "n00_00_n00_01";
                incident(changes, WARMUP, tick+90, road, "SLOW");
                changes.add(new Change(WARMUP, road, "DEMAND_SURGE", "demand", false));
                changes.add(new Change(tick+90, road, "OPEN", "demand", false));
            }
            case DISCONNECTED -> {
                incident(changes,tick - 5,tick + 65,"n00_00_n00_01","ENTRY_CLOSED");
                incident(changes,tick - 5,tick + 65,"n00_00_n01_00","ENTRY_CLOSED");
            }
        }
        changes.sort(Comparator.comparingInt(Change::tick));
        return new Schedule(missions,List.copyOf(changes));
    }

    private static void incident(List<Change> changes,int start,int end,String road,String effect) {
        changes.add(new Change(start,road,effect,"scheduled",false));
        changes.add(new Change(end,road,"OPEN","scheduled",false));
    }

    static RoutingSimulation warmed(Fixture fixture, long seed, HistoricalProfile profile) {
        var world = RoutingSimulation.benchmark(Graph.grid(fixture.size),fixture.stations(),seed,
                fixture == Fixture.PREDICTABLE,profile);
        for (int tick=0;tick<WARMUP;tick++) world.step();
        return world;
    }

    static Result evaluate(RoutingSimulation warmed, Schedule schedule, Policy policy) {
        var world = warmed.forkPolicy(policy.horizon,policy.priority);
        var start = world.benchmarkTotals();
        var evaluationEnd = start;
        var counters = new TreeMap<String,MissionCounters>();
        if (!policy.reference) schedule.missions().forEach(mission -> counters.put(mission.id(),new MissionCounters()));
        var queues = new double[END-WARMUP+1];
        var backlogs = new double[queues.length];
        queues[0]=start.queued();
        backlogs[0]=start.boundaryBacklog();
        var active = new TreeMap<String,JunctionService.State>();
        int missionIndex=0, changeIndex=0, lastGrantEnd=-1;
        long fullRoadSeconds=0;
        double peakQueue=start.queued();
        long started=System.nanoTime();
        for (int tick=WARMUP;tick<END;tick++) {
            while (changeIndex<schedule.changes().size() && schedule.changes().get(changeIndex).tick()==tick) {
                var change=schedule.changes().get(changeIndex++);
                world.incident(change.road(),change.effect(),change.report(),change.id());
            }
            while (!policy.reference && missionIndex<schedule.missions().size() && schedule.missions().get(missionIndex).tick()==tick) {
                var mission=schedule.missions().get(missionIndex++);
                try {
                    world.activate(mission.id(),mission.origin(),mission.destination());
                } catch (IllegalArgumentException rejected) {
                    counters.get(mission.id()).rejected=true;
                }
            }
            counters.forEach((id, counter) -> {
                var kind=world.benchmarkWaiting(id);
                if (kind!=null) counter.waits.merge(kind,1L,Long::sum);
            });
            fullRoadSeconds+=world.benchmarkFullRoads();
            world.step();
            world.drainEvents();
            world.benchmarkRequests().forEach(request -> counters.get(request.ambulanceId()).requests.add(new GrantKey(request)));
            var grants=world.benchmarkGrants();
            for (var entry : grants.entrySet()) {
                if (!sameGrant(active.get(entry.getKey()),entry.getValue()))
                    counters.get(entry.getValue().grant().ambulanceId()).grants++;
            }
            for (var entry : active.entrySet()) {
                var previous=entry.getValue();
                if (sameGrant(previous,grants.get(entry.getKey()))) continue;
                lastGrantEnd=tick+1;
                if (!previous.grantPassed()) counters.get(previous.grant().ambulanceId()).unsuccessful++;
            }
            active.clear();
            active.putAll(grants);
            var totals=world.benchmarkTotals();
            queues[tick+1-WARMUP]=totals.queued();
            backlogs[tick+1-WARMUP]=totals.boundaryBacklog();
            peakQueue=Math.max(peakQueue,totals.queued());
            if (tick+1==EVALUATION_END) evaluationEnd=totals;
        }
        if (!active.isEmpty()) lastGrantEnd=-1;
        var end=world.benchmarkTotals();
        var missions=world.benchmarkFleet().stream().filter(a -> counters.containsKey(a.id()))
                .map(a -> outcome(a,counters.get(a.id()))).toList();
        return new Result(policy,Delay.between(start,evaluationEnd),Delay.between(evaluationEnd,end),start,end,
                missions,peakQueue,fullRoadSeconds,world.benchmarkForecastCount(),System.nanoTime()-started,
                queues,backlogs,lastGrantEnd);
    }

    private static boolean sameGrant(JunctionService.State first,JunctionService.State second) {
        return first!=null && second!=null && new GrantKey(first.grant()).equals(new GrantKey(second.grant()));
    }

    private static Outcome outcome(RoutingSimulation.Ambulance a, MissionCounters c) {
        Long actual=a.arrivedAt()==null?null:a.arrivedAt()-a.activatedAt();
        Double error=actual==null||a.initialEta()==null?null:a.initialEta()-actual;
        String status=c.rejected?"REJECTED":actual==null?"UNFINISHED":a.arrivedAt()<=EVALUATION_END?"ON_TIME":"LATE";
        return new Outcome(a.id(),status,actual,error,a.replans(),a.reroutes(),c.waits.getOrDefault("signal",0L),
                c.waits.getOrDefault("queue_or_receiving",0L),c.waits.getOrDefault("impassable",0L),
                c.waits.getOrDefault("route_unavailable",0L),c.requests.size(),c.grants,c.unsuccessful);
    }

    static int recovery(double[] enabled, double[] disabled, int grantEnd) {
        if (grantEnd < WARMUP) return -1;
        int streak = 0;
        for (int i=grantEnd-WARMUP;i<enabled.length;i++) {
            double tolerance=Math.max(1,.05*disabled[i]);
            streak=Math.abs(enabled[i]-disabled[i])<=tolerance?streak+1:0;
            if (streak==RECOVERY_SECONDS) return i-RECOVERY_SECONDS+1-(grantEnd-WARMUP);
        }
        return -1;
    }

    private static String hash(Object value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.toString().getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void row(PrintWriter out,Object... values) {
        out.println(String.join("\t",Arrays.stream(values).map(value -> value==null?"":value.toString()).toList()));
    }

    private static void write(PrintWriter out,Fixture fixture,long seed,String scheduleId,Result result,Result disabled) {
        var policy=result.policy();
        int recovery=disabled==null?-1:recovery(result.queues(),disabled.queues(),result.lastGrantEnd());
        var end=result.end();
        int recoveredTick=result.lastGrantEnd()+recovery;
        String horizon=policy.reference()?"reference":policy.horizon()<0?"all":Integer.toString(policy.horizon());
        var evaluation=result.evaluation();
        var followup=result.followup();
        row(out,"run",fixture,seed,scheduleId,horizon,policy.priority(),result.missions().size(),
                evaluation.boundary(),evaluation.junction(),evaluation.running(),
                followup.boundary(),followup.junction(),followup.running(),
                disabled==null?null:evaluation.total()+followup.total()-disabled.evaluation().total()-disabled.followup().total(),
                recovery<0?null:recovery,recovery<0?null:result.backlogs()[recoveredTick-WARMUP],
                recovery<0?null:disabled.backlogs()[recoveredTick-WARMUP],
                end.exited()-result.start().exited(),end.travelling(),end.queued(),
                end.boundaryBacklog(),result.peakQueue(),result.fullRoadSeconds(),result.forecasts(),
                result.elapsedNanos()/1_000_000.0);
        for (var a : result.missions()) {
            row(out,"mission",fixture,seed,horizon,policy.priority(),a.id(),a.status(),a.actual(),a.etaError(),
                    a.replans(),a.reroutes(),a.signalWait(),a.receivingWait(),a.impassableWait(),a.routeWait(),
                    a.requests(),a.grants(),a.unsuccessfulGrants());
        }
    }

    public static void main(String[] args) {
        if (args.length < 2 || args.length > 4 || !Set.of("smoke","core","scale").contains(args[0])) {
            throw new IllegalArgumentException("Usage: BenchmarkSuite smoke|core|scale ENGINE_REVISION [FIXTURE [START:END]]");
        }
        Fixture selection=args.length>=3?Fixture.valueOf(args[2]):null;
        String[] seedInterval=args.length==4?args[3].split(":",-1):null;
        if (seedInterval!=null && seedInterval.length!=2) throw new IllegalArgumentException("Expected START:END seeds");
        long firstSeed=seedInterval==null?Long.MIN_VALUE:Long.parseLong(seedInterval[0]);
        long endSeed=seedInterval==null?Long.MAX_VALUE:Long.parseLong(seedInterval[1]);
        if (firstSeed>=endSeed) throw new IllegalArgumentException("Expected an increasing seed interval");
        var out = new PrintWriter(System.out,true);
        row(out,"# geopulse-m5-v1","engine="+args[1],"scope="+args[0],"warmup="+WARMUP,
                "evaluationEnd="+EVALUATION_END,"end="+END);
        row(out,"# run","fixture","seed","schedule","horizon","priority","missions","eval_boundary","eval_junction","eval_running",
                "followup_boundary","followup_junction","followup_running","signed_priority_delay","recovery_seconds","backlog_at_recovery",
                "reference_backlog_at_recovery","exited","travelling","queued","boundary_backlog","peak_queue","full_road_seconds",
                "junction_forecasts","elapsed_ms");
        row(out,"# mission","fixture","seed","horizon","priority","id","status","actual_seconds","eta_minus_actual",
                "replans","reroutes","signal_wait","receiving_wait","impassable_wait","route_wait","requests","grants","unsuccessful_grants");
        var profiles = new HashMap<String,HistoricalProfile>();
        for (var fixture : Fixture.values()) {
            if (selection!=null && selection!=fixture) continue;
            if (fixture==Fixture.SCALE && args[0].equals("core") || fixture!=Fixture.SCALE && args[0].equals("scale")) continue;
            boolean pulse=fixture==Fixture.PREDICTABLE;
            String profileKey=fixture.size+":"+pulse;
            var profile=profiles.computeIfAbsent(profileKey, ignored -> CalibrationRunner.calibrateEvaluation(
                    Graph.grid(fixture.size),Set.copyOf(fixture.stations().values()),pulse));
            row(out,"# profile",fixture,profile.seeds(),profile.bucketSeconds(),profile.buckets(),hash(profile));
            var seeds=args[0].equals("smoke")?List.of(fixture==Fixture.SCALE?2000L:1000L)
                    :fixture==Fixture.SCALE?CalibrationRunner.SCALE_BENCHMARK_SEEDS:CalibrationRunner.CORE_BENCHMARK_SEEDS;
            for (long seed : seeds) {
                if (seed<firstSeed || seed>=endSeed) continue;
                var schedule=schedule(fixture,seed);
                String scheduleId=hash(List.of(fixture,seed,schedule));
                var warm=warmed(fixture,seed,profile);
                for (int horizon : List.of(0,2,-1)) {
                    var disabled=evaluate(warm,schedule,new Policy(horizon,false,false));
                    write(out,fixture,seed,scheduleId,disabled,null);
                    write(out,fixture,seed,scheduleId,evaluate(warm,schedule,new Policy(horizon,true,false)),disabled);
                }
                write(out,fixture,seed,scheduleId,evaluate(warm,schedule,new Policy(0,false,true)),null);
            }
        }
    }
}
