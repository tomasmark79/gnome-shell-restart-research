// Private, one-shot headless experiment. No host or general recovery API.
#include "interruptWatchdog.h"
#include <js/Interrupt.h>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <thread>

namespace {
GjsContext* context;
JSContext* native;
GSourceFunc resumed_callback;
std::thread worker;
std::mutex mutex;
std::condition_variable condition;
bool stopped = true;
bool armed = false;
bool used = false;
guint resumed_source;
std::atomic<bool> requested{false};
unsigned delivered;
unsigned denied;
unsigned resumed;

gboolean on_resumed(gpointer) {
    resumed_source = 0;
    ++resumed;
    return resumed_callback(nullptr);
}

bool on_interrupt(JSContext*) {
    if (!requested.exchange(false))
        return true;
    if (!gjs_context_tgnome_mark_interrupt(context)) {
        ++denied;
        g_message("TGNOME watchdog interruption refused");
        return true;
    }
    ++delivered;
    // Runs only after the interrupted outer callback has returned to GLib.
    resumed_source = g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, on_resumed, nullptr, nullptr);
    g_message("TGNOME watchdog interruption delivered");
    return false;
}
}

gboolean tgnome_watchdog_start(GjsContext* embedding, GSourceFunc callback) {
    if (worker.joinable() || !embedding || !callback)
        return false;
    context = embedding;
    native = static_cast<JSContext*>(gjs_context_get_native_context(context));
    if (!JS_AddInterruptCallback(native, on_interrupt))
        return false;
    resumed_callback = callback;
    stopped = false;
    worker = std::thread([] {
        std::unique_lock<std::mutex> lock(mutex);
        condition.wait(lock, [] { return stopped || armed; });
        if (stopped)
            return;
        if (condition.wait_for(lock, std::chrono::milliseconds(1000), [] { return stopped; }))
            return;
        armed = false;
        requested.store(true);
        JS_RequestInterruptCallback(native);
    });
    return true;
}

gboolean tgnome_watchdog_arm(void) {
    std::lock_guard<std::mutex> lock(mutex);
    if (stopped || used)
        return false;
    used = true;
    armed = true;
    condition.notify_all();
    return true;
}

char* tgnome_watchdog_status(void) {
    return g_strdup_printf("{\"delivered\":%u,\"denied\":%u,\"nativeResumptions\":%u}",
                           delivered, denied, resumed);
}

void tgnome_watchdog_stop(void) {
    {
        std::lock_guard<std::mutex> lock(mutex);
        stopped = true;
        condition.notify_all();
    }
    if (worker.joinable())
        worker.join();
    requested.store(false);
    g_clear_handle_id(&resumed_source, g_source_remove);
}
