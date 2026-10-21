import GLib from 'gi://GLib';
import System from 'system';

// Validate the collection observer independently of GNOME UI ownership.
// This process opens no display or D-Bus connection.
const completed = new Set();
const finalizers = new FinalizationRegistry(name => completed.add(name));
const retained = {purpose: 'positive retention control'};
finalizers.register(retained, 'retained');
(() => finalizers.register({}, 'unreferenced'))();
const loop = new GLib.MainLoop(null, false);
let attempts = 0;
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
    System.gc();
    // queue_finalization_registry_cleanup() alone does not schedule a job.
    Promise.resolve().then(() => {});
    attempts++;
    if (attempts < 3)
        return GLib.SOURCE_CONTINUE;
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
        if (!completed.has('unreferenced') || completed.has('retained'))
            System.exit(1);
        print(`GC observer controls passed; ${retained.purpose}`);
        loop.quit();
        return GLib.SOURCE_REMOVE;
    });
    return GLib.SOURCE_REMOVE;
});
loop.run();
