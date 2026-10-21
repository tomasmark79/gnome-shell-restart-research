
// Private experiment ABI. No GIR/public API or Shell integration.
#include "gi/value.h"

extern "C" GJS_EXPORT gboolean gjs_context_tgnome_native_object(
    GjsContext* self, const char* name, GObject** object, gboolean put) {
    auto* context = GjsContextPrivate::from_object(self);
    if (!context || !context->is_owner_thread() || context->destroying())
        return false;
    Gjs::AutoMainRealm realm(context);
    JSContext* cx = context->context();
    JS::RootedObject global(cx, context->global());
    JS::RootedValue value(cx);
    GValue native = G_VALUE_INIT;
    g_value_init(&native, G_TYPE_OBJECT);
    bool ok;
    if (put) {
        g_value_set_object(&native, *object);
        ok = gjs_value_from_g_value(cx, &value, &native) &&
             JS_DefineProperty(cx, global, name, value, 0);
    } else {
        ok = JS_GetProperty(cx, global, name, &value) &&
             gjs_value_to_g_value(cx, value, &native);
        if (ok)
            *object = G_OBJECT(g_value_dup_object(&native));
    }
    g_value_unset(&native);
    return ok;
}
