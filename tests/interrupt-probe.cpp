// Standalone embedding experiment. The supervisor owns runtime isolation and
// deadlines; this executable never creates a compositor or opens a display.
#include <gjs/gjs.h>
#include <gio/gio.h>
#include <js/Interrupt.h>
#include <js/CompilationAndEvaluation.h>
#include <js/CompileOptions.h>
#include <js/SourceText.h>
#include <js/Value.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

namespace {
std::atomic<bool> requested{false};
std::atomic<unsigned> delivered{0};
std::atomic<unsigned> denied{0};
unsigned heartbeats = 0;
bool recoverable = false;
GjsContext* embedding_context = nullptr;

bool interrupt(JSContext*) {
    // SpiderMonkey also calls this hook for its own work. Never terminate
    // unless our watchdog explicitly requested this particular intervention.
    if (!requested.exchange(false))
        return true;
#ifdef TGNOME_RECOVERABLE_GJS
    if (recoverable && !gjs_context_tgnome_mark_interrupt(embedding_context)) {
        const auto count = denied.fetch_add(1) + 1;
        g_print("{\"event\":\"interrupt-denied\",\"count\":%u}\n", count);
        return true;
    }
#endif
    const auto count = delivered.fetch_add(1) + 1;
    g_print("{\"event\":\"interrupt-delivered\",\"count\":%u}\n", count);
    return false;
}

bool take_marker(GjsContext* context) {
#ifdef TGNOME_RECOVERABLE_GJS
    return gjs_context_tgnome_take_interrupt(context);
#else
    (void) context;
    return false;
#endif
}

class Watchdog {
    JSContext* const context;
    std::mutex mutex;
    std::condition_variable changed;
    bool stopping = false;
    bool armed = false;
    unsigned serial = 0;
    std::thread worker;

    void run() {
        std::unique_lock<std::mutex> lock(mutex);
        while (!stopping) {
            changed.wait(lock, [&] { return stopping || armed; });
            if (stopping)
                break;
            const auto ticket = serial;
            if (changed.wait_for(lock, std::chrono::milliseconds(500), [&] {
                    return stopping || !armed || serial != ticket;
                }))
                continue;
            requested.store(true);
            // The documented cross-thread API only sets the interrupt request.
            // The hook itself runs on the context's JS thread, with no reentry.
            JS_RequestInterruptCallback(context);
            armed = false;
        }
    }

 public:
    explicit Watchdog(JSContext* cx) : context(cx), worker([this] { run(); }) {}
    void arm() {
        std::lock_guard<std::mutex> lock(mutex);
        ++serial;
        requested.store(false);
        armed = true;
        changed.notify_all();
    }
    void disarm() {
        std::lock_guard<std::mutex> lock(mutex);
        armed = false;
        requested.store(false);
        changed.notify_all();
    }
    ~Watchdog() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            stopping = true;
            armed = false;
            requested.store(false);
            changed.notify_all();
        }
        worker.join(); // Always precedes GjsContext disposal.
    }
};

std::string json_string(const char* input) {
    std::string result = "\"";
    for (const unsigned char c : std::string(input ? input : "")) {
        if (c == '\\' || c == '"') {
            result += '\\';
            result += static_cast<char>(c);
        } else if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c == '\t') result += "\\t";
        else if (c < 32) {
            char escaped[7];
            g_snprintf(escaped, sizeof escaped, "\\u%04x", c);
            result += escaped;
        } else result += static_cast<char>(c);
    }
    return result + '"';
}

bool evaluate(GjsContext* context, const char* script, const char* filename,
              int* status, GError** error) {
    return gjs_context_eval(context, script, -1, filename, status, error);
}

bool verify(GjsContext* context, const char* expression) {
    GError* error = nullptr;
    int status = -1;
    const std::string script = "(" + std::string(expression) + ") ? 0 : 1;";
    const bool ok = evaluate(context, script.c_str(), "<verification>", &status, &error);
    if (!ok)
        g_printerr("verification failed: %s\n", error ? error->message : "unknown");
    g_clear_error(&error);
    return ok && status == 0;
}

void pump_for(unsigned milliseconds) {
    const auto end = g_get_monotonic_time() + milliseconds * 1000;
    while (g_get_monotonic_time() < end) {
        g_main_context_iteration(nullptr, false);
        g_usleep(1000);
    }
}

struct RawEvaluation {
    const char* script;
    bool accepted = false;
};

void raw_evaluate(GjsContext* context, void* data) {
    auto* request = static_cast<RawEvaluation*>(data);
    auto* cx = static_cast<JSContext*>(gjs_context_get_native_context(context));
    JS::CompileOptions options(cx);
    options.setFileAndLine("<raw-native-entry>", 1);
    JS::SourceText<mozilla::Utf8Unit> source;
    JS::RootedValue result(cx);
    request->accepted = source.init(cx, request->script, std::strlen(request->script),
                                   JS::SourceOwnership::Borrowed) &&
        JS::Evaluate(cx, options, source, &result);
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 2 || g_strcmp0(g_getenv("TGNOME_INTERRUPT_ISOLATED"), "1") != 0) {
        g_printerr("Run this experimental binary through interrupt-supervisor.py\n");
        return 2;
    }
    const std::string mode = argv[1];
    if (mode != "hard" && mode != "recoverable" && mode != "recover-then-hard" &&
        mode != "nested" && mode != "nested-loop" && mode != "promise" &&
        mode != "module" && mode != "raw-nested" && mode != "unscoped" &&
        mode != "foreign-thread" && mode != "protected" && mode != "native-closure")
        return 2;
    recoverable = mode != "hard";
#ifndef TGNOME_RECOVERABLE_GJS
    if (recoverable)
        return 2;
#endif
    GjsContext* context = gjs_context_new();
    embedding_context = context;
    auto* native = static_cast<JSContext*>(gjs_context_get_native_context(context));
    if (!JS_AddInterruptCallback(native, interrupt)) {
        g_object_unref(context);
        return 2;
    }
    bool passed = true;
    const bool special = mode != "hard" && mode != "recoverable" && mode != "recover-then-hard";
    const auto ticker = g_timeout_add(10, [](gpointer) -> gboolean {
        ++heartbeats;
        return G_SOURCE_CONTINUE;
    }, nullptr);
    {
        Watchdog watchdog(native);
        GError* error = nullptr;
        int status = -1;
        passed = evaluate(context,
            "globalThis.marker = 73;"
            "globalThis.ProbeObject = imports.gi.GObject.registerClass("
            " {GTypeName: 'TgnomeInterruptObject'}, class extends imports.gi.GObject.Object {});"
            "globalThis.savedObject = new ProbeObject(); savedObject.marker = 'original';",
            "<setup>", &status, &error);
        g_clear_error(&error);
        if (mode == "foreign-thread") {
#ifdef TGNOME_RECOVERABLE_GJS
            std::atomic<bool> accepted{true};
            std::atomic<bool> scope_accepted{true};
            std::thread caller([&] {
                accepted.store(gjs_context_tgnome_mark_interrupt(context));
                scope_accepted.store(gjs_context_tgnome_protect_scope(context, true));
            });
            caller.join();
            passed = passed && !accepted.load() && !scope_accepted.load() &&
                gjs_context_tgnome_protected_depth(context) == 0 && !take_marker(context) &&
                verify(context, "marker === 73 && savedObject.marker === 'original'");
            g_print("{\"case\":\"foreign-thread-refused\",\"passed\":%s}\n", passed ? "true" : "false");
#endif
        } else if (mode == "native-closure") {
#ifdef TGNOME_RECOVERABLE_GJS
            passed = passed && gjs_context_tgnome_protect_scope(context, true);
            const bool timer_setup = evaluate(context,
                "globalThis.nativeDone = false; globalThis.nativeFinally = false;"
                "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => {"
                " try { const until = Date.now() + 1200; while (Date.now() < until) {} }"
                " finally { nativeFinally = true; } nativeDone = true; });",
                "<native-tagged-timer>", &status, &error);
            const bool timer_closed = gjs_context_tgnome_protect_scope(context, false);
            g_clear_error(&error);
            watchdog.arm();
            pump_for(1400);
            watchdog.disarm();
            passed = passed && timer_setup && timer_closed && delivered.load() == 0 &&
                denied.load() == 1 && gjs_context_tgnome_protected_depth(context) == 0 &&
                verify(context, "nativeDone && nativeFinally && marker === 73");
            g_print("{\"case\":\"native-tagged-timer\",\"passed\":%s}\n", passed ? "true" : "false");

            GCancellable* cancellable = g_cancellable_new();
            g_cancellable_push_current(cancellable);
            passed = passed && gjs_context_tgnome_protect_scope(context, true);
            const bool signal_setup = evaluate(context,
                "nativeDone = nativeFinally = false;"
                "imports.gi.GObject.Object.prototype.connect.call(imports.gi.Gio.Cancellable.get_current(), 'cancelled', () => {"
                " try { const until = Date.now() + 1200; while (Date.now() < until) {} }"
                " finally { nativeFinally = true; } nativeDone = true; });",
                "<native-tagged-signal>", &status, &error);
            const bool signal_closed = gjs_context_tgnome_protect_scope(context, false);
            g_clear_error(&error);
            g_cancellable_pop_current(cancellable);
            watchdog.arm();
            g_cancellable_cancel(cancellable);
            watchdog.disarm();
            g_object_unref(cancellable);
            passed = passed && signal_setup && signal_closed && delivered.load() == 0 &&
                denied.load() == 2 && gjs_context_tgnome_protected_depth(context) == 0 &&
                verify(context, "nativeDone && nativeFinally && savedObject.marker === 'original'");
            g_print("{\"case\":\"native-tagged-signal\",\"passed\":%s}\n", passed ? "true" : "false");

            passed = passed && gjs_context_tgnome_protect_scope(context, true);
            const bool throwing_setup = evaluate(context,
                "globalThis.nativeThrowEntered = false;"
                "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => {"
                " nativeThrowEntered = true; throw new Error('TGNOME tagged expected exception'); });",
                "<native-tagged-exception>", &status, &error);
            const bool throwing_closed = gjs_context_tgnome_protect_scope(context, false);
            g_clear_error(&error);
            pump_for(50);
            passed = passed && throwing_setup && throwing_closed &&
                gjs_context_tgnome_protected_depth(context) == 0 && verify(context, "nativeThrowEntered");
            g_print("{\"case\":\"native-tagged-exception-closed\",\"passed\":%s}\n", passed ? "true" : "false");

            passed = passed && evaluate(context,
                "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => { while(true) {} });",
                "<unprotected-after-tagged>", &status, &error);
            g_clear_error(&error);
            const auto before_ticks = heartbeats;
            const auto before = g_get_monotonic_time();
            watchdog.arm();
            while (delivered.load() == 0 && g_get_monotonic_time() - before < 3000000)
                g_main_context_iteration(nullptr, true);
            watchdog.disarm();
            pump_for(80);
            passed = passed && delivered.load() == 1 && denied.load() == 2 &&
                heartbeats > before_ticks && gjs_context_tgnome_protected_depth(context) == 0 &&
                !take_marker(context) && verify(context, "marker === 73 && savedObject.marker === 'original'");
            g_print("{\"case\":\"unprotected-after-native-tagged\",\"passed\":%s}\n", passed ? "true" : "false");
#endif
        } else if (special) {
            // This is deliberately outside the recovery contract: a native
            // call reenters JS while an older JS frame is still active.
            passed = passed && evaluate(context,
                "globalThis.nested = new imports.gi.Gio.Cancellable();"
                "globalThis.outerResumed = false;"
                "imports.gi.GObject.Object.prototype.connect.call(nested, 'cancelled', () => {"
                " marker = 74; while (true) {} });",
                "<nested-setup>", &status, &error);
            g_clear_error(&error);
            watchdog.arm();
            if (mode == "protected") {
#ifdef TGNOME_RECOVERABLE_GJS
                passed = passed && gjs_context_tgnome_protect_scope(context, true);
                evaluate(context, "while (true) {}", "<protected-native-entry>", &status, &error);
#endif
            } else if (mode == "nested") {
                evaluate(context, "nested.cancel(); outerResumed = true; marker = 75;",
                         "<nested-dispatch>", &status, &error);
            } else if (mode == "nested-loop") {
                evaluate(context,
                    "const nestedLoop = new imports.gi.GLib.MainLoop(null, false);"
                    "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => { while(true) {} });"
                    "nestedLoop.run(); outerResumed = true;",
                    "<nested-main-loop>", &status, &error);
            } else if (mode == "promise") {
                evaluate(context, "Promise.resolve().then(() => { while (true) {} });",
                         "<promise-job>", &status, &error);
            } else if (mode == "module") {
                g_autofree char* path = g_build_filename(g_getenv("XDG_RUNTIME_DIR"), "blocked.mjs", nullptr);
                g_autofree char* uri = g_filename_to_uri(path, nullptr, &error);
                uint8_t module_status = 0;
                if (uri && g_file_set_contents(path, "while (true) {}", -1, &error) &&
                    gjs_context_register_module(context, "tgnome.blocked", uri, &error)) {
                    const bool accepted = gjs_context_eval_module(
                        context, "tgnome.blocked", &module_status, &error);
                    g_print("{\"event\":\"module-returned\",\"accepted\":%s}\n",
                            accepted ? "true" : "false");
                }
            } else {
                RawEvaluation raw{mode == "raw-nested"
                    ? "nested.cancel(); outerResumed = true; marker = 75;" : "while (true) {}"};
                gjs_context_run_in_realm(context, raw_evaluate, &raw);
            }
            watchdog.disarm();
            g_clear_error(&error);
            passed = false; // These unsupported loops must remain blocked until supervised termination.
            g_print("{\"case\":\"unsupported-entry-returned\",\"passed\":false}\n");
        }
        if (passed && !special) {
            passed = evaluate(context,
                "globalThis.benignCalls = 0;"
                "globalThis.benign = new imports.gi.Gio.Cancellable();"
                "imports.gi.GObject.Object.prototype.connect.call(benign, 'cancelled', () => { benignCalls++; });"
                "benign.cancel();"
                "Promise.resolve().then(() => { benignCalls++; });",
                "<benign-nested-entry>", &status, &error);
            g_clear_error(&error);
            passed = passed && !take_marker(context) && verify(context,
                "benignCalls === 2 && marker === 73 && savedObject.marker === 'original'");
            g_print("{\"case\":\"benign-nested-entry\",\"passed\":%s}\n",
                    passed ? "true" : "false");
        }
#ifdef TGNOME_RECOVERABLE_GJS
        if (passed && recoverable && !special) {
            passed = !gjs_context_tgnome_protect_scope(context, false) &&
                gjs_context_tgnome_protect_scope(context, true) &&
                gjs_context_tgnome_protect_scope(context, true) &&
                gjs_context_tgnome_protected_depth(context) == 2;
            watchdog.arm();
            passed = passed && evaluate(context,
                "globalThis.protectedFinally = false;"
                "try { const until = Date.now() + 800; while (Date.now() < until) {} }"
                "finally { protectedFinally = true; }",
                "<protected-finite-scope>", &status, &error);
            watchdog.disarm();
            g_clear_error(&error);
            passed = passed && delivered.load() == 0 && denied.load() == 1 && !take_marker(context) &&
                gjs_context_tgnome_protected_depth(context) == 2 &&
                gjs_context_tgnome_protect_scope(context, false) &&
                gjs_context_tgnome_protected_depth(context) == 1 &&
                gjs_context_tgnome_protect_scope(context, false) &&
                gjs_context_tgnome_protected_depth(context) == 0 &&
                !gjs_context_tgnome_protect_scope(context, false) && verify(context,
                    "protectedFinally && marker === 73 && savedObject.marker === 'original'");
            g_print("{\"case\":\"protected-scope-refused-then-closed\",\"passed\":%s}\n",
                    passed ? "true" : "false");
        }
#endif
        for (unsigned cycle = 1; passed && !special && cycle <= 3; ++cycle) {
            watchdog.arm();
            const auto before = g_get_monotonic_time();
            const bool accepted = evaluate(context,
                "globalThis.caught = false; globalThis.finalized = false;"
                "globalThis.afterLoop = false;"
                "try { while (true) {} } catch (e) { caught = true; while (true) {} }"
                "finally { finalized = true; } afterLoop = true;",
                "<synchronous-spin>", &status, &error);
            watchdog.disarm();
            const bool marker = take_marker(context);
            const auto elapsed = (g_get_monotonic_time() - before) / 1000;
            const std::string failure = json_string(error ? error->message : "");
            g_clear_error(&error);
            const bool retained = verify(context,
                "marker === 73 && savedObject instanceof ProbeObject && savedObject.marker === 'original'");
            const bool no_cleanup = verify(context, "!caught && !finalized && !afterLoop");
            const bool same_context = native == gjs_context_get_native_context(context);
            passed = !accepted && no_cleanup && retained && same_context && marker == recoverable &&
                elapsed >= 100 && elapsed < 3000 && delivered.load() == cycle;
            g_print("{\"case\":\"synchronous-spin\",\"cycle\":%u,\"passed\":%s,"
                    "\"elapsedMs\":%ld,\"retainedObject\":%s,\"sameNativeContext\":%s,"
                    "\"catchAndFinallySkipped\":%s,\"markerAcknowledged\":%s,\"error\":%s}\n",
                    cycle, passed ? "true" : "false", static_cast<long>(elapsed),
                    retained ? "true" : "false", same_context ? "true" : "false",
                    no_cleanup ? "true" : "false", marker == recoverable ? "true" : "false", failure.c_str());
        }
        if (passed && !special) {
            passed = evaluate(context,
                "globalThis.entered = false; caught = finalized = afterLoop = false;"
                "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => {"
                " entered = true; try { while (true) {} } catch (e) { caught = true; }"
                " finally { finalized = true; } afterLoop = true; });",
                "<callback-setup>", &status, &error);
            g_clear_error(&error);
            const auto before_ticks = heartbeats;
            const auto before = g_get_monotonic_time();
            watchdog.arm();
            while (delivered.load() < 4 && g_get_monotonic_time() - before < 3000000)
                g_main_context_iteration(nullptr, true);
            watchdog.disarm();
            pump_for(80);
            const bool retained = verify(context,
                "marker === 73 && savedObject instanceof ProbeObject && savedObject.marker === 'original'");
            const bool cleanup_correct = verify(context, "entered && !caught && !finalized && !afterLoop");
            passed = passed && delivered.load() == 4 && retained && cleanup_correct &&
                heartbeats > before_ticks && native == gjs_context_get_native_context(context) &&
                !take_marker(context);
            g_print("{\"case\":\"glib-callback-spin\",\"passed\":%s,"
                    "\"cleanupMatchedMode\":%s,\"nativeHeartbeatsResumed\":%s}\n",
                    passed ? "true" : "false", cleanup_correct ? "true" : "false",
                    heartbeats > before_ticks ? "true" : "false");
        }
        if (passed && recoverable && !special) {
            GCancellable* cancellable = g_cancellable_new();
            g_cancellable_push_current(cancellable);
            passed = evaluate(context,
                "entered = caught = finalized = afterLoop = false;"
                "imports.gi.GObject.Object.prototype.connect.call("
                " imports.gi.Gio.Cancellable.get_current(), 'cancelled', () => {"
                " entered = true; try { while (true) {} } catch(e) { caught = true; }"
                " finally { finalized = true; } afterLoop = true; });",
                "<gobject-signal-setup>", &status, &error);
            g_clear_error(&error);
            const auto before_ticks = heartbeats;
            watchdog.arm();
            g_cancellable_cancel(cancellable);
            watchdog.disarm();
            g_cancellable_pop_current(cancellable);
            g_object_unref(cancellable);
            pump_for(80);
            passed = passed && delivered.load() == 5 && !take_marker(context) && verify(context,
                "entered && !finalized && !afterLoop && marker === 73 && savedObject.marker === 'original'") &&
                heartbeats > before_ticks;
            g_print("{\"case\":\"gobject-signal-spin\",\"passed\":%s,"
                    "\"nativeHeartbeatsResumed\":%s}\n", passed ? "true" : "false",
                    heartbeats > before_ticks ? "true" : "false");
        }
        if (passed && !special) {
            const auto count = delivered.load();
            passed = verify(context, "(imports.system.gc(), marker === 73)");
            pump_for(50);
            passed = passed && delivered.load() == count;
            g_print("{\"case\":\"unarmed-gc-control\",\"passed\":%s}\n", passed ? "true" : "false");
        }
        if (passed && mode == "recover-then-hard") {
            recoverable = false;
            passed = evaluate(context,
                "imports.gi.GLib.timeout_add_once(imports.gi.GLib.PRIORITY_DEFAULT, 1, () => { while (true) {} });",
                "<unmarked-after-recovery>", &status, &error);
            g_clear_error(&error);
            watchdog.arm();
            while (passed)
                g_main_context_iteration(nullptr, true);
        }
    }
    g_source_remove(ticker);
    g_object_unref(context);
    g_print("{\"classification\":\"RESEARCH PROTOTYPE\",\"passed\":%s,"
            "\"interruptions\":%u,\"shellRecoveryDemonstrated\":false}\n",
            passed ? "true" : "false", delivered.load());
    return passed ? 0 : 1;
}
