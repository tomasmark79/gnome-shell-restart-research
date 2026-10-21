import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import 'resource:///org/gnome/gjs/modules/esm/_bootstrap/default.js';
import {owner, token, View} from './state.js';

if (owner !== globalThis || globalThis.moduleExecutions !== 1)
    throw new Error('Dependency compiled into the wrong global or reused');
if (!(globalThis.backendObject instanceof GObject.Object))
    throw new Error('Canonical backend object lost native identity');
if (new TextEncoder().encode('ui').length !== 2 || typeof console.log !== 'function')
    throw new Error('ESM bootstrap was not initialized in the UI global');

globalThis.asyncFinished = false;
Promise.resolve().then(() => {
    setTimeout(() => {
        globalThis.asyncFinished = owner === globalThis;
    }, 0);
});

// Exercise a real GI callback, then remove its native root before collection.
const cancellable = new Gio.Cancellable();
const id = cancellable.connect(() => {
    globalThis.callbackCount = (globalThis.callbackCount ?? 0) + 1;
});
cancellable.cancel();
cancellable.disconnect(id);
if (globalThis.callbackCount !== 1)
    throw new Error('Fresh-realm native callback did not execute');

let typedSignalCompleted = false;
const typedId = globalThis.backendEmitter.connect('boxed-payload', (_emitter, datetime) => {
    typedSignalCompleted = datetime.to_unix() === 123456;
});
globalThis.backendEmitter.emit('boxed-payload', GLib.DateTime.new_from_unix_utc(123456));
globalThis.backendEmitter.disconnect(typedId);
if (!typedSignalCompleted)
    throw new Error('Boxed GI signal argument was not delivered in the fresh realm');

globalThis.typeStatus = 'absent';
if (globalThis.caseMode.startsWith('delegate')) {
    // Only the implementation belongs to this UI realm. The registered native
    // type, vfunc trampoline and object instance were created once in backend.
    class UiProducer {
        produce() {
            const info = new Gio.FileInfo();
            info.set_name(`ui-${globalThis.uiGeneration}`);
            return info;
        }
    }
    globalThis.nativeOwner.delegate = new UiProducer();
    const info = globalThis.nativeOwner.next_file(null);
    if (info.get_name() !== `ui-${globalThis.uiGeneration}`)
        throw new Error('Native vfunc dispatched to an old UI implementation');
    globalThis.typeStatus = 'delegated';
}
if (globalThis.caseMode === 'gtype') {
    try {
        const Ui = GObject.registerClass({GTypeName: 'TgnomeRealmPinnedUi'},
            class Ui extends GObject.Object {});
        const instance = new Ui();
        if (!(instance instanceof GObject.Object))
            throw new Error('Registered native instance lost its base class');
        globalThis.typeStatus = 'registered';
    } catch (error) {
        if (!String(error).includes('already registered'))
            throw error;
        globalThis.typeStatus = 'duplicate';
    }
}
globalThis.realmMarker = {owner, token, View, nativeClass: GObject.Object};
