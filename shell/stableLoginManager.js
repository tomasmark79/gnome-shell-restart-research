
function wireTgnomeSessionSecurity(session) {
    global._tgnomeTrackRootEmitter(session);
    if (global._tgnomeSecurityVm === true && !session._tgnomeDurableLockWired) {
        global._tgnomeWithBackendLifetime(() => session.connectSignal('Lock', () => {
            global._tgnomeWithBackendLifetime(() =>
                global._tgnomeAcceptDurableLock(session));
        }));
        session._tgnomeDurableLockWired = true;
    }
    return session;
}
