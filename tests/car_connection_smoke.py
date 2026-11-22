"""Actual API27 UI report and settings entry; no claimed real phone session."""
import car_api27_smoke as base
import json

def main():
    base.main()
    result=json.loads((base.OUT/'result.json').read_text())
    result['passed']=False
    base.save('result.json',result)
    base.start('com.coupe.connect.ConnectionDiagnosticsActivity')
    root=base.wait_ui('connection-diagnostics',['Bluetooth visible en Android:'])
    visible=base.texts(root)
    base.check('diagnosticsFromActualReceiver',all(word in visible for word in ['Radio:','API 27','Ruta Bluetooth:','Paso actual:']))
    base.check('noFalseProjectionClaim','sin sesión confirmada' in visible and 'proyección: ACTIVA' not in visible)
    base.check('diagnosticsNativeNoWebView',not any(n.get('class')=='android.webkit.WebView' for n in root.iter('node')))
    base.adb('shell','am','force-stop','com.coupe.connect')
    base.start('com.andrerinas.openheadunit.main.SettingsActivity')
    root=base.wait_ui('diagnostics-settings-entry',['Comprobar conexión'])
    nodes=[n for n in root.iter('node') if n.get('text')=='Comprobar conexión']
    base.check('diagnosticsSettingsEntryVisible',bool(nodes))
    import re
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

if __name__=='__main__':main()
