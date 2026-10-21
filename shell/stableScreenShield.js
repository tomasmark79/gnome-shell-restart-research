
ScreenShield.prototype.disposeTgnomeUi = function () {
    if (this._tgnomeDisposed)
        return;
    this._tgnomeDisposed = true;
    // Release these native grabs while Main's modal stack still owns them.
    // Actor destruction may occur after the failed candidate resets that stack.
    this._dialog?.popModal();
    if (this._grab) {
        Main.popModal(this._grab);
        this._grab = null;
    }
    if (this._becameActiveId) {
        this.idleMonitor.remove_watch(this._becameActiveId);
        this._becameActiveId = 0;
    }
    this._inhibitCancellable?.cancel();
    this._inhibitor?.close(null);
    this._inhibitor = null;
    this._inhibited = false;
    if (this._tgnomePresenceSignal) {
        this._presence.disconnectSignal(this._tgnomePresenceSignal);
        this._tgnomePresenceSignal = 0;
    }
};

const lockTgnomeScreenShield = ScreenShield.prototype.lock;
ScreenShield.prototype.lock = function (...args) {
    if (this._tgnomeDisposed)
        return;
    if (global._tgnomeSecurityVm === true)
        global._tgnomeSecurityLockRequested = true;
    return lockTgnomeScreenShield.apply(this, args);
};

for (const method of ['deactivate', '_continueDeactivate', '_completeDeactivate', '_onUserBecameActive']) {
    const original = ScreenShield.prototype[method];
    ScreenShield.prototype[method] = function (...args) {
        if (this._tgnomeDisposed)
            return;
        // A new candidate starts with _isLocked=false. An idle/wake callback
        // must not treat that temporary default as an authenticated unlock.
        if (method === 'deactivate' && global._tgnomeSecurityVm === true &&
            global._tgnomeSecurityLockRequested && !this._isLocked)
            return;
        const result = original.apply(this, args);
        if (method === '_completeDeactivate' && global._tgnomeSecurityVm === true &&
            this === Main.screenShield && !this._isLocked)
            global._tgnomeSecurityLockRequested = false;
        return result;
    };
}
