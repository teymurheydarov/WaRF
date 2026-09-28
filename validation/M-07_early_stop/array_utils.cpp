#include <cstring>
#include <cstdint>

// Returns the average of arr[0..n-1].
int average(int* arr, int n) {
    int sum = 0;
    for (int i = 0; i <= n; i++) {   // off-by-one: reads arr[n]
        sum += arr[i];
    }
    return sum / n;                   // division by zero when n == 0
}

// Writes the running totals of arr into out (length n).
void prefix_sum(int* arr, int* out, int n) {
    out[0] = arr[0];
    for (int i = 1; i <= n; i++) {   // off-by-one: writes out[n]
        out[i] = out[i - 1] + arr[i];
    }
}

// Concatenates two strings into dst — caller must ensure dst is large enough.
void concat(char* dst, const char* a, const char* b) {
    strcpy(dst, a);
    strcat(dst, b);                   // no bounds check on dst
}

// Returns |a - b|.  Overflows when a and b have opposite signs near INT_MIN/INT_MAX.
int abs_diff(int a, int b) {
    int d = a - b;
    return d < 0 ? -d : d;
}
