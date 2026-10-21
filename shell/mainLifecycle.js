
// Commit the module binding atomically from the main loop's point of view.
// No evaluation, nested main loop or asynchronous work occurs during transfer.
export function reloadPanel(injectFailure = false) {
    panel = Panel.replacePanel(panel, injectFailure);
    return Panel.panelReloadStatus();
}

export function getPanelReloadStatus() {
    return Panel.panelReloadStatus();
}

export function getPanelTransferStatus() {
    return Panel.panelTransferStatus();
}

global._tgnomeRunPanelTransfer = () => reloadPanel();
global._tgnomeRecoverInterruptedPanelTransfer = () => Panel.recoverInterruptedPanelTransfer();
