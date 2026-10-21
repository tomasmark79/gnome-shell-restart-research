
// BackgroundManager owns a reference to the schema's cached BackgroundSource.
// Destroying only its actors leaves that source retaining the retired layout.
const destroyTgnomeUnlockDialog = UnlockDialog.prototype._onDestroy;
UnlockDialog.prototype._onDestroy = function (...args) {
    for (const manager of this._bgManagers ?? [])
        manager.destroy();
    this._bgManagers = [];
    return destroyTgnomeUnlockDialog.apply(this, args);
};
