// Fresh GJS UI realms, real ESM/GI, canonical backend bindings and GC evidence.
// No compositor, display, session bus or host services are used by this probe.
#include <gjs/gjs.h>
#include <gio/gio.h>
#include <js/CompilationAndEvaluation.h>
#include <js/CompileOptions.h>
#include <js/Conversions.h>
#include <js/Exception.h>
#include <js/GCAPI.h>
#include <js/GlobalObject.h>
#include <js/Modules.h>
#include <js/Promise.h>
#include <js/PropertyAndElement.h>
#include <js/Realm.h>
#include <js/RootingAPI.h>
#include <js/SourceText.h>
#include <js/String.h>
#include <js/Value.h>
#include <jsapi.h>
#include <cstring>
#include <string>

// Private ABI only in realm-gjs, intentionally not introspected or installed.
extern "C" void* gjs_context_tgnome_create_ui_realm(GjsContext*);

static bool evaluate(JSContext* cx, const char* text,
                     JS::MutableHandleValue result) {
    JS::SourceText<mozilla::Utf8Unit> source;
    if (!source.init(cx, text, strlen(text), JS::SourceOwnership::Borrowed))
        return false;
    JS::CompileOptions options(cx);
    options.setFileAndLine("realm-probe", 1);
    return JS::Evaluate(cx, options, source, result);
}

static bool statement(JSContext* cx, const char* text) {
    JS::RootedValue ignored(cx);
    return evaluate(cx, text, &ignored);
}

static bool load_module(JSContext* cx, const char* filename) {
    gchar* text = nullptr;
    gsize length = 0;
    if (!g_file_get_contents(filename, &text, &length, nullptr))
        return false;
    gchar* uri = g_filename_to_uri(filename, nullptr, nullptr);
    JS::SourceText<mozilla::Utf8Unit> source;
    if (!source.init(cx, text, length, JS::SourceOwnership::Borrowed)) {
        g_free(text);
        g_free(uri);
        return false;
    }
    JS::CompileOptions options(cx);
    options.setFileAndLine(uri, 1).setSourceIsLazy(false);
    JS::RootedObject module(cx, JS::CompileModule(cx, options, source));
    g_free(text);
    if (!module) {
        g_free(uri);
        return false;
    }
    JS::RootedObject metadata(cx, JS_NewPlainObject(cx));
    JS::RootedString uri_string(cx, JS_NewStringCopyZ(cx, uri));
    g_free(uri);
    if (!metadata || !uri_string ||
        !JS_DefineProperty(cx, metadata, "uri", uri_string, 0) ||
        !JS_DefineProperty(cx, metadata, "internal", false, 0))
        return false;
    JS::SetModulePrivate(module, JS::ObjectValue(*metadata));
    JS::RootedValue result(cx);
    if (!JS::ModuleLink(cx, module) || !JS::ModuleEvaluate(cx, module, &result))
        return false;
    if (!result.isObject())
        return false;
    JS::RootedObject promise(cx, &result.toObject());
    // Fixtures deliberately contain no top-level await. Pending is a failure,
    // never interpreted as a successful module evaluation.
    if (JS::GetPromiseState(promise) != JS::PromiseState::Fulfilled) {
        if (JS::GetPromiseState(promise) == JS::PromiseState::Rejected) {
            JS::RootedValue error(cx, JS::GetPromiseResult(promise));
            JS_SetPendingException(cx, error);
        }
        return false;
    }
    return true;
}

static void capture_main(GjsContext* context, void* data) {
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    *static_cast<JS::RootedObject*>(data) = JS::CurrentGlobalOrNull(cx);
}

static bool run(GjsContext* context, JSContext* cx,
                JS::HandleObject backend, const char* mode, const char* entry) {
    JSAutoRealm backend_realm(cx, backend);
    if (!statement(cx,
        "globalThis.backendObject = new imports.gi.GObject.Object();"
        "globalThis.realmRefs = []; globalThis.typeStatuses = [];"
        "globalThis.backendEpoch = {};"
        "globalThis.BackendBoxedEmitter = imports.gi.GObject.registerClass({"
        "GTypeName:'TgnomeRealmBoxedEmitter',Signals:{'boxed-payload':{"
        "param_types:[imports.gi.GLib.DateTime.$gtype]}}},"
        "class BackendBoxedEmitter extends imports.gi.GObject.Object {});"
        "globalThis.backendEmitter = new BackendBoxedEmitter();"))
        return false;
    const bool delegated = strncmp(mode, "delegate", 8) == 0;
    const bool retain_delegate = strcmp(mode, "delegate-held") == 0;
    if (delegated && !statement(cx,
        "globalThis.Gio = imports.gi.Gio;"
        "globalThis.GObject = imports.gi.GObject;"
        "globalThis.BackendEnumerator = GObject.registerClass("
        "{GTypeName:'TgnomeStableRealmEnumerator'},"
        "class BackendEnumerator extends Gio.FileEnumerator {"
        "vfunc_next_file() {"
        "if (!this.delegate) throw new Gio.IOErrorEnum({"
        "code:Gio.IOErrorEnum.BUSY,message:'No UI generation'});"
        "return this.delegate.produce();"
        "} vfunc_close_fn() { return true; } });"
        "globalThis.nativeOwner = new BackendEnumerator({"
        "container:Gio.File.new_for_path('/tgnome-virtual-no-io')});"
        "globalThis.nativeOwnerIdentity = nativeOwner;"))
        return false;
    JS::RootedValue object(cx);
    if (!JS_GetProperty(cx, backend, "backendObject", &object))
        return false;
    JS::RootedValue emitter(cx);
    if (!JS_GetProperty(cx, backend, "backendEmitter", &emitter))
        return false;
    for (int generation = 0; generation < 3; ++generation) {
        // All strong roots to this generation are scoped to this iteration.
        JS::RootedObject candidate(cx, static_cast<JSObject*>(
            gjs_context_tgnome_create_ui_realm(context)));
        if (!candidate || candidate == backend)
            return false;
        {
            JSAutoRealm candidate_realm(cx, candidate);
            JS::RootedString case_mode(cx, JS_NewStringCopyZ(cx, mode));
            if (!case_mode ||
                !JS_DefineProperty(cx, candidate, "caseMode", case_mode, 0) ||
                !JS_DefineProperty(cx, candidate, "backendObject", object, 0) ||
                !JS_DefineProperty(cx, candidate, "backendEmitter", emitter, 0) ||
                !JS_DefineProperty(cx, candidate, "uiGeneration", generation, 0))
                return false;
            if (delegated) {
                JS::RootedValue owner(cx);
                if (!JS_GetProperty(cx, backend, "nativeOwner", &owner) ||
                    !JS_DefineProperty(cx, candidate, "nativeOwner", owner, 0))
                    return false;
            }
            if (!load_module(cx, entry))
                return false;
            // Complete a Promise -> GJS timer chain in the candidate realm.
            // Each source must release its callback before GC measurements.
            const gint64 deadline = g_get_monotonic_time() + G_TIME_SPAN_SECOND;
            JS::RootedValue finished(cx);
            do {
                while (g_main_context_iteration(nullptr, false)) {}
                if (!JS_GetProperty(cx, candidate, "asyncFinished", &finished))
                    return false;
                if (finished.isBoolean() && finished.toBoolean())
                    break;
                g_usleep(1000);
            } while (g_get_monotonic_time() < deadline);
            if (!finished.isBoolean() || !finished.toBoolean())
                return false;
        }
        if (!JS_DefineProperty(cx, backend, "candidate", candidate, 0) ||
            !statement(cx,
                "if (candidate.realmMarker.owner !== candidate || "
                "candidate.realmMarker.View === globalThis.previousView || "
                "candidate.realmMarker.nativeClass !== imports.gi.GObject.Object || "
                "candidate.backendObject !== backendObject || "
                "candidate.backendEpoch !== undefined || "
                "globalThis.moduleExecutions !== undefined) "
                "throw new Error('Realm/module/backend boundary failed');"
                // previousView is retained only until the next comparison.
                "globalThis.previousView = candidate.realmMarker.View;"
                "realmRefs.push({global:new WeakRef(candidate),"
                "marker:new WeakRef(candidate.realmMarker),"
                "token:new WeakRef(candidate.realmMarker.token)});"
                "typeStatuses.push(candidate.typeStatus);"
                "delete globalThis.candidate;"))
            return false;
        if (delegated && !statement(cx,
            "if (nativeOwner !== nativeOwnerIdentity || "
            "nativeOwner.constructor !== BackendEnumerator) "
            "throw new Error('Backend native instance/type changed');"))
            return false;
        if (delegated && (!retain_delegate || generation < 2) && !statement(cx,
            "nativeOwner.delegate = null;"
            "{ let busy = false; try { nativeOwner.next_file(null); }"
            "catch (error) { busy = error.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.BUSY); }"
            "if (!busy) throw new Error('Missing UI accepted a native vfunc call'); }"))
            return false;
        g_print("{\"event\":\"realm-generation\",\"generation\":%d}\n", generation);
    }
    if (!statement(cx, "delete globalThis.previousView;"))
        return false;
    for (int cycle = 0; cycle < 6; ++cycle) {
        JS::ClearKeptObjects(cx);
        gjs_context_gc(context);
        while (g_main_context_iteration(nullptr, false)) {}
    }
    if (!statement(cx,
        "globalThis.gcResult = realmRefs.map(ref => ({"
        "globalCollected:ref.global.deref() === undefined,"
        "markerCollected:ref.marker.deref() === undefined,"
        "tokenCollected:ref.token.deref() === undefined}));"))
        return false;
    JS::RootedValue result(cx);
    if (!evaluate(cx,
        "JSON.stringify({event:'realm-result', types:typeStatuses, gc:gcResult,"
        "backendAlive:backendObject instanceof imports.gi.GObject.Object,"
        "freshModuleGraphs:true, canonicalNativeBindings:true,"
        "esmBootstrap:true, promiseTimerCompleted:true, typedSignalCompleted:true})", &result))
        return false;
    JS::RootedString result_string(cx, JS::ToString(cx, result));
    JS::UniqueChars json = JS_EncodeStringToUTF8(cx, result_string);
    if (!json)
        return false;
    g_print("%s\n", json.get());
    return true;
}

int main(int argc, char** argv) {
    if (argc != 3 || (strcmp(argv[1], "plain") && strcmp(argv[1], "gtype") &&
                     strcmp(argv[1], "delegate") && strcmp(argv[1], "delegate-held")))
        return 2;
    GjsContext* context = gjs_context_new();
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    bool passed;
    {
        JS::RootedObject backend(cx);
        gjs_context_run_in_realm(context, capture_main, &backend);
        passed = run(context, cx, backend, argv[1], argv[2]);
        if (!passed && JS_IsExceptionPending(cx)) {
            JSAutoRealm ar(cx, backend);
            JS::RootedValue error(cx);
            if (JS_GetPendingException(cx, &error)) {
                JS_ClearPendingException(cx);
                JS::RootedString message(cx, JS::ToString(cx, error));
                JS::UniqueChars utf8 = message ? JS_EncodeStringToUTF8(cx, message) : nullptr;
                g_printerr("realm failure: %s\n", utf8 ? utf8.get() : "unprintable");
            }
        }
        {
            JSAutoRealm ar(cx, backend);
            // FileEnumerator.dispose closes the stream. Complete this while JS
            // is executable, rather than asking its vfunc to run during GC.
            if (!statement(cx, "if (globalThis.nativeOwner) {"
                "nativeOwner.delegate = null; nativeOwner.close(null); }"))
                passed = false;
        }
    }
    g_object_unref(context);
    return passed ? 0 : 1;
}
