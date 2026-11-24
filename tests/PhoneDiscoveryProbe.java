package com.coupe.phone.audit;

import android.app.*;
import android.content.*;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.service.notification.StatusBarNotification;
import java.io.*;
import java.lang.reflect.Method;

/** Emulator-only instrumentation of the exact signed target APK. No Bluetooth event or AA session. */
public final class PhoneDiscoveryProbe extends Instrumentation {
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    private void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    private Intent target(String name){return new Intent().setComponent(new ComponentName("com.coupe.phone","com.coupe.phone."+name)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);}
    private void capture(String name)throws Exception {
        Bitmap image=getUiAutomation().takeScreenshot();check(image!=null,"Screenshot unavailable");
        try(FileOutputStream out=new FileOutputStream(new File(getTargetContext().getCacheDir(),name))){image.compress(Bitmap.CompressFormat.PNG,100,out);}
        image.recycle();
    }
    @Override public void onStart(){Bundle report=new Bundle();
        try {
            Context context=getTargetContext();
            dalvik.system.DexClassLoader tests=new dalvik.system.DexClassLoader(
                getContext().getApplicationInfo().sourceDir,getContext().getCodeCacheDir().getPath(),null,context.getClassLoader());
            check(Class.forName("com.coupe.phone.ReceiverDiscovery",true,tests)==
                Class.forName("com.coupe.phone.ReceiverDiscovery",true,context.getClassLoader()),"Controller is not from shipping APK");
            String controller=(String)Class.forName("ReceiverDiscoveryTest",true,tests).getMethod("run").invoke(null);
            check(controller.contains("passed=true"),"Discovery controller tests failed");
            report.putString("controller",controller);
            report.putString("shippingControllerExercisedOnArt","true");
            check(context.getPackageManager().getPackageInfo("com.coupe.phone",0).versionCode==21,"Wrong target version");
            Activity initial=startActivitySync(target("MainActivity"));waitForIdleSync();
            runOnMainSync(()->initial.finish());waitForIdleSync();
            Activity legacy=startActivitySync(target("ConnectionActivity").putExtra("open_connection_settings",true));
            waitForIdleSync();Thread.sleep(700);capture("legacy-notification-entry.png");
            Class<?> helper=Class.forName("com.coupe.phone.PhoneNotifications",true,context.getClassLoader());
            Method connected=helper.getDeclaredMethod("connected",Context.class,String.class);connected.setAccessible(true);
            runOnMainSync(()->{try{connected.invoke(null,context,"Vehículo de prueba");}catch(Exception e){throw new RuntimeException(e);}});
            NotificationManager manager=(NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE);
            Notification notice=null;
            for(int i=0;i<20&&notice==null;i++){
                for(StatusBarNotification item:manager.getActiveNotifications())if(item.getId()==802)notice=item.getNotification();
                if(notice==null)Thread.sleep(100);
            }
            check(notice!=null,"Connected notification not posted");
            check(notice.extras.getCharSequence(Notification.EXTRA_TEXT).toString().contains("Comprueba la proyección"),"Old hotspot text");
            check(notice.actions!=null&&notice.actions.length==1,"Unexpected connected actions");
            check("Ver mi garaje".contentEquals(notice.actions[0].title),"Wrong connected action");
            check(notice.contentIntent.equals(notice.actions[0].actionIntent),"Content and action differ");
            Method monitor=helper.getDeclaredMethod("monitor",Context.class,String.class,boolean.class);monitor.setAccessible(true);
            Notification foreground=(Notification)monitor.invoke(null,context,"Estado sintético de prueba",true);
            check(foreground.actions.length==2,"Wrong monitor actions");
            check("Ver mi garaje".contentEquals(foreground.actions[1].title),"Monitor still opens hotspot");
            check(foreground.contentIntent.equals(foreground.actions[1].actionIntent),"Monitor content/action differ");
            ActivityMonitor observed=addMonitor("com.coupe.phone.MainActivity",null,false);
            notice.contentIntent.send();
            Activity destination=waitForMonitorWithTimeout(observed,5000);
            check(destination!=null,"Real notification PendingIntent did not open Mi garaje");
            waitForIdleSync();Thread.sleep(500);capture("notification-opens-garage.png");
            report.putString("passed","true");report.putString("targetVersionCode","21");
            report.putString("actualConnectedNotificationPosted","true");
            report.putString("actualPendingIntentOpenedMainActivity","true");
            report.putString("foregroundMonitorActionUsesGarage","true");
            report.putString("scope","Exact APK, shipping discovery controller on ART with synthetic transport/time and notification; no physical Bluetooth or phone projection session");
            finish(Activity.RESULT_OK,report);
        }catch(Throwable failure){report.putString("passed","false");report.putString("error",failure.toString());finish(Activity.RESULT_CANCELED,report);}
    }
}
