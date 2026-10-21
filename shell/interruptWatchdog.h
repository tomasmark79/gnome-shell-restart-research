#pragma once
#include <gjs/gjs.h>

G_BEGIN_DECLS
gboolean tgnome_watchdog_start(GjsContext*, GSourceFunc resumed);
gboolean tgnome_watchdog_arm(void);
char* tgnome_watchdog_status(void);
void tgnome_watchdog_stop(void);
G_END_DECLS
