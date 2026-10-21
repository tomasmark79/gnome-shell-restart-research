
function connectTgnomeEmitterDestroy(owner, callback) {
    const connect = () => owner.connect_after('destroy', callback);
    return globalThis.global?._tgnomeWithBackendLifetime?.(connect) ?? connect();
}

function clearTgnomeUiSignalTrackers(manager) {
    const durable = global._tgnomeDurableOwners ?? new Set();
    for (const tracker of [...manager._signalTrackers.values()]) {
        for (const owner of [...tracker._map.keys()]) {
            if (!durable.has(owner))
                tracker.untrack(owner);
        }
    }
}

function trackTgnomeBackendOwner(owner) {
    if (!(global._tgnomeBackendScopeDepth > 0) || owner === globalThis ||
        owner?._tgnomeUiOwned)
        return;
    // This module is also imported by standalone D-Bus workers, which do not
    // load Mutter's Clutter typelib. Query the already registered type instead.
    const actorType = GObject.type_from_name('ClutterActor');
    const isActor = actorType && owner instanceof GObject.Object &&
        GObject.type_is_a(owner.constructor.$gtype, actorType);
    if (!isActor)
        global._tgnomeDurableOwners.add(owner);
}

export function rearmTgnomeUiLifetime() {
    const manager = SignalManager.getDefault();
    global.connect('tgnome-ui-reset', () => {
        clearTgnomeUiSignalTrackers(manager);
    });
}
