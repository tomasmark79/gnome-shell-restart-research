import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Clutter from 'gi://Clutter';
import System from 'system';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const PATH = '/org/gnome/Shell/Extensions/Tgnome';
let actorsCreated = 0;
let actorsDestroyed = 0;
const IFACE = `<node><interface name="org.gnome.Shell.Extensions.Tgnome">
<method name="Status"><arg type="s" direction="out"/></method>
<method name="ReloadUI"><arg type="b" direction="in"/><arg type="s" direction="out"/></method>
<method name="ReloadTheme"><arg type="s" direction="out"/></method>
<method name="ReloadPanel"><arg type="b" direction="in"/><arg type="s" direction="out"/></method>
<method name="ExercisePanel"><arg type="s" direction="out"/></method>
<method name="ExerciseDateMenuRealm"><arg type="s" direction="out"/></method>
<method name="SetTestOverview"><arg type="b" direction="in"/><arg type="s" direction="out"/></method>
<method name="PrepareRuntimeReset"><arg type="s" direction="out"/></method>
<method name="ReloadDesktopUi"><arg type="s" direction="out"/></method>
<method name="ArmOwnedDelay"><arg type="u" direction="in"/><arg type="s" direction="out"/></method>
<method name="ArmPreparationFault"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="ArmCleanupMode"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="ExerciseQuarantineRefusals"><arg type="s" direction="out"/></method>
<method name="ExercisePolicyRetirement"><arg type="s" direction="out"/></method>
<method name="CollectUiGarbage"><arg type="s" direction="out"/></method>
<method name="ExerciseWindowMenu"><arg type="s" direction="out"/></method>
<method name="DumpUiHeap"><arg type="s" direction="out"/></method>
<method name="ArmUiFailure"><arg type="u" direction="in"/><arg type="s" direction="out"/></method>
<method name="ArmUiFailureAt"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="out"/></method>
<method name="PrepareTestKeyboard"><arg type="s" direction="out"/></method>
<method name="TypeIntoProbe"><arg type="u" direction="in"/><arg type="s" direction="out"/></method>
<method name="CaptureTestFrame"><arg type="s" direction="out"/></method>
<method name="ArrangeProbeWindows"><arg type="s" direction="out"/></method>
<method name="ExerciseNativeOverview"><arg type="s" direction="out"/></method>
</interface></node>`;

// Only this object owns the restartable actors. Never destroy Main.panel,
// Main.layoutManager, window actors, global.stage or the GJS context.
function assertPanelTransferSettled() {
    if (Main.getPanelTransferStatus?.().pending)
        throw new Gio.IOErrorEnum({code: Gio.IOErrorEnum.BUSY,
            message: 'Interrupted panel transfer requires native recovery before another UI reload'});
}

class UIIsland {
    constructor(generation) {
        this.button = new PanelMenu.Button(0.0, 'Tgnome lifetime experiment');
        actorsCreated++;
        this.button.connect('destroy', () => actorsDestroyed++);
        try {
            this.button.add_child(new St.Label({text: `UI island ${generation}`}));
            Main.panel.addToStatusArea('tgnome-island', this.button);
        } catch (error) {
            this.destroy();
            throw error;
        }
    }

    destroy() {
        this.button?.destroy();
        this.button = null;
    }
}

export default class RestartIsland extends Extension {
    enable() {
        this._generation = 0;
        this._failures = 0;
        this._busy = false;
        this._themeReloads = 0;
        this._island = new UIIsland(0);
        this._initialPanel = Main.panel;
        global._tgnomeFirstWindowManager ??= Main.wm;
        this._initialIndicators = new Map(Object.entries(Main.panel.statusArea));
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, PATH);
    }

    Status() {
        const backendProof = global._tgnomeInterruptFixture?.backendProof;
        const panelLifecycle = Main.getPanelReloadStatus?.() ?? null;
        const desktopReloaded = (global._tgnomeUiGeneration ?? 0) > 0;
        const windows = global.get_window_actors().map(actor => {
            const window = actor.meta_window;
            const rect = window.get_frame_rect();
            return {id: window.get_stable_sequence(), title: window.get_title(),
                workspace: window.get_workspace()?.index(),
                frame: [rect.x, rect.y, rect.width, rect.height]};
        }).sort((a, b) => a.id - b.id);
        return JSON.stringify({classification: desktopReloaded || panelLifecycle?.generation > 0
            ? 'SHELL RELOAD' : 'RESEARCH PROTOTYPE',
            scope: desktopReloaded
                ? 'desktop UI instances reinitialized; GJS, backend models and compositor retained'
                : panelLifecycle?.generation > 0
                ? 'panel actor reinitialized; indicator instances, GJS and compositor retained'
                : 'extension-owned panel indicator only',
            pid: new Gio.Credentials().get_unix_pid(),
            runtimeEpoch: global._tgnomeRuntimeEpoch ?? null,
            backendScopeDepth: global._tgnomeBackendScopeDepth ?? null,
            nativeBackendScopeDepth: global.tgnome_backend_depth?.() ?? null,
            protectedBackendFixture: backendProof ? {...backendProof,
                signalStillConnected: Boolean(backendProof.lateSignalId &&
                    GObject.signal_handler_is_connected(global.stage, backendProof.lateSignalId))} : null,
            uiGeneration: global._tgnomeUiGeneration ?? null,
            uiReloadState: global._tgnomeUiReloadState ?? null,
            uiFailures: global._tgnomeUiFailures ?? [],
            uiBuildSerial: global._tgnomeUiBuildSerial ?? 0,
            lateUiOutcomes: global._tgnomeLateUiOutcomes ?? [],
            cleanupWait: global._tgnomeCleanupWait ?? null,
            preparationFailures: global._tgnomePreparationFailures ?? [],
            latePreparationCompletions: global._tgnomeLatePreparationCompletions ?? 0,
            timeLimits: Main.timeLimitsManager ? {
                nativeAddress: System.addressOfGObject(Main.timeLimitsManager),
                retained: Main.timeLimitsManager._tgnomeRetained ?? false,
                shutdownCalls: Main.timeLimitsManager._tgnomeShutdownCalls ?? null,
                state: Main.timeLimitsManager.state,
                transitions: Main.timeLimitsManager._stateTransitions.map(value => ({...value})),
                loginUserReady: Main.timeLimitsManager._loginUser !== null,
                clockSourceActive: Boolean(Main.timeLimitsManager._timeChangeId &&
                    GLib.MainContext.default().find_source_by_id(Main.timeLimitsManager._timeChangeId)),
            } : null,
            retiredUi: Main.getTgnomeRetiredUiStatus?.() ?? null,
            uiRegistrations: global._tgnomeGetUiRegistrationCounts?.() ?? null,
            lastReleasedRegistrations: global._tgnomeLastReleasedRegistrations ?? null,
            windowManagerPreserved: global._tgnomeFirstWindowManager === Main.wm,
            stageActions: global.stage.get_actions().map(action =>
                action.get_name() ?? action.constructor.name).sort(),
            stageChildren: global.stage.get_children().map(actor =>
                `${actor.get_name() ?? ''}:${actor.constructor.name}`).sort(),
            windowGroupAttached: global.window_group.get_parent() === Main.layoutManager.uiGroup,
            generation: this._generation, failures: this._failures,
            active: this._island !== null, busy: this._busy,
            actorsCreated, actorsDestroyed,
            liveOwnedActors: actorsCreated - actorsDestroyed,
            panelEntryMatches: Main.panel.statusArea['tgnome-island'] === this._island?.button,
            themeReloads: this._themeReloads,
            shellState: {overview: Main.overview.visible, modalCount: Main.modalCount,
                startingUp: Main.layoutManager._startingUp,
                mode: Main.sessionMode.currentMode},
            panel: {supported: typeof Main.reloadPanel === 'function',
                realms: Main.getPanelRealmStatus?.() ?? null,
                dateMenuRealms: Main.getDateMenuRealmStatus?.() ?? null,
                transfer: Main.getPanelTransferStatus?.() ?? null,
                lifecycle: panelLifecycle,
                replaced: this._initialPanel !== Main.panel,
                containerCount: Main.layoutManager.panelBox.get_children()
                    .filter(actor => actor.name === 'panel').length,
                focusGroupCount: Main.ctrlAltTabManager._items
                    .filter(item => item.root === Main.panel).length,
                totalFocusGroups: Main.ctrlAltTabManager._items.length,
                menuCount: Main.panel.menuManager._menus.length,
                retainedIndicators: [...this._initialIndicators]
                    .every(([role, indicator]) => Main.panel.statusArea[role] === indicator)},
            desktop: {windows,
                focus: global.display.focus_window?.get_stable_sequence() ?? null,
                monitors: Main.layoutManager.monitors.map(m => [m.x, m.y, m.width, m.height]),
                workspace: global.workspace_manager.get_active_workspace_index()},
            shellRestartSupported: false, extensionCodeReloadSupported: false,
            desktopUiReloadSupported: (global.backend.is_headless() || global._tgnomeSecurityVm === true) &&
                GLib.getenv('TGNOME_PERSISTENT_CONTEXT') === '1' &&
                GLib.getenv('TGNOME_ALLOW_RUNTIME_RESET') === '1' &&
                GLib.getenv('TGNOME_TEST_FAILURES') === '1'});
    }

    ReloadUI(fail) {
        assertPanelTransferSettled();
        if (this._busy)
            throw new Error('UI operation already in progress');
        // Fault injection is available only in an explicitly isolated test Shell.
        if (fail && GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Fault injection is disabled');
        this._busy = true;
        try {
            this._island?.destroy();
            this._island = null;
            if (fail)
                throw new Error('Injected construction failure');
            const next = this._generation + 1;
            this._island = new UIIsland(next);
            this._generation = next;
        } catch (error) {
            this._failures++;
            // Bounded fallback: restore the last generation once. No timers,
            // retries, new processes, D-Bus names or compositor restarts.
            try {
                this._island = new UIIsland(this._generation);
            } catch (restoreError) {
                console.error(restoreError);
            }
            throw error;
        } finally {
            this._busy = false;
        }
        return this.Status();
    }

    ReloadTheme() {
        assertPanelTransferSettled();
        Main.reloadThemeResource();
        Main.loadTheme();
        this._themeReloads++;
        return this.Status();
    }

    ReloadPanel(fail) {
        assertPanelTransferSettled();
        if (typeof Main.reloadPanel !== 'function')
            throw new Error('Panel reload requires the locally patched Shell');
        Main.reloadPanel(fail);
        return this.Status();
    }

    ExercisePanel() {
        if (GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Panel interaction checks are restricted to isolated tests');
        const focus = global.display.focus_window;
        const checked = [];
        try {
            for (const role of ['dateMenu', 'quickSettings']) {
                const menu = Main.panel.statusArea[role].menu;
                try {
                    menu.open(0);
                    if (!menu.isOpen || Main.panel.menuManager.activeMenu !== menu)
                        throw new Error(`Panel menu failed to open: ${role}`);
                } finally {
                    menu.close(0);
                }
                if (Main.panel.menuManager.activeMenu || Main.modalCount)
                    throw new Error(`Panel menu leaked a grab: ${role}`);
                checked.push(role);
            }
        } finally {
            if (focus)
                Main.activateWindow(focus);
        }
        return JSON.stringify({menusChecked: checked, modalCount: Main.modalCount});
    }

    async ExerciseDateMenuRealmAsync(_params, invocation) {
        const focus = global.display.focus_window;
        let menu = null;
        try {
            if (!global.backend.is_headless() ||
                GLib.getenv('TGNOME_ALLOW_UI_REALMS') !== '1' ||
                GLib.getenv('TGNOME_TEST_FAILURES') !== '1' ||
                typeof Main.getDateMenuRealmStatus !== 'function' || Main.modalCount)
                throw new Error('Date menu realm probe requires the private idle Shell');
            const dateMenu = Main.panel.statusArea.dateMenu;
            menu = dateMenu.menu;
            menu.open(0);
            const callsBefore = Main.getDateMenuRealmStatus().records
                .find(record => !record.retired).calls['EventsSection.setDate'] ?? 0;
            const today = new Date();
            const tomorrow = new Date(today);
            tomorrow.setDate(tomorrow.getDate() + 1);
            dateMenu._calendar.setDate(tomorrow);
            dateMenu._date.emit('clicked', 0);
            const selected = dateMenu._calendar._selectedDate;
            const clickedToday = selected.getFullYear() === today.getFullYear() &&
                selected.getMonth() === today.getMonth() && selected.getDate() === today.getDate();
            if (!clickedToday)
                throw new Error('TodayButton native clicked vfunc did not restore today');
            const callsAfter = Main.getDateMenuRealmStatus().records
                .find(record => !record.retired).calls['EventsSection.setDate'] ?? 0;
            const typedDateEvents = callsAfter - callsBefore;
            if (typedDateEvents < 2)
                throw new Error('Typed selected-date-changed callbacks did not reach the UI realm');
            await new Promise(resolve =>
                GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 100, resolve));
            if (!menu.isOpen || !menu.actor.mapped || menu.actor.width <= 0 || menu.actor.height <= 0)
                throw new Error('Date menu was not allocated and mapped');
            const frame = await this._captureTestFrame();
            const type = dateMenu.constructor.$gtype;
            const result = {frame: frame.path, mapped: true, clickedToday, typedDateEvents,
                allocation: [menu.actor.width, menu.actor.height],
                nativeType: GObject.type_name(type),
                parentType: GObject.type_name(GObject.type_parent(type)),
                correctParent: dateMenu instanceof PanelMenu.Button &&
                    GObject.type_parent(type) === PanelMenu.Button.$gtype,
                realms: Main.getDateMenuRealmStatus()};
            menu.close(0);
            menu = null;
            if (Main.modalCount || Main.panel.menuManager.activeMenu)
                throw new Error('Date menu realm probe leaked its modal grab');
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(result)]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.DateRealmProbeFailed', String(error));
        } finally {
            menu?.close(0);
            if (focus)
                Main.activateWindow(focus);
        }
    }

    async ExerciseWindowMenuAsync(_params, invocation) {
        try {
            if ((GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' &&
                 GLib.getenv('TGNOME_REBIND_TYPES') !== '1') ||
                GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
                throw new Error('Window menu probe requires the isolated stable Shell');
            const window = global.display.focus_window;
            if (!window || Main.modalCount)
                throw new Error('Window menu probe requires a focused client and no grab');
            const manager = Main.wm._windowMenuManager;
            manager.showWindowMenuForWindow(window, Meta.WindowMenuType.WM,
                window.get_frame_rect());
            const menu = manager._manager.activeMenu;
            try {
                if (!menu?.isOpen)
                    throw new Error('Window menu failed to open');
                await new Promise(resolve =>
                    GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 400, resolve));
            } finally {
                menu?.close(0);
                Main.activateWindow(window);
            }
            if (Main.modalCount || manager._manager.activeMenu)
                throw new Error('Window menu leaked its modal grab');
            invocation.return_value(new GLib.Variant('(s)',
                [JSON.stringify({opened: true, closed: true})]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.MenuProbeFailed', String(error));
        }
    }

    SetTestOverview(visible) {
        if (GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Overview checks are restricted to isolated tests');
        if (visible)
            Main.overview.show();
        else
            Main.overview.hide();
        return this.Status();
    }

    async PrepareRuntimeResetAsync(_params, invocation) {
        try {
            const result = await this._prepareRuntimeReset(false);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(result)]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.PreparationFailed', String(error));
        }
    }

    async ReloadDesktopUiAsync(_params, invocation) {
        try {
            if (!(global.backend.is_headless() || global._tgnomeSecurityVm === true) ||
                GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1')
                throw new Error('Desktop UI reload requires the isolated stable headless Shell or dedicated security VM');
            const preparation = await this._prepareRuntimeReset(true);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({
                accepted: true, classification: 'SHELL RELOAD',
                scope: 'desktop UI reconstruction scheduled; compositor retained',
                preparation, native: preparation.native})]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.ReloadFailed', String(error));
        }
    }

    ArmOwnedDelay(milliseconds) {
        this.PrepareTestKeyboard();
        if (milliseconds < 250 || milliseconds > 1000 || global._tgnomeUiPreparing)
            throw new Error('Owned delay must be 250..1000ms in an idle test fixture');
        global._tgnomeOwnedDelay = milliseconds;
        return JSON.stringify({armed: milliseconds});
    }

    async _prepareRuntimeReset(owned) {
        let ownsPreparation = false;
        let reserved = false;
        let commit;
        let abort;
        let commitError = null;
        try {
            // This check precedes ownership flags, backend work and the native
            // reservation. Read-only Status remains available during handoff.
            assertPanelTransferSettled();
            if (GLib.getenv('TGNOME_ALLOW_RUNTIME_RESET') !== '1' ||
                GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
                throw new Error('Runtime preparation is restricted to isolated tests');
            if (global._tgnomeUiPreparing || global._tgnomeResetPrepared ||
                global._tgnomeUiReloadState === 'starting')
                throw new Error('UI reset is already preparing, prepared or starting');
            if (Main.modalCount || Main.overview.visible || Main.layoutManager._startingUp ||
                Main.screenshotUI.screencast_in_progress ||
                Main.sessionMode.currentMode !== 'user')
                throw new Error('Runtime reset requires an idle unlocked UI without active screencasting');
            global._tgnomeUiPreparing = true;
            ownsPreparation = true;
            if (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') === '1') {
                const reply = await global._tgnomeReportUiOutcome('Status');
                const native = JSON.parse(reply.deep_unpack()[0]);
                if (native.uiActive)
                    throw new Error('A native UI transaction is already active');
                if (native.attempts >= 3)
                    throw new Error('Laboratory request limit reached before preparation');
            }
            if (owned) {
                const aborted = new Promise((_resolve, reject) => {
                    abort = reason => reject(new Error(reason));
                });
                // Observe cancellation even when the current native RPC has
                // not reached its following await point yet.
                aborted.catch(() => {});
                global._tgnomeAbortPreparation = abort;
                await global._tgnomeReportUiOutcome('BeginUiReload');
                reserved = true;
                const delay = global._tgnomeOwnedDelay ?? 0;
                global._tgnomeOwnedDelay = 0;
                const stalled = global._tgnomePreparationFault === 'stalled';
                if (delay || stalled) {
                    await Promise.race([aborted, new Promise(resolve =>
                        GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, stalled ? 7000 : delay, () => {
                            if (stalled)
                                global._tgnomeLatePreparationCompletions =
                                    (global._tgnomeLatePreparationCompletions ?? 0) + 1;
                            resolve();
                        }))]);
                }
            }
            // Only the whole-context research variant stops its backend model.
            // The stable UI lifetime leaves it and its pending work alive.
            if (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1')
                await Main.timeLimitsManager.shutdown();
            else if (!Main.timeLimitsManager._tgnomeRetained)
                throw new Error('UI preparation requires the durable time-limits backend');
            const fault = global._tgnomePreparationFault;
            global._tgnomePreparationFault = null;
            let result;
            commit = () => {
                try {
                    if (Main.modalCount || Main.overview.visible || Main.layoutManager._startingUp ||
                        Main.screenshotUI.screencast_in_progress ||
                        Main.sessionMode.currentMode !== 'user')
                        throw new Error('UI changed before preparation commit');
                    if (fault === 'before-mutation')
                        throw new Error('Injected preparation failure before mutation');
                    Main.captureTgnomeUiObjects?.();
                    result = {prepared: true, releasedKeybindings: 0, forwardRecovered: false};
                    try {
                        result.releasedKeybindings = global._tgnomeReleaseKeybindings();
                        if (fault === 'after-bindings')
                            throw new Error('Injected preparation failure after keybindings');
                        global._tgnomeResetPrepared = true;
                        this.disable();
                        if (fault === 'after-disable')
                            throw new Error('Injected preparation failure after disable');
                    } catch (error) {
                        // Once UI mutation starts, finish the idempotent release
                        // and reconstruct. Cancelling would strand a partial UI.
                        result.releasedKeybindings += global._tgnomeReleaseKeybindings();
                        global._tgnomeResetPrepared = true;
                        this.disable();
                        result.forwardRecovered = true;
                        result.preparationError = String(error);
                        this._recordPreparationFailure(error, true);
                    }
                    global._tgnomeUiPreparing = false;
                    return true;
                } catch (error) {
                    commitError = error;
                    return false;
                }
            };
            if (owned) {
                global._tgnomeCommitPreparation = commit;
                const reply = await global._tgnomeReportUiOutcome('StartUiReload');
                result.native = JSON.parse(reply.deep_unpack()[0]);
            } else if (!commit()) {
                throw commitError;
            }
            return result;
        } catch (error) {
            const failure = commitError ?? error;
            if (ownsPreparation) {
                global._tgnomePreparationFault = null;
                this._recordPreparationFailure(failure, false);
            }
            if (reserved) {
                try { await global._tgnomeReportUiOutcome('CancelUiReload'); }
                catch { /* Native commit refusal/expiry already ended the lease. */ }
            }
            throw failure;
        } finally {
            if (ownsPreparation) {
                global._tgnomeUiPreparing = false;
                if (global._tgnomeCommitPreparation === commit)
                    global._tgnomeCommitPreparation = null;
                if (global._tgnomeAbortPreparation === abort)
                    global._tgnomeAbortPreparation = null;
            }
        }
    }

    _recordPreparationFailure(error, forwardRecovered) {
        global._tgnomePreparationFailures ??= [];
        global._tgnomePreparationFailures.push({message: String(error), forwardRecovered});
    }

    ArmPreparationFault(fault) {
        this.PrepareTestKeyboard();
        if (!['before-mutation', 'after-bindings', 'after-disable', 'stalled'].includes(fault) ||
            global._tgnomeUiPreparing || global._tgnomeResetPrepared)
            throw new Error('Preparation fault requires an idle isolated stable Shell');
        global._tgnomePreparationFault = fault;
        return JSON.stringify({armed: fault});
    }

    ExercisePolicyRetirement() {
        this.PrepareTestKeyboard();
        const policy = new MessageTray.NotificationGenericPolicy();
        const owner = new St.Widget();
        policy.connectObject('notify::enable', () => {}, 'notify', () => {}, owner);
        policy.destroy();
        owner.destroy();
        return JSON.stringify({policyDisposed: true, ownerDestroyed: true});
    }

    ArmCleanupMode(mode) {
        this.PrepareTestKeyboard();
        if (!['delayed', 'never'].includes(mode) || global._tgnomeUiPreparing ||
            global._tgnomeUiReloadState === 'starting')
            throw new Error('Cleanup mode requires an idle isolated stable Shell');
        global._tgnomeCleanupMode = mode;
        return JSON.stringify({armed: mode});
    }

    async ExerciseQuarantineRefusalsAsync(_params, invocation) {
        try {
            this.PrepareTestKeyboard();
            const serial = global._tgnomeUiBuildSerial;
            const refused = [];
            for (const [candidate, ready, expected] of [
                [serial - 1, true, 'different UI candidate'],
                [serial, false, 'Cleanup readiness has not been confirmed'],
                [serial, true, 'Cleanup acknowledgement is not prepared'],
            ]) {
                try { await global._tgnomeReportUiOutcome('UiFailed', ready, candidate); }
                catch (error) {
                    if (!String(error).includes(expected))
                        throw error;
                    refused.push({candidate, ready, reason: String(error)});
                    continue;
                }
                throw new Error('Native quarantine accepted an invalid cleanup acknowledgement');
            }
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({refused})]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.QuarantineProbeFailed', String(error));
        }
    }

    async CaptureTestFrameAsync(_params, invocation) {
        try {
            const frame = await this._captureTestFrame();
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(frame)]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.FrameProbeFailed', String(error));
        }
    }

    async _captureTestFrame() {
        let stream = null;
        try {
            if (!global.backend.is_headless() ||
                (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' &&
                 GLib.getenv('TGNOME_REBIND_TYPES') !== '1') ||
                GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
                throw new Error('Frame capture requires the isolated headless fixture');
            const path = GLib.build_filenamev([global.userdatadir, 'tgnome-frame.png']);
            stream = Gio.File.new_for_path(path).replace(null, false,
                Gio.FileCreateFlags.PRIVATE, null);
            const screenshot = new Shell.Screenshot();
            await screenshot.screenshot(false, stream);
            stream.close(null);
            stream = null;
            return {path};
        } finally {
            stream?.close(null);
        }
    }

    ArrangeProbeWindows() {
        this.PrepareTestKeyboard();
        const windows = global.get_window_actors().map(actor => actor.meta_window)
            .filter(window => window.get_title() === 'Tgnome persistent connection probe')
            .sort((a, b) => a.get_stable_sequence() - b.get_stable_sequence());
        if (windows.length !== 2 || Main.modalCount || Main.overview.visible)
            throw new Error('Arrangement requires exactly two idle private probe windows');
        return JSON.stringify({windows: windows.map((window, index) => {
            const frame = [40 + 600 * index, 180, 500, 160];
            window.move_resize_frame(true, ...frame);
            return {id: window.get_stable_sequence(), frame};
        })});
    }

    PrepareTestKeyboard() {
        if (!global.backend.is_headless() ||
            (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' &&
             GLib.getenv('TGNOME_REBIND_TYPES') !== '1') ||
            GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Virtual input is restricted to the isolated headless fixture');
        global._tgnomeTestKeyboard ??= global.stage.context.get_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        return JSON.stringify({nativeAddress: System.addressOfGObject(global._tgnomeTestKeyboard)});
    }

    _tapTestKey(keyval) {
        const keyboard = global._tgnomeTestKeyboard;
        keyboard.notify_keyval(GLib.get_monotonic_time(), keyval, Clutter.KeyState.PRESSED);
        keyboard.notify_keyval(GLib.get_monotonic_time(), keyval, Clutter.KeyState.RELEASED);
    }

    async ExerciseNativeOverviewAsync(_params, invocation) {
        const previousFocus = global.display.focus_window;
        let ownsTransition = false;
        try {
            const keyboard = JSON.parse(this.PrepareTestKeyboard());
            if (Main.modalCount || Main.overview.visible || Main.layoutManager._startingUp)
                throw new Error('Native overview probe requires an idle desktop');
            ownsTransition = true;
            const waitUntil = async predicate => {
                for (let attempt = 0; attempt < 120; attempt++) {
                    if (predicate())
                        return;
                    await new Promise(resolve =>
                        GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 25, resolve));
                }
                throw new Error('Native overview transition did not complete');
            };
            this._tapTestKey(Clutter.KEY_Super_L);
            await waitUntil(() => Main.overview.visible && !Main.overview.animationInProgress);
            const frame = await this._captureTestFrame();
            this._tapTestKey(Clutter.KEY_Escape);
            await waitUntil(() => !Main.overview.visible &&
                Main.actionMode === Shell.ActionMode.NORMAL);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify({
                opened: true, closed: true, ...keyboard, ...frame})]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.OverviewInputFailed', String(error));
        } finally {
            if (ownsTransition && Main.overview.visible)
                Main.overview.hide();
            if (ownsTransition && previousFocus)
                Main.activateWindow(previousFocus);
        }
    }

    async TypeIntoProbeAsync([pid], invocation) {
        try {
            const keyboardIdentity = JSON.parse(this.PrepareTestKeyboard());
            if (Main.modalCount || Main.overview.visible || Main.layoutManager._startingUp)
                throw new Error('Input probe requires an idle normal desktop');
            const window = global.get_window_actors().map(actor => actor.meta_window)
                .find(window => window.get_pid() === pid &&
                    window.get_title() === 'Tgnome persistent connection probe');
            if (!window)
                throw new Error('PID does not identify a private connection probe window');
            const previousFocus = global.display.focus_window;
            try {
                Main.activateWindow(window);
                await new Promise(resolve =>
                    GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 150, resolve));
                if (global.display.focus_window !== window || Main.modalCount)
                    throw new Error('The intended probe did not receive focus');
                for (const keyval of [Clutter.KEY_End, Clutter.KEY_a])
                    this._tapTestKey(keyval);
                await new Promise(resolve =>
                    GLib.timeout_add_once(GLib.PRIORITY_DEFAULT, 150, resolve));
            } finally {
                if (previousFocus)
                    Main.activateWindow(previousFocus);
            }
            invocation.return_value(new GLib.Variant('(s)',
                [JSON.stringify({pid, ...keyboardIdentity, sent: true})]));
        } catch (error) {
            invocation.return_dbus_error('org.gnome.Shell.Tgnome.InputProbeFailed', String(error));
        }
    }

    ArmUiFailure(count) {
        return this.ArmUiFailureAt('post-construction', count);
    }

    ArmUiFailureAt(stage, count) {
        if (!global.backend.is_headless() ||
            GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' ||
            GLib.getenv('TGNOME_TEST_FAILURES') !== '1' ||
            !['after-layout', 'overview-constructor', 'after-panel', 'post-construction',
                'startup-wait', 'layout-wait'].includes(stage) ||
            ![1, 2].includes(count) || global._tgnomeUiPreparing ||
            global._tgnomeUiReloadState === 'starting')
            throw new Error('UI failure injection requires an idle isolated stable Shell');
        global._tgnomeUiFailureBudget = count;
        global._tgnomeUiFailureStage = stage;
        return JSON.stringify({armed: count, stage});
    }

    DumpUiHeap() {
        if (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' ||
            GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Heap probe requires the isolated stable Shell');
        return JSON.stringify({path: global._tgnomeDumpUiHeap()});
    }

    CollectUiGarbage() {
        if (GLib.getenv('TGNOME_PERSISTENT_CONTEXT') !== '1' ||
            GLib.getenv('TGNOME_TEST_FAILURES') !== '1')
            throw new Error('Garbage collection probe requires the isolated stable Shell');
        global._tgnomeCollectGarbage();
        return JSON.stringify({requested: true});
    }

    disable() {
        this._dbus?.unexport();
        this._dbus = null;
        this._island?.destroy();
        this._island = null;
    }
}
