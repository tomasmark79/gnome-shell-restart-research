// Prepended only to the stable-context init module. Its imports are provided
// by runtimeInit.js in the same generated ES module.
const exportedObjects = new Set();
const exportLocations = new Map();
const ownedNames = new Map();
const watchedNames = new Map();
const permanentExports = new Set();
const exportDelegates = new WeakMap();
const nativeGlobal = Shell.Global.get();
nativeGlobal._tgnomeBackendScopeDepth = 0;
nativeGlobal._tgnomeDurableOwners = new Set();
nativeGlobal._tgnomeDurableBindings = new Set();
nativeGlobal._tgnomeWithBackendExecution = callback => {
    const nativeGuard = typeof nativeGlobal.tgnome_backend_scope === 'function';
    if (nativeGuard && !nativeGlobal.tgnome_backend_scope(true))
        throw new Error('Native backend lifetime protection could not be entered');
    try {
        return callback();
    } finally {
        if (nativeGuard && !nativeGlobal.tgnome_backend_scope(false))
            throw new Error('Native backend lifetime protection is unbalanced');
    }
};
nativeGlobal._tgnomeWithBackendLifetime = callback =>
    nativeGlobal._tgnomeWithBackendExecution(() => {
        nativeGlobal._tgnomeBackendScopeDepth++;
        try {
            const result = callback();
            if (result && !result._tgnomeUiOwned &&
                (typeof result === 'object' || typeof result === 'function'))
                nativeGlobal._tgnomeDurableOwners.add(result);
            return result;
        } finally {
            nativeGlobal._tgnomeBackendScopeDepth--;
        }
    });
nativeGlobal._tgnomeWrapBackendCallback = callback => {
    if (typeof nativeGlobal.tgnome_backend_scope !== 'function' ||
        !(nativeGlobal._tgnomeBackendScopeDepth > 0) || typeof callback !== 'function')
        return callback;
    // Protect execution, without promoting return values or changing the
    // allocation lifetime of resources made by a later callback.
    return function (...args) {
        return nativeGlobal._tgnomeWithBackendExecution(() => callback.apply(this, args));
    };
};
const wrapObject = Gio.DBusExportedObject.wrapJSObject;
Gio.DBusExportedObject.wrapJSObject = function (info, delegate) {
    const object = wrapObject.call(this, info, delegate);
    exportDelegates.set(object, delegate);
    if (nativeGlobal._tgnomeBackendScopeDepth)
        permanentExports.add(object);
    return object;
};

const exportObject = Gio.DBusExportedObject.prototype.export;
const unexportObject = Gio.DBusExportedObject.prototype.unexport;
Gio.DBusExportedObject.prototype.export = function (...args) {
    const result = exportObject.apply(this, args);
    // System-bus agents belong to durable backend components, not to UI.
    if (args[0] === Gio.DBus.session) {
        exportedObjects.add(this);
        exportLocations.set(this, `${args[1]}:${this.get_info().name}`);
    } else {
        const delegate = exportDelegates.get(this);
        if (delegate)
            nativeGlobal._tgnomeDurableOwners.add(delegate);
    }
    return result;
};
Gio.DBusExportedObject.prototype.unexport = function (...args) {
    exportedObjects.delete(this);
    exportLocations.delete(this);
    permanentExports.delete(this);
    return unexportObject.apply(this, args);
};
const ownName = Gio.DBusConnection.prototype.own_name;
const unownName = Gio.DBusConnection.prototype.unown_name;
Gio.DBusConnection.prototype.own_name = function (...args) {
    const id = ownName.apply(this, args);
    ownedNames.set(id, {connection: this, name: args[0],
        permanent: nativeGlobal._tgnomeBackendScopeDepth > 0});
    return id;
};
Gio.DBusConnection.prototype.unown_name = function (id) {
    ownedNames.delete(id);
    return unownName.call(this, id);
};
for (const name of ['bus_own_name', 'bus_own_name_on_connection']) {
    const original = Gio[name];
    Gio[name] = function (...args) {
        const id = original.apply(Gio, args);
        ownedNames.set(id, {name: args[1],
            permanent: nativeGlobal._tgnomeBackendScopeDepth > 0});
        return id;
    };
}
const unownBusName = Gio.bus_unown_name;
Gio.bus_unown_name = function (id) {
    ownedNames.delete(id);
    return unownBusName.call(Gio, id);
};
for (const name of ['bus_watch_name', 'bus_watch_name_on_connection']) {
    const original = Gio[name];
    Gio[name] = function (...args) {
        const id = original.apply(Gio, args);
        watchedNames.set(id, {name: args[1],
            permanent: nativeGlobal._tgnomeBackendScopeDepth > 0});
        return id;
    };
}
const unwatchBusName = Gio.bus_unwatch_name;
Gio.bus_unwatch_name = function (id) {
    watchedNames.delete(id);
    return unwatchBusName.call(Gio, id);
};

const signalTargets = new Set([nativeGlobal, nativeGlobal.context, nativeGlobal.settings, nativeGlobal.display,
    nativeGlobal.window_manager, nativeGlobal.stage, nativeGlobal.window_group,
    nativeGlobal.top_window_group]);
const signalRecords = new Map();
const rootEmitterRecords = new Map();
nativeGlobal._tgnomeTrackRootEmitter = emitter => {
    if (!emitter || rootEmitterRecords.has(emitter))
        return emitter;
    const records = new Map();
    rootEmitterRecords.set(emitter, records);
    if (emitter instanceof GObject.Object)
        signalTargets.add(emitter);
    // Plain JS signals and DBus connectSignal() bypass GObject.connect().
    // Track only selected persistent roots, with separate ID namespaces.
    const pairs = emitter instanceof GObject.Object
        ? [['connectSignal', 'disconnectSignal']]
        : [['connect', 'disconnect']];
    for (const [connectName, disconnectName] of pairs) {
        if (typeof emitter[connectName] !== 'function')
            continue;
        const connect = emitter[connectName];
        const disconnect = emitter[disconnectName];
        emitter[connectName] = function (...args) {
            args[1] = nativeGlobal._tgnomeWrapBackendCallback(args[1]);
            const id = connect.apply(this, args);
            records.set(id, {signal: args[0], disconnectName,
                durable: nativeGlobal._tgnomeBackendScopeDepth > 0});
            return id;
        };
        emitter[disconnectName] = function (id) {
            records.delete(id);
            return disconnect.call(this, id);
        };
    }
    return emitter;
};
const stageActions = new Map();
for (const name of ['add_action', 'add_action_full']) {
    const original = nativeGlobal.stage[name];
    nativeGlobal.stage[name] = function (...args) {
        const result = original.apply(this, args);
        stageActions.set(args[name === 'add_action' ? 0 : 2],
            nativeGlobal._tgnomeBackendScopeDepth > 0);
        return result;
    };
}
for (const name of ['connect', 'connect_after']) {
    const original = GObject.Object.prototype[name];
    GObject.Object.prototype[name] = function (...args) {
        const id = original.apply(this, args);
        if (signalTargets.has(this)) {
            if (!signalRecords.has(this))
                signalRecords.set(this, new Map());
            signalRecords.get(this).set(id, {
                durable: nativeGlobal._tgnomeBackendScopeDepth > 0,
                signal: args[0],
                site: new Error().stack.split('\n').find(line =>
                    line.includes('resource:///org/gnome/shell/') &&
                    !['/ui/init.js:', '/misc/signalTracker.js:', '/ui/environment.js:']
                        .some(path => line.includes(path))) ?? 'unknown'});
        }
        return id;
    };
}
const disconnectSignal = GObject.Object.prototype.disconnect;
GObject.Object.prototype.disconnect = function (id) {
    signalRecords.get(this)?.delete(id);
    return disconnectSignal.call(this, id);
};
function countSignals() {
    let total = 0;
    let permanent = 0;
    const inventory = [];
    for (const [emitter, records] of signalRecords) {
        for (const [id, info] of records) {
            if (!GObject.signal_handler_is_connected(emitter, id)) {
                records.delete(id);
                continue;
            }
            total++;
            permanent += info.durable ? 1 : 0;
            const site = info.signal === 'workareas-changed' ? `:${info.site}` : '';
            inventory.push(`${GObject.type_name(emitter.constructor.$gtype)}:${info.signal}:${info.durable ? 'backend' : 'ui'}${site}`);
        }
    }
    for (const [emitter, records] of rootEmitterRecords) {
        for (const info of records.values()) {
            total++;
            permanent += info.durable ? 1 : 0;
            inventory.push(`${emitter.constructor.name}:${info.signal}:${info.durable ? 'backend' : 'ui'}`);
        }
    }
    return {total, permanent, inventory: inventory.sort()};
}
function pruneStageActions() {
    const attached = new Set(nativeGlobal.stage.get_actions());
    for (const action of stageActions.keys()) {
        if (!attached.has(action))
            stageActions.delete(action);
    }
}
nativeGlobal._tgnomeReleaseUiStageActions = () => {
    nativeGlobal._tgnomeBeforeUiTeardown?.();
    pruneStageActions();
    for (const [action, durable] of [...stageActions]) {
        if (!durable) {
            if (action.get_actor() === nativeGlobal.stage)
                nativeGlobal.stage.remove_action(action);
            stageActions.delete(action);
        }
    }
};
nativeGlobal._tgnomeReleaseUiRegistrations = () => {
    const counts = {exports: exportedObjects.size, ownedNames: ownedNames.size,
        signals: countSignals(), stageActions: stageActions.size,
        watchedNames: watchedNames.size};
    nativeGlobal._tgnomeReleaseUiStageActions();
    for (const object of [...exportedObjects]) {
        if (!permanentExports.has(object))
            object.unexport();
    }
    for (const [id, info] of [...ownedNames]) {
        if (!info.permanent)
            Gio.bus_unown_name(id);
    }
    for (const [id, info] of [...watchedNames]) {
        if (!info.permanent)
            Gio.bus_unwatch_name(id);
    }
    for (const [emitter, records] of signalRecords) {
        for (const [id, info] of [...records]) {
            if (!info.durable && GObject.signal_handler_is_connected(emitter, id))
                emitter.disconnect(id);
        }
    }
    for (const [emitter, records] of rootEmitterRecords) {
        for (const [id, info] of [...records]) {
            if (!info.durable)
                emitter[info.disconnectName](id);
        }
    }
    nativeGlobal._tgnomeLastReleasedRegistrations = counts;
};
nativeGlobal._tgnomeGetUiRegistrationCounts = () => {
    pruneStageActions();
    return {exports: exportedObjects.size,
    ownedNames: ownedNames.size, signals: countSignals(),
    permanentExports: permanentExports.size,
    stageActions: stageActions.size,
    watchedNames: watchedNames.size,
    exportInventory: [...exportLocations.values()].sort(),
    nameInventory: [...ownedNames.values()].map(info => info.name).sort(),
    watchInventory: [...watchedNames.values()].map(info => info.name).sort()};
};
