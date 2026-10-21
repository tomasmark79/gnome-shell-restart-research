/* Private laboratory endpoint. Never compiled into the default/panel build. */
#include <sys/stat.h>
#include <unistd.h>

void _shell_global_reset_gjs_probe (ShellGlobal *self,
                                   GWeakNotify notify,
                                   gpointer data);

static gboolean tgnome_probe_allowed;
static gboolean tgnome_security_vm;
static guint tgnome_probe_attempts;
static guint tgnome_ui_failures;
static guint tgnome_ui_retry_attempts;
static guint tgnome_ui_commits;
static guint tgnome_ui_build_serial;
static guint tgnome_ui_timeouts;
static guint tgnome_ui_quarantines;
static guint tgnome_ui_timeout_id;
static gboolean tgnome_ui_quarantined;
static guint tgnome_preparation_failures;
static guint tgnome_preparation_timeouts;
static guint tgnome_preparation_timeout_id;
static gint64 tgnome_preparation_deadline;
static gboolean tgnome_ui_active;
static gboolean tgnome_ui_retried;
static guint tgnome_contexts_finalized;
static const char *tgnome_probe_state = "initial";
static GDBusConnection *tgnome_probe_bus;
static GDBusNodeInfo *tgnome_probe_node;
static guint tgnome_probe_registration;
static guint tgnome_ui_reset_signal;
static gboolean tgnome_in_place_probe;
static GHashTable *tgnome_initial_object_types;

static void
tgnome_collect_object_types (GType parent, GHashTable *types)
{
  guint n_children;
  guint i;
  GType *children = g_type_children (parent, &n_children);
  for (i = 0; i < n_children; i++)
    {
      g_hash_table_add (types, GSIZE_TO_POINTER (children[i]));
      tgnome_collect_object_types (children[i], types);
    }
  g_free (children);
}

static char *
tgnome_new_object_types (void)
{
  GHashTable *types = g_hash_table_new (g_direct_hash, g_direct_equal);
  GHashTableIter iter;
  gpointer type;
  GList *names = NULL;
  GList *item;
  GString *json = g_string_new ("[");

  tgnome_collect_object_types (G_TYPE_OBJECT, types);
  if (!tgnome_initial_object_types)
    tgnome_initial_object_types = g_hash_table_ref (types);
  g_hash_table_iter_init (&iter, types);
  while (g_hash_table_iter_next (&iter, &type, NULL))
    if (!g_hash_table_contains (tgnome_initial_object_types, type))
      names = g_list_prepend (names, (gpointer) g_type_name (GPOINTER_TO_SIZE (type)));
  names = g_list_sort (names, (GCompareFunc) g_strcmp0);
  for (item = names; item; item = item->next)
    g_string_append_printf (json, "%s\"%s\"", item == names ? "" : ",", (char *) item->data);
  g_string_append_c (json, ']');
  g_list_free (names);
  g_hash_table_unref (types);
  return g_string_free (json, FALSE);
}

static guint
tgnome_registered_object_types (GType parent)
{
  guint n_children;
  guint i;
  guint count = 0;
  GType *children = g_type_children (parent, &n_children);
  for (i = 0; i < n_children; i++)
    count += 1 + tgnome_registered_object_types (children[i]);
  g_free (children);
  return count;
}

static void
tgnome_runtime_configure (int argc, char **argv)
{
  gboolean headless = FALSE;
  int i;

  for (i = 1; i < argc; i++)
    headless |= g_str_equal (argv[i], "--headless");
#ifdef TGNOME_SECURITY_VM
  {
    struct stat marker_stat;
    g_autofree char *marker = NULL;
    g_autofree char *product = NULL;

    // Only the separate VM build can pass this gate. Environment variables
    // alone never enable a native-backend reload in the regular package.
    tgnome_security_vm =
      lstat ("/etc/tgnome-vm-fixture", &marker_stat) == 0 &&
      S_ISREG (marker_stat.st_mode) && marker_stat.st_uid == 0 &&
      (marker_stat.st_mode & 0022) == 0 &&
      g_file_get_contents ("/etc/tgnome-vm-fixture", &marker, NULL, NULL) &&
      g_strcmp0 (marker, "security-reload-v1\n") == 0 &&
      g_file_get_contents ("/sys/class/dmi/id/product_name", &product, NULL, NULL) &&
      g_strcmp0 (g_strstrip (product), "TgnomeSecurityFixture") == 0;
  }
#endif
  tgnome_probe_allowed = (headless || tgnome_security_vm) &&
    g_strcmp0 (g_getenv ("TGNOME_ALLOW_RUNTIME_RESET"), "1") == 0 &&
    g_getenv ("GNOME_SHELL_JS") == NULL;
}

static guint
tgnome_registered_probe_types (GType parent)
{
  guint n_children;
  guint count = 0;
  guint i;
  GType *children = g_type_children (parent, &n_children);

  for (i = 0; i < n_children; i++)
    {
      if (g_str_has_prefix (g_type_name (children[i]), "TgnomeRT_"))
        count++;
      count += tgnome_registered_probe_types (children[i]);
    }
  g_free (children);
  return count;
}

static void
tgnome_runtime_prepare (void)
{
  tgnome_ui_reset_signal = g_signal_new ("tgnome-ui-reset", SHELL_TYPE_GLOBAL,
    G_SIGNAL_RUN_LAST, 0, NULL, NULL, NULL, G_TYPE_NONE, 0);
}

static void
tgnome_runtime_ui_shutdown (void)
{
  ShellGlobal *global = shell_global_get ();

  // UI destruction must run while its JS context is valid. This separate
  // signal deliberately does not invoke native ShellWindowTracker shutdown.
  g_signal_emit (global, tgnome_ui_reset_signal, 0);
  g_signal_handlers_disconnect_matched (global, G_SIGNAL_MATCH_ID,
    tgnome_ui_reset_signal, 0, NULL, NULL, NULL);
}

static char *
tgnome_runtime_status (void)
{
  g_autofree char *new_types = tgnome_new_object_types ();
  int security_bits = 0;
  int published_generation = 0;
  if (tgnome_ui_commits > 0 &&
      g_strcmp0 (g_getenv ("TGNOME_PERSISTENT_CONTEXT"), "1") == 0)
    {
      GError *error = NULL;
      // UiStarted is an asynchronous acknowledgement. Main publishes the
      // generation and releases the security curtain after receiving it.
      // Observe that final publication without depending on any UI D-Bus
      // object or extension (extensions are disabled on the lock screen).
      if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
          "(globalThis.global?._tgnomeUiReloadState === 'started' ? "
          "globalThis.global._tgnomeUiGeneration : 0) || 0;",
          -1, "<tgnome-ui-publication>", &published_generation, &error))
        {
          published_generation = -1;
          g_clear_error (&error);
        }
    }
  if (tgnome_security_vm)
    {
      GError *error = NULL;
      if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
          "(() => { const s = globalThis.global?._tgnomeGetSecurityBoundary?.(); "
          "return s ? (1 | (s.pendingLock ? 2 : 0) | "
          "(s.curtainVisible ? 4 : 0) | (s.grabbed ? 8 : 0) | "
          "(s.topmost ? 16 : 0) | (!s.screenShieldPresent ? 32 : 0) | "
          "(s.pausedWithoutShield ? 64 : 0)) : 0; })();",
          -1, "<tgnome-security-status>", &security_bits, &error))
        {
          security_bits = -1;
          g_clear_error (&error);
        }
    }
  return g_strdup_printf ("{\"pid\":%d,\"publishedUiGeneration\":%d,\"attempts\":%u,\"contextsFinalized\":%u,"
                          "\"state\":\"%s\",\"registeredProbeTypes\":%u,"
                          "\"registeredObjectTypes\":%u,\"newObjectTypes\":%s,"
                          "\"uiFailures\":%u,\"uiRetryAttempts\":%u,\"uiCommits\":%u,"
                          "\"uiBuildSerial\":%u,\"uiTimeouts\":%u,\"uiQuarantined\":%s,"
                          "\"uiQuarantines\":%u,"
                          "\"preparationFailures\":%u,\"preparationTimeouts\":%u,"
                          "\"uiActive\":%s,\"securityVm\":%s,\"securityBoundaryBits\":%d,\"researchOnly\":true}",
                          (int) getpid (), published_generation,
                          tgnome_probe_attempts, tgnome_contexts_finalized,
                          tgnome_probe_state,
                          tgnome_registered_probe_types (G_TYPE_OBJECT),
                          tgnome_registered_object_types (G_TYPE_OBJECT), new_types,
                          tgnome_ui_failures, tgnome_ui_retry_attempts, tgnome_ui_commits,
                          tgnome_ui_build_serial, tgnome_ui_timeouts,
                          tgnome_ui_quarantined ? "true" : "false",
                          tgnome_ui_quarantines,
                          tgnome_preparation_failures, tgnome_preparation_timeouts,
                          tgnome_ui_active ? "true" : "false",
                          tgnome_security_vm ? "true" : "false", security_bits);
}

static gboolean
tgnome_preparation_expired (gpointer data)
{
  GError *error = NULL;
  int result;
  (void) data;
  tgnome_preparation_timeout_id = 0;
  if (!tgnome_ui_active || !g_str_equal (tgnome_probe_state, "ui-preparing"))
    return G_SOURCE_REMOVE;
  tgnome_ui_active = FALSE;
  tgnome_preparation_failures++;
  tgnome_preparation_timeouts++;
  tgnome_probe_state = "ui-preparation-timeout";
  if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
                        "global._tgnomeAbortPreparation?.('Native preparation deadline exceeded');",
                        -1, "<tgnome-preparation-timeout>", &result, &error))
    {
      g_warning ("TGNOME preparation cancellation failed: %s", error->message);
      g_clear_error (&error);
    }
  return G_SOURCE_REMOVE;
}

static gboolean
tgnome_ui_cancellation_expired (gpointer data)
{
  (void) data;
  tgnome_ui_timeout_id = 0;
  if (tgnome_ui_active && g_str_equal (tgnome_probe_state, "ui-cancelling"))
    {
      tgnome_ui_active = FALSE;
      tgnome_ui_quarantined = TRUE;
      tgnome_ui_quarantines++;
      tgnome_probe_state = "ui-cancellation-timeout";
    }
  return G_SOURCE_REMOVE;
}

static gboolean
tgnome_ui_construction_expired (gpointer data)
{
  GError *error = NULL;
  int result;
  (void) data;
  tgnome_ui_timeout_id = 0;
  if (!tgnome_ui_active || !g_str_equal (tgnome_probe_state, "same-context-ui-starting"))
    return G_SOURCE_REMOVE;
  tgnome_ui_timeouts++;
  tgnome_probe_state = "ui-cancelling";
  if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
                        "global._tgnomeAbortUiCandidate?.('Native UI construction deadline exceeded');",
                        -1, "<tgnome-construction-timeout>", &result, &error))
    {
      g_warning ("TGNOME candidate cancellation failed: %s", error->message);
      g_clear_error (&error);
    }
  tgnome_ui_timeout_id = g_timeout_add (2000, tgnome_ui_cancellation_expired, NULL);
  return G_SOURCE_REMOVE;
}

static void
tgnome_context_finalized (gpointer data, GObject *object)
{
  (void) data;
  (void) object;
  tgnome_contexts_finalized++;
  g_message ("TGNOME previous GJS context finalized (%u)",
             tgnome_contexts_finalized);
}

static gboolean
tgnome_runtime_reset_idle (gpointer data)
{
  ShellGlobal *global = shell_global_get ();
  GError *error = NULL;
  uint8_t status;
  int gate_status;

  (void) data;
  if (!gjs_context_eval (_shell_global_get_gjs_context (global),
                        "if (!global._tgnomeResetPrepared) throw new Error('UI reset not prepared');",
                        -1, "<tgnome-reset-gate>", &gate_status, &error))
    {
      tgnome_probe_state = "not-prepared";
      tgnome_ui_active = FALSE;
      g_warning ("TGNOME reset preparation missing: %s", error->message);
      g_clear_error (&error);
      return G_SOURCE_REMOVE;
    }
  tgnome_probe_state = "resetting";
  if (tgnome_in_place_probe &&
      !gjs_context_eval (_shell_global_get_gjs_context (global),
                        "global._tgnomeReleaseUiStageActions();", -1,
                        "<tgnome-input-actions>", &gate_status, &error))
    goto in_place_fail;
  tgnome_runtime_ui_shutdown ();
  if (!gjs_context_eval (_shell_global_get_gjs_context (global),
                        "global._tgnomeReleaseSources();", -1,
                        "<tgnome-source-cleanup>", &gate_status, &error))
    {
      tgnome_probe_state = "source-cleanup-failed";
      tgnome_ui_active = FALSE;
      g_warning ("TGNOME source cleanup failed: %s", error->message);
      g_clear_error (&error);
      return G_SOURCE_REMOVE;
    }
  if (tgnome_in_place_probe)
    {
      g_autofree char *start_script = NULL;
      if (!gjs_context_eval (_shell_global_get_gjs_context (global),
                            "global._tgnomeReleaseUiRegistrations();", -1,
                            "<tgnome-registration-cleanup>", &gate_status, &error))
        goto in_place_fail;
      g_setenv ("TGNOME_UI_RESTARTING", "1", TRUE);
      tgnome_ui_build_serial++;
      start_script = g_strdup_printf ("global._tgnomeRestartUiInPlace(%u);", tgnome_ui_build_serial);
      if (!gjs_context_eval (_shell_global_get_gjs_context (global),
                            start_script, -1,
                            "<tgnome-ui-start>", &gate_status, &error))
        goto in_place_fail;
      tgnome_probe_state = "same-context-ui-starting";
      tgnome_ui_timeout_id = g_timeout_add (5000, tgnome_ui_construction_expired, NULL);
      return G_SOURCE_REMOVE;
    }
  _shell_global_reset_gjs_probe (global, tgnome_context_finalized, NULL);
  tgnome_probe_state = "new-context-created";
  g_setenv ("TGNOME_UI_RESTARTING", "1", TRUE);
  if (!gjs_context_eval_module_file (_shell_global_get_gjs_context (global),
                                    "resource:///org/gnome/shell/ui/init.js",
                                    &status, &error))
    {
      tgnome_probe_state = "module-evaluation-failed";
      g_warning ("TGNOME reset module failed: %s", error->message);
      g_clear_error (&error);
    }
  return G_SOURCE_REMOVE;
in_place_fail:
  tgnome_ui_active = FALSE;
  tgnome_probe_state = "in-place-evaluation-failed";
  g_warning ("TGNOME in-place evaluation failed: %s", error->message);
  g_clear_error (&error);
  return G_SOURCE_REMOVE;
}

#ifdef TGNOME_INTERRUPTION_SHELL
#include "interruptRuntime.h"
#endif

static void
tgnome_runtime_method (GDBusConnection       *connection,
                       const char            *sender,
                       const char            *object_path,
                       const char            *interface_name,
                       const char            *method_name,
                       GVariant              *parameters,
                       GDBusMethodInvocation *invocation,
                       gpointer               user_data)
{
  g_autofree char *status = NULL;
  (void) connection;
  (void) sender;
  (void) object_path;
  (void) interface_name;
  (void) parameters;
  (void) user_data;

#ifdef TGNOME_INTERRUPTION_SHELL
  if (tgnome_interrupt_method (method_name, invocation))
    return;
#endif

  if (g_str_equal (method_name, "BeginUiReload") ||
      g_str_equal (method_name, "StartUiReload") ||
      g_str_equal (method_name, "CancelUiReload"))
    {
      if (g_strcmp0 (sender, g_dbus_connection_get_unique_name (connection)) != 0 ||
          g_strcmp0 (g_getenv ("TGNOME_PERSISTENT_CONTEXT"), "1") != 0)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_PERMISSION_DENIED, "Owned reload coordination requires this Shell connection");
          return;
        }
      if (g_str_equal (method_name, "BeginUiReload"))
        {
          if (tgnome_ui_quarantined)
            {
              g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                G_IO_ERROR_BUSY, "UI is quarantined until the current candidate confirms cleanup");
              return;
            }
          if (tgnome_probe_attempts >= 3 || tgnome_ui_active || tgnome_ui_quarantined)
            {
              g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                G_IO_ERROR_BUSY, "Owned reload is busy or its laboratory limit is reached");
              return;
            }
          tgnome_probe_attempts++;
          tgnome_ui_active = TRUE;
          tgnome_ui_retried = FALSE;
          tgnome_in_place_probe = TRUE;
          tgnome_probe_state = "ui-preparing";
          tgnome_preparation_deadline = g_get_monotonic_time () + 5 * G_TIME_SPAN_SECOND;
          tgnome_preparation_timeout_id = g_timeout_add (5000, tgnome_preparation_expired, NULL);
        }
      else
        {
          if (!tgnome_ui_active || !g_str_equal (tgnome_probe_state, "ui-preparing"))
            {
              g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                G_IO_ERROR_FAILED, "No owned preparation is active");
              return;
            }
          if (g_str_equal (method_name, "CancelUiReload"))
            {
              g_clear_handle_id (&tgnome_preparation_timeout_id, g_source_remove);
              tgnome_preparation_failures++;
              tgnome_ui_active = FALSE;
              tgnome_probe_state = "ui-preparation-failed";
            }
          else
            {
              GError *gate_error = NULL;
              int gate_status = 1;
              gboolean evaluated;
              if (g_get_monotonic_time () >= tgnome_preparation_deadline)
                {
                  g_clear_handle_id (&tgnome_preparation_timeout_id, g_source_remove);
                  tgnome_preparation_expired (NULL);
                  g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                    G_IO_ERROR_TIMED_OUT, "Owned preparation deadline expired before commit");
                  return;
                }
              // Commit is synchronous and runs only after the native lease
              // validation. No async gap may separate UI mutation and scheduling.
              g_clear_handle_id (&tgnome_preparation_timeout_id, g_source_remove);
              tgnome_probe_state = "ui-committing";
              evaluated = gjs_context_eval (
                _shell_global_get_gjs_context (shell_global_get ()),
                "if (typeof global._tgnomeCommitPreparation !== 'function') "
                "throw new Error('Owned commit callback missing'); "
                "global._tgnomeCommitPreparation(); "
                "(global._tgnomeResetPrepared && !global._tgnomeUiPreparing && "
                "global._tgnomeUiReloadState !== 'starting') ? 0 : 1;",
                -1, "<tgnome-owned-gate>", &gate_status, &gate_error);
              if (!evaluated || gate_status != 0)
                {
                  g_clear_error (&gate_error);
                  tgnome_preparation_failures++;
                  tgnome_ui_active = FALSE;
                  tgnome_probe_state = "ui-preparation-failed";
                  g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                    G_IO_ERROR_FAILED, "Owned UI preparation is incomplete");
                  return;
                }
              tgnome_probe_state = "scheduled";
              g_idle_add_full (G_PRIORITY_LOW, tgnome_runtime_reset_idle, NULL, NULL);
            }
        }
    }
  else if (g_str_equal (method_name, "UiStarted") ||
      g_str_equal (method_name, "UiFailed"))
    {
      guint serial;
      gboolean cleanup_ready = FALSE;
      if (g_strcmp0 (sender, g_dbus_connection_get_unique_name (connection)) != 0)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_PERMISSION_DENIED, "UI outcomes must originate from this Shell connection");
          return;
        }
      if (g_str_equal (method_name, "UiStarted"))
        g_variant_get (parameters, "(u)", &serial);
      else
        g_variant_get (parameters, "(ub)", &serial, &cleanup_ready);
      if (serial != tgnome_ui_build_serial)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_FAILED, "Outcome belongs to a different UI candidate");
          return;
        }
      // A late cleanup acknowledgement may reopen explicit recovery, but
      // expiry has permanently ended automatic retries for this transaction.
      if (tgnome_ui_quarantined && !tgnome_ui_active &&
          g_str_equal (tgnome_probe_state, "ui-cancellation-timeout") &&
          g_str_equal (method_name, "UiFailed"))
        {
          if (!cleanup_ready)
            {
              g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                G_IO_ERROR_FAILED, "Cleanup readiness has not been confirmed");
              return;
            }
          {
            GError *gate_error = NULL;
            int gate_status = 1;
            gboolean evaluated = gjs_context_eval (
              _shell_global_get_gjs_context (shell_global_get ()),
              "(global._tgnomeResetPrepared && !global._tgnomeUiPreparing && "
              "global._tgnomeUiReloadState === 'failed') ? 0 : 1;",
              -1, "<tgnome-late-cleanup-gate>", &gate_status, &gate_error);
            if (!evaluated || gate_status != 0)
              {
                g_clear_error (&gate_error);
                g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                  G_IO_ERROR_FAILED, "Cleanup acknowledgement is not prepared");
                return;
              }
          }
          tgnome_ui_failures++;
          tgnome_ui_quarantined = FALSE;
          tgnome_probe_state = "ui-failed";
          status = tgnome_runtime_status ();
          g_dbus_method_invocation_return_value (invocation, g_variant_new ("(s)", status));
          return;
        }
      if (!tgnome_in_place_probe || !tgnome_ui_active ||
          (!g_str_equal (tgnome_probe_state, "same-context-ui-starting") &&
           !(g_str_equal (method_name, "UiFailed") &&
             g_str_equal (tgnome_probe_state, "ui-cancelling"))))
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_FAILED, "No UI construction is awaiting an outcome");
          return;
        }
      g_clear_handle_id (&tgnome_ui_timeout_id, g_source_remove);
      if (g_str_equal (method_name, "UiStarted"))
        {
          tgnome_ui_active = FALSE;
          tgnome_ui_commits++;
          tgnome_probe_state = "ui-ready";
        }
      else
        {
          tgnome_ui_failures++;
          if (!cleanup_ready)
            {
              if (!tgnome_ui_quarantined)
                tgnome_ui_quarantines++;
              tgnome_ui_quarantined = TRUE;
            }
          if (cleanup_ready && !tgnome_ui_retried)
            {
              tgnome_ui_retried = TRUE;
              tgnome_ui_retry_attempts++;
              tgnome_probe_state = "recovery-scheduled";
              g_idle_add_full (G_PRIORITY_LOW, tgnome_runtime_reset_idle, NULL, NULL);
            }
          else
            {
              tgnome_ui_active = FALSE;
              tgnome_probe_state = "ui-failed";
            }
        }
    }
  else if (g_str_equal (method_name, "ResetProbe") ||
      g_str_equal (method_name, "ReloadUiProbe") ||
      g_str_equal (method_name, "RecoverUi"))
    {
      gboolean stable = g_strcmp0 (g_getenv ("TGNOME_PERSISTENT_CONTEXT"), "1") == 0;
      gboolean recovery = g_str_equal (method_name, "RecoverUi");
      gboolean in_place = !g_str_equal (method_name, "ResetProbe");
      if (recovery)
        {
          guint serial;
          g_variant_get (parameters, "(u)", &serial);
          // A recovery caller need not depend on the failed extension/UI.
          // Bind its request to one failed candidate so a delayed/replayed
          // call cannot restart a later generation or consume another slot.
          if (serial != tgnome_ui_build_serial || tgnome_ui_active ||
              !g_str_equal (tgnome_probe_state, "ui-failed") || tgnome_ui_quarantined)
            {
              g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
                G_IO_ERROR_BUSY, "Recovery requires the current failed candidate with confirmed cleanup; UI may be quarantined");
              return;
            }
        }
      if (tgnome_ui_quarantined)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_BUSY, "UI is quarantined until the current candidate confirms cleanup");
          return;
        }
      if (stable != in_place)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_NOT_SUPPORTED, "This probe requires the matching development variant");
          return;
        }
      if (tgnome_probe_attempts >= (in_place ? 3u : 1u))
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_NOT_SUPPORTED, "Laboratory attempt limit reached; Only one laboratory reset is permitted per context probe");
          return;
        }
      if (tgnome_ui_active || tgnome_ui_quarantined)
        {
          g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
            G_IO_ERROR_BUSY, "A UI construction transaction is active");
          return;
        }
      {
        GError *gate_error = NULL;
        int gate_status = 1;
        gboolean evaluated = gjs_context_eval (
          _shell_global_get_gjs_context (shell_global_get ()),
          "(global._tgnomeResetPrepared && !global._tgnomeUiPreparing && "
          "global._tgnomeUiReloadState !== 'starting') ? 0 : 1;",
          -1, "<tgnome-admission-gate>", &gate_status, &gate_error);
        if (!evaluated || gate_status != 0)
          {
            g_clear_error (&gate_error);
            g_dbus_method_invocation_return_error (invocation, G_IO_ERROR,
              G_IO_ERROR_FAILED, "UI is not prepared; request was not admitted");
            return;
          }
      }
      tgnome_ui_active = in_place;
      tgnome_ui_retried = FALSE;
      tgnome_probe_attempts++;
      tgnome_in_place_probe = in_place;
      tgnome_probe_state = "scheduled";
      g_idle_add_full (G_PRIORITY_LOW, tgnome_runtime_reset_idle, NULL, NULL);
    }
  status = tgnome_runtime_status ();
  g_dbus_method_invocation_return_value (invocation, g_variant_new ("(s)", status));
}

static void
tgnome_runtime_start (void)
{
  static const GDBusInterfaceVTable vtable = { .method_call = tgnome_runtime_method };
  static const char xml[] =
    "<node><interface name='org.gnome.Shell.TgnomeRuntime'>"
    "<method name='Status'><arg type='s' direction='out'/></method>"
#ifdef TGNOME_INTERRUPTION_SHELL
    "<method name='InterruptUiProbe'><arg type='s' direction='out'/></method>"
    "<method name='InterruptUiStatus'><arg type='s' direction='out'/></method>"
    "<method name='InterruptHandoffStatus'><arg type='s' direction='out'/></method>"
    "<method name='ReleaseInterruptHandoff'><arg type='s' direction='out'/></method>"
#endif
    "<method name='ResetProbe'><arg type='s' direction='out'/></method>"
    "<method name='ReloadUiProbe'><arg type='s' direction='out'/></method>"
    "<method name='RecoverUi'><arg type='u' direction='in'/><arg type='s' direction='out'/></method>"
    "<method name='BeginUiReload'><arg type='s' direction='out'/></method>"
    "<method name='StartUiReload'><arg type='s' direction='out'/></method>"
    "<method name='CancelUiReload'><arg type='s' direction='out'/></method>"
    "<method name='UiStarted'><arg type='u' direction='in'/><arg type='s' direction='out'/></method>"
    "<method name='UiFailed'><arg type='u' direction='in'/><arg type='b' direction='in'/><arg type='s' direction='out'/></method>"
    "</interface></node>";
  GError *error = NULL;

  if (!tgnome_probe_allowed)
    return;
  if (tgnome_security_vm)
    {
      int result;
      if (!gjs_context_eval (_shell_global_get_gjs_context (shell_global_get ()),
            "Object.defineProperty(imports.gi.Shell.Global.get(), '_tgnomeSecurityVm', "
            "{value: true, writable: false, configurable: false});",
            -1, "<tgnome-security-vm>", &result, &error))
        goto fail;
    }
  tgnome_probe_node = g_dbus_node_info_new_for_xml (xml, &error);
  if (!tgnome_probe_node)
    goto fail;
  tgnome_probe_bus = g_bus_get_sync (G_BUS_TYPE_SESSION, NULL, &error);
  if (!tgnome_probe_bus)
    goto fail;
  tgnome_probe_registration = g_dbus_connection_register_object (
    tgnome_probe_bus, "/org/gnome/Shell/TgnomeRuntime",
    tgnome_probe_node->interfaces[0], &vtable, NULL, NULL, &error);
  if (!tgnome_probe_registration)
    goto fail;
  tgnome_probe_state = "ready";
#ifdef TGNOME_INTERRUPTION_SHELL
  if (!tgnome_security_vm && g_strcmp0 (g_getenv ("TGNOME_ALLOW_INTERRUPTION"), "1") == 0)
    {
      tgnome_interrupt_available = tgnome_watchdog_start (
        _shell_global_get_gjs_context (shell_global_get ()), tgnome_interrupt_resumed);
      if (!tgnome_interrupt_available)
        g_warning ("TGNOME watchdog unavailable");
    }
#endif
  return;
fail:
  g_warning ("TGNOME native endpoint unavailable: %s", error->message);
  g_clear_error (&error);
}

static void
tgnome_runtime_stop (void)
{
#ifdef TGNOME_INTERRUPTION_SHELL
  tgnome_watchdog_stop ();
  g_clear_handle_id (&tgnome_interrupt_handoff_timeout, g_source_remove);
  g_clear_handle_id (&tgnome_interrupt_settle_source, g_source_remove);
  g_clear_handle_id (&tgnome_backend_emit_source, g_source_remove);
  g_clear_pointer (&tgnome_interrupt_reply, g_free);
  g_clear_pointer (&tgnome_interrupt_error, g_free);
#endif
  g_clear_handle_id (&tgnome_preparation_timeout_id, g_source_remove);
  g_clear_handle_id (&tgnome_ui_timeout_id, g_source_remove);
  if (tgnome_probe_registration)
    g_dbus_connection_unregister_object (tgnome_probe_bus, tgnome_probe_registration);
  g_clear_pointer (&tgnome_probe_node, g_dbus_node_info_unref);
  g_clear_object (&tgnome_probe_bus);
  g_clear_pointer (&tgnome_initial_object_types, g_hash_table_unref);
}
