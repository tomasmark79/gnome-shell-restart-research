// This registry belongs to one complete GJS runtime. Track only registrations
// made through its JS wrappers; native Mutter watches and redraw work survive.
import TgnomeMeta from 'gi://Meta';

const tgnomeNativeWork = new Map();
function tgnomeTrackNativeWork(prototype, addName, removeName, completion) {
    const add = prototype[addName];
    const remove = prototype[removeName];
    prototype[addName] = function (...args) {
        const owner = this;
        if (!tgnomeNativeWork.has(owner))
            tgnomeNativeWork.set(owner, new Map());
        const work = tgnomeNativeWork.get(owner);
        const callbackIndex = args.length - 1;
        const callback = args[callbackIndex];
        let id = 0;
        args[callbackIndex] = function (...parameters) {
            const keep = callback.apply(this, parameters);
            if (completion === 'once' || (completion === 'boolean' && !keep))
                work.delete(id);
            return keep;
        };
        id = add.apply(owner, args);
        work.set(id, () => remove.call(owner, id));
        return id;
    };
    prototype[removeName] = function (id) {
        tgnomeNativeWork.get(this)?.delete(id);
        return remove.call(this, id);
    };
}
tgnomeTrackNativeWork(TgnomeMeta.Laters.prototype, 'add', 'remove', 'boolean');
tgnomeTrackNativeWork(TgnomeMeta.IdleMonitor.prototype, 'add_idle_watch', 'remove_watch');
tgnomeTrackNativeWork(TgnomeMeta.IdleMonitor.prototype, 'add_user_active_watch', 'remove_watch', 'once');

function tgnomeReleaseNativeWork() {
    for (const tracker of global._tgnomeFocusTrackers ?? []) {
        tracker.deregisterFocusListener();
        tracker.deregisterCaretListener();
        tracker._atspiListener.disconnect(tracker._tgnomeListenerSignal);
        tracker._atspiListener = null;
    }
    global._tgnomeFocusTrackers?.clear();
    let count = 0;
    for (const work of tgnomeNativeWork.values()) {
        for (const remove of work.values()) {
            remove();
            count++;
        }
        work.clear();
    }
    tgnomeNativeWork.clear();
    console.info(`TGNOME removed ${count} remaining JS Mutter registrations`);
    System.gc();
}
