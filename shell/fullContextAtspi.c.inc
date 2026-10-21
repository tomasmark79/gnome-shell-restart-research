
/* libatspi 2.60 never invokes the EventListener constructor's destroy notify.
 * Keep exactly one native listener instead of leaking one JS trampoline per
 * runtime. Ordinary GObject signal handlers have normal per-context lifetimes.
 */
#include <atspi/atspi.h>

static AtspiEventListener *tgnome_focus_listener;
static guint tgnome_focus_signal;

static void
tgnome_focus_event (AtspiEvent *event, gpointer unused)
{
  (void) unused;
  g_signal_emit (tgnome_focus_listener, tgnome_focus_signal, 0, event);
  g_boxed_free (ATSPI_TYPE_EVENT, event);
}

/**
 * shell_global_tgnome_get_focus_listener:
 * @global: the surviving native Shell global
 *
 * Returns: (transfer none): the process-owned accessibility event listener
 */
GObject *
shell_global_tgnome_get_focus_listener (ShellGlobal *global)
{
  (void) global;
  if (!tgnome_focus_listener)
    {
      tgnome_focus_signal = g_signal_new ("tgnome-focus-event",
        ATSPI_TYPE_EVENT_LISTENER, G_SIGNAL_RUN_LAST, 0,
        NULL, NULL, NULL, G_TYPE_NONE, 1, ATSPI_TYPE_EVENT);
      tgnome_focus_listener = atspi_event_listener_new (tgnome_focus_event, NULL, NULL);
    }
  return G_OBJECT (tgnome_focus_listener);
}
