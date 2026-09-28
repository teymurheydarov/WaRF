#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* Copies src into a fixed-size local buffer — no length check */
void log_message(const char* src) {
    char buf[64];
    strcpy(buf, src);                   /* overflows if strlen(src) >= 64 */
    printf("[LOG] %s\n", buf);
}

/* Reads a line from stdin into a fixed buffer */
void read_input(char* out) {
    gets(out);                          /* removed from C11; unbounded read */
}

/* Concatenates two strings into a caller-supplied buffer */
void build_path(char* dst, const char* dir, const char* file) {
    strcpy(dst, dir);
    strcat(dst, "/");
    strcat(dst, file);                  /* no check that dst is large enough */
}

/* Formats a greeting — format string from caller */
void greet(const char* name_fmt) {
    printf(name_fmt);                   /* format string injection */
}

int main(void) {
    char path[32];
    build_path(path, "/very/long/directory/path/that/exceeds/buffer", "file.txt");
    log_message("hello");
    return 0;
}
