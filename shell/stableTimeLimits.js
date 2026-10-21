
// Usage accounting belongs to the surviving login session. Rebuilding its UI
// must not stop the model or add artificial active/inactive transitions.
export function createTgnomeBackendManager() {
    return global._tgnomeWithBackendLifetime(() => {
        const backend = callback => global._tgnomeWithBackendLifetime(callback);
        const clock = {
            sourceRemove: GLib.source_remove,
            getRealTimeSecs: () => Math.floor(GLib.get_real_time() / GLib.USEC_PER_SEC),
            getMonotonicTimeSecs: () => Math.floor(GLib.get_monotonic_time() / GLib.USEC_PER_SEC),
            timeoutAddSeconds: (...args) => backend(() => GLib.timeout_add_seconds(...args)),
            timeChangeNotify: callback => backend(() => {
                const source = Shell.time_change_source_new();
                source.set_callback(callback);
                return source.attach(null);
            }),
        };
        const manager = new TimeLimitsManager(null, clock);
        manager._tgnomeRetained = true;
        manager._tgnomeShutdownCalls = 0;
        const shutdown = manager.shutdown.bind(manager);
        manager.shutdown = () => {
            manager._tgnomeShutdownCalls++;
            return shutdown();
        };
        // This is the actual native Shell shutdown signal, not the UI reset
        // signal. Preserve upstream's final asynchronous history flush here.
        global.connect('shutdown', () => {
            const loop = new GLib.MainLoop(null, false);
            const source = GLib.idle_source_new();
            source.set_callback(() => {
                manager.shutdown()
                    .catch(error => console.warn(`Failed to stop time limits manager: ${error.message}`))
                    .finally(() => loop.quit());
                return GLib.SOURCE_REMOVE;
            });
            source.attach(loop.get_context());
            loop.run();
        });
        return manager;
    });
}
