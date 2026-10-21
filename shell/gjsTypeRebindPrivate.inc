// Private whole-context experiment. Included in gi/private.cpp only.
// Static GTypes keep native metadata; a context may reattach only after the
// former owner finalized and only with the same declared ABI.
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <js/CallAndConstruct.h>

static bool tgnome_rebind_enabled() {
    return g_strcmp0(g_getenv("TGNOME_REBIND_TYPES"), "1") == 0;
}

struct TgnomeTypeRecord {
    std::string schema;
    GjsContext* owner = nullptr;  // Weak, never keeps a runtime alive.
    unsigned registrations = 0;
};
static std::map<GType, std::unique_ptr<TgnomeTypeRecord>> tgnome_type_records;
static std::map<unsigned, int> tgnome_signal_accumulators;

static void tgnome_assign_owner(TgnomeTypeRecord* record) {
    record->owner = gjs_context_get_current();
    ++record->registrations;
    g_object_weak_ref(G_OBJECT(record->owner), [](void* data, GObject*) {
        static_cast<TgnomeTypeRecord*>(data)->owner = nullptr;
    }, record);
}

static bool tgnome_type_schema(JSContext* cx, GType parent, GTypeFlags flags,
                               const GType* interfaces, uint32_t n_interfaces,
                               JS::HandleObject properties, uint32_t n_properties,
                               std::string* schema) {
    *schema = std::to_string(parent) + ":" + std::to_string(flags);
    for (uint32_t i = 0; i < n_interfaces; ++i)
        *schema += ":i" + std::to_string(interfaces[i]);
    for (uint32_t i = 0; i < n_properties; ++i) {
        JS::RootedValue value(cx);
        if (!JS_GetElement(cx, properties, i, &value) || !value.isObject())
            return false;
        JS::RootedObject wrapper(cx, &value.toObject());
        if (!gjs_typecheck_param(cx, wrapper, G_TYPE_NONE, true))
            return false;
        GParamSpec* spec = gjs_g_param_from_param(cx, wrapper);
        GValue def = G_VALUE_INIT;
        g_value_init(&def, G_PARAM_SPEC_VALUE_TYPE(spec));
        g_param_value_set_default(spec, &def);
        // GLib's diagnostic formatter mishandles a null G_TYPE_STRV default.
        // All pointer-backed property defaults are null (except strings and
        // explicitly specified variants); encode null before formatting.
        const bool pointer_value = G_VALUE_HOLDS_STRING(&def) ||
            G_VALUE_HOLDS_BOXED(&def) || G_VALUE_HOLDS_OBJECT(&def) ||
            G_VALUE_HOLDS_PARAM(&def) || G_VALUE_HOLDS_POINTER(&def) ||
            G_VALUE_HOLDS_VARIANT(&def);
        char* text = pointer_value && !g_value_peek_pointer(&def)
            ? g_strdup("<null>") : g_strdup_value_contents(&def);
        *schema += ":p" + std::string(spec->name) + ":" +
            std::to_string(G_PARAM_SPEC_TYPE(spec)) + ":" +
            std::to_string(G_PARAM_SPEC_VALUE_TYPE(spec)) + ":" +
            std::to_string(spec->flags) + ":" + text;
        g_free(text);
        g_value_unset(&def);
        // Bounds are part of the native property's contract, not JS state.
        if (G_IS_PARAM_SPEC_INT(spec)) {
            auto* p = G_PARAM_SPEC_INT(spec);
            *schema += ":" + std::to_string(p->minimum) + ":" + std::to_string(p->maximum);
        } else if (G_IS_PARAM_SPEC_UINT(spec)) {
            auto* p = G_PARAM_SPEC_UINT(spec);
            *schema += ":" + std::to_string(p->minimum) + ":" + std::to_string(p->maximum);
        } else if (G_IS_PARAM_SPEC_INT64(spec)) {
            auto* p = G_PARAM_SPEC_INT64(spec);
            *schema += ":" + std::to_string(p->minimum) + ":" + std::to_string(p->maximum);
        } else if (G_IS_PARAM_SPEC_UINT64(spec)) {
            auto* p = G_PARAM_SPEC_UINT64(spec);
            *schema += ":" + std::to_string(p->minimum) + ":" + std::to_string(p->maximum);
        } else if (G_IS_PARAM_SPEC_DOUBLE(spec)) {
            auto* p = G_PARAM_SPEC_DOUBLE(spec);
            char* bounds = g_strdup_printf(":%a:%a", p->minimum, p->maximum);
            *schema += bounds;
            g_free(bounds);
        }
    }
    return true;
}

static bool tgnome_reuse_type(JSContext* cx, GType type,
                              const std::string& schema) {
    auto found = tgnome_type_records.find(type);
    if (!tgnome_rebind_enabled() || found == tgnome_type_records.end()) {
        gjs_throw(cx, "Type name %s is already registered", g_type_name(type));
        return false;
    }
    auto* record = found->second.get();
    if (record->owner) {
        gjs_throw(cx, "Type %s previous context is still live", g_type_name(type));
        return false;
    }
    if (record->schema != schema) {
        gjs_throw(cx, "Type %s incompatible rebind schema", g_type_name(type));
        return false;
    }
    tgnome_assign_owner(record);
    return true;
}

static void tgnome_remember_type(GType type, const std::string& schema) {
    if (!tgnome_rebind_enabled())
        return;
    auto record = std::make_unique<TgnomeTypeRecord>();
    record->schema = schema;
    tgnome_assign_owner(record.get());
    tgnome_type_records[type] = std::move(record);
}

struct TgnomeSignalBridge {
    GClosure* delegate = nullptr;
    GClosure* native = nullptr;
    GThread* owner = g_thread_self();
};
static std::map<std::pair<GType, unsigned>, std::unique_ptr<TgnomeSignalBridge>>
    tgnome_signal_bridges;

static bool gjs_tgnome_rebind_enabled(JSContext*, unsigned argc, JS::Value* vp) {
    JS::CallArgsFromVp(argc, vp).rval().setBoolean(tgnome_rebind_enabled());
    return true;
}

static bool gjs_tgnome_watch_child(JSContext* cx, unsigned argc, JS::Value* vp) {
    JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
    int priority, pid;
    if (!gjs_parse_call_args(cx, "tgnome_watch_child", args, "ii",
                             "priority", &priority, "pid", &pid))
        return false;
    if (!tgnome_rebind_enabled() || pid <= 0) {
        gjs_throw(cx, "Native child reaping requires the private runtime build");
        return false;
    }
    // IBus deliberately remains a child of the compositor. Its eventual exit
    // must be reaped by process-lifetime native code, not an old JS runtime.
    unsigned id = g_child_watch_add_full(priority, pid,
        [](GPid child, int, void*) { g_spawn_close_pid(child); }, nullptr, nullptr);
    args.rval().setNumber(id);
    return true;
}

static bool gjs_tgnome_override_signal(JSContext* cx, unsigned argc, JS::Value* vp) {
    JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
    int id;
    JS::RootedObject type_wrapper(cx), callable(cx);
    if (!gjs_parse_call_args(cx, "tgnome_override_signal", args, "ioo",
                             "signal", &id, "type", &type_wrapper,
                             "callable", &callable))
        return false;
    GType type;
    if (!gjs_gtype_get_actual_gtype(cx, type_wrapper, &type) ||
        !tgnome_rebind_enabled() || !JS::IsCallable(callable)) {
        gjs_throw(cx, "Signal rebind requires the private runtime experiment");
        return false;
    }
    auto key = std::make_pair(type, static_cast<unsigned>(id));
    auto& entry = tgnome_signal_bridges[key];
    if (!entry) {
        entry = std::make_unique<TgnomeSignalBridge>();
        entry->native = g_closure_new_simple(sizeof(GClosure), entry.get());
        g_closure_set_marshal(entry->native,
            [](GClosure* closure, GValue* ret, unsigned n, const GValue* params,
               void* hint, void*) {
                auto* bridge = static_cast<TgnomeSignalBridge*>(closure->data);
                if (bridge->owner == g_thread_self() && bridge->delegate)
                    g_closure_invoke(bridge->delegate, ret, n, params, hint);
                else if (ret && G_IS_VALUE(ret))
                    g_value_reset(ret);
            });
        g_signal_override_class_closure(id, type, entry->native);
    }
    if (entry->delegate) {
        gjs_throw(cx, "Signal delegate is still attached");
        return false;
    }
    // The callable is rooted only within this context. Invalidation releases
    // the delegate; the permanent native signal closure holds no JS root.
    entry->delegate = Gjs::Closure::create_marshaled(cx, callable,
                                                    "runtime signal delegate");
    g_closure_ref(entry->delegate);
    g_closure_sink(entry->delegate);
    g_closure_add_invalidate_notifier(entry->delegate, entry.get(),
        [](void* data, GClosure* closure) {
            static_cast<TgnomeSignalBridge*>(data)->delegate = nullptr;
            g_closure_unref(closure);
        });
    args.rval().setUndefined();
    return true;
}
