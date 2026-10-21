// Serial GjsContext replacement across a native-owned GType, no desktop access.
#include <gjs/gjs.h>
#include <gio/gio.h>
#include <js/CompilationAndEvaluation.h>
#include <js/CompileOptions.h>
#include <js/GCAPI.h>
#include <js/GlobalObject.h>
#include <js/PropertyAndElement.h>
#include <js/RootingAPI.h>
#include <js/SourceText.h>
#include <js/String.h>
#include <jsapi.h>
#include <cstring>
#include <string>
#include <thread>

extern "C" gboolean gjs_context_tgnome_native_object(
    GjsContext*, const char*, GObject**, gboolean);

static GjsContext* active = nullptr;  // Borrowed, cleared before disposal.
static const auto owner = std::this_thread::get_id();
static unsigned context_finalized = 0, object_finalized = 0;
static unsigned pulse_signal;
static void context_gone(void*, GObject*) { ++context_finalized; }
static void object_gone(void*, GObject*) { ++object_finalized; }

struct WeakEvidence {
    JS::Heap<JSObject*> global{nullptr}, marker{nullptr}, callback{nullptr};
    JS::Heap<JSObject*> wrapper{nullptr}, signal_callback{nullptr};
    unsigned sweeps = 0;
    bool track_wrapper = false;
};
static void sweep(JSTracer* tracer, void* data) {
    auto* evidence = static_cast<WeakEvidence*>(data);
    ++evidence->sweeps;
    if (evidence->global)
        JS_UpdateWeakPointerAfterGC(tracer, &evidence->global);
    if (evidence->marker)
        JS_UpdateWeakPointerAfterGC(tracer, &evidence->marker);
    if (evidence->callback)
        JS_UpdateWeakPointerAfterGC(tracer, &evidence->callback);
    if (evidence->wrapper)
        JS_UpdateWeakPointerAfterGC(tracer, &evidence->wrapper);
    if (evidence->signal_callback)
        JS_UpdateWeakPointerAfterGC(tracer, &evidence->signal_callback);
}

struct Script { const char* source; bool ok = false; };
static void script_in_realm(GjsContext* context, void* data) {
    auto* script = static_cast<Script*>(data);
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    JS::SourceText<mozilla::Utf8Unit> source;
    if (!source.init(cx, script->source, strlen(script->source),
                     JS::SourceOwnership::Borrowed))
        return;
    JS::CompileOptions options(cx);
    options.setFileAndLine("native-type-probe", 1);
    JS::RootedValue result(cx);
    script->ok = JS::Evaluate(cx, options, source, &result);
}
static bool run(GjsContext* context, const char* text) {
    Script script{text};
    gjs_context_run_in_realm(context, script_in_realm, &script);
    return script.ok;
}
static void observe(GjsContext* context, void* data) {
    auto* evidence = static_cast<WeakEvidence*>(data);
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    JS::RootedObject global(cx, JS::CurrentGlobalOrNull(cx));
    evidence->global = global;
    JS::RootedValue value(cx);
    g_assert(JS_GetProperty(cx, global, "marker", &value) && value.isObject());
    evidence->marker = &value.toObject();
    g_assert(JS_GetProperty(cx, global, "uiNextName", &value) && value.isObject());
    evidence->callback = &value.toObject();
    if (evidence->track_wrapper) {
        g_assert(JS_GetProperty(cx, global, "backend", &value) && value.isObject());
        evidence->wrapper = &value.toObject();
    }
    g_assert(JS_GetProperty(cx, global, "uiOnPulse", &value));
    if (value.isObject())
        evidence->signal_callback = &value.toObject();
    g_assert(JS_AddWeakPointerZonesCallback(cx, sweep, evidence));
}

// The permanent GType stores only native code addresses. No JS roots/class data.
struct NativeEnumerator { GFileEnumerator parent; };
struct NativeEnumeratorClass { GFileEnumeratorClass parent; };
G_DEFINE_TYPE(NativeEnumerator, native_enumerator, G_TYPE_FILE_ENUMERATOR)
struct Dispatch { std::string name; bool ok = false; };
static void dispatch(GjsContext* context, void* data) {
    auto* result = static_cast<Dispatch*>(data);
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    JS::RootedObject global(cx, JS::CurrentGlobalOrNull(cx));
    JS::RootedValue function(cx), value(cx);
    if (!JS_GetProperty(cx, global, "uiNextName", &function) ||
        !JS::Call(cx, global, function, JS::HandleValueArray::empty(), &value) ||
        !value.isString())
        return;
    JS::RootedString string(cx, value.toString());
    JS::UniqueChars utf8 = JS_EncodeStringToUTF8(cx, string);
    if (utf8) { result->name = utf8.get(); result->ok = true; }
}
static GFileInfo* next_file(GFileEnumerator*, GCancellable*, GError** error) {
    if (!active || std::this_thread::get_id() != owner) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_BUSY, "No active runtime");
        return nullptr;
    }
    Dispatch result;
    gjs_context_run_in_realm(active, dispatch, &result);
    if (!result.ok) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_FAILED, "JS dispatch failed");
        return nullptr;
    }
    GFileInfo* info = g_file_info_new();
    g_file_info_set_name(info, result.name.c_str());
    return info;
}
static gboolean close_file(GFileEnumerator*, GCancellable*, GError**) { return true; }
static void native_enumerator_class_init(NativeEnumeratorClass* klass) {
    auto* enumerator = G_FILE_ENUMERATOR_CLASS(klass);
    enumerator->next_file = next_file;
    enumerator->close_fn = close_file;
    pulse_signal = g_signal_new("pulse", G_TYPE_FROM_CLASS(klass), G_SIGNAL_RUN_LAST,
                                0, nullptr, nullptr, nullptr, G_TYPE_NONE, 1, G_TYPE_INT);
}
static void native_enumerator_init(NativeEnumerator*) {}

static bool expect_name(GObject* object, const std::string& name) {
    GError* error = nullptr;
    GFileInfo* info = g_file_enumerator_next_file(G_FILE_ENUMERATOR(object), nullptr, &error);
    bool ok = info && !error && name == g_file_info_get_name(info);
    g_clear_object(&info);
    g_clear_error(&error);
    return ok;
}
static void gap(GObject* object) {
    GError* error = nullptr;
    auto* info = g_file_enumerator_next_file(G_FILE_ENUMERATOR(object), nullptr, &error);
    g_assert(!info && g_error_matches(error, G_IO_ERROR, G_IO_ERROR_BUSY));
    g_clear_error(&error);
    g_signal_emit(object, pulse_signal, 0, -1);
}

static int positive() {
    GFile* container = g_file_new_for_path("/tgnome-no-io");
    GObject* object = G_OBJECT(g_object_new(native_enumerator_get_type(),
                                           "container", container, nullptr));
    g_object_unref(container);
    g_object_weak_ref(object, object_gone, nullptr);
    GObject* identity = object;
    GType type = G_OBJECT_TYPE(object);
    gap(object);
    for (unsigned generation = 1; generation <= 3; ++generation) {
        WeakEvidence evidence;
        evidence.track_wrapper = true;
        GjsContext* context = gjs_context_new();
        g_object_weak_ref(G_OBJECT(context), context_gone, nullptr);
        g_assert(run(context, "imports.gi.Gio; imports.gi.GObject;"));
        g_assert(gjs_context_tgnome_native_object(context, "backend", &object, true));
        active = context;
        std::string setup =
            "if (typeof uiEpoch !== 'undefined') throw Error('old global');"
            "globalThis.uiEpoch=" + std::to_string(generation) + ";"
            "globalThis.marker={epoch:uiEpoch};globalThis.uiCalls=0;"
            "globalThis.uiSignals=0;"
            "globalThis.uiNextName=()=> 'ui-'+uiEpoch+':'+ ++uiCalls;"
            "globalThis.uiOnPulse=(_self,n)=>{"
            "if(n!==uiEpoch) throw Error('stale signal');++uiSignals;};"
            "globalThis.handler=backend.connect('pulse',uiOnPulse);"
            "if(backend.next_file(null).get_name()!=='ui-'+uiEpoch+':1')"
            "throw Error('GI vfunc');";
        g_assert(run(context, setup.c_str()));
        gjs_context_run_in_realm(context, observe, &evidence);
        g_assert(expect_name(object, "ui-" + std::to_string(generation) + ":2"));
        g_signal_emit(object, pulse_signal, 0, static_cast<int>(generation));
        g_assert(run(context,
            "if(uiCalls!==2||uiSignals!==1) throw Error('dispatch count');"
            "backend.disconnect(handler);delete globalThis.handler;"));
        g_assert(!g_signal_has_handler_pending(object, pulse_signal, 0, true));
        active = nullptr;
        // All JS::Rooted locals were destroyed before disposing this context.
        g_object_unref(context);
        bool released = context_finalized == generation && !evidence.global &&
                        !evidence.marker && !evidence.callback && !evidence.wrapper &&
                        !evidence.signal_callback && evidence.sweeps > 0;
        g_assert(object == identity && G_OBJECT_TYPE(object) == type && !object_finalized);
        g_print("{\"event\":\"generation\",\"generation\":%u,\"native\":\"%p\","
                "\"gtype\":\"%s\",\"contextsFinalized\":%u,\"globalCleared\":%s,"
                "\"markerCleared\":%s,\"callbackCleared\":%s,\"weakSweeps\":%u,"
                "\"wrapperCleared\":%s,\"signalCallbackCleared\":%s,"
                "\"released\":%s}\n", generation, static_cast<void*>(object),
                g_type_name(type), context_finalized, evidence.global ? "false":"true",
                evidence.marker ? "false":"true", evidence.callback ? "false":"true",
                evidence.sweeps, evidence.wrapper ? "false":"true",
                evidence.signal_callback ? "false":"true", released ? "true":"false");
        g_assert(released);
        gap(object);
    }
    g_assert(g_file_enumerator_close(G_FILE_ENUMERATOR(object), nullptr, nullptr));
    g_object_unref(object);
    g_assert(object_finalized == 1);
    g_print("{\"event\":\"native-result\",\"passed\":true,\"contextsFinalized\":3,"
            "\"nativeFinalized\":1}\n");
    return 0;
}

static int negative() {
    GObject* object = nullptr;
    WeakEvidence evidence;
    GjsContext* context = gjs_context_new();
    g_object_weak_ref(G_OBJECT(context), context_gone, nullptr);
    g_assert(run(context,
        "var Gio=imports.gi.Gio;var GObject=imports.gi.GObject;"
        "globalThis.marker={epoch:1};globalThis.uiNextName=()=> 'old-context';"
        "var Old=GObject.registerClass({GTypeName:'TgnomeContextOwnedEnumerator'},"
        "class Old extends Gio.FileEnumerator {"
        "vfunc_next_file(_c){let f=new Gio.FileInfo();f.set_name(uiNextName());return f;}"
        "vfunc_close_fn(_c){return true;}});"
        "globalThis.backend=new Old({container:Gio.File.new_for_path('/tgnome-no-io')});"));
    g_assert(gjs_context_tgnome_native_object(context, "backend", &object, false));
    g_assert(expect_name(object, "old-context"));
    gjs_context_run_in_realm(context, observe, &evidence);
    g_object_unref(context);
    g_print("{\"event\":\"negative-disposed\",\"contextsFinalized\":%u,"
            "\"globalCleared\":%s,\"callbackCleared\":%s}\n",context_finalized,
            evidence.global ? "false":"true",evidence.callback ? "false":"true");
    context = gjs_context_new();
    g_assert(run(context,"imports.gi.Gio; imports.gi.GObject;"
                         "globalThis.uiNextName=()=> 'replacement-context';"));
    g_print("{\"event\":\"negative-wrap-entry\"}\n");
    g_assert(gjs_context_tgnome_native_object(context,"backend",&object,true));
    g_print("{\"event\":\"negative-vfunc-entry\"}\n");
    bool rebound = expect_name(object,"replacement-context");
    g_print("{\"event\":\"negative-result\",\"replacementDispatch\":%s}\n",
            rebound ? "true":"false");
    g_object_unref(context);
    g_object_unref(object);
    return rebound ? 3 : 0;
}
int main(int argc, char** argv) {
    g_assert(argc == 2);
    return strcmp(argv[1], "native") == 0 ? positive() : negative();
}
