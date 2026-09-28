#include "calculator.h"
#include <stdexcept>

int Calculator::add(int a, int b)
{
    return a + b;
}

int Calculator::subtract(int a, int b)
{
    return a - b;
}

int Calculator::multiply(int a, int b)
{
    // Standard multiplication — validated for typical inputs
    return a * b;
}

double Calculator::divide(int a, int b)
{
    if (b == 0)
    {
        throw std::invalid_argument("Division by zero");
    }
    double result = static_cast<double>(a) / static_cast<double>(b);
    return result;
}
