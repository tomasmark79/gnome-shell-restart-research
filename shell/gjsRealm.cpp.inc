
// Experimental embedding ABI, deliberately absent from the installed GIR/header.
// Used only by realm-probe and the private headless realm-shell. Keeps the main
// global/native GI registry and creates a disposable UI global/module registry.
#include <js/MapAndSet.h>

static bool tgnome_realm_compile(JSContext* cx, unsigned argc, JS::Value* vp) {
    JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
    if (argc != 2 || !args[0].isString() || !args[1].isString()) {
        JS_ReportErrorASCII(cx, "Expected a module URI and source string");
        return false;
    }
    JS::RootedString uri_string(cx, args[0].toString());
    JS::UniqueChars uri = JS_EncodeStringToUTF8(cx, uri_string);
    JS::RootedString source(cx, args[1].toString());
    size_t length;
    char16_t* text;
    if (!uri || !gjs_string_get_char16_data(cx, source, &text, &length))
        return false;
    JS::SourceText<char16_t> buffer;
    if (!buffer.init(cx, text, length, JS::SourceOwnership::TakeOwnership))
        return false;
    JS::CompileOptions options(cx);
    options.setFileAndLine(uri.get(), 1).setSourceIsLazy(false);
    // The function was allocated in the target realm. Do not enter AutoMainRealm:
    // the upstream internal compileModule() would compile into the old global.
    JS::RootedObject module(cx, JS::CompileModule(cx, options, buffer));
    if (!module)
        return false;
    args.rval().setObject(*module);
    return true;
}

extern "C" GJS_EXPORT void* gjs_context_tgnome_create_ui_realm(GjsContext* self) {
    auto* context = GjsContextPrivate::from_object(self);
    if (!context || !context->is_owner_thread() || context->destroying())
        return nullptr;
    JSContext* cx = context->context();
    JS::RootedObject backend(cx, context->global());
    JS::RootedObject global(cx, gjs_create_global_object(
        cx, GjsGlobalType::DEFAULT, backend));
    if (!global)
        return nullptr;
    JS::RootedObject compiler(cx);
    {
        JSAutoRealm ar(cx, global);
        // Native bindings are deliberately canonical, owned by the backend.
        // UI modules and their lexical globals are independently instantiated.
        gjs_set_global_slot(global, GjsGlobalSlot::IMPORTS,
                            gjs_get_global_slot(backend, GjsGlobalSlot::IMPORTS));
        if (!gjs_define_global_properties(cx, global, GjsGlobalType::DEFAULT,
                                         "TGNOME disposable UI", "default"))
            return nullptr;
        JSFunction* function = JS_NewFunction(cx, tgnome_realm_compile, 2, 0,
                                              "tgnomeCompileModule");
        if (!function)
            return nullptr;
        compiler = JS_GetFunctionObject(function);
    }
    {
        Gjs::AutoInternalRealm ar(context);
        // The maps have independent contents, but canonical native prototypes.
        // Internal loader ICs otherwise retain a disposable realm's Map.prototype
        // through calls to registry.get()/set(), after all UI owners detach.
        // Native argument conversion also looks up GI in the callback realm's
        // registry. Share the canonical native bindings, not an empty map.
        gjs_set_global_slot(global, GjsGlobalSlot::NATIVE_REGISTRY,
                            gjs_get_global_slot(backend, GjsGlobalSlot::NATIVE_REGISTRY));
        for (GjsGlobalSlot slot : {GjsGlobalSlot::MODULE_REGISTRY,
                                   GjsGlobalSlot::SOURCE_MAP_REGISTRY}) {
            JS::RootedObject registry(cx, JS::NewMapObject(cx));
            if (!registry)
                return nullptr;
            gjs_set_global_slot(global, slot, JS::ObjectValue(*registry));
        }
        static constexpr char16_t factory_text[] =
            u"(function(backendLoader, target, compiler) {"
            u"const loader = new backendLoader.constructor(target);"
            u"loader.compileFunc = compiler;"
            u"loader.schemeHandlers = new Map(backendLoader.schemeHandlers);"
            u"setGlobalModuleLoader(target, loader);"
            u"})";
        JS::SourceText<char16_t> source;
        if (!source.init(cx, factory_text, G_N_ELEMENTS(factory_text) - 1,
                         JS::SourceOwnership::Borrowed))
            return nullptr;
        JS::CompileOptions options(cx);
        options.setFileAndLine("tgnome-realm-loader", 1);
        JS::RootedValue factory(cx), ignored(cx);
        if (!JS::Evaluate(cx, options, source, &factory))
            return nullptr;
        JS::RootedValueArray<3> args(cx);
        args[0].set(gjs_get_global_slot(backend, GjsGlobalSlot::MODULE_LOADER));
        args[1].setObject(*global);
        args[2].setObject(*compiler);
        if (!JS::Call(cx, JS::UndefinedHandleValue, factory, args, &ignored))
            return nullptr;
    }
    // Caller must immediately root the returned pointer before any JS/GC call.
    return global.get();
}

static bool tgnome_create_ui_module(JSContext* cx, unsigned argc, JS::Value* vp) {
    JS::CallArgs args = JS::CallArgsFromVp(argc, vp);
    if (argc != 2 || !args[0].isString() || !args[1].isObject()) {
        JS_ReportErrorASCII(cx, "Expected a UI module URI and backend bindings");
        return false;
    }
    JS::RootedString uri_string(cx, args[0].toString());
    JS::UniqueChars uri = JS_EncodeStringToUTF8(cx, uri_string);
    if (!uri)
        return false;
    // A fixed local resource, not a caller-selected module execution service.
    if (strcmp(uri.get(), "resource:///org/gnome/shell/ui/tgnomePanelRealm.js") &&
        strcmp(uri.get(), "resource:///org/gnome/shell/ui/tgnomeDateMenuRealm.js")) {
        JS_ReportErrorASCII(cx, "Unsupported experimental UI module");
        return false;
    }
    auto* context = GjsContextPrivate::from_cx(cx);
    JS::RootedObject global(cx, static_cast<JSObject*>(
        gjs_context_tgnome_create_ui_realm(context->public_context())));
    if (!global)
        return false;
    JSAutoRealm ar(cx, global);
    JS::RootedObject bindings(cx, &args[1].toObject());
    if (!JS_DefineProperty(cx, global, "_tgnomeUiBackend", bindings,
                           JSPROP_READONLY | JSPROP_PERMANENT))
        return false;
    JS::RootedObject module(cx, gjs_module_load(cx, uri.get(), uri.get()));
    JS::RootedValue result(cx);
    if (!module || !JS::ModuleLink(cx, module) ||
        !JS::ModuleEvaluate(cx, module, &result))
        return false;
    if (!result.isObject())
        return false;
    JS::RootedObject promise(cx, &result.toObject());
    if (JS::GetPromiseState(promise) != JS::PromiseState::Fulfilled) {
        if (JS::GetPromiseState(promise) == JS::PromiseState::Rejected) {
            JS::RootedValue error(cx, JS::GetPromiseResult(promise));
            JS_SetPendingException(cx, error);
        } else {
            JS_ReportErrorASCII(cx, "UI module initialization cannot await");
        }
        return false;
    }
    JS::RootedObject exports(cx, JS::GetModuleNamespace(cx, module));
    if (!exports || !JS_GetProperty(cx, exports, "implementation", args.rval()))
        return false;
    return true;
}

extern "C" GJS_EXPORT gboolean
gjs_context_tgnome_install_ui_loader(GjsContext* self) {
    auto* context = GjsContextPrivate::from_object(self);
    if (!context || !context->is_owner_thread() || context->destroying())
        return false;
    Gjs::AutoMainRealm ar(context);
    JS::RootedObject global(context->context(), context->global());
    return JS_DefineFunction(context->context(), global,
                             "_tgnomeCreateUiRealmModule",
                             tgnome_create_ui_module, 2, 0) != nullptr;
}
