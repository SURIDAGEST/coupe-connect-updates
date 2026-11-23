"""Actual API27 UI report and settings entry; no claimed real phone session."""
import car_api27_smoke as base
import json
import re

strict_wait=base.wait_ui
original_start=base.start
def explicit_start(component,*extras):
    # Shell launches of private activities can leave Settings above the local desktop's task.
    # Ask Android explicitly to show the named desktop, rather than accepting a brought-forward task.
    if component=='com.coupe.connect.MainActivity':extras=('--activity-clear-top',*extras)
    return original_start(component,*extras)
base.start=explicit_start
webview_evidence={}
def actual_ui(name,needles,attempts=8):
    if not name.startswith('dashboard'):return strict_wait(name,needles,attempts)
    # Old WebViews can draw correctly while UIAutomator exposes only the native WebView node.
    # Do not equate absent accessibility text with absent pixels. Preserve images for visual QA.
    for _ in range(attempts):
        root=base.dump(name)
        views=[n for n in root.iter('node') if n.get('class')=='android.webkit.WebView' and n.get('package')=='com.coupe.connect']
        if views:
            bounds=list(map(int,re.findall(r'\d+',views[0].get('bounds',''))))
            if len(bounds)==4 and bounds[2]-bounds[0]>=640 and bounds[3]-bounds[1]>=360:
                base.screenshot(name)
                webview_evidence[name]={'nativeWebViewPresent':True,'bounds':bounds,'accessibilityTextPresent':any(s.lower() in base.texts(root).lower() for s in needles),'requiresScreenshotVisualReview':True}
                base.save('webview-inspection.json',webview_evidence)
                return root
        base.time.sleep(1)
    base.screenshot(name)
    raise AssertionError('Expected actual native WebView absent: '+name)

base.wait_ui=actual_ui

def main():
    base.main()
    result=json.loads((base.OUT/'result.json').read_text())
    result['passed']=False
    base.save('result.json',result)
    base.adb('shell','wm','size','800x480')
    base.start('com.coupe.connect.ConnectionDiagnosticsActivity')
    root=base.wait_ui('connection-diagnostics',['Bluetooth visible en Android:'])
    visible=base.texts(root)
    base.check('diagnosticsFromActualReceiver',all(word in visible for word in ['Radio:','API 27','Ruta Bluetooth:','Paso actual:']))
    base.check('noFalseProjectionClaim','sin sesión confirmada' in visible and 'proyección: ACTIVA' not in visible)
    base.check('diagnosticsNativeNoWebView',not any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    base.adb('shell','am','force-stop','com.coupe.connect')
    # Pin the destination to the compiled settings fragment; do not restore the coordinate picker.
    base.start('com.andrerinas.openheadunit.main.SettingsActivity','--ei','extra_destination',str(0x7f090386))
    root=base.wait_ui('diagnostics-settings-entry',['Comprobar conexión'])
    nodes=[n for n in root.iter('node') if n.get('text')=='Comprobar conexión']
    base.check('diagnosticsSettingsEntryVisible',bool(nodes))
    bounds=list(map(int,re.findall(r'\d+',nodes[0].get('bounds',''))));assert len(bounds)==4
    base.adb('shell','input','tap',(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
    base.wait_ui('diagnostics-opened-from-settings',['Bluetooth visible en Android:'])
    base.check('diagnosticsSettingsEntryWorks',True)
    base.start('com.coupe.connect.MainActivity','--ez','localDesktop','true')
    base.wait_ui('dashboard-after-diagnostics',['Android Auto','Navegación','Teléfono'])
    log=base.adb('logcat','-d')[1];(base.OUT/'logcat-after-diagnostics.txt').write_text(log,encoding='utf-8')
    fatal=bool(re.search(r'FATAL EXCEPTION[^\n]*\n(?:.*\n){0,5}.*Process: com\.coupe\.connect',log))
    anr='ANR in com.coupe.connect' in log
    base.check('noOwnFatalAfterDiagnostics',not fatal);base.check('noOwnAnrAfterDiagnostics',not anr)
    result.update(passed=True,checks=base.CHECKS,postRunErrors={'ownFatal':fatal,'ownAnr':anr},
        scope=result['scope']+' Also tests the actual read-only diagnostic response and settings navigation. Not a repair or test of physical wireless pairing.')
    base.save('result.json',result)

if __name__=='__main__':
    try:main()
    except Exception:
        base.save('result.json',{'passed':False,'checks':base.CHECKS})
        raise
    finally:
        (base.OUT/'final-logcat.txt').write_text(base.adb('logcat','-d')[1],encoding='utf-8')
