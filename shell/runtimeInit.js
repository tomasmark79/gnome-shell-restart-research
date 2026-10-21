import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import System from 'system';

// A context must not leave GLib callbacks that will later enter disposed JS.
// Capture only sources created by this generation's JS APIs; Mutter's native
// event sources and the C reset supervisor are outside this registry.
const sourceIds = new Set();
const durableSourceIds = new Set();
const removeSource = GLib.source_remove;
GLib.source_remove = function (id) {
    if (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') === '1' &&
        !GLib.MainContext.default().find_source_by_id(id))
        console.error(`TGNOME stale source removal ${id}`, new Error().stack);
    sourceIds.delete(id);
    durableSourceIds.delete(id);
    return removeSource.call(GLib, id);
};
for (const name of ['idle_add', 'idle_add_once', 'timeout_add', 'timeout_add_once',
    'timeout_add_seconds', 'timeout_add_seconds_once']) {
    if (typeof GLib[name] !== 'function')
        continue;
    const original = GLib[name];
    const once = name.endsWith('_once');
    GLib[name] = function (...args) {
        const index = args.length - 1;
        // Native GJS closures capture protection at callback creation. This
        // wrapper only accounts for source ownership and completion.
        const callback = args[index];
        let id = 0;
        args[index] = (...parameters) => {
            if (once)
                sourceIds.delete(id);
            if (once)
                durableSourceIds.delete(id);
            const keep = callback(...parameters);
            if (!keep)
                sourceIds.delete(id);
            if (!keep)
                durableSourceIds.delete(id);
            return keep;
        };
        id = original.apply(GLib, args);
        sourceIds.add(id);
        if (Shell.Global.get()._tgnomeBackendScopeDepth > 0)
            durableSourceIds.add(id);
        return id;
    };
}
const sourceExecution = new WeakMap();
function sourceExecutionToken(source) {
    if (!sourceExecution.has(source))
        sourceExecution.set(source, {protected: false});
    return sourceExecution.get(source);
}
if (typeof Shell.Global.get().tgnome_backend_scope === 'function') {
    const setCallback = GLib.Source.prototype.set_callback;
    GLib.Source.prototype.set_callback = function (callback, ...args) {
        if (typeof callback !== 'function')
            return setCallback.call(this, callback, ...args);
        const token = sourceExecutionToken(this);
        token.protected ||= Shell.Global.get()._tgnomeBackendScopeDepth > 0;
        return setCallback.call(this, function (...parameters) {
            const invoke = () => callback.apply(this, parameters);
            return token.protected
                ? Shell.Global.get()._tgnomeWithBackendExecution(invoke) : invoke();
        }, ...args);
    };
}
const attachSource = GLib.Source.prototype.attach;
GLib.Source.prototype.attach = function (...args) {
    const id = attachSource.call(this, ...args);
    sourceIds.add(id);
    if (Shell.Global.get()._tgnomeBackendScopeDepth > 0) {
        durableSourceIds.add(id);
        if (typeof Shell.Global.get().tgnome_backend_scope === 'function')
            sourceExecutionToken(this).protected = true;
    }
    return id;
};

// Native main.c owns Mutter's one long-lived loop. The module evaluation must
// return before that loop starts, and before any future GJS context disposal.
const epoch = GLib.uuid_string_random();
if (GLib.getenv('TGNOME_UNIQUE_GTYPE_PROBE') === '1') {
    // Research only: static GTypes cannot be unregistered on context disposal.
    // Unique names let one bounded experiment investigate the next blocker;
    // retained type registrations explicitly disqualify this as a final design.
    const registerClass = GObject.registerClass;
    let serial = 0;
    GObject.registerClass = function (metadata, klass) {
        if (klass === undefined) {
            klass = metadata;
            metadata = {};
        }
        const name = (metadata.GTypeName ?? klass.name).replace(/[^A-Za-z0-9_]/g, '_');
        const GTypeName = `TgnomeRT_${epoch.replaceAll('-', '')}_${name}_${++serial}`;
        return registerClass({...metadata, GTypeName}, klass);
    };
}
GLib.idle_add_once(GLib.PRIORITY_DEFAULT, () => {
    import('./environment.js').then(() => {
        global._tgnomeRuntimeEpoch = epoch;
        global._tgnomeUiGeneration = 0;
        global._tgnomeReportUiOutcome = (method, cleanupReady = false,
            serial = global._tgnomeUiBuildSerial ?? 0) =>
            new Promise((resolve, reject) => {
                Gio.DBus.session.call(Gio.DBus.session.get_unique_name(),
                    '/org/gnome/Shell/TgnomeRuntime', 'org.gnome.Shell.TgnomeRuntime',
                    method, method === 'UiFailed'
                        ? new GLib.Variant('(ub)', [serial, cleanupReady])
                        : method === 'UiStarted' ? new GLib.Variant('(u)', [serial]) : null,
                    null, Gio.DBusCallFlags.NONE, 5000, null,
                    (connection, result) => {
                        try { resolve(connection.call_finish(result)); }
                        catch (error) { reject(error); }
                    });
            });
        global._tgnomeCollectGarbage = () => {
            System.gc();
            // GJS 1.88.1 queues finalizer cleanup without scheduling a job.
            // Enqueue one so its normal job dispatcher runs pending cleanup.
            Promise.resolve().then(() => {});
        };
        global._tgnomeDumpUiHeap = () => {
            const path = GLib.build_filenamev([global.userdatadir, 'tgnome-ui.heap']);
            System.dumpHeap(path);
            return path;
        };
        global._tgnomeRestartUiInPlace = serial => import('./main.js')
            .then(main => main.restartTgnomeUiInPlace(serial));
        global._tgnomeReleaseSources = () => {
            let removed = 0;
            const context = GLib.MainContext.default();
            for (const id of sourceIds) {
                const source = context.find_source_by_id(id);
                if (source && !durableSourceIds.has(id)) {
                    source.destroy();
                    removed++;
                }
                if (!source || !durableSourceIds.has(id))
                    sourceIds.delete(id);
                if (!source)
                    durableSourceIds.delete(id);
            }
            console.info(`TGNOME removed ${removed} remaining JS event sources`);
            return removed;
        };
        const bindings = new Set();
        const addKeybinding = global.display.add_keybinding;
        global.display.add_keybinding = function (name, ...args) {
            const result = addKeybinding.call(this, name, ...args);
            if (result !== 0)
                bindings.add(name);
            if (result !== 0 && global._tgnomeBackendScopeDepth > 0)
                global._tgnomeDurableBindings.add(name);
            return result;
        };
        global._tgnomeReleaseKeybindings = () => {
            let count = 0;
            for (const name of [...bindings]) {
                if (global._tgnomeDurableBindings?.has(name))
                    continue;
                global.display.remove_keybinding(name);
                bindings.delete(name);
                count++;
            }
            return count;
        };
        return import('./main.js');
    }).then(main => main.start()).catch(error => {
        // Experimental reset failures must not intentionally terminate Mutter.
        // A broken UI is recorded while the native loop remains inspectable.
        console.error('TGNOME runtime startup failed', error);
    });
});
