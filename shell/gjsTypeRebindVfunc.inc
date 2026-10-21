// Context-independent vfunc entry points. Included in gi/object.cpp.
#include <map>
#include <memory>
#include <cstring>

struct TgnomeVfuncBridge {
    GI::AutoVFuncInfo info;
    ffi_cif cif{};
    ffi_closure* native = nullptr;
    void* fallback = nullptr;
    GjsCallbackTrampoline* delegate = nullptr;  // Weak until invalidated.
    GThread* owner = g_thread_self();
    void* pinned_class;

    TgnomeVfuncBridge(GType type, const GI::VFuncInfo& value)
        : info(value), pinned_class(g_type_class_ref(type)) {}
    ~TgnomeVfuncBridge() {
        if (native)
            info.destroy_closure(native);
        g_type_class_unref(pinned_class);
    }
};
// GType vtables are process lifetime; so are their bridge addresses. Each slot
// is allocated once, irrespective of the number of serial JS contexts.
static std::map<void**, std::unique_ptr<TgnomeVfuncBridge>> tgnome_vfunc_bridges;
static unsigned tgnome_vfunc_gap_calls;
extern "C" GJS_EXPORT unsigned gjs_tgnome_rebind_bridge_count() {
    return tgnome_vfunc_bridges.size();
}
extern "C" GJS_EXPORT unsigned gjs_tgnome_rebind_gap_calls() {
    return tgnome_vfunc_gap_calls;
}

static bool tgnome_install_vfunc_bridge(JSContext* cx, GType type, void** slot,
                                       const GI::VFuncInfo& info,
                                       GjsCallbackTrampoline* delegate) {
    auto& entry = tgnome_vfunc_bridges[slot];
    if (!entry) {
        entry = std::make_unique<TgnomeVfuncBridge>(type, info);
        entry->fallback = *slot;
        entry->native = entry->info.create_closure(&entry->cif,
            [](ffi_cif* cif, void* result, void** args, void* data) {
                auto* bridge = static_cast<TgnomeVfuncBridge*>(data);
                if (bridge->owner != g_thread_self()) {
                    // Do not even read a delegate owned by another thread.
                    if (result && cif->rtype->size)
                        std::memset(result, 0, cif->rtype->size);
                    return;
                }
                if (bridge->delegate) {
                    ffi_call(cif, FFI_FN(bridge->delegate->get_func_ptr()), result, args);
                } else {
                    ++tgnome_vfunc_gap_calls;
                    // Preserve native parent behavior (including out args).
                    // Parent JS overrides also use permanent bridges.
                    if (bridge->fallback)
                        ffi_call(cif, FFI_FN(bridge->fallback), result, args);
                    else if (result && cif->rtype->size)
                        std::memset(result, 0, cif->rtype->size);
                }
            }, entry.get());
        if (!entry->native) {
            entry.reset();
            gjs_throw(cx, "Unable to create native runtime vfunc bridge");
            return false;
        }
    }
    if (entry->delegate) {
        gjs_throw(cx, "Vfunc delegate is still attached");
        return false;
    }
    entry->delegate = delegate;
    g_closure_add_invalidate_notifier(delegate, entry.get(),
        [](void* data, GClosure*) {
            static_cast<TgnomeVfuncBridge*>(data)->delegate = nullptr;
        });
    *slot = entry->info.closure_native_address(entry->native);
    return true;
}
