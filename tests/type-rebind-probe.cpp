// Reuse the existing weak-reference/native-object instrumentation unchanged.
#define main original_native_type_main
#include "native-type-probe.cpp"
#undef main
#include <cerrno>
#include <sys/wait.h>

extern "C" unsigned gjs_tgnome_rebind_bridge_count();
extern "C" unsigned gjs_tgnome_rebind_gap_calls();

static unsigned object_type_count(GType parent) {
    unsigned n;
    GType* children = g_type_children(parent, &n);
    unsigned count = n;
    for (unsigned i = 0; i < n; ++i)
        count += object_type_count(children[i]);
    g_free(children);
    return count;
}

int main(int argc, char** argv) {
    if (argc == 2 && g_str_equal(argv[1], "--reaper-child")) {
        g_usleep(150000);
        return 7;
    }
    g_setenv("TGNOME_REBIND_TYPES", "1", true);
    GObject* object = nullptr;
    GObject* identity = nullptr;
    GType identity_type = G_TYPE_INVALID;
    unsigned first_signal = 0, first_count = 0, bridges = 0;
    for (unsigned generation = 1; generation <= 3; ++generation) {
        GjsContext* context = gjs_context_new();
        g_object_weak_ref(G_OBJECT(context), context_gone, nullptr);
        std::string script =
            "const {GObject,Gio}=imports.gi;"
            "globalThis.uiEpoch=" + std::to_string(generation) + ";"
            "globalThis.marker={epoch:uiEpoch};globalThis.uiCalls=0;"
            "globalThis.uiSignals=0;globalThis.uiHandlerSignals=0;"
            "globalThis.uiProperty=uiEpoch;"
            "globalThis.uiNextName=()=>{if(marker.epoch!==uiEpoch)throw Error('stale');"
            "return 'rebound-'+uiEpoch+':'+(++uiCalls);};"
            "globalThis.RebindInterface=GObject.registerClass({"
            "GTypeName:'TgnomeRebindInterface',Requires:[GObject.Object]},"
            "class RebindInterface extends GObject.Interface{});"
            "if(uiEpoch>1){let refused=false;try{GObject.registerClass({"
            "GTypeName:'TgnomeRebindEnumerator'},class Wrong extends GObject.Object{});"
            "}catch(e){refused=e.message.includes('incompatible rebind schema');}"
            "if(!refused)throw Error('incompatible ABI accepted');}"
            "globalThis.RebindType=GObject.registerClass({"
            "GTypeName:'TgnomeRebindEnumerator',Implements:[RebindInterface],"
            "Properties:{value:GObject.ParamSpec.int('value','value','value',"
            "GObject.ParamFlags.READWRITE,0,1000,0)},"
            "Signals:{pulse:{param_types:[GObject.TYPE_INT]}}},"
            "class RebindType extends Gio.FileEnumerator{"
            "vfunc_next_file(){let info=new Gio.FileInfo();info.set_name(uiNextName());return info;}"
            "vfunc_close_fn(){return true;}"
            "get value(){return uiProperty;}set value(n){uiProperty=n;}"
            "on_pulse(n){uiSignals+=n;}"
            "});"
            "let refused=false;try{GObject.registerClass({GTypeName:'TgnomeRebindEnumerator'},"
            "class Duplicate extends GObject.Object{});}catch(e){"
            "refused=e.message.includes('previous context is still live');}"
            "if(!refused)throw Error('live-context reuse accepted');";
        g_assert(run(context, script.c_str()));
        if (!object) {
            g_assert(run(context, "globalThis.backend=new RebindType({container:Gio.File.new_for_path('/tgnome-no-io')});"));
            g_assert(gjs_context_tgnome_native_object(context, "backend", &object, false));
            identity = object;
            identity_type = G_OBJECT_TYPE(object);
            first_signal = g_signal_lookup("pulse", identity_type);
            g_object_weak_ref(object, object_gone, nullptr);
        } else {
            g_assert(gjs_context_tgnome_native_object(context, "backend", &object, true));
            g_assert(run(context, "if(!(backend instanceof RebindType))throw Error('wrong prototype');"));
        }
        g_assert(object == identity && G_OBJECT_TYPE(object) == identity_type);
        g_assert(first_signal == g_signal_lookup("pulse", identity_type));
        g_assert(expect_name(object, "rebound-" + std::to_string(generation) + ":1"));
        int value = -1;
        g_object_get(object, "value", &value, nullptr);
        g_assert(value == static_cast<int>(generation));
        g_object_set(object, "value", static_cast<int>(generation + 100), nullptr);
        g_assert(run(context, "if(uiProperty!==uiEpoch+100)throw Error('native property setter');"
                      "globalThis.uiOnPulse=()=>{++uiHandlerSignals;};"
                      "globalThis.handler=backend.connect('pulse',uiOnPulse);"));
        g_signal_emit(object, first_signal, 0, static_cast<int>(generation));
        g_assert(run(context, "if(uiSignals!==uiEpoch||uiHandlerSignals!==1)throw Error('signal dispatch');"
                      "backend.disconnect(handler);delete globalThis.handler;"));
        // Force relocation of a weak native wrapper inside every fresh
        // runtime, then trigger its native toggle-ref callback. Context
        // destruction alone does not exercise per-runtime weak-GC hooks.
        g_assert(run(context, "globalThis.transient=new Gio.FileInfo();transient.expando=uiEpoch;"));
        GObject* transient = nullptr;
        g_assert(gjs_context_tgnome_native_object(context, "transient", &transient, false));
        g_object_unref(transient);  // Borrowed through the still-live JS global.
        gjs_context_run_in_realm(context, [](GjsContext* ctx, void*) {
            auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(ctx));
            JS::PrepareForFullGC(cx);
            JS::NonIncrementalGC(cx, JS::GCOptions::Shrink, JS::GCReason::API);
        }, nullptr);
        g_object_ref(transient);
        g_assert(run(context, "if(transient.expando!==uiEpoch)throw Error('weak wrapper lost');"));
        g_object_unref(transient);
        g_assert(run(context, "delete globalThis.transient;"));
        WeakEvidence evidence;
        evidence.track_wrapper = true;
        gjs_context_run_in_realm(context, observe, &evidence);
        GPid child = 0;
        int child_watch = 0;
        char* child_args[] = {argv[0], const_cast<char*>("--reaper-child"), nullptr};
        GError* child_error = nullptr;
        g_assert(g_spawn_async(nullptr, child_args, nullptr, G_SPAWN_DO_NOT_REAP_CHILD,
                               nullptr, nullptr, &child, &child_error));
        std::string watch_script = "imports._gi.tgnome_watch_child(0," +
            std::to_string(child) + ");";
        g_assert(gjs_context_eval(context, watch_script.c_str(), -1,
                                 "<native-child-watch>", &child_watch, &child_error));
        g_assert(!child_error && child_watch > 0);
        unsigned count = object_type_count(G_TYPE_OBJECT);
        if (generation == 1) {
            first_count = count;
            bridges = gjs_tgnome_rebind_bridge_count();
        }
        g_assert(count == first_count && gjs_tgnome_rebind_bridge_count() == bridges);
        g_object_unref(context);
        bool released = context_finalized == generation && !evidence.global &&
            !evidence.marker && !evidence.callback && !evidence.wrapper &&
            !evidence.signal_callback && evidence.sweeps;
        g_assert(released);
        const auto deadline = g_get_monotonic_time() + 2 * G_TIME_SPAN_SECOND;
        while (g_main_context_find_source_by_id(nullptr, child_watch) &&
               g_get_monotonic_time() < deadline) {
            while (g_main_context_iteration(nullptr, false)) {}
            g_usleep(1000);
        }
        g_assert(!g_main_context_find_source_by_id(nullptr, child_watch));
        int child_status;
        g_assert(waitpid(child, &child_status, WNOHANG) == -1 && errno == ECHILD);
        // Invoke the exact old native vfunc and signal entry points after the
        // complete JSContext has gone. No dangling GJS trampoline may run.
        GError* error = nullptr;
        GFileInfo* info = g_file_enumerator_next_file(G_FILE_ENUMERATOR(object), nullptr, &error);
        g_assert(!info && !error);
        g_signal_emit(object, first_signal, 0, -1);
        g_print("{\"generation\":%u,\"contextsFinalized\":%u,\"released\":true,"
                "\"native\":\"%p\",\"gtype\":%lu,\"objectTypes\":%u,"
                "\"bridges\":%u,\"gapCalls\":%u,\"nativeChildReaped\":true}\n", generation,
                context_finalized, static_cast<void*>(object),
                static_cast<unsigned long>(identity_type), count, bridges,
                gjs_tgnome_rebind_gap_calls());
    }
    g_object_unref(object);
    g_assert(object_finalized == 1);
    g_print("{\"passed\":true,\"contextsFinalized\":3,\"nativeFinalized\":1}\n");
}
