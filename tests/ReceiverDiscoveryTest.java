import com.coupe.phone.ReceiverDiscovery;
import java.util.*;

/** Host and ART test of the shipping controller. Transport/time are explicitly synthetic. */
public final class ReceiverDiscoveryTest {
    private static final String A="02:00:00:00:00:01", B="02:00:00:00:00:02";
    private static final UUID OTHER=UUID.fromString("0000111f-0000-1000-8000-00805f9b34fb");
    private static int checks;
    private static void check(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    private static final class Fixture implements ReceiverDiscovery.Scheduler, ReceiverDiscovery.Transport, ReceiverDiscovery.Observer {
        long now;
        final Map<Runnable,Long> tasks=new LinkedHashMap<Runnable,Long>();
        final Map<String,Integer> calls=new HashMap<String,Integer>();
        final Map<String,ReceiverDiscovery.State> states=new HashMap<String,ReceiverDiscovery.State>();
        final List<Long> times=new ArrayList<Long>();
        boolean bonded=true, accepted=true, denyBond, denyRequest, failRequest, inline;
        final ReceiverDiscovery controller=new ReceiverDiscovery(this,this,this);
        public long now(){return now;}
        public void post(Runnable task,long delay){check(delay>=0,"negative delay");tasks.put(task,now+delay);}
        public void remove(Runnable task){tasks.remove(task);}
        public boolean bonded(String address){if(denyBond)throw new SecurityException();return bonded;}
        public boolean requestServices(String address){
            calls.put(address,count(address)+1);times.add(now);
            if(denyRequest)throw new SecurityException();if(failRequest)throw new IllegalStateException();
            if(inline)controller.services(address,Arrays.asList(ReceiverDiscovery.ANDROID_AUTO));
            return accepted;
        }
        public void changed(String address,ReceiverDiscovery.State state,int attempts){
            check(attempts>=1&&attempts<=4,"attempt bound");states.put(address,state);
        }
        int count(String address){Integer n=calls.get(address);return n==null?0:n;}
        void connect(String...addresses){controller.reconcile(Arrays.asList(addresses));}
        void advance(long end){
            int guard=0;
            while(true){Runnable next=null;long first=Long.MAX_VALUE;
                for(Map.Entry<Runnable,Long> item:tasks.entrySet())if(item.getValue()<first){first=item.getValue();next=item.getKey();}
                if(next==null||first>end)break;
                check(++guard<1000,"unbounded timer loop");now=first;tasks.remove(next);next.run();
            }now=end;
        }
        void reply(String address,UUID...uuids){controller.services(address,Arrays.asList(uuids));}
    }
    public static String run(){
        checks=0;
        Fixture f=new Fixture();f.connect(A);check(f.count(A)==0,"first request must be queued");
        for(int i=0;i<100;i++)f.connect(A);f.advance(0);check(f.count(A)==1,"duplicate connected events");
        f.advance(1000000);check(f.count(A)==4,"bounded no-response retries");
        check(f.times.equals(Arrays.asList(0L,15000L,35000L,65000L)),"startup retry slots");
        check(f.states.get(A)==ReceiverDiscovery.State.NO_RESPONSE&&f.tasks.isEmpty(),"timeout terminates");
        f.connect(A);f.advance(2000000);check(f.count(A)==4,"completed session must not repeat on render");

        f=new Fixture();f.accepted=false;f.connect(A);f.advance(100000);
        check(f.count(A)==4&&f.states.get(A)==ReceiverDiscovery.State.REQUEST_REJECTED,"request refusal recovery");
        f=new Fixture();f.connect(A);f.advance(0);f.reply(A,ReceiverDiscovery.ANDROID_AUTO);f.advance(100000);
        check(f.count(A)==1&&f.states.get(A)==ReceiverDiscovery.State.FOUND&&f.tasks.isEmpty(),"found stops all retries");
        f=new Fixture();f.connect(A);f.advance(0);f.reply(A,OTHER);f.advance(15000);
        check(f.count(A)==2,"receiver starting after pairing is queried again");
        f.reply(A,OTHER,ReceiverDiscovery.ANDROID_AUTO);f.advance(100000);
        check(f.count(A)==2&&f.states.get(A)==ReceiverDiscovery.State.FOUND,"late receiver discovery");

        f=new Fixture();f.connect(A);f.advance(0);f.reply(B,ReceiverDiscovery.ANDROID_AUTO);
        check(f.states.get(A)==ReceiverDiscovery.State.CHECKING,"foreign response cannot claim our receiver");
        f.connect();f.reply(A,ReceiverDiscovery.ANDROID_AUTO);f.advance(100000);
        check(f.count(A)==1&&f.states.get(A)!=ReceiverDiscovery.State.FOUND,"disconnect cancels pending response");
        f.connect(A);f.reply(A,ReceiverDiscovery.ANDROID_AUTO);f.advance(100000);
        check(f.count(A)==2&&f.states.get(A)==ReceiverDiscovery.State.CHECKING,"unsolicited reply before request ignored");
        f.reply(A,ReceiverDiscovery.ANDROID_AUTO);check(f.states.get(A)==ReceiverDiscovery.State.FOUND,"reconnect permits fresh discovery");

        f=new Fixture();f.connect(A,B,"bad",null);f.advance(0);
        check(f.count(A)==1&&f.count(B)==1&&f.calls.size()==2,"only valid configured connected peers");
        f.reply(B,ReceiverDiscovery.ANDROID_AUTO);f.connect(B);f.advance(100000);
        check(f.count(A)==1&&f.count(B)==1,"per-peer cancellation preserves another car");
        f.controller.stop();check(f.tasks.isEmpty(),"stop clears all work");

        f=new Fixture();f.bonded=false;f.connect(A);f.advance(100000);
        check(f.count(A)==0&&f.states.get(A)==ReceiverDiscovery.State.NOT_BONDED,"never induce pairing");
        f=new Fixture();f.denyBond=true;f.connect(A);f.advance(100000);
        check(f.count(A)==0&&f.states.get(A)==ReceiverDiscovery.State.PERMISSION_REQUIRED,"permission lost before request");
        f=new Fixture();f.denyRequest=true;f.connect(A);f.advance(100000);
        check(f.count(A)==1&&f.states.get(A)==ReceiverDiscovery.State.PERMISSION_REQUIRED,"permission lost during request");
        f=new Fixture();f.failRequest=true;f.connect(A);f.advance(100000);
        check(f.count(A)==4&&f.states.get(A)==ReceiverDiscovery.State.REQUEST_REJECTED,"Bluetooth service exception bounded");
        f=new Fixture();f.inline=true;f.connect(A);f.advance(100000);
        check(f.count(A)==1&&f.states.get(A)==ReceiverDiscovery.State.FOUND&&f.tasks.isEmpty(),"inline response cannot leave timeout armed");
        f=new Fixture();f.connect(A.toLowerCase(Locale.ROOT));f.advance(0);
        f.reply(A.toLowerCase(Locale.ROOT),ReceiverDiscovery.ANDROID_AUTO);
        check(f.count(A)==1&&f.states.get(A)==ReceiverDiscovery.State.FOUND,"normalized addresses");
        f=new Fixture();f.connect(A);f.advance(0);f.reply(A);f.advance(15000);f.reply(A);
        f.advance(35000);f.reply(A);f.advance(65000);f.reply(A);f.advance(100000);
        check(f.states.get(A)==ReceiverDiscovery.State.NOT_DETECTED&&f.count(A)==4,"missing UUID is distinct from timeout");
        f=new Fixture();f.connect(A);f.advance(0);f.controller.services(A,null);f.advance(15000);
        check(f.count(A)==2&&f.states.get(A)==ReceiverDiscovery.State.CHECKING,"null response is retried");
        f.controller.stop();f.advance(100000);check(f.count(A)==2,"explicit stop prevents later work");

        // Interleave arrivals, losses, delayed/foreign replies and teardown. Four calls per arrival,
        // no I/O after cancellation and no projection claim anywhere in this controller.
        for(int seed=0;seed<400;seed++){
            Random random=new Random(seed);f=new Fixture();boolean connected=false;int baseline=0;
            for(int event=0;event<100;event++){
                int choice=random.nextInt(7);
                if(choice==0){f.connect();connected=false;}
                else if(choice==1){if(!connected)baseline=f.count(A);connected=true;f.connect(A);}
                else if(choice==2)f.reply(A,ReceiverDiscovery.ANDROID_AUTO);
                else if(choice==3)f.reply(B,ReceiverDiscovery.ANDROID_AUTO);
                else if(choice==4)f.reply(A,OTHER);
                else if(choice==5){f.controller.stop();connected=false;}
                int before=f.count(A);f.advance(f.now+random.nextInt(8000));
                if(!connected)check(before==f.count(A),"work after cancellation seed "+seed);
                else check(f.count(A)-baseline<=4,"retry budget seed "+seed);
            }
            f.controller.stop();int before=f.count(A);f.advance(f.now+1000000);
            check(f.count(A)==before&&f.tasks.isEmpty(),"teardown drains seed "+seed);
        }
        return "passed=true; controllerChecks="+checks+"; randomizedTimelines=400; physicalBluetooth=false";
    }
    public static void main(String[] args){System.out.println(run());}
}
