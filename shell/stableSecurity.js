
// The dedicated native-backend VM needs a lifetime independent of each UI
// candidate for lock intent and input shielding. The normal headless package
// does not create this actor or alter its input path.
import TgnomeSecurityClutter from 'gi://Clutter';

if (global._tgnomeSecurityVm === true) {
    global._tgnomeSecurityLockRequested ??= false;
    const curtain = global._tgnomeWithBackendLifetime(() => {
        const actor = new St.Widget({
            name: 'tgnomeSecurityCurtain', reactive: true, can_focus: true,
            visible: false, style: 'background-color: black;',
            constraints: new TgnomeSecurityClutter.BindConstraint({
                source: global.stage, coordinate: TgnomeSecurityClutter.BindCoordinate.ALL,
            }),
        });
        global.stage.add_child(actor);
        return actor;
    });
    let grab = null;
    let protections = 0;
    let durableLockRequests = 0;
    global._tgnomeAcceptDurableLock = session => {
        // This handler survives UI registration release and does not capture
        // a ScreenShield. The independent curtain already protects any gap.
        global._tgnomeSecurityLockRequested = true;
        durableLockRequests++;
        session.SetLockedHintAsync(true).catch(error =>
            console.error('TGNOME durable lock hint failed', error));
    };
    global._tgnomeWithBackendLifetime(() => global.stage.connect('child-added', () => {
        // A replacement layout appends a fresh uiGroup to the stage. Keep
        // the independent curtain above it until the protected commit ends.
        if (grab)
            global.stage.set_child_above_sibling(curtain, null);
    }));
    global._tgnomeProtectUiReconstruction = () => {
        if (screenShield?.locked)
            global._tgnomeSecurityLockRequested = true;
        curtain.show();
        global.stage.set_child_above_sibling(curtain, null);
        if (!grab) {
            grab = global.stage.grab(curtain);
            protections++;
        }
        curtain.grab_key_focus();
    };
    global._tgnomeRestoreSecurityBeforeCommit = () => {
        if (!global._tgnomeSecurityLockRequested)
            return;
        if (!screenShield)
            throw new Error('Pending lock has no replacement ScreenShield');
        if (!screenShield.locked)
            screenShield.lock(false);
        if (!screenShield.locked || !screenShield.actor.visible || !modalCount)
            throw new Error('Replacement ScreenShield has not acquired lock input');
    };
    global._tgnomeReleaseSecurityCurtain = () => {
        grab?.dismiss();
        grab = null;
        curtain.hide();
    };
    global._tgnomeGetSecurityBoundary = () => ({
        pendingLock: global._tgnomeSecurityLockRequested,
        curtainVisible: curtain.visible, grabbed: grab !== null, protections,
        topmost: curtain.visible && global.stage.get_last_child() === curtain,
        screenShieldPresent: screenShield !== null,
        pausedWithoutShield: global._tgnomeSecurityGapPaused === true,
        durableLockRequests,
    });
}
