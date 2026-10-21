
IBusManager.prototype._createTgnomeCandidatePopup = function () {
    this._candidatePopup = new IBusCandidatePopup.CandidatePopup();
    this._candidatePopup.connect('destroy', () => {
        this._candidatePopup = null;
    });
    if (this._panelService)
        this._candidatePopup.setPanelService(this._panelService);
};
// The persistent manager owns its preload timer even when the new keyboard
// indicator requests a reload outside the manager's construction scope.
const tgnomePreloadEngines = IBusManager.prototype.preloadEngines;
IBusManager.prototype.preloadEngines = function (...args) {
    return global._tgnomeWithBackendLifetime(() =>
        tgnomePreloadEngines.apply(this, args));
};

export function suspendTgnomeCandidatePopup() {
    _ibusManager?._candidatePopup?.setPanelService(null);
    _ibusManager?._candidatePopup?.hide();
}
