#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <gdk/gdkx.h>
#include <wayland-client.h>
#include <X11/Xlib.h>
#include <sys/stat.h>
#include <unistd.h>

static GdkDisplay *display;
static GtkWidget *window;
static GtkWidget *entry;
static gchar *expected_typed_hash;
static unsigned long ticks;

static gboolean heartbeat(gpointer unused)
{
    (void) unused;
    int fd;
    const char *backend;
    unsigned long window_id;
    if (GDK_IS_WAYLAND_DISPLAY(display)) {
        struct wl_display *wl = gdk_wayland_display_get_wl_display(display);
        if (wl_display_roundtrip(wl) < 0)
            _exit(3);
        fd = wl_display_get_fd(wl);
        backend = "wayland";
        window_id = wl_proxy_get_id((struct wl_proxy *)
            gdk_wayland_window_get_wl_surface(gtk_widget_get_window(window)));
    } else if (GDK_IS_X11_DISPLAY(display)) {
        Display *x = gdk_x11_display_get_xdisplay(display);
        XSync(x, False);
        fd = ConnectionNumber(x);
        backend = "x11";
        window_id = GDK_WINDOW_XID(gtk_widget_get_window(window));
    } else {
        _exit(4);
    }
    struct stat st;
    if (fstat(fd, &st) < 0)
        _exit(5);
    gchar *text_hash = g_compute_checksum_for_string(G_CHECKSUM_SHA256,
        gtk_entry_get_text(GTK_ENTRY(entry)), -1);
    g_print("{\"pid\":%d,\"backend\":\"%s\",\"fd\":%d,\"inode\":%lu,\"windowId\":%lu,\"tick\":%lu,\"unsavedTextSha256\":\"%s\",\"expectedTypedSha256\":\"%s\"}\n",
            getpid(), backend, fd, (unsigned long) st.st_ino, window_id, ++ticks,
            text_hash, expected_typed_hash);
    g_free(text_hash);
    return G_SOURCE_CONTINUE;
}

int main(int argc, char **argv)
{
    gtk_init(&argc, &argv);
    display = gdk_display_get_default();
    window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Tgnome persistent connection probe");
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_box_pack_start(GTK_BOX(box), gtk_label_new("Original display connection"),
                       FALSE, FALSE, 0);
    entry = gtk_entry_new();
    gchar *unsaved_text = g_uuid_string_random();
    gtk_entry_set_text(GTK_ENTRY(entry), unsaved_text);
    gchar *typed_text = g_strconcat(unsaved_text, "a", NULL);
    expected_typed_hash = g_compute_checksum_for_string(G_CHECKSUM_SHA256, typed_text, -1);
    g_free(typed_text);
    g_free(unsaved_text);
    gtk_box_pack_start(GTK_BOX(box), entry, FALSE, FALSE, 0);
    gtk_container_add(GTK_CONTAINER(window), box);
    gtk_widget_show_all(window);
    gtk_widget_grab_focus(entry);
    gtk_editable_set_position(GTK_EDITABLE(entry), -1);
    g_timeout_add(200, heartbeat, NULL);
    gtk_main();
    return 0;
}
