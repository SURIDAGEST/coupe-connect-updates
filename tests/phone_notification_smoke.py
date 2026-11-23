"""Exact signed phone APK on a disposable API36 emulator, with synthetic notification instrumentation."""
import car_virtual_boot_audit as v
from pathlib import Path
import os,json,hashlib,re,subprocess,time
v.PKG='com.coupe.phone'
MAIN=v.PKG+'/.MainActivity'
GARAGE='/data/user/0/com.coupe.phone/shared_prefs/coupe_phone_garage.xml'

def focus():
    return '\n'.join(s for s in v.adb('shell','dumpsys','window')[1].splitlines() if 'mCurrentFocus' in s)

def main():
    v.check('emulatorOnly',v.adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1')
    v.check('actualApi36',v.adb('shell','getprop','ro.build.version.sdk')[1].strip()=='36')
    for name,key in [('candidate.apk','PHONE_SHA256'),('probe.apk','PROBE_SHA256')]:
        v.check('exact-'+name,hashlib.sha256(Path(name).read_bytes()).hexdigest()==os.environ[key])
    v.check('baseline19',hashlib.sha256(Path('baseline.apk').read_bytes()).hexdigest()=='566e291af9808ab36fb107e786cd157fc0f7858053cc9702691a5b43e6035302')
    for apk in ['baseline.apk']:
        result=v.adb('install','--no-streaming','-r',apk,timeout=120);v.save('baseline-install.json',result)
        v.check('baselineInstalled',result[0]==0 and 'Success' in result[1])
    for p in ['BLUETOOTH_CONNECT','POST_NOTIFICATIONS']:
        v.check('granted-'+p,v.adb('shell','pm','grant',v.PKG,'android.permission.'+p)[0]==0)
    v.start(MAIN);v.wait_text('01-baseline-garage',['Mi garaje'])
    v.adb('root');v.adb('wait-for-device');v.adb('shell','am','force-stop',v.PKG)
    code,before,_=v.adb('shell','cat',GARAGE);v.check('baselineGaragePresent',code==0 and 'garage_json' in before)
    result=v.adb('install','--no-streaming','-r','candidate.apk',timeout=120);v.save('candidate-install.json',result)
    v.check('upgradeInstalled',result[0]==0 and 'Success' in result[1])
    v.check('garageUnchangedByUpgrade',v.adb('shell','cat',GARAGE)[1]==before)
    package=v.adb('shell','dumpsys','package',v.PKG)[1];(v.OUT/'package.txt').write_text(package)
    v.check('version20AndMin26','versionCode=20' in package and 'minSdk=26' in package)
    v.adb('logcat','-c');v.start(MAIN);v.wait_text('02-new-garage',['Mi garaje'])
    v.adb('shell','am','start','-n',v.PKG+'/.ConnectionActivity','--ez','open_connection_settings','true')
    time.sleep(2);current=focus();v.save('legacy-entry-focus.json',current)
    v.check('legacyPendingIntentDoesNotOpenSystemSettings','com.coupe.phone' in current and 'ConnectionActivity' in current and 'com.android.settings' not in current)
    v.ui('03-legacy-entry');v.shot('03-legacy-entry')
    result=v.adb('install','--no-streaming','-r','probe.apk',timeout=120);v.save('probe-install.json',result)
    v.check('privateProbeInstalled',result[0]==0 and 'Success' in result[1])
    try:
        result=v.adb('shell','am','instrument','-w','-r','com.coupe.phone.audit/com.coupe.phone.audit.NotificationProbe',timeout=120)
        v.save('instrumentation.json',result)
        v.check('exactAppNotificationInstrumentationPassed',result[0]==0 and 'passed=true' in result[1] and 'targetVersionCode=20' in result[1])
        v.check('actualNotificationPosted','actualConnectedNotificationPosted=true' in result[1])
        v.check('actualNotificationOpensGarage','actualPendingIntentOpenedMainActivity=true' in result[1])
        v.check('foregroundActionUsesGarage','foregroundMonitorActionUsesGarage=true' in result[1])
        for name in ['legacy-notification-entry.png','notification-opens-garage.png']:
            picture=subprocess.run(v.B+['exec-out','cat','/data/user/0/com.coupe.phone/cache/'+name],capture_output=True,timeout=30)
            v.check('captured-'+name,picture.returncode==0 and picture.stdout.startswith(b'\x89PNG'))
            (v.OUT/name).write_bytes(picture.stdout)
        v.check('garageUnchangedByNotificationNavigation',v.adb('shell','cat',GARAGE)[1]==before)
    finally:v.adb('uninstall','com.coupe.phone.audit')
    logs=v.adb('logcat','-d')[1];(v.OUT/'logcat.txt').write_text(logs,encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.phone',logs))
    anr='ANR in com.coupe.phone' in logs
    v.check('noOwnFatal',not fatal);v.check('noOwnAnr',not anr)
    v.save('result.json',{'passed':True,'checks':v.CHECKS,'phoneSha256':os.environ['PHONE_SHA256'],'sdk':36,
        'postRunErrors':{'ownFatal':fatal,'ownAnr':anr},'physicalPhoneTested':False,'phoneProjectionTested':False,
        'scope':'Real signed APK, upgrade from phone19 and actual Android Notification/PendingIntent with synthetic notification. No Bluetooth event, OPPO, Wi-Fi bootstrap or Android Auto projection.'})

if __name__=='__main__':
    try:main()
    except Exception:
        v.save('result.json',{'passed':False,'checks':v.CHECKS});raise
    finally:(v.OUT/'final-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
