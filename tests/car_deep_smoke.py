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

def start(component):
    # am start -W can wait forever for a dispatcher that finishes before drawing,
    # even though the existing destination is already resumed. Observe that destination.
    return v.adb('shell','am','start','--activity-clear-top','-n',component)
v.start=start

def foreground_desktop(name):
    for _ in range(25):
        windows=v.adb('shell','dumpsys','window')[1]
        focused='\n'.join(s for s in windows.splitlines() if 'mCurrentFocus' in s)
        if _ % 5 == 0 or 'com.android.systemui' in focused or 'ImmersiveModeConfirmation' in focused:
            # First immersive launch presents Android's own education dialog on API35.
            # Acknowledge only this exact system prompt; never bypass app/permission dialogs.
            v.ui(name+'-system-tip')
            tip=v.OUT/(name+'-system-tip.xml')
            if tip.exists():
                nodes=list(ET.fromstring(tip.read_text(encoding='utf-8')).iter('node'))
                if any(n.get('text')=='Viewing full screen' for n in nodes):
                    button=next((n for n in nodes if n.get('text')=='Got it' and n.get('package') in ('android','com.android.systemui')),None)
                    if button is not None:
                        bounds=list(map(int,re.findall(r'\d+',button.get('bounds',''))));assert len(bounds)==4
                        v.adb('shell','input','tap',(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
                        v.check('systemFullscreenTipAcknowledged',True)
                        continue
        activity=v.adb('shell','dumpsys','activity','top')[1]
        if re.search(r'com\.coupe\.connect/(?:com\.coupe\.connect\.)?MainActivity',focused) and 'android.webkit.WebView{' in activity:
            time.sleep(4)
            (v.OUT/(name+'-views.txt')).write_text(activity,encoding='utf-8')
            v.ui(name);v.shot(name);return True
        time.sleep(1)
    (v.OUT/(name+'-windows.txt')).write_text(windows,encoding='utf-8')
    (v.OUT/(name+'-views.txt')).write_text(activity,encoding='utf-8')
    v.shot(name);return False

def select_home(component):
    if int(v.adb('shell','getprop','ro.build.version.sdk')[1])>=29:
        # A preferred Activity alone is overwritten by RoleManager at boot on modern Android.
        role=v.adb('shell','cmd','role','add-role-holder','--user','0','android.app.role.HOME',component.split('/')[0],'0')
        assert role[0]==0,role
    return v.adb('shell','cmd','package','set-home-activity',component)

def stop_for_fixture(stock):
    select_home(stock)
    v.adb('shell','am','start','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')
    v.adb('shell','am','force-stop',v.PKG)
    for _ in range(12):
        if not v.adb('shell','pidof',v.PKG)[1].strip():return
        time.sleep(.5)
    raise AssertionError('The receiver did not stop before the AVD fixture')

def main():
    v.check('emulatorOnly',v.adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1')
    sdk=int(v.adb('shell','getprop','ro.build.version.sdk')[1].strip())
    v.check('actualRequestedApi',sdk==int(os.environ.get('EXPECTED_API','27')) and sdk in (27,35))
    expected=os.environ['CANDIDATE_SHA256']
    v.check('exactCandidate',hashlib.sha256(Path('candidate.apk').read_bytes()).hexdigest()==expected)
    v.check('exactBaseline',hashlib.sha256(Path('baseline.apk').read_bytes()).hexdigest()=='ca99a8d191c4fdaf8b280b1a303251d1042dcbdf85fb06311c3cc5196624eee5')
    result=v.adb('install','--no-streaming','-r','baseline.apk',timeout=120);v.save('baseline-install.json',result)
    v.check('baselineInstalled',result[0]==0 and 'Success' in result[1])
    v.adb('root');v.adb('wait-for-device');v.adb('shell','wm','size','800x480');v.adb('shell','wm','density','160')
    v.adb('shell','settings','put','system','accelerometer_rotation','0');v.adb('shell','settings','put','system','user_rotation','0')
    v.adb('logcat','-c')
    stock=v.home();v.start(v.WAIT);time.sleep(4)
    # Android 15 prints appId where API27 printed userId (this AVD runs user 0).
    package_before=v.adb('shell','dumpsys','package',v.PKG)[1]
    (v.OUT/'package-before-fixture.txt').write_text(package_before,encoding='utf-8')
    app_id=re.search(r'\b(?:userId|appId)=(\d+)',package_before)
    assert app_id is not None,'PackageManager did not expose the application UID; no preference fixture written'
    uid=int(app_id.group(1));v.check('applicationUidVerified',10000<=uid<20000)
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
        (v.OUT/'baseline-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
        v.adb('logcat','-c') # candidate attribution begins before package replacement broadcasts
        result=v.adb('install','--no-streaming','-r','candidate.apk',timeout=120);v.save('candidate-install.json',result)
        v.check('upgradeInstalled',result[0]==0 and 'Success' in result[1])
        v.check('preferencesUnchangedByUpgrade',v.adb('shell','cat',v.CE)[1].encode('utf-8')==fixture and v.adb('shell','cat',v.DE)[1].encode('utf-8')==device)
        package=v.adb('shell','dumpsys','package',v.PKG)[1];(v.OUT/'package.txt').write_text(package)
        v.check('version23AndMin27','versionCode=23' in package and 'minSdk=27' in package)
        v.adb('shell','pm','grant',v.PKG,'android.permission.ACCESS_COARSE_LOCATION')
        v.adb('shell','pm','grant',v.PKG,'android.permission.ACCESS_FINE_LOCATION')
        if sdk>=31:
            for permission in ['BLUETOOTH_CONNECT','BLUETOOTH_SCAN','BLUETOOTH_ADVERTISE']:
                v.adb('shell','pm','grant',v.PKG,'android.permission.'+permission)
        if sdk>=33:v.adb('shell','pm','grant',v.PKG,'android.permission.NEARBY_WIFI_DEVICES')
        v.adb('shell','svc','wifi','enable')
        v.start(v.WAIT);v.check('entryOpensUnifiedDesktop',foreground_desktop('01-desktop-from-entry'))
        for attempt in range(2,6):
            v.adb('shell','am','force-stop',v.PKG);v.start(v.WAIT)
            v.check('coldProcessStart'+str(attempt),foreground_desktop('01-cold-start-'+str(attempt)))
        v.start(NATIVE);v.check('engineEntryAlsoReturnsToDesktop',foreground_desktop('01b-desktop-from-engine'))
        # The screen-share entry remains available without implicitly starting capture.
        v.start(v.PKG+'/com.coupe.connect.ScreenShareActivity')
        v.wait_text('01c-screen-share-entry',['Compartir pantalla del coche','Compartir con autorización de Android'])
        v.check('screenShareEntryStillAvailable',True)
        v.check('screenShareRequiresExplicitConsent','ScreenShareService' not in v.adb('shell','dumpsys','activity','services',v.PKG)[1])
        v.adb('shell','input','keyevent','4');v.check('screenShareReturnsToDesktop',foreground_desktop('01d-desktop-after-screen-share'))
        v.start(v.DIAG);text=v.wait_text('02-live-diagnostics',['Bluetooth visible en Android:','Configurado:'])
        v.check('actualReceiverResponds',('API '+str(sdk)) in text and 'Paso actual:' in text)
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
        # Real command acknowledgement: pause the receiver before opening Wi-Fi.
        v.start(v.WAIT);v.check('desktopBeforeInternet',foreground_desktop('06b-before-internet'))
        v.adb('shell','am','start-foreground-service','-n',SERVICE,'-a','com.coupe.connect.USE_INTERNET')
        for _ in range(20):
            focus=v.adb('shell','dumpsys','window')[1]
            if any('mCurrentFocus' in line and 'com.android.settings' in line for line in focus.splitlines()):break
            time.sleep(.5)
        else:raise AssertionError('Wi-Fi settings did not open after receiver acknowledgement')
        v.check('internetCommandOpensSystemWifiAfterPause',True);v.shot('06c-system-wifi-after-ack')
        v.start(v.DIAG);text=v.wait_text('06d-pause-result',['Resultado de Conectar:'])
        v.check('internetPauseConfirmed','internet_paused' in text)
        v.adb('shell','am','start-foreground-service','-n',SERVICE,'-a','com.coupe.connect.CANCEL_PHONE')
        time.sleep(1);v.start(v.DIAG);text=v.wait_text('06e-cancel-result',['Resultado de Conectar:'])
        v.check('cancelCommandResponds','cancel_requested' in text)
        # Exercise the user's actual HOME cancellation route, not just a forced HOME fixture.
        v.adb('shell','pm','disable',v.ALIAS)
        v.adb('shell','am','start','--activity-clear-top','-n',v.WAIT,'--ez','configureHome','true')
        # configureHome is the explicit in-app user request and immediately opens Android's chooser.
        time.sleep(2)
        focus=v.adb('shell','dumpsys','window')[1]
        v.check('officialHomeChooserOpened',any('mCurrentFocus' in line and ('com.android.settings' in line or 'permissioncontroller' in line) for line in focus.splitlines()))
        v.shot('06g-official-home-chooser');v.adb('shell','input','keyevent','4')
        v.wait_text('06h-after-home-cancel',['Encender con Coupé'])
        v.check('homeChooserCancelKeepsOriginalHome',v.home()==stock)
        choices=v.adb('shell','cmd','package','query-activities','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')
        v.save('home-choices-after-cancel.json',choices)
        v.check('homeChooserCancelRestoresDisabledAlias',choices[0]==0 and 'CarLauncherAlias' not in choices[1])
        # Emulate the preference written only after real HOME acceptance. Fixture, not user consent.
        stop_for_fixture(stock)
        fixture_home=v.fixture(v.adb('shell','cat',v.CE)[1].encode('utf-8'),{'enable-car-launcher':True})
        v.write_pref(v.CE,fixture_home,uid)
        v.adb('shell','pm','enable',v.ALIAS)
        result=select_home(v.ALIAS);v.save('set-home.json',result)
        v.check('avdHomeFixture',result[0]==0 and v.home()==v.ALIAS)
        # Wait for PackageManager to persist HOME before the actual virtual reboot.
        for _ in range(25):
            if 'CarLauncherAlias' in v.adb('shell','cat','/data/system/users/0/package-restrictions.xml')[1]:break
            time.sleep(1)
        else:raise AssertionError('HOME fixture was not persisted')
        (v.OUT/'pre-reboot-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
        v.restart()
        for _ in range(20):
            if v.home()==v.ALIAS:break
            time.sleep(1)
        v.check('homeSurvivesRealVirtualReboot',v.home()==v.ALIAS)
        v.check('bootOpensUnifiedDesktop',foreground_desktop('07-desktop-after-reboot'))
        services=v.adb('shell','dumpsys','activity','services',v.PKG)[1];(v.OUT/'services-after-boot.txt').write_text(services)
        v.check('receiverRunsBehindDesktop','AapService' in services)
        if sdk>=29:v.check('bootUsesConnectedDeviceType','foregroundServiceType=0x00000010' in services or 'foregroundServiceType=0x10' in services)
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
    before=v.OUT/'pre-reboot-logcat.txt'
    log=(before.read_text(encoding='utf-8') if before.exists() else '')+(v.OUT/'final-logcat.txt').read_text(encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log));anr='ANR in com.coupe.connect' in log
    v.check('noOwnFatal',not fatal);v.check('noOwnAnr',not anr)
    restoration=json.loads((v.OUT/'restoration.json').read_text());v.check('restorationComplete',all(restoration.values()))
    v.save('result.json',{'passed':True,'candidateSha256':expected,'checks':v.CHECKS,
        'postRunErrors':{'ownFatal':fatal,'ownAnr':anr},'physicalRadioTested':False,'phoneSessionTested':False,
        'sdk':sdk,'logScope':'Candidate installation through reboot; pre- and post-reboot logs',
        'scope':'Actual emulator upgrade, WebView, diagnostics, no-phone connect/cancel/Internet commands, HOME reboot and AVD data preservation. No real phone or radio transport.'})

if __name__=='__main__':
    try:main()
    except Exception:
        v.save('result.json',{'passed':False,'checks':v.CHECKS});raise
    finally:
        (v.OUT/'final-logcat.txt').write_text(v.adb('logcat','-d')[1],encoding='utf-8')
        for name in v.adb('shell','ls','/data/anr')[1].split():
            if not re.fullmatch(r'anr_[A-Za-z0-9._-]+',name):continue
            trace=v.adb('shell','cat','/data/anr/'+name)[1]
            if 'Cmd line: com.coupe.connect' in trace or 'Cmdline: com.coupe.connect' in trace:
                (v.OUT/(name+'.txt')).write_text(trace,encoding='utf-8')
