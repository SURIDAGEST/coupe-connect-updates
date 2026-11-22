"""Real Android 8.1 regression/host checks. No phone, OBD, Spotify or real voice is simulated."""
from pathlib import Path
import subprocess,json,hashlib,os,re,time,xml.etree.ElementTree as ET
OUT=Path('audit');OUT.mkdir(exist_ok=True)
CHECKS={}
def adb(*args,timeout=90):
    result=subprocess.run(['adb',*map(str,args)],capture_output=True,timeout=timeout)
    return result.returncode,result.stdout.decode(errors='replace'),result.stderr.decode(errors='replace')
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def check(name,ok):
    CHECKS[name]=bool(ok);save('checks.json',CHECKS)
    if not ok:raise AssertionError(name)
def dump(name):
    for attempt in range(4):
        adb('shell','uiautomator','dump','/sdcard/audit.xml',timeout=30)
        code,text,error=adb('shell','cat','/sdcard/audit.xml')
        if code==0 and '<hierarchy' in text:
            (OUT/(name+'.xml')).write_text(text,encoding='utf-8');return ET.fromstring(text)
        time.sleep(1)
    raise AssertionError('Cannot inspect real native UI: '+name)
def texts(root):return ' '.join(n.get('text','')+' '+n.get('content-desc','') for n in root.iter('node'))
def screenshot(name):
    result=subprocess.run(['adb','exec-out','screencap','-p'],capture_output=True,timeout=30)
    if result.returncode==0:(OUT/(name+'.png')).write_bytes(result.stdout)
def start(component,*extras):
    result=adb('shell','am','start','-W','-n','com.coupe.connect/'+component,*extras)
    save('last-start.json',result);return result
def wait_ui(name,needles,attempts=8):
    for attempt in range(attempts):
        root=dump(name)
        if any(word.lower() in texts(root).lower() for word in needles):screenshot(name);return root
        time.sleep(1)
    screenshot(name);raise AssertionError('Expected UI absent: '+name)
def main():
    env={key:adb('shell','getprop',key)[1].strip() for key in ['ro.build.version.sdk','ro.build.version.release','ro.product.cpu.abilist','ro.build.fingerprint']};save('environment.json',env)
    check('actualApi27',env['ro.build.version.sdk']=='27')
    old=adb('install','--no-streaming','-r','baseline.apk');save('baseline-install.json',old)
    check('oldApkRejectedForNewerSdk',old[0]!=0 and 'OLDER_SDK' in old[1]+old[2])
    candidate=Path('candidate.apk');expected=os.environ['CANDIDATE_SHA256']
    check('candidateHashMatches',hashlib.sha256(candidate.read_bytes()).hexdigest()==expected)
    install=adb('install','--no-streaming','-r',candidate);save('candidate-install.json',install)
    check('candidateInstalled',install[0]==0 and 'Success' in install[1])
    package=adb('shell','dumpsys','package','com.coupe.connect')[1];(OUT/'package.txt').write_text(package)
    check('minimumApi27InInstalledPackage','minSdk=27' in package)
    adb('root');adb('wait-for-device');adb('shell','wm','size','800x480');adb('shell','wm','density','160')
    adb('shell','settings','put','system','accelerometer_rotation','0');adb('shell','settings','put','system','user_rotation','0')
    adb('logcat','-c')
    home_before=adb('shell','cmd','package','resolve-activity','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')[1]
    start('com.andrerinas.openheadunit.main.MainActivity')
    root=wait_ui('receiver-first',['Coupé','Coup','Android Auto','Open Headunit','Welcome','Connect','Conectar'])
    check('receiverColdStartVisible',True)
    adb('shell','am','force-stop','com.coupe.connect')
    start('com.andrerinas.openheadunit.main.MainActivity')
    root=wait_ui('receiver-second',['Coupé','Coup','Android Auto','Open Headunit','Welcome','Connect','Conectar'])
    check('receiverSecondStartVisible',True)
    start('com.coupe.connect.MainActivity','--ez','localDesktop','true')
    root=wait_ui('dashboard',['Android Auto','Configuración','Configuracion','Ajustes','Navegación','Teléfono'])
    check('dashboardWebViewVisible',any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    start('com.andrerinas.openheadunit.main.SettingsActivity','--ei','extra_destination',str(int(os.environ['MAP_PICKER_ID'],0)))
    root=wait_ui('coordinates',['Latitud (','Longitud ('])
    check('legacyCoordinatesVisible','Latitud (' in texts(root) and 'Longitud (' in texts(root))
    check('legacyCoordinatesNoSecondWebView',not any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    # Return to the actual dashboard with the same WebView data directory intact.
    start('com.coupe.connect.MainActivity','--ez','localDesktop','true')
    wait_ui('dashboard-return',['Android Auto','Configuración','Configuracion','Ajustes','Navegación','Teléfono'])
    check('dashboardReturnsAfterNativeSettings',True)
    adb('shell','wm','size','1024x600')
    wait_ui('dashboard-1024',['Android Auto','Configuración','Configuracion','Ajustes','Navegación','Teléfono'])
    check('dashboardSecondResolutionVisible',True)
    log=adb('logcat','-d')[1];(OUT/'logcat.txt').write_text(log,encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log))
    anr='ANR in com.coupe.connect' in log
    check('noOwnFatal',not fatal);check('noOwnAnr',not anr)
    home_after=adb('shell','cmd','package','resolve-activity','--brief','-a','android.intent.action.MAIN','-c','android.intent.category.HOME')[1]
    check('homeUnchanged',home_before==home_after)
    save('result.json',{'passed':True,'candidateSha256':expected,'checks':CHECKS,'postRunErrors':{'ownFatal':fatal,'ownAnr':anr},'scope':'API27 package-manager regression and real receiver/dashboard/native-coordinate UI. No physical ARMv7, phone projection, audio, microphone or OBD test.','phoneSessionTested':False,'physicalRadioTested':False})
if __name__=='__main__':main()
