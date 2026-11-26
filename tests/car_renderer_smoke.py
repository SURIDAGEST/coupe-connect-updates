"""Private exact-APK renderer audit on a fresh GitHub-hosted Android emulator only."""
from pathlib import Path
import hashlib,json,os,re,subprocess,time,queue,threading

PACKAGE='com.coupe.connect'
PROBE='com.coupe.connect.audit.renderer'
INSTRUMENT=PROBE+'/com.coupe.connect.audit.CarRendererProbe'
OUT=Path('audit');SERIAL=None

def run(*args,timeout=90,required=True):
    result=subprocess.run(list(map(str,args)),capture_output=True,timeout=timeout)
    output=result.stdout.decode('utf-8',errors='replace')
    error=result.stderr.decode('utf-8',errors='replace')
    if required and result.returncode:raise AssertionError(str(args[0])+': '+error[-1200:]+output[-1200:])
    return result.returncode,output,error

def adb(*args,**kwargs):return run('adb','-s',SERIAL,*args,**kwargs)
def save(name,value):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def instrument(version,folder):
    command=['adb','-s',SERIAL,'shell','am','instrument','-w','-r','-e','apk_sha256',os.environ['CAR_SHA256'],
             '-e','version_code',str(version),INSTRUMENT]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    lines=queue.Queue();output=[];deadline=time.monotonic()+240;kill_done=False
    def read():
        for line in process.stdout:lines.put(line)
        lines.put(None)
    reader=threading.Thread(target=read,daemon=True);reader.start()
    try:
        while True:
            assert time.monotonic()<deadline,'Instrumentation timed out'
            try:line=lines.get(timeout=1)
            except queue.Empty:continue
            if line is None:break
            output.append(line)
            if line.strip()=='INSTRUMENTATION_STATUS: flow_renderer_kill=isolated-emulator-api27':
                assert int(os.environ['EXPECTED_API'])==27 and not kill_done
                assert adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1'
                logs=adb('logcat','-d','-v','brief')[1]
                linked=re.findall(r'Start proc (\d+):com\.android\.webview:sandboxed_process\d+/[^\n]*for webview_service com\.coupe\.connect/org\.chromium\.[^\n]+',logs)
                assert linked,'No isolated renderer linked to our target app'
                pid=linked[-1];processes=adb('shell','ps','-A')[1]
                matching=[x for x in processes.splitlines() if len(x.split())>2 and x.split()[1]==pid]
                assert len(matching)==1 and re.match(r'u\d+_i\d+\s',matching[0]) and 'com.android.webview:sandboxed_process' in matching[0]
                (folder/'host-renderer-termination.json').write_text(json.dumps({'pid':int(pid),'process':matching[0],'targetLinked':True,'isolatedEmulator':True},indent=2),encoding='utf-8')
                adb('shell','kill','-9',pid);kill_done=True
        return process.wait(timeout=10),''.join(output),''
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
        (folder/'instrumentation.txt').write_text(''.join(output),encoding='utf-8')

def tools():
    sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','')))
    choices=sorted(p for p in (sdk/'build-tools').glob('*') if (p/'aapt').is_file() and (p/'apksigner').is_file())
    assert choices,'Android build tools unavailable'
    return choices[-1]

def verify_apk(path,expected_hash,expected_package,signer,build_tools):
    assert re.fullmatch('[0-9a-f]{64}',expected_hash)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected_hash,'Wrong APK input'
    _,badging,_=run(build_tools/'aapt','dump','badging',path)
    assert "name='"+expected_package+"'" in badging.splitlines()[0],'Wrong package'
    _,cert,_=run(build_tools/'apksigner','verify','--print-certs',path)
    hashes=re.findall(r'certificate SHA-256 digest:\s*([a-fA-F0-9]{64})',cert)
    assert [x.lower() for x in hashes]==[signer],'Wrong APK signer'
    return badging

def main():
    global SERIAL
    # Never stop an existing app or change display/network settings on this PC or a phone.
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_OS')=='Linux'
    assert os.environ.get('COUPE_ISOLATED_RENDERER_CI')=='true'
    assert os.environ.get('GITHUB_REPOSITORY')=='SURIDAGEST/coupe-connect-updates'
    OUT.mkdir(exist_ok=True)
    _,devices,_=run('adb','devices')
    live=[line.split()[0] for line in devices.splitlines()[1:] if len(line.split())==2 and line.split()[1]=='device']
    assert len(live)==1 and live[0].startswith('emulator-'),'Exactly one isolated emulator required'
    SERIAL=live[0]
    assert adb('shell','getprop','ro.kernel.qemu')[1].strip()=='1','Physical devices are forbidden'
    installed=adb('shell','pm','list','packages')[1].splitlines()
    assert 'package:'+PACKAGE not in installed and 'package:'+PROBE not in installed,'Fresh emulator required; preserve existing app data'
    expected_api=int(os.environ['EXPECTED_API']);version=int(os.environ.get('EXPECTED_VERSION_CODE','25'))
    assert expected_api in (27,35) and int(adb('shell','getprop','ro.build.version.sdk')[1].strip())==expected_api
    signer=os.environ['EXPECTED_SIGNER_SHA256'];assert re.fullmatch('[0-9a-f]{64}',signer)
    sdk_tools=tools()
    candidate=Path('candidate.apk');probe=Path('probe.apk')
    badging=verify_apk(candidate,os.environ['CAR_SHA256'],PACKAGE,signer,sdk_tools)
    assert "versionCode='"+str(version)+"'" in badging.splitlines()[0]
    assert 'application-debuggable' not in badging,'Production candidate must not be debuggable'
    verify_apk(probe,os.environ['PROBE_SHA256'],PROBE,signer,sdk_tools)
    adb('root');adb('wait-for-device')
    adb('install','--no-streaming','-r',candidate,timeout=180)
    adb('install','--no-streaming','-r',probe,timeout=180)
    # Offline is an explicit emulator fixture; no real maps or network session is claimed.
    adb('shell','svc','wifi','disable',required=False);adb('shell','svc','data','disable',required=False)
    if expected_api>=31:
        for permission in ['BLUETOOTH_CONNECT','BLUETOOTH_SCAN']:
            adb('shell','pm','grant',PACKAGE,'android.permission.'+permission,required=False)
    results=[]
    try:
        for width,height in [(800,480),(1024,600)]:
            label=str(width)+'x'+str(height);folder=OUT/label;folder.mkdir(exist_ok=True)
            # This package was installed by this audit on the fresh, guarded emulator.
            adb('shell','am','force-stop',PACKAGE)
            adb('shell','wm','size',label);adb('shell','wm','density','160')
            code,text,error=instrument(version,folder)
            (folder/'instrumentation.txt').write_text(text+'\n'+error,encoding='utf-8')
            match=re.search(r'^INSTRUMENTATION_RESULT: flow_report=(\{.*\})$',text,re.M)
            assert code==0 and match,'Instrumentation did not return a report: '+label
            report=json.loads(match.group(1));save(label+'/renderer-report.json',report)
            assert report.get('passed') is True and 'INSTRUMENTATION_CODE: -1' in text,'Renderer recovery failed: '+label
            assert report['apkSha256']==os.environ['CAR_SHA256'] and report['versionCode']==version
            for name in ['flow-renderer-before.png','flow-renderer-native.png','flow-renderer-after.png']:
                adb('pull','/data/user/0/'+PACKAGE+'/cache/'+name,folder/name)
                assert (folder/name).stat().st_size>0
            results.append({'viewport':[width,height],'report':label+'/renderer-report.json','passed':True})
        save('summary.json',{'passed':True,'apkSha256':os.environ['CAR_SHA256'],'probeSha256':os.environ['PROBE_SHA256'],
            'api':expected_api,'versionCode':version,'checks':results,'scope':'Actual Android emulator; explicit memory-pressure callback and real renderer termination; no physical phone/iPhone/audio/performance acceptance.'})
    finally:
        _,logs,error=adb('logcat','-d','-v','threadtime',required=False)
        (OUT/'logcat.txt').write_text(logs+'\n'+error,encoding='utf-8')
        _,processes,_=adb('shell','ps','-A',required=False);(OUT/'processes.txt').write_text(processes,encoding='utf-8')

if __name__=='__main__':main()
