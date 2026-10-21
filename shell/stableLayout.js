
LayoutManager.prototype._tgnomeStartupCancelled = function () {
    return this._tgnomeStartupAborted || this._tgnomeDestroying ||
        this._tgnomeCandidate?.cancelled;
};

LayoutManager.prototype.cancelTgnomeStartup = function () {
    if (this._tgnomeStartupAborted)
        return;
    this._tgnomeStartupAborted = true;
    this._bgLoadCancellable?.cancel();
    this._primaryMonitorReadyResolver?.();
    this._primaryMonitorReadyResolver = null;
    this._updateBackgroundsResolvers?.resolve();
    if (this._tgnomeSystemBgLoadedId && this._systemBackground)
        this._systemBackground.disconnect(this._tgnomeSystemBgLoadedId);
    this._tgnomeSystemBgLoadedId = 0;
    this._tgnomeSystemBgResolve?.();
    this._tgnomeSystemBgResolve = null;
    this._systemBackground?.destroy();
    this._systemBackground = null;
    this._coverPane?.destroy();
    this._coverPane = null;
    global.window_group.remove_clip();
};
