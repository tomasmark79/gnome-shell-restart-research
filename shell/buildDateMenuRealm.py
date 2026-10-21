"""Lift all eight dateMenu.js class implementations into one owned UI realm.

Run only in the Nix build tree, after the pinned Shell lifecycle patches.
Registered GTypes remain canonical; even pre-native _init/super calls execute
the original method bodies using a backend WeakMap to select their UI scope.
"""
from pathlib import Path
import re

path = Path('js/ui/dateMenu.js')
source = path.read_text()
matches = list(re.finditer(r'^(?:export )?const (\w+) = GObject.registerClass\(', source, re.M))
names = [match[1] for match in matches]
assert names == ['TodayButton', 'EventsSection', 'WorldClocksSection',
                 'WeatherSection', 'MessagesIndicator', 'FreezableBinLayout',
                 'CalendarColumnLayout', 'DateMenuButton'], names
imports_end = source.index('const NC_ =')
helpers = source[imports_end:matches[0].start()]
proxy_start = helpers.index('const ClocksIntegrationIface =')
proxy_end = helpers.index('\n', helpers.index('const ClocksProxy ='))
proxy = helpers[proxy_start:proxy_end]
helpers = helpers[:proxy_start] + helpers[proxy_end:]
canonical = source[:imports_end] + proxy + '\n\n'
behavior = """// Original method bodies from pinned dateMenu.js, no GType registration.
import 'resource:///org/gnome/gjs/modules/esm/_bootstrap/default.js';
const {Clutter, Gio, GLib, GnomeDesktop, GObject, GWeather, Pango, Shell, St,
    Main, PanelMenu, Calendar, Weather, formatDateWithCFormatString,
    formatTime, clearCachedLocalTimeZone, ClocksProxy, Date, global, _, N_, C_}
    = globalThis._tgnomeUiBackend;
""" + helpers
behavior += """
function dateMenuConnect(emitter, ...args) {
    return globalThis._tgnomeUiBackend.connect(implementation, emitter, args);
}
function dateMenuDisconnect(emitter, id) {
    return globalThis._tgnomeUiBackend.disconnect(implementation, emitter, id);
}
"""
parents = {}
for match in matches:
    name = match[1]
    class_match = re.search(r'class (\w+) extends ([\w.]+) \{', source[match.end():])
    assert class_match[1] == name
    start = match.end() + class_match.start()
    end = source.index('\n});', start) + 4
    assert not source[match.end():start].strip(), 'Unexpected registration metadata'
    original = source[start:end]
    parent = class_match[2]
    parents[name] = parent
    methods = re.findall(r'^    (?!get |set )([A-Za-z_]\w*)\([^\n]*', original, re.M)
    setters = re.findall(r'^    set (\w+)\(', original, re.M)
    getters = re.findall(r'^    get (\w+)\(', original, re.M)
    assert methods[0] == '_init' and not getters, (name, methods, getters)
    lifted = original[:-3].replace(f'class {name} extends', f'class {name}Behavior extends', 1) + '}'
    lifted = re.sub(r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.connect\(',
                    r'dateMenuConnect(\1, ', lifted)
    lifted = re.sub(r'\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.disconnect\(',
                    r'dateMenuDisconnect(\1, ', lifted)
    # Gio.Settings._init is permanent JS. Passing a foreign params prototype
    # lets its missing-property/prototype IC retain the disposable UI realm.
    lifted = lifted.replace('new Gio.Settings(', 'globalThis._tgnomeUiBackend.createSettings(')
    behavior += lifted + '\n'
    canonical += ('export ' if name == 'DateMenuButton' else '')
    canonical += f'const {name} = GObject.registerClass(\nclass {name} extends {parent} {{\n'
    canonical += f'    _init(...args) {{ dateMenuInitialize(this, "{name}", args); }}\n'
    for method in methods[1:]:
        canonical += f'    {method}(...args) {{ return dateMenuDispatch(this, "{name}", "{method}", args); }}\n'
    for setter in setters:
        canonical += f'    set {setter}(value) {{ dateMenuSet(this, "{name}", "{setter}", value); }}\n'
    canonical += '});\n\n'

for name in names[:-1]:
    behavior += f'function {name}(...args) {{ return globalThis._tgnomeUiBackend.createWidget("{name}", implementation, args); }}\n'
behavior += 'export const implementation = {scope: globalThis, prototypes: {\n'
behavior += ',\n'.join(f'    {name}: {name}Behavior.prototype' for name in names)
behavior += '\n}};\n'
Path('js/ui/tgnomeDateMenuRealm.js').write_text(behavior)

canonical += 'const dateMenuClasses = {' + ', '.join(names) + '};\n'
canonical += 'const dateMenuParents = {' + ', '.join(f'{name}: {parent}' for name, parent in parents.items()) + '};\n'
canonical += """
const dateMenuOwners = new WeakMap();
const dateMenuScopes = new WeakMap();
const dateMenuConstruction = [];
const dateMenuRealmRecords = [];
const dateMenuFinalizers = new FinalizationRegistry(({record, kind, name}) => {
    if (kind === 'instance')
        record.collectedInstances[name] = (record.collectedInstances[name] ?? 0) + 1;
    else
        record[kind] = true;
});
const dateMenuBindings = {Clutter, Gio, GLib, GnomeDesktop, GObject, GWeather,
    Pango, Shell, St, Main, PanelMenu, Calendar, Weather,
    formatDateWithCFormatString, formatTime, clearCachedLocalTimeZone,
    ClocksProxy, Date, global, _: globalThis._, N_: globalThis.N_, C_: globalThis.C_,
    createWidget: dateMenuCreateWidget,
    connect: dateMenuConnectOwned, disconnect: dateMenuDisconnectOwned,
    createSettings: params => new Gio.Settings({...params})};

function dateMenuNewScope() {
    if (!globalThis._tgnomeCreateUiRealmModule && !global.tgnome_prepare_ui_realms())
        throw new Error('Date menu realms require the private headless variant');
    const implementation = globalThis._tgnomeCreateUiRealmModule(
        'resource:///org/gnome/shell/ui/tgnomeDateMenuRealm.js', dateMenuBindings);
    const record = {generation: dateMenuRealmRecords.length + 1, retired: false,
        globalCollected: false, implementationCollected: false, failed: false,
        instances: 0, releasedInstances: 0, classes: {}, collectedInstances: {}, calls: {}, retiredCalls: 0,
        connections: 0, disconnected: 0, disconnectFailures: []};
    const scope = {implementation, record, instances: new Set(),
        connections: [], retired: false};
    dateMenuScopes.set(implementation, scope);
    dateMenuRealmRecords.push(record);
    dateMenuFinalizers.register(implementation.scope, {record, kind: 'globalCollected'});
    dateMenuFinalizers.register(implementation, {record, kind: 'implementationCollected'});
    return scope;
}

function dateMenuCreateWidget(name, implementation, args) {
    const scope = dateMenuScopes.get(implementation);
    if (!scope || scope.retired || name === 'DateMenuButton' || !dateMenuClasses[name])
        throw new Error('Invalid date menu construction scope');
    dateMenuConstruction.push(scope);
    try { return Reflect.construct(dateMenuClasses[name], args); }
    finally { dateMenuConstruction.pop(); }
}

function dateMenuConnectOwned(implementation, emitter, args) {
    const scope = dateMenuScopes.get(implementation);
    if (!scope || scope.retired)
        throw new Error('Cannot register a retired date menu callback');
    const id = Reflect.apply(emitter.connect, emitter, args);
    // Owned actors release their callbacks during recursive native destroy.
    // Persistent models/settings/clocks need explicit component teardown.
    if (!(emitter instanceof Clutter.Actor)) {
        scope.connections.push({emitter, id});
        scope.record.connections++;
    }
    return id;
}

function dateMenuDisconnectOwned(implementation, emitter, id) {
    const scope = dateMenuScopes.get(implementation);
    if (scope) {
        const index = scope.connections.findIndex(entry => entry.emitter === emitter && entry.id === id);
        if (index >= 0) {
            scope.connections.splice(index, 1);
            scope.record.disconnected++;
        }
    }
    emitter.disconnect(id);
}

function dateMenuInitialize(object, name, args) {
    const root = name === 'DateMenuButton';
    const scope = root ? dateMenuNewScope() : dateMenuConstruction.at(-1);
    if (!scope || scope.retired)
        throw new Error(`No date menu UI scope for ${name}`);
    // The native GObject may not exist yet. Never read/write its properties
    // before the original implementation calls super._init().
    dateMenuOwners.set(object, {scope, name});
    scope.instances.add(object);
    scope.record.instances++;
    scope.record.classes[name] = (scope.record.classes[name] ?? 0) + 1;
    dateMenuFinalizers.register(object, {record: scope.record, kind: 'instance', name});
    try {
        Reflect.apply(scope.implementation.prototypes[name]._init, object, args);
        if (root)
            object.connect('destroy', dateMenuRootDestroyed);
    } catch (error) {
        scope.record.failed = true;
        if (root) {
            try { object.destroy(); } catch (_) { /* May precede native init. */ }
            dateMenuRetire(scope);
        }
        throw error;
    }
}

function dateMenuDispatch(object, name, method, args) {
    const owner = dateMenuOwners.get(object);
    if (!owner || owner.scope.retired) {
        if (owner)
            owner.scope.record.retiredCalls++;
        if (method.startsWith('vfunc_')) {
            const inherited = dateMenuParents[name].prototype[method];
            if (inherited)
                return Reflect.apply(inherited, object, args);
        }
        return undefined;
    }
    const {scope} = owner;
    const key = `${name}.${method}`;
    scope.record.calls[key] = (scope.record.calls[key] ?? 0) + 1;
    return Reflect.apply(scope.implementation.prototypes[name][method], object, args);
}

function dateMenuSet(object, name, property, value) {
    const owner = dateMenuOwners.get(object);
    if (owner && !owner.scope.retired)
        Reflect.set(owner.scope.implementation.prototypes[name], property, value, object);
}

function dateMenuRootDestroyed(object) {
    const owner = dateMenuOwners.get(object);
    if (owner)
        dateMenuRetire(owner.scope);
}

function dateMenuRetire(scope) {
    if (scope.retired)
        return;
    scope.retired = true;
    scope.record.retired = true;
    for (const {emitter, id} of scope.connections.splice(0).reverse()) {
        try {
            const connected = emitter instanceof GObject.Object
                ? GObject.signal_handler_is_connected(emitter, id)
                : typeof emitter.signalHandlerIsConnected === 'function'
                ? emitter.signalHandlerIsConnected(id) : true;
            if (connected)
                emitter.disconnect(id);
            scope.record.disconnected++;
        } catch (error) {
            scope.record.disconnectFailures.push(String(error));
        }
    }
    // Wait until recursive native destroy and its JS handlers have returned.
    // This source must survive teardown of the current UI generation.
    global._tgnomeWithBackendLifetime(() => GLib.idle_add(
        GLib.PRIORITY_HIGH_IDLE, () => {
            for (const instance of scope.instances)
                dateMenuOwners.delete(instance);
            scope.record.releasedInstances = scope.instances.size;
            scope.instances.clear();
            dateMenuScopes.delete(scope.implementation);
            scope.implementation = null;
            return GLib.SOURCE_REMOVE;
        }));
}

export function getDateMenuRealmStatus() {
    return {scope: 'dateMenu.js class behavior; canonical types and parent classes retained',
        records: dateMenuRealmRecords.map(record => ({...record,
            classes: {...record.classes}, collectedInstances: {...record.collectedInstances},
            calls: {...record.calls}}))};
}
"""
path.write_text(canonical)
resource = Path('js/js-resources.gresource.xml')
text = resource.read_text()
anchor = '<file>ui/dateMenu.js</file>'
assert text.count(anchor) == 1
resource.write_text(text.replace(anchor, anchor + '\n    <file>ui/tgnomeDateMenuRealm.js</file>'))
