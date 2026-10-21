
// Module definitions and GTypes are permanent in the in-place experiment.
// Re-arm only the per-UI lifetime hooks removed by the native reset supervisor.
export function rearmTgnomeUiLifetime() {
    global.connectObject('tgnome-ui-reset', () => sessionSignalHolder.destroy(),
        sessionSignalHolder);
    SignalTracker.rearmTgnomeUiLifetime();
}
