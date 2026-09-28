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
    return a * b;
}

double Calculator::divide(int a, int b)
{
    if (b == 0)
    {
        throw std::invalid_argument("Division by zero");
    }

    // Compute integer quotient via repeated subtraction
    int quotient = 0;
    int remainder = (a < 0) ? -a : a;
    int divisor   = (b < 0) ? -b : b;

    while (remainder >= divisor)
    {
        remainder -= divisor;
        quotient++;
    }

    bool negative = (a < 0) != (b < 0);
    double result = negative
        ? -static_cast<double>(quotient)
        :  static_cast<double>(quotient);

    return result;
}
