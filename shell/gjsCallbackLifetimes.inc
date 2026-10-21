// Native-only ownership ledger for the private context replacement build.
// Entries contain no JS values, and never keep a GjsContext alive.
#include <map>
#include <mutex>

static std::mutex tgnome_callback_mutex;
static unsigned tgnome_callback_epoch;
static std::map<unsigned, std::map<std::string, unsigned>> tgnome_callbacks;

static unsigned tgnome_callback_register(JSContext* cx, const char* name) {
    if (g_strcmp0(g_getenv("TGNOME_REBIND_TYPES"), "1") != 0)
        return 0;
    auto* context = GjsContextPrivate::from_cx(cx)->public_context();
    const GQuark key = g_quark_from_static_string("tgnome-callback-epoch");
    std::lock_guard<std::mutex> lock(tgnome_callback_mutex);
    unsigned epoch = GPOINTER_TO_UINT(g_object_get_qdata(G_OBJECT(context), key));
    if (!epoch) {
        epoch = ++tgnome_callback_epoch;
        g_object_set_qdata(G_OBJECT(context), key, GUINT_TO_POINTER(epoch));
    }
    ++tgnome_callbacks[epoch][name];
    return epoch;
}

static void tgnome_callback_unregister(unsigned epoch, const char* name) {
    if (!epoch)
        return;
    std::lock_guard<std::mutex> lock(tgnome_callback_mutex);
    auto& names = tgnome_callbacks.at(epoch);
    if (--names.at(name) == 0)
        names.erase(name);
}

extern "C" GJS_EXPORT char* gjs_tgnome_callback_lifetimes() {
    std::lock_guard<std::mutex> lock(tgnome_callback_mutex);
    std::string json = "{\"latestEpoch\":" + std::to_string(tgnome_callback_epoch) +
        ",\"epochs\":{";
    bool first_epoch = true;
    for (const auto& [epoch, names] : tgnome_callbacks) {
        if (!first_epoch)
            json += ",";
        first_epoch = false;
        json += "\"" + std::to_string(epoch) + "\":{";
        bool first_name = true;
        for (const auto& [name, count] : names) {
            if (!first_name)
                json += ",";
            first_name = false;
            json += "\"" + name + "\":" + std::to_string(count);
        }
        json += "}";
    }
    json += "}}";
    return g_strdup(json.c_str());
}
