
export async function restartTgnomeUiInPlace(serial) {
    global._tgnomeUiReloadState = 'starting';
    global._tgnomeUiBuildSerial = serial;
    const candidate = new TgnomeUiCandidate(serial);
    global._tgnomeCurrentUiCandidate = candidate;
    global._tgnomeAbortUiCandidate = reason => candidate.abort(reason);
    actionMode = Shell.ActionMode.NONE;
    try {
        const environment = await import('./environment.js');
        candidate.check();
        environment.rearmTgnomeUiLifetime();
        // These objects are lazily allocated, unlike the eagerly replaced UI
        // managers in _initializeUI(). Their old actors were destroyed.
        runDialog = null;
        lookingGlass = null;
        welcomeDialog = null;
        // A failed candidate must not inherit globals naming disposed objects
        // from the previous generation. Keep only the explicitly durable
        // sessionMode, window manager and component manager.
        panel = overview = messageTray = screenShield = notificationDaemon = null;
        windowAttentionHandler = ctrlAltTabManager = padOsdService = null;
        osdWindowManager = osdMonitorLabeler = screenshotUI = null;
        shellAccessDialogDBusService = shellAudioSelectionDBusService = null;
        shellDBusService = shellMountOpDBusService = null;
        uiGroup = magnifier = xdndHandler = keyboard = layoutManager = null;
        kbdA11yDialog = inputMethod = introspectService = locatePointer = null;
        endSessionDialog = breakManager = screenTimeDBus = null;
        breakManagerDispatcher = timeLimitsDispatcher = null;
        brightnessManager = brightnessDBus = extensionManager = null;
        wm._tilePreview = null;
        modalActorFocusStack.length = 0;
        modalCount = 0;
        global._tgnomeResetPrepared = false;
        await candidate.wait(start(candidate));
        // The durable window manager's source actor belongs to the old UI
        // group. Replace that helper after the new layout exists.
        wm._windowMenuManager = new TgnomeWindowMenu.WindowMenuManager();
        const systemActions = await import('../misc/systemActions.js');
        candidate.check();
        systemActions.rebindTgnomeLayout();
        if (layoutManager._startingUp) {
            const layout = layoutManager;
            let id = 0;
            const finished = new Promise(resolve => {
                id = layout.connect('startup-complete', () => {
                    layout.disconnect(id);
                    id = 0;
                    resolve();
                });
            });
            try { await candidate.wait(finished); }
            finally { if (id) layout.disconnect(id); }
        }
        inputMethod.rebindTgnomeKeyboard();
        tgnomeUiCheckpoint('post-construction');
        global._tgnomeRestoreSecurityBeforeCommit?.();
        await candidate.wait(global._tgnomeReportUiOutcome('UiStarted', false, serial));
        candidate.committed = true;
        candidate.cancelHandlers.clear();
        if (!screenShield?.locked)
            actionMode = Shell.ActionMode.NORMAL;
        global._tgnomeReleaseSecurityCurtain?.();
        global._tgnomeUiGeneration = (global._tgnomeUiGeneration ?? 0) + 1;
        global._tgnomeUiReloadState = 'started';
    } catch (error) {
        candidate.abort(String(error));
        global._tgnomeUiReloadState = 'failed';
        global._tgnomeUiReloadError = String(error);
        const timedOut = error instanceof TgnomeUiTimeoutError;
        const injected = error instanceof TgnomeInjectedUiError || (timedOut && candidate.injected);
        global._tgnomeUiFailures ??= [];
        global._tgnomeUiFailures.push({build: serial,
            message: String(error), injected, timedOut, stage: error.stage ?? 'unknown'});
        if (injected || timedOut)
            console.warn('TGNOME laboratory UI fault', String(error));
        else
            console.error('TGNOME in-place UI startup failed', error);
        let cleanupReady = false;
        try {
            TgnomeIBus.suspendTgnomeCandidatePopup();
            global.stage.context.get_backend().set_input_method(null);
            inputMethod?.disposeTgnomeUi();
            captureTgnomeUiObjects(`failed-${serial}`);
            const cleanupMode = global._tgnomeCleanupMode;
            global._tgnomeCleanupMode = null;
            if (cleanupMode) {
                global._tgnomeCleanupWait = {serial, mode: cleanupMode, entered: true, released: false};
                if (cleanupMode === 'never')
                    await new Promise(() => {});
                else
                    await new Promise(resolve => global._tgnomeWithBackendLifetime(() =>
                        GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 9000, () => {
                            global._tgnomeCleanupWait.released = true;
                            resolve();
                        })));
            }
            await extensionManager?._disableAllExtensions();
            global._tgnomeReleaseKeybindings();
            global._tgnomeResetPrepared = true;
            cleanupReady = candidate.cancelErrors.length === 0;
        } catch (cleanupError) {
            console.error('TGNOME failure preparation failed', cleanupError);
        }
        try {
            await global._tgnomeReportUiOutcome('UiFailed', cleanupReady, serial);
        } catch (reportError) {
            console.error('TGNOME failure outcome unavailable', reportError);
        }
    } finally {
        if (global._tgnomeCurrentUiCandidate === candidate) {
            global._tgnomeCurrentUiCandidate = null;
            global._tgnomeAbortUiCandidate = null;
        }
    }
}
class TgnomeInjectedUiError extends Error {}
class TgnomeUiTimeoutError extends Error {}

class TgnomeUiCandidate {
    constructor(serial) {
        this.serial = serial;
        this.cancelled = false;
        this.committed = false;
        this.injected = false;
        this.cancelHandlers = new Set();
        this.cancelErrors = [];
        this.aborted = new Promise((_resolve, reject) => { this.reject = reject; });
        this.aborted.catch(() => {});
    }

    check() {
        if (this.cancelled)
            throw this.error;
        if (!this.committed && global._tgnomeCurrentUiCandidate !== this)
            throw new Error('Obsolete UI candidate continuation');
    }

    async wait(operation) {
        const result = await Promise.race([operation, this.aborted]);
        this.check();
        return result;
    }

    abort(reason) {
        if (this.cancelled || this.committed)
            return false;
        this.cancelled = true;
        this.error = new TgnomeUiTimeoutError(reason);
        this.error.stage = this.injectedStage ?? 'construction';
        try {
            for (const cancel of this.cancelHandlers) {
                try { cancel(); }
                catch (error) {
                    this.cancelErrors.push(String(error));
                    console.error('TGNOME candidate cancellation hook failed', error);
                }
            }
        } finally {
            this.cancelHandlers.clear();
            this.reject(this.error);
        }
        return true;
    }
}

export function getTgnomeUiCandidate() {
    return global._tgnomeCurrentUiCandidate ?? null;
}

function checkTgnomeUiCandidate(candidate) {
    candidate?.check();
}

async function waitTgnomeUiCandidate(candidate, operation) {
    return candidate ? candidate.wait(operation) : operation;
}

export async function waitTgnomeStartupProbe(candidate, stage = 'startup-wait') {
    if (!candidate || global._tgnomeUiFailureStage !== stage ||
        !(global._tgnomeUiFailureBudget > 0))
        return;
    global._tgnomeUiFailureBudget--;
    candidate.injected = true;
    candidate.injectedStage = stage;
    const serial = candidate.serial;
    // Leave a full second after the cancellation grace in quarantine tests;
    // the ordinary stale-candidate test still overlaps the corrective build.
    const lateMilliseconds = global._tgnomeCleanupMode ? 8000 : 7000;
    // Deliberately outlive UI source release. The callback has no UI actors;
    // it attempts an obsolete native outcome to test authenticated stale work.
    const late = new Promise(resolve => global._tgnomeWithBackendLifetime(() =>
        GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, lateMilliseconds, () => {
            global._tgnomeLateUiOutcomes ??= [];
            recordTgnomeLateUiOutcome(serial).catch(error =>
                global._tgnomeLateUiOutcomes.push({serial, rejected: false, probeError: String(error)}));
            resolve();
        })));
    await candidate.wait(late);
}

async function waitTgnomeSecurityGapProbe(candidate) {
    if (global._tgnomeSecurityVm !== true || !candidate ||
        global._tgnomeUiFailureStage !== 'security-gap' ||
        !(global._tgnomeUiFailureBudget > 0))
        return;
    global._tgnomeSecurityGapPaused = true;
    try {
        await waitTgnomeStartupProbe(candidate, 'security-gap');
    } finally {
        global._tgnomeSecurityGapPaused = false;
    }
}

async function recordTgnomeLateUiOutcome(serial) {
    const before = await global._tgnomeReportUiOutcome('Status');
    let rejected = false;
    let reason = null;
    try { await global._tgnomeReportUiOutcome('UiStarted', false, serial); }
    catch (error) { rejected = true; reason = String(error); }
    const after = await global._tgnomeReportUiOutcome('Status');
    global._tgnomeLateUiOutcomes.push({serial, rejected, reason,
        before: JSON.parse(before.deep_unpack()[0]), after: JSON.parse(after.deep_unpack()[0])});
}

export function tgnomeUiCheckpoint(stage) {
    if (global._tgnomeUiReloadState !== 'starting' ||
        !(global._tgnomeUiFailureBudget > 0) ||
        (global._tgnomeUiFailureStage ?? 'post-construction') !== stage)
        return;
    global._tgnomeUiFailureBudget--;
    const error = new TgnomeInjectedUiError(`Injected UI failure at ${stage}`);
    error.stage = stage;
    throw error;
}
const tgnomeUiCandidateJournal = new Map();

// A constructor can throw before the assignment to Main.overview occurs.
// Keep that candidate reachable for retirement accounting until cleanup starts.
export function registerTgnomeUiCandidate(name, object) {
    tgnomeUiCandidateJournal.set(name, object);
}
const tgnomeRetiredUi = [];
const tgnomeUiFinalizers = new FinalizationRegistry(record => {
    record.collected = true;
});

function tgnomeDestroyedCallback(record) {
    return () => { record.destroyed = true; };
}

export function captureTgnomeUiObjects(generation = global._tgnomeUiGeneration ?? 0) {
    if (tgnomeRetiredUi.some(record => record.generation === generation))
        return;
    const control = {generation, name: 'unreferenced-control',
        collected: false, destroyed: null, expectedCollected: true};
    tgnomeRetiredUi.push(control);
    tgnomeUiFinalizers.register({}, control);
    const backend = {generation, name: 'retained-backend-control',
        collected: false, destroyed: null, expectedCollected: false};
    tgnomeRetiredUi.push(backend);
    tgnomeUiFinalizers.register(wm, backend);
    for (const [name, object] of Object.entries({
        panel, layoutManager, overview: overview ?? tgnomeUiCandidateJournal.get('overview'),
        extensionManager, inputMethod, keyboard, xdndHandler,
        screenshotUI, messageTray, timeLimitsDispatcher, screenShield,
        screencastAreaIndicator: screenshotUI?._screencastAreaIndicator,
        quickSettings: panel?.statusArea.quickSettings,
    })) {
        if (!object)
            continue; // This candidate failed before constructing the target.
        object._tgnomeRetirement = `${generation}:${name}`;
        const record = {generation, name, collected: false, destroyed: null,
            expectedCollected: true};
        tgnomeUiFinalizers.register(object, record);
        if (object instanceof St.Widget) {
            record.destroyed = false;
            object.connect('destroy', tgnomeDestroyedCallback(record));
        }
        tgnomeRetiredUi.push(record);
    }
    tgnomeUiCandidateJournal.clear();
}

export function getTgnomeRetiredUiStatus() {
    return tgnomeRetiredUi.map(record => ({...record}));
}

import * as TgnomeWindowMenu from './windowMenu.js';
import * as TgnomeIBus from '../misc/ibusManager.js';

// The swipe tracker's transform binding holds a native callback referencing
// the tracker. Dispose it while its UI actors still exist, before detaching
// stage gestures and destroying the old UI group.
global._tgnomeBeforeUiTeardown = () => {
    global._tgnomeProtectUiReconstruction?.();
    screenShield?.disposeTgnomeUi();
    layoutManager?.cancelTgnomeStartup();
    overview?._swipeTracker?.destroy();
    if (timeLimitsDispatcher?._manager)
        timeLimitsDispatcher.destroy();
};
