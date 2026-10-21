"""Transform the pinned, already lifecycle-patched Panel into a stable GType.

Executed inside the Nix build tree only. Original method bodies are reused in
the disposable module; canonical forwarding methods own the native GType.
"""
from pathlib import Path
import re

path = Path('js/ui/panel.js')
source = path.read_text()
start = source.index('export const Panel = GObject.registerClass(\nclass Panel extends St.Widget {')
end = source.index('\n});', start) + len('\n});')
original = source[start:end]
assert original.count('GObject.registerClass') == 1
init = """        super._init({
            name: 'panel',
            reactive: true,
        });"""
assert original.count(init) == 1
behavior = original.replace('export const Panel = GObject.registerClass(\nclass Panel', 'class PanelBehavior', 1)
behavior = behavior[:-3] + '}'  # replace the final }); with }
behavior = behavior.replace(init, '', 1)
module = """// Generated from the pinned upstream Panel after local lifecycle fixes.
import 'resource:///org/gnome/gjs/modules/esm/_bootstrap/default.js';
const {Clutter, Meta, St, Main, CtrlAltTab, PopupMenu, PanelMenu,
    PANEL_ITEM_IMPLEMENTATIONS, global, _} = globalThis._tgnomeUiBackend;
""" + behavior + "\nexport const implementation = {prototype: PanelBehavior.prototype, scope: globalThis};\n"
Path('js/ui/tgnomePanelRealm.js').write_text(module)

methods = re.findall(r'^    (?!get |set )([A-Za-z_][A-Za-z_0-9]*)\([^\n]*', original, re.M)
assert len(methods) == 19, methods
canonical = """export const Panel = GObject.registerClass(
class Panel extends St.Widget {
    _init(deferMount = false) {
        super._init({name: 'panel', reactive: true});
        if (!globalThis._tgnomeCreateUiRealmModule && !global.tgnome_prepare_ui_realms())
            throw new Error('Panel UI realms require the private headless variant');
        this._tgnomePanelRealm = globalThis._tgnomeCreateUiRealmModule(
            'resource:///org/gnome/shell/ui/tgnomePanelRealm.js', panelRealmBindings);
        const record = {generation: ++panelRealmGeneration, disposed: false,
            globalCollected: false, implementationCollected: false,
            allocations: 0, preferredWidths: 0, keyEvents: 0};
        this._tgnomePanelRealmRecord = record;
        panelRealmRecords.push(record);
        panelRealmFinalizers.register(this._tgnomePanelRealm.scope, {record, kind: 'globalCollected'});
        panelRealmFinalizers.register(this._tgnomePanelRealm, {record, kind: 'implementationCollected'});
        this.connect('destroy', panelRealmDestroyed);
        Reflect.apply(this._tgnomePanelRealm.prototype._init, this, [deferMount]);
    }
"""
for method in methods:
    if method == '_init':
        continue
    counter = {'vfunc_allocate': 'allocations',
               'vfunc_get_preferred_width': 'preferredWidths',
               'vfunc_key_press_event': 'keyEvents'}.get(method)
    canonical += f'    {method}(...args) {{\n'
    if counter:
        canonical += f'        this._tgnomePanelRealmRecord.{counter}++;\n'
    canonical += f'        return Reflect.apply(this._tgnomePanelRealm.prototype.{method}, this, args);\n    }}\n'
canonical += """    get boxOpacity() {
        return Reflect.get(this._tgnomePanelRealm.prototype, 'boxOpacity', this);
    }
    set boxOpacity(value) {
        Reflect.set(this._tgnomePanelRealm.prototype, 'boxOpacity', value, this);
    }
});

const panelRealmBindings = {Clutter, Meta, St, Main, CtrlAltTab, PopupMenu,
    PanelMenu, PANEL_ITEM_IMPLEMENTATIONS, global, _: globalThis._};
let panelRealmGeneration = 0;
const panelRealmRecords = [];
const panelRealmFinalizers = new FinalizationRegistry(({record, kind}) => {
    record[kind] = true;
});
function panelRealmDestroyed(actor) {
    actor._tgnomePanelRealmRecord.disposed = true;
    actor._tgnomePanelRealm = null;
}
export function getPanelRealmStatus() {
    return {scope: 'panel behavior in disposable globals; canonical GType retained',
        records: panelRealmRecords.map(record => ({...record}))};
}
"""
path.write_text(source[:start] + canonical + source[end:])

resource = Path('js/js-resources.gresource.xml')
text = resource.read_text()
anchor = '<file>ui/panel.js</file>'
assert text.count(anchor) == 1
resource.write_text(text.replace(anchor, anchor + '\n    <file>ui/tgnomePanelRealm.js</file>'))
