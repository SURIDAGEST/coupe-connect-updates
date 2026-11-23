"""API27 runtime evidence using fresh native XML and the Activity's own view dump.

Old WebViews sometimes omit accessibility nodes. WebView checks use actual Activity view
hierarchies plus foreground ownership and screenshots, which require visual review.
"""
import car_api27_smoke as b
from pathlib import Path
import os,json,hashlib,re,time,xml.etree.ElementTree as ET

def dump(name):
    for _ in range(4):
        b.adb('shell','rm','-f','/sdcard/audit.xml')
        result=b.adb('shell','uiautomator','dump','/sdcard/audit.xml',timeout=30)
        code,text,error=b.adb('shell','cat','/sdcard/audit.xml')
        if result[0]==0 and code==0 and '<hierarchy' in text:
            (b.OUT/(name+'.xml')).write_text(text,encoding='utf-8');return ET.fromstring(text)
        time.sleep(1)
    b.screenshot(name)
    raise AssertionError('No fresh accessibility dump: '+name)
b.dump=dump

def start(component,*extras):
    if component=='com.coupe.connect.MainActivity':extras=('--activity-clear-top',*extras)
    return b.start(component,*extras)

def desktop(name):
    start('com.coupe.connect.MainActivity','--ez','localDesktop','true')
    for _ in range(8):
        window=b.adb('shell','dumpsys','window','windows')[1]
        focus='\n'.join(line for line in window.splitlines() if 'mCurrentFocus' in line)
        hierarchy=b.adb('shell','dumpsys','activity','top')[1]
        if re.search(r'com\.coupe\.connect/(?:com\.coupe\.connect)?\.MainActivity\b',focus) and 'android.webkit.WebView{' in hierarchy:
            (b.OUT/(name+'-window.txt')).write_text(window,encoding='utf-8')
            (b.OUT/(name+'-views.txt')).write_text(hierarchy,encoding='utf-8')
            b.screenshot(name)
            return True
        time.sleep(1)
    (b.OUT/(name+'-window.txt')).write_text(window,encoding='utf-8')
    (b.OUT/(name+'-views.txt')).write_text(hierarchy,encoding='utf-8')
    b.screenshot(name)
    raise AssertionError('Foreground dashboard/view hierarchy not verified: '+name)

def main():
    env={key:b.adb('shell','getprop',key)[1].strip() for key in ['ro.build.version.sdk','ro.build.version.release','ro.product.cpu.abilist','ro.build.fingerprint']};b.save('environment.json',env)
    b.check('actualApi27',env['ro.build.version.sdk']=='27')
    old=b.adb('install','--no-streaming','-r','baseline.apk');b.save('baseline-install.json',old)
    b.check('oldApkRejectedForNewerSdk',old[0]!=0 and 'OLDER_SDK' in old[1]+old[2])
    expected=os.environ['CANDIDATE_SHA256'];b.check('candidateHashMatches',hashlib.sha256(Path('candidate.apk').read_bytes()).hexdigest()==expected)
    installed=b.adb('install','--no-streaming','-r','candidate.apk');b.save('candidate-install.json',installed)
    b.check('candidateInstalled',installed[0]==0 and 'Success' in installed[1])
    package=b.adb('shell','dumpsys','package','com.coupe.connect')[1];(b.OUT/'package.txt').write_text(package)
    b.check('minimumApi27InInstalledPackage','minSdk=27' in package)
    b.adb('root');b.adb('wait-for-device');b.adb('shell','wm','size','800x480');b.adb('shell','wm','density','160')
    b.adb('shell','settings','put','system','accelerometer_rotation','0');b.adb('shell','settings','put','system','user_rotation','0');b.adb('logcat','-c')
    home=lambda:b.adb('shell','cmd','package','resolve-activity','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')[1]
    before=home()
    for name in ['receiver-first','receiver-second']:
        if name=='receiver-second':b.adb('shell','am','force-stop','com.coupe.connect')
        start('com.andrerinas.openheadunit.main.MainActivity');b.wait_ui(name,['Coup','Android Auto','Open Headunit','Welcome','Connect','Conectar'])
        b.check(name+'Visible',True)
    b.check('dashboardWebViewHierarchyVisible',desktop('dashboard'))
    start('com.andrerinas.openheadunit.main.SettingsActivity','--ei','extra_destination',str(int(os.environ['MAP_PICKER_ID'],0)))
    root=b.wait_ui('coordinates',['Latitud (','Longitud ('])
    b.check('legacyCoordinatesVisible','Latitud (' in b.texts(root) and 'Longitud (' in b.texts(root))
    b.check('legacyCoordinatesNoSecondWebView',not any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    b.check('dashboardReturnsAfterNativeSettings',desktop('dashboard-return'))
    b.adb('shell','wm','size','1024x600');b.check('dashboardSecondResolutionVisible',desktop('dashboard-1024'))
    b.adb('shell','wm','size','800x480')
    start('com.coupe.connect.ConnectionDiagnosticsActivity')
    root=b.wait_ui('connection-diagnostics',['Bluetooth visible en Android:']);visible=b.texts(root)
    b.check('diagnosticsFromActualReceiver',all(word in visible for word in ['Radio:','API 27','Ruta Bluetooth:','Paso actual:']))
    b.check('noFalseProjectionClaim','sin sesión confirmada' in visible and 'proyección: ACTIVA' not in visible)
    b.check('diagnosticsNativeNoWebView',not any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    start('com.andrerinas.openheadunit.main.SettingsActivity','--ei','extra_destination',str(0x7f090386))
    root=b.wait_ui('diagnostics-settings-entry',['Comprobar conexión'])
    nodes=[n for n in root.iter('node') if n.get('text')=='Comprobar conexión'];b.check('diagnosticsSettingsEntryVisible',bool(nodes))
    bounds=list(map(int,re.findall(r'\d+',nodes[0].get('bounds',''))));assert len(bounds)==4
    b.adb('shell','input','tap',(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
    b.wait_ui('diagnostics-opened-from-settings',['Bluetooth visible en Android:']);b.check('diagnosticsSettingsEntryWorks',True)
    b.check('dashboardAfterDiagnosticsVisible',desktop('dashboard-after-diagnostics'))
    log=b.adb('logcat','-d')[1];(b.OUT/'final-logcat.txt').write_text(log,encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log));anr='ANR in com.coupe.connect' in log
    b.check('noOwnFatal',not fatal);b.check('noOwnAnr',not anr);b.check('homeUnchanged',before==home())
    b.save('result.json',{'passed':True,'candidateSha256':expected,'checks':b.CHECKS,'postRunErrors':{'ownFatal':fatal,'ownAnr':anr},'scope':'Real API27 install, receiver, foreground dashboard View hierarchy/screenshots, native coordinates and actual receiver diagnostics opened directly and from Settings. Screenshots require visual review. No physical phone, ARMv7, audio, Spotify or pairing test.','phoneSessionTested':False,'physicalRadioTested':False})

if __name__=='__main__':
    try:main()
    except Exception:
        b.save('result.json',{'passed':False,'checks':b.CHECKS});raise
    finally:
        (b.OUT/'final-logcat.txt').write_text(b.adb('logcat','-d')[1],encoding='utf-8')
