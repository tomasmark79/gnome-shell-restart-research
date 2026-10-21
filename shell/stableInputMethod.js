
InputMethod.prototype.rebindTgnomeKeyboard = function () {
    const keyboard = Main.keyboard;
    if (this._tgnomeDisposed || !keyboard || this._tgnomeKeyboard === keyboard)
        return;
    this._tgnomeKeyboard?.disconnectObject(this);
    this._tgnomeKeyboard = keyboard;
    keyboard.connectObject('visibility-changed', () => this._updateCapabilities(), this);
    this._updateCapabilities();
};

InputMethod.prototype.disposeTgnomeUi = function () {
    if (this._tgnomeDisposed)
        return;
    this._tgnomeDisposed = true;
    const context = this._context;
    this._clear();
    this._ibus.disconnectObject(this);
    this._inputSourceManager.disconnectObject(this);
    context?.destroy();
};
