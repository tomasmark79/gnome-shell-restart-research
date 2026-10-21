
export function rebindTgnomeLayout() {
    const actions = getDefault();
    actions._tgnomeLayout.disconnect(actions._tgnomeLayoutSignal);
    actions._tgnomeLayout = Main.layoutManager;
    actions._tgnomeLayoutSignal = Main.layoutManager.connect('monitors-changed',
        () => actions._updateOrientationLock());
    actions._updateOrientationLock();
}
