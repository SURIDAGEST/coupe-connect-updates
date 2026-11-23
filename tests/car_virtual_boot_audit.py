"""Fault and boot checks on an isolated API27 emulator. Never runs on a physical device.

Setup consent and HOME selection below are synthetic AVD fixtures, not evidence of a
phone session or a user's acceptance. The original HOME and private preferences are restored.
"""
from pathlib import Path
import subprocess,os,re,json,time,hashlib,xml.etree.ElementTree as ET

OUT=Path('audit');OUT.mkdir(exist_ok=True)
SERIAL=os.environ.get('ANDROID_SERIAL','emulator-5554')
assert re.fullmatch(r'emulator-\d+',SERIAL),'Virtual devices only'
B=['adb','-s',SERIAL]
PKG='com.coupe.connect'
ALIAS=PKG+'/com.andrerinas.openheadunit.CarLauncherAlias'
WAIT=PKG+'/com.coupe.connect.AndroidAutoWaitingActivity'
DIAG=PKG+'/com.coupe.connect.ConnectionDiagnosticsActivity'
CE='/data/user/0/com.coupe.connect/shared_prefs/settings.xml'
DE='/data/user_de/0/com.coupe.connect/shared_prefs/settings_device_protected.xml'
CHECKS={}

def adb(*args,timeout=45):
    r=subprocess.run(B+list(map(str,args)),capture_output=True,timeout=timeout)
    return r.returncode,r.stdout.decode('utf-8','replace'),r.stderr.decode('utf-8','replace')
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def check(name,ok):
    CHECKS[name]=bool(ok);save('checks.json',CHECKS)
    if not ok:raise AssertionError(name)
def shot(name):
    r=subprocess.run(B+['exec-out','screencap','-p'],capture_output=True,timeout=30)
    if r.returncode==0:(OUT/(name+'.png')).write_bytes(r.stdout)
def ui(name):
    adb('shell','rm','-f','/sdcard/virtual-audit.xml')
    code,_,_=adb('shell','uiautomator','dump','/sdcard/virtual-audit.xml',timeout=30)
    status,text,_=adb('shell','cat','/sdcard/virtual-audit.xml')
    if code==0 and status==0 and '<hierarchy' in text:
        (OUT/(name+'.xml')).write_text(text,encoding='utf-8')
        return ' '.join(n.get('text','')+' '+n.get('content-desc','') for n in ET.fromstring(text).iter('node'))
    return ''
def wait_text(name,required):
    for _ in range(8):
        text=ui(name)
        if all(s in text for s in required):shot(name);return text
        time.sleep(1)
    shot(name);raise AssertionError('Expected UI missing: '+name)
def start(component):return adb('shell','am','start','-W','--activity-clear-top','-n',component)
def home():
    text=adb('shell','cmd','package','resolve-activity','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')[1]
    matches=re.findall(r'(?m)^[A-Za-z0-9._]+/[A-Za-z0-9._$]+$',text)
    assert len(matches)==1,(text,matches)
    return matches[0]
def write_pref(path,data,uid):
    assert path in (CE,DE)
    directory=path.rsplit('/',1)[0]
    adb('shell','mkdir','-p',directory)
    r=subprocess.run(B+['shell','cat > '+path],input=data,capture_output=True,timeout=30)
    assert r.returncode==0
    adb('shell','chown',str(uid)+':'+str(uid),directory,path);adb('shell','chmod','600',path)
def fixture(original,changes):
    root=ET.fromstring(original or '<map />')
    for key,value in changes.items():
        node=next((n for n in root if n.get('name')==key),None)
        if node is None:node=ET.SubElement(root,'boolean',{'name':key})
        node.tag='boolean';node.set('value','true' if value else 'false')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
def restart():
    before=adb('shell','cat','/proc/sys/kernel/random/boot_id')[1].strip()
    adb('reboot');adb('wait-for-device',timeout=120)
    for _ in range(100):
        after=adb('shell','cat','/proc/sys/kernel/random/boot_id')[1].strip()
        if after and after!=before and adb('shell','getprop','sys.boot_completed')[1].strip()=='1':
            save('virtual-boot-ids.json',{'before':before,'after':after,'changed':True})
            adb('root');adb('wait-for-device')
            return
        time.sleep(1)
    raise AssertionError('Virtual reboot did not finish')

def main():
    check('virtualDeviceOnly',adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1')
    check('actualApi27',adb('shell','getprop','ro.build.version.sdk')[1].strip()=='27')
    expected=os.environ['CANDIDATE_SHA256'];apk=Path('candidate.apk')
    check('exactPublishedApk',hashlib.sha256(apk.read_bytes()).hexdigest()==expected)
    result=adb('install','--no-streaming','-r',apk,timeout=120);save('install.json',result);check('installed',result[0]==0 and 'Success' in result[1])
    adb('root');adb('wait-for-device');adb('shell','wm','size','800x480');adb('shell','wm','density','160');adb('logcat','-c')
    original_home=home();save('home-before.json',original_home)
    package=adb('shell','dumpsys','package',PKG)[1];uid=int(re.search(r'userId=(\d+)',package).group(1))
    original_ce=original_de=None;prefs_captured=False
    original_location=adb('shell','settings','get','secure','location_mode')[1].strip()
    original_providers=adb('shell','settings','get','secure','location_providers_allowed')[1].strip()
    try:
        start(WAIT)
        wait_text('00-setup-required',['Welcome to Open Headunit'])
        check('setupNotBypassedOnFreshInstall',True)
        adb('shell','am','force-stop',PKG)
        code,text,_=adb('shell','cat',CE);assert code==0;original_ce=text.encode('utf-8')
        code,text,_=adb('shell','cat',DE);original_de=text.encode('utf-8') if code==0 else None
        prefs_captured=True
        start(DIAG);wait_text('01-permission-missing',['ubicación: no','sin sesión confirmada'])
        check('missingLocationPermissionReported',True)
        for permission in ['android.permission.ACCESS_COARSE_LOCATION','android.permission.ACCESS_FINE_LOCATION']:
            assert adb('shell','pm','grant',PKG,permission)[0]==0
        wait_text('02-permission-granted',['ubicación: sí','sin sesión confirmada'])
        check('grantedLocationPermissionReported',True)
        # Directly writing location_mode through adb does not toggle provider state on API27.
        # Change the actual allowed providers, then verify the injected OS condition.
        for provider in ['gps','network']:adb('shell','settings','put','secure','location_providers_allowed','-'+provider)
        providers=adb('shell','settings','get','secure','location_providers_allowed')[1].strip()
        save('disabled-location-providers.json',providers)
        check('locationProvidersActuallyDisabled','gps' not in providers and 'network' not in providers)
        wait_text('03-location-off',['ubicación: sí','activada: no'])
        check('permissionAndProviderDistinguished',True)
        for provider in ['gps','network']:adb('shell','settings','put','secure','location_providers_allowed','+'+provider)
        wait_text('04-location-on',['activada: sí','sin sesión confirmada'])
        check('providerRestoredWithoutFakeSession',True)
        adb('shell','am','force-stop',PKG)
        ready=fixture(original_ce,{'has-completed-setup-wizard':True,'has-accepted-disclaimer':True,'enable-car-launcher':True,'auto-start-on-boot':True,'auto-start-on-boot-in-background':True,'auto-start-on-screen-on':True})
        device=fixture(original_de,{'auto-start-on-boot':True,'auto-start-on-screen-on':True,'wireless-paused-by-boot-loop':False})
        write_pref(CE,ready,uid);write_pref(DE,device,uid)
        adb('shell','svc','wifi','disable');start(WAIT)
        wait_text('05-radio-wifi-off',['Wi-Fi de la pantalla apagado'])
        check('radioWifiOffExplained',True)
        adb('shell','svc','wifi','enable');wait_text('06-radio-wifi-on',['Esperando a tu teléfono'])
        check('wifiRestoredReturnsToWaiting',True)
        # Choose HOME only inside this disposable virtual device, after its exact identity check.
        adb('shell','pm','enable',ALIAS)
        result=adb('shell','cmd','package','set-home-activity',ALIAS);save('set-home.json',result)
        check('virtualHomeFixtureSelected',result[0]==0 and home()==ALIAS)
        for _ in range(25):
            if 'CarLauncherAlias' in adb('shell','cat','/data/system/users/0/package-restrictions.xml')[1]:break
            time.sleep(1)
        else:raise AssertionError('Virtual HOME component was not persisted')
        restart()
        wait_text('07-after-reboot',['Coupé Connect','Esperando a tu teléfono'])
        check('homeEntryAfterActualVirtualReboot',home()==ALIAS)
        services=adb('shell','dumpsys','activity','services',PKG)[1];(OUT/'services-after-reboot.txt').write_text(services,encoding='utf-8')
        check('receiverServicePresentAfterBoot','AapService' in services)
        # HOME respawns a force-stopped launcher immediately. Put the stock HOME back before
        # changing the cold-start fixture, so no process caches the old preferences first.
        adb('shell','cmd','package','set-home-activity',original_home)
        adb('shell','am','start','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')
        adb('shell','am','force-stop',PKG)
        for _ in range(10):
            if not adb('shell','pidof',PKG)[1].strip():break
            time.sleep(.5)
        check('receiverStoppedBeforePauseFixture',not adb('shell','pidof',PKG)[1].strip())
        paused=fixture(device,{'wireless-paused-by-boot-loop':True});write_pref(DE,paused,uid)
        paused_values={n.get('name'):n.get('value') for n in ET.fromstring(adb('shell','cat',DE)[1])}
        check('pauseFixtureWrittenBeforeStart',paused_values.get('wireless-paused-by-boot-loop')=='true')
        adb('shell','cmd','package','set-home-activity',ALIAS)
        start(WAIT);text=wait_text('08-recovery-paused',['Inicio inalámbrico en pausa'])
        check('bootLoopPauseExplained',True)
        if 'Reintentar conexión inalámbrica' not in text:
            adb('shell','input','swipe','700','430','700','160','350')
        wait_text('09-explicit-retry-available',['Reintentar conexión inalámbrica'])
        check('explicitRecoveryActionReachable',True)
        time.sleep(3)
        values={n.get('name'):n.get('value') for n in ET.fromstring(adb('shell','cat',DE)[1])}
        check('pauseNotSilentlyCleared',values.get('wireless-paused-by-boot-loop')=='true')
    finally:
        # Restore HOME first, so Android cannot relaunch Coupé while its private bytes are restored.
        adb('shell','cmd','package','set-home-activity',original_home)
        adb('shell','am','start','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')
        adb('shell','am','force-stop',PKG)
        adb('shell','pm','disable',ALIAS)
        if original_ce is not None:write_pref(CE,original_ce,uid)
        if original_de is not None:write_pref(DE,original_de,uid)
        elif prefs_captured:adb('shell','rm','-f',DE)
        adb('shell','svc','wifi','enable')
        if original_location.isdigit():adb('shell','settings','put','secure','location_mode',original_location)
        if original_providers!='null':adb('shell','settings','put','secure','location_providers_allowed',original_providers)
        de=adb('shell','cat',DE)
        save('restoration.json',{'homeRestored':home()==original_home,'originalCeBytesRestored':original_ce is not None and adb('shell','cat',CE)[1].encode('utf-8')==original_ce,'originalDeBytesRestored':prefs_captured and ((original_de is None and de[0]!=0) or (original_de is not None and de[1].encode('utf-8')==original_de))})
        (OUT/'final-logcat.txt').write_text(adb('logcat','-d')[1],encoding='utf-8')
    log=(OUT/'final-logcat.txt').read_text(encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log));anr='ANR in com.coupe.connect' in log
    check('noOwnFatal',not fatal);check('noOwnAnr',not anr)
    restored=json.loads((OUT/'restoration.json').read_text());check('originalVirtualHomeRestored',restored['homeRestored']);check('originalVirtualPreferencesRestored',restored['originalCeBytesRestored'] and restored['originalDeBytesRestored'])
    save('result.json',{'passed':True,'candidateSha256':expected,'checks':CHECKS,'syntheticConsentAndHomeFixture':True,'actualRebootOfVirtualAndroid':True,'physicalAccOrPhoneTested':False,'mapsSpotifyAudioTested':False,'scope':'API27 virtual permission, location, Wi-Fi availability, HOME/reboot and boot-loop safety. No Bluetooth/Wi-Fi Direct hardware, real phone or media session.'})

if __name__=='__main__':
    try:main()
    except Exception:
        save('failure.json',{'passed':False,'checks':CHECKS});raise
