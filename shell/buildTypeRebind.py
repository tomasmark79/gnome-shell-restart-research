"""Patch the pinned GJS sources for the separate context-rebind experiment."""
from pathlib import Path


def replace(path, old, new, count=1):
    source = Path(path).read_text()
    assert source.count(old) == count, (path, old, source.count(old))
    Path(path).write_text(source.replace(old, new))


replace('gi/private.cpp', 'using mozilla::Nothing;',
        'using mozilla::Nothing;\n#include "tgnomeTypeRebindPrivate.inc"')
duplicate = '''    if (g_type_from_name(name) != G_TYPE_INVALID) {
        gjs_throw(cx, "Type name %s is already registered", name);
        return false;
    }'''
source = Path('gi/private.cpp').read_text()
assert source.count(duplicate) == 2
schema = '''    std::string rebind_schema;
    if (!tgnome_type_schema(cx, PARENT, FLAGS, iface_types, n_interfaces,
                            properties, n_properties, &rebind_schema))
        return false;
    GType existing = g_type_from_name(name);
    if (existing != G_TYPE_INVALID) {
        if (!tgnome_reuse_type(cx, existing, rebind_schema))
            return false;
        *gtype = existing;
        OUTPUTS
        return true;
    }'''
interface = schema.replace('PARENT', 'G_TYPE_INTERFACE').replace('FLAGS', 'GTypeFlags(0)').replace('OUTPUTS', '')
object_type = schema.replace('PARENT', 'parent_priv->gtype()').replace('FLAGS', 'type_flags').replace(
    'OUTPUTS', '*n_interfaces_out = n_interfaces;\n        *iface_types_out = iface_types.release();')
source = source.replace(duplicate, interface, 1).replace(duplicate, object_type, 1)
source = source.replace('    *gtype = interface_type;',
                        '    tgnome_remember_type(interface_type, rebind_schema);\n    *gtype = interface_type;', 1)
source = source.replace('    *gtype = instance_type;',
                        '    tgnome_remember_type(instance_type, rebind_schema);\n    *gtype = instance_type;', 1)
signal_anchor = '    unsigned signal_id = g_signal_newv('
assert source.count(signal_anchor) == 1
source = source.replace(signal_anchor, '''    unsigned existing_signal = g_signal_lookup(signal_name.get(), gtype);
    if (tgnome_rebind_enabled() && existing_signal) {
        auto record = tgnome_type_records.find(gtype);
        GSignalQuery query{};
        g_signal_query(existing_signal, &query);
        bool compatible = record != tgnome_type_records.end() &&
            record->second->registrations > 1 && query.itype == gtype &&
            query.signal_flags == static_cast<GSignalFlags>(flags) &&
            query.return_type == return_type && query.n_params == n_parameters &&
            tgnome_signal_accumulators.at(existing_signal) == accumulator_enum;
        for (uint32_t i = 0; compatible && i < n_parameters; ++i)
            compatible = query.param_types[i] == params[i];
        if (!compatible) {
            gjs_throw(cx, "Signal %s incompatible rebind schema", signal_name.get());
            return false;
        }
        args.rval().setInt32(existing_signal);
        return true;
    }
''' + signal_anchor)
source = source.replace('    args.rval().setInt32(signal_id);',
    '''    if (tgnome_rebind_enabled() && signal_id)
        tgnome_signal_accumulators[signal_id] = accumulator_enum;
    args.rval().setInt32(signal_id);''', 1)
source = source.replace('static JSFunctionSpec private_module_funcs[] = {',
    '''static JSFunctionSpec private_module_funcs[] = {
    JS_FN("tgnome_rebind_enabled", gjs_tgnome_rebind_enabled, 0, 0),
    JS_FN("tgnome_watch_child", gjs_tgnome_watch_child, 2, 0),
    JS_FN("tgnome_override_signal", gjs_tgnome_override_signal, 3, 0),''', 1)
Path('gi/private.cpp').write_text(source)

replace('gi/object.cpp', 'bool ObjectPrototype::hook_up_vfunc_impl(',
        '#include "tgnomeTypeRebindVfunc.inc"\n\nbool ObjectPrototype::hook_up_vfunc_impl(')
replace('gi/object.cpp', '        *vfunc_slot_ptr = trampoline->get_func_ptr();',
        '''        if (g_strcmp0(g_getenv("TGNOME_REBIND_TYPES"), "1") == 0) {
            if (!tgnome_install_vfunc_bridge(cx, m_gtype, vfunc_slot_ptr, vfunc.ref(), trampoline))
                return false;
        } else {
            *vfunc_slot_ptr = trampoline->get_func_ptr();
        }''')
replace('gi/object.cpp', 'ObjectPrototype::~ObjectPrototype() {',
        '''ObjectPrototype::~ObjectPrototype() {
    if (ObjectPrototype::for_gtype(m_gtype) == this)
        g_type_set_qdata(m_gtype, gjs_object_priv_quark(), nullptr);''')
replace('modules/core/overrides/GObject.js',
        '                GObject.signal_override_class_closure(id, klass.$gtype, function (...argArray) {',
        '''                const override = Gi.tgnome_rebind_enabled()
                    ? Gi.tgnome_override_signal : GObject.signal_override_class_closure;
                override(id, klass.$gtype, function (...argArray) {''')

# Upstream keeps this registration bit for the process. After JS_DestroyContext
# the hook is gone, so a subsequent runtime never updates weak native wrappers
# during moving GC. A later toggle-up then dereferences the old JS address.
replace('gi/object.cpp', 'bool ObjectInstance::s_weak_pointer_callback = false;\n', '')
replace('gi/object.h', '    static bool s_weak_pointer_callback;\n', '')
replace('gjs/context-private.h',
        '    std::atomic_bool m_destroying = ATOMIC_VAR_INIT(false);',
        '''    std::atomic_bool m_destroying = ATOMIC_VAR_INIT(false);
    bool m_object_weak_pointer_callback = false;''')
replace('gjs/context-private.h',
        '    [[nodiscard]] bool destroying() const { return m_destroying.load(); }',
        '''    [[nodiscard]] bool destroying() const { return m_destroying.load(); }
    bool has_object_weak_pointer_callback() const { return m_object_weak_pointer_callback; }
    void mark_object_weak_pointer_callback() { m_object_weak_pointer_callback = true; }''')
replace('gi/object.cpp',
        '''    if (!s_weak_pointer_callback) {
        JS_AddWeakPointerCompartmentCallback(
            cx, &ObjectInstance::update_heap_wrapper_weak_pointers, nullptr);
        s_weak_pointer_callback = true;
    }''',
        '''    auto* context = GjsContextPrivate::from_cx(cx);
    if (!context->has_object_weak_pointer_callback()) {
        if (g_strcmp0(g_getenv("TGNOME_REBIND_TYPES"), "1") == 0)
            ToggleQueue::get_default()->restart();
        JS_AddWeakPointerCompartmentCallback(
            cx, &ObjectInstance::update_heap_wrapper_weak_pointers, nullptr);
        context->mark_object_weak_pointer_callback();
    }''')
replace('gi/toggle.h', '    void shutdown();',
        '''    void shutdown();
    void restart() {
        g_assert(q.empty());
        m_shutdown = false;
    }''')

replace('gi/function.cpp', 'GjsCallbackTrampoline::GjsCallbackTrampoline(',
        '#include "tgnomeCallbackLifetimes.inc"\n\nGjsCallbackTrampoline::GjsCallbackTrampoline(')
replace('gi/function.cpp', '    add_finalize_notifier<GjsCallbackTrampoline>();',
        '''    m_tgnome_epoch = tgnome_callback_register(cx, m_info.name());
    add_finalize_notifier<GjsCallbackTrampoline>();''')
replace('gi/function.cpp', 'GjsCallbackTrampoline::~GjsCallbackTrampoline() {',
        '''GjsCallbackTrampoline::~GjsCallbackTrampoline() {
    tgnome_callback_unregister(m_tgnome_epoch, m_info.name());''')
replace('gi/function.h', '    bool m_is_vfunc : 1;',
        '    bool m_is_vfunc : 1;\n    unsigned m_tgnome_epoch = 0;')
