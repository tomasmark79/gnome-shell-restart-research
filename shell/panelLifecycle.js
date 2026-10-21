
// Development-only ownership boundary. Appended to upstream panel.js by the
// local Nix override, so it uses that module's exact GNOME 50.5 classes/imports.
// Indicator instances and their service connections outlive the panel actor.
let reloadGeneration = 0;
let panelActorsDestroyed = 0;
let panelTransfer = null;
const retiredPanelTransfers = [];
const panelTransferFinalizers = new FinalizationRegistry(record => { record.collected = true; });

export function panelTransferStatus() {
    return {pending: panelTransfer !== null,
        retired: retiredPanelTransfers.map(record => ({...record}))};
}

// The interrupted JS frame cannot run catch/finally. Keep the transaction
// outside that frame until native recovery has explicitly settled it.
export function recoverInterruptedPanelTransfer(interrupted = true) {
    if (!panelTransfer)
        return null;
    const {oldPanel, replacement, entries, record} = panelTransfer;
    if (!['detaching', 'detached', 'adopting'].includes(record.phase))
        throw new Error(`Panel transfer cannot roll back phase ${record.phase}`);
    record.adoptedBeforeRecovery = Object.keys(replacement.statusArea).length;
    record.interrupted = interrupted;
    if (!retiredPanelTransfers.includes(record))
        retiredPanelTransfers.push(record);
    releaseIndicators(replacement, entries);
    replacement.destroy();
    adoptIndicators(oldPanel, entries);
    const boxes = [oldPanel._leftBox, oldPanel._centerBox, oldPanel._rightBox];
    record.oldPanelRestored = entries.every(({role, indicator, boxIndex, position, visible}) =>
        oldPanel.statusArea[role] === indicator &&
        indicator.container.get_parent() === boxes[boxIndex] &&
        boxes[boxIndex].get_children().indexOf(indicator.container) === position &&
        indicator.container.visible === visible);
    if (!record.oldPanelRestored)
        throw new Error('Interrupted panel indicators were not restored');
    record.recovered = true;
    panelTransfer = null;
    return {...record};
}

export function panelReloadStatus() {
    return {generation: reloadGeneration, destroyed: panelActorsDestroyed,
        scope: 'panel actor/layout/gestures/menu manager; indicator instances survive'};
}

function snapshotIndicators(panel) {
    const entries = Object.entries(panel.statusArea).map(([role, indicator]) => {
        const parent = indicator.container.get_parent();
        const boxes = [panel._leftBox, panel._centerBox, panel._rightBox];
        const boxIndex = boxes.indexOf(parent);
        if (boxIndex < 0)
            throw new Error(`Unsupported detached indicator ${role}`);
        return {role, indicator, boxIndex,
            position: parent.get_children().indexOf(indicator.container),
            visible: indicator.container.visible};
    });
    const containers = new Set(entries.map(entry => entry.indicator.container));
    if ([panel._leftBox, panel._centerBox, panel._rightBox]
        .some(box => box.get_children().some(child => !containers.has(child))))
        throw new Error('Unsupported panel children outside statusArea');
    if (panel.menuManager._menus.some(menu =>
        !entries.some(entry => entry.indicator.menu === menu)))
        throw new Error('Unsupported additional panel menus');
    return entries;
}

function releaseIndicators(panel, entries) {
    for (const {indicator} of entries) {
        indicator.menu?.close(0);
        if (indicator.menu) {
            panel.menuManager.removeMenu(indicator.menu);
            indicator.menu.disconnectObject(panel);
            delete indicator.menu._openChangedConnected;
        }
        indicator.disconnectObject(panel);
        const parent = indicator.container.get_parent();
        if (parent)
            parent.remove_child(indicator.container);
    }
    panel.statusArea = {};
}

function adoptIndicators(panel, entries, injectFailure = false) {
    const boxes = [panel._leftBox, panel._centerBox, panel._rightBox];
    for (const entry of [...entries].sort((a, b) => a.position - b.position)) {
        panel._addToPanelBox(entry.role, entry.indicator, entry.position,
            boxes[entry.boxIndex]);
        entry.indicator.container.visible = entry.visible;
        if (panelTransfer?.replacement === panel)
            global._tgnomePanelTransferCheckpoint?.('adopting');
        if (injectFailure)
            throw new Error('Injected panel adoption failure');
    }
}

export function replacePanel(oldPanel, injectFailure = false) {
    if (panelTransfer)
        throw new Error('A panel transfer is awaiting recovery');
    if (GLib.getenv('TGNOME_ALLOW_PANEL_RELOAD') !== '1')
        throw new Error('Panel reload is restricted to an isolated development Shell');
    if (Main.modalCount || Main.overview.visible || Main.sessionMode.currentMode !== 'user')
        throw new Error('Close menus and overview in an unlocked user session first');
    if (injectFailure && GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
        throw new Error('Fault injection is disabled');

    const entries = snapshotIndicators(oldPanel);
    // Construct before detaching the current panel. Services are not created
    // because the deferred constructor does not initialize status indicators.
    const replacement = new Panel(true);
    replacement.style = oldPanel.style;
    replacement._sessionStyle = oldPanel._sessionStyle;
    if (replacement._sessionStyle)
        replacement.add_style_class_name(replacement._sessionStyle);
    const record = {phase: 'detaching', entries: entries.length,
        adoptedBeforeRecovery: null, recovered: false, oldPanelRestored: false,
        destroyed: false, collected: false};
    panelTransfer = {oldPanel, replacement, entries, record};
    replacement.connect('destroy', () => { record.destroyed = true; });
    panelTransferFinalizers.register(replacement, record);
    try {
        releaseIndicators(oldPanel, entries);
        record.phase = 'detached';
        global._tgnomePanelTransferCheckpoint?.('detached');
        record.phase = 'adopting';
        adoptIndicators(replacement, entries, injectFailure);
        record.phase = 'attaching';
        Main.layoutManager.panelBox.add_child(replacement);
        Main.ctrlAltTabManager.addGroup(replacement,
            _('Top Bar'), 'shell-focus-top-bar-symbolic',
            {sortGroup: CtrlAltTab.SortGroup.TOP});
    } catch (error) {
        // Detach any partially adopted objects before destroying the staged
        // actor. Restore the original panel exactly once; never restart Mutter.
        // Synchronous construction/registration errors still use the same
        // rollback; no interruption checkpoint runs during final attachment.
        record.phase = 'adopting';
        recoverInterruptedPanelTransfer(false);
        throw error;
    }
    oldPanel.connect('destroy', () => panelActorsDestroyed++);
    oldPanel.destroy();
    reloadGeneration++;
    panelTransfer = null;
    return replacement;
}
