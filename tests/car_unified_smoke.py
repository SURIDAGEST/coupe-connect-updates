"""Actual API27 install/upgrade/HOME/receiver checks; synthetic preferences only on a disposable AVD.

No phone, Bluetooth radio, Spotify playback, real cartography or physical ACC test.
The original HOME and private preference bytes are restored even on failure.
"""
import car_virtual_boot_audit as v
from pathlib import Path
import hashlib,json,os,re,time,xml.etree.ElementTree as ET

DESKTOP=v.PKG+'/com.coupe.connect.MainActivity'
NATIVE=v.PKG+'/com.andrerinas.openheadunit.main.MainActivity'
SETTINGS=v.PKG+'/com.andrerinas.openheadunit.main.SettingsActivity'
SERVICE=v.PKG+'/com.andrerinas.openheadunit.aap.AapService'

def foreground_desktop(name):
    for _ in range(25):
        windows=v.adb('shell','dumpsys','window','windows')[1]
        focused='\n'.join(s for s in windows.splitlines() if 'mCurrentFocus' in s)
        activity=v.adb('shell','dumpsys','activity','top')[1]
        if re.search(r'com\.coupe\.connect/(?:com\.coupe\.connect\.)?MainActivity',focused) and 'android.webkit.WebView{' in activity:
            time.sleep(4)
            (v.OUT/(name+'-views.txt')).write_text(activity,encoding='utf-8')
            v.ui(name);v.shot(name);return True
        time.sleep(1)
    v.shot(name);return False

def stop_for_fixture(stock):
    v.adb('shell','cmd','package','set-home-activity',stock)
    v.adb('shell','am','start','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')
    v.adb('shell','am','force-stop',v.PKG)
    for _ in range(12):
        if not v.adb('shell','pidof',v.PKG)[1].strip():return
        time.sleep(.5)
    raise AssertionError('The receiver did not stop before the AVD fixture')

def main():
    v.check('emulatorOnly',v.adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1')
    v.check('actualApi27',v.adb('shell','getprop','ro.build.version.sdk')[1].strip()=='27')
    expected=os.environ['CANDIDATE_SHA256']
    v.check('exactCandidate',hashlib.sha256(Path('candidate.apk').read_bytes()).hexdigest()==expected)
    v.check('exactBaseline',hashlib.sha256(Path('baseline.apk').read_bytes()).hexdigest()=='2de4a8aa575327af385d94a0e80f3929c1ccec03cbbc563c8e7ffd4f31153f5a')
    result=v.adb('install','--no-streaming','baseline.apk',timeout=120);v.save('baseline-install.json',result)
    v.check('baselineInstalled',result[0]==0 and 'Success' in result[1])
    v.adb('root');v.adb('wait-for-device');v.adb('shell','wm','size','800x480');v.adb('shell','wm','density','160')
    v.adb('shell','settings','put','system','accelerometer_rotation','0');v.adb('shell','settings','put','system','user_rotation','0')
    v.adb('logcat','-c')
    stock=v.home();v.start(v.WAIT);time.sleep(4)
    uid=int(re.search(r'userId=(\d+)',v.adb('shell','dumpsys','package',v.PKG)[1]).group(1))
    stop_for_fixture(stock)
    ce=v.adb('shell','cat',v.CE);de=v.adb('shell','cat',v.DE)
    original_ce=ce[1].encode('utf-8') if ce[0]==0 else None
    original_de=de[1].encode('utf-8') if de[0]==0 else None
    try:
        fixture=v.fixture(original_ce,{'has-completed-setup-wizard':True,'has-accepted-disclaimer':True,
            'auto-start-on-boot':True,'auto-start-on-boot-in-background':False,'auto-start-on-screen-on':True})
        xml=ET.fromstring(fixture);sentinel=ET.SubElement(xml,'string',{'name':'coupe-ui1-upgrade-sentinel'});sentinel.text='AVD TEST ONLY - preserve me'
        fixture=ET.tostring(xml,encoding='utf-8',xml_declaration=True)
        v.write_pref(v.CE,fixture,uid)
        device=v.fixture(original_de,{'auto-start-on-boot':True,'auto-start-on-boot-in-background':False,'auto-start-on-screen-on':True,'wireless-paused-by-boot-loop':False})
        v.write_pref(v.DE,device,uid)
        result=v.adb('install','--no-streaming','-r','candidate.apk',timeout=120);v.save('candidate-install.json',result)
        v.check('upgradeInstalled',result[0]==0 and 'Success' in result[1])
        v.check('preferencesUnchangedByUpgrade',v.adb('shell','cat',v.CE)[1].encode('utf-8')==fixture and v.adb('shell','cat',v.DE)[1].encode('utf-8')==device)
        package=v.adb('shell','dumpsys','package',v.PKG)[1];(v.OUT/'package.txt').write_text(package)
        v.check('version21AndMin27','versionCode=21' in package and 'minSdk=27' in package)
        v.adb('shell','pm','grant',v.PKG,'android.permission.ACCESS_COARSE_LOCATION')
        v.adb('shell','pm','grant',v.PKG,'android.permission.ACCESS_FINE_LOCATION')
        v.adb('shell','svc','wifi','enable')
        v.start(v.WAIT);v.check('entryOpensUnifiedDesktop',foreground_desktop('01-desktop-from-entry'))
        v.start(v.DIAG);text=v.wait_text('02-live-diagnostics',['Bluetooth visible en Android:','Configurado:'])
        v.check('actualReceiverResponds','API 27' in text and 'Paso actual:' in text)
        v.check('noInventedPhoneSession','sin sesión confirmada' in text and 'proyección: ACTIVA' not in text)
        v.start(SETTINGS);time.sleep(3);v.start(v.DIAG)
        text=v.wait_text('03-diagnostics-after-settings',['Bluetooth visible en Android:'])
        v.check('pauseHasContext','ANTERIOR a abrir Ajustes' in text or 'Ajustes ha pausado' in text or 'iniciado: no' in text)
        v.start(v.WAIT);v.check('returnUsesSameDesktop',foreground_desktop('04-desktop-after-settings'))
        # Exercise the actual compiled service command. The AVD has no paired phone.
        result=v.adb('shell','am','start-foreground-service','-n',SERVICE,'-a','com.coupe.connect.CONNECT_PHONE');v.save('connect-command.json',result)
        time.sleep(3);v.shot('05-connect-result-on-desktop')
        v.start(v.DIAG);text=v.wait_text('06-connect-result-diagnostics',['Resultado de Conectar:'])
        v.check('realConnectHandlerResponds',any(code in text for code in ['bluetooth_off','pair_phone','bluetooth_route','permission']))
        v.check('connectDoesNotInventProjection','proyección: ACTIVA' not in text)
        v.adb('shell','pm','enable',v.ALIAS)
        result=v.adb('shell','cmd','package','set-home-activity',v.ALIAS);v.save('set-home.json',result)
        v.check('avdHomeFixture',result[0]==0 and v.home()==v.ALIAS)
        # Wait for PackageManager to persist HOME before the actual virtual reboot.
        for _ in range(25):
            if 'CarLauncherAlias' in v.adb('shell','cat','/data/system/users/0/package-restrictions.xml')[1]:break
            time.sleep(1)
        else:raise AssertionError('HOME fixture was not persisted')
        v.restart();v.check('homeSurvivesRealVirtualReboot',v.home()==v.ALIAS)
        v.check('bootOpensUnifiedDesktop',foreground_desktop('07-desktop-after-reboot'))
        services=v.adb('shell','dumpsys','activity','services',v.PKG)[1];(v.OUT/'services-after-boot.txt').write_text(services)
        v.check('receiverRunsBehindDesktop','AapService' in services)
        values=ET.fromstring(v.adb('shell','cat',v.CE)[1]);v.check('dataSentinelSurvivesBoot',any(n.get('name')=='coupe-ui1-upgrade-sentinel' and n.text==sentinel.text for n in values))
        for width,height in [(1024,600),(640,360),(800,480)]:
            v.adb('shell','wm','size',str(width)+'x'+str(height));v.start(v.WAIT)
            v.check('desktopAt'+str(width)+'x'+str(height),foreground_desktop('08-desktop-'+str(width)+'x'+str(height)))
    finally:
        stop_for_fixture(stock);v.adb('shell','pm','disable',v.ALIAS)
        if original_ce is None:v.adb('shell','rm','-f',v.CE)
        else:v.write_pref(v.CE,original_ce,uid)
        if original_de is None:v.adb('shell','rm','-f',v.DE)
        else:v.write_pref(v.DE,original_de,uid)
        final_ce=v.adb('shell','cat',v.CE);final_de=v.adb('shell','cat',v.DE)
        v.save('restoration.json',{'homeRestored':v.home()==stock,
            'originalCeBytesRestored':(final_ce[0]!=0 if original_ce is None else final_ce[1].encode('utf-8')==original_ce),
            'originalDeBytesRestored':(final_de[0]!=0 if original_de is None else final_de[1].encode('utf-8')==original_de)})
        (v.OUT/'final-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
    log=(v.OUT/'final-logcat.txt').read_text(encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log));anr='ANR in com.coupe.connect' in log
    v.check('noOwnFatal',not fatal);v.check('noOwnAnr',not anr)
    restoration=json.loads((v.OUT/'restoration.json').read_text());v.check('restorationComplete',all(restoration.values()))
    v.save('result.json',{'passed':True,'candidateSha256':expected,'checks':v.CHECKS,
        'postRunErrors':{'ownFatal':fatal,'ownAnr':anr},'physicalRadioTested':False,'phoneSessionTested':False,
        'scope':'Actual API27 upgrade, foreground WebView, native diagnostics, no-phone connect command, HOME reboot and preservation of AVD data. Post-reboot log only; screenshots need visual review.'})

if __name__=='__main__':
    try:main()
    except Exception:
        v.save('result.json',{'passed':False,'checks':v.CHECKS});raise
    finally:(v.OUT/'final-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
