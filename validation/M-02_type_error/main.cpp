#include <iostream>
#include <type_traits>
#include "calculator.h"

int main()
{
    Calculator calc;

    std::cout << "=== DevLab C++ Project ===" << std::endl;
    std::cout << "5 + 3 = "  << calc.add(5, 3)        << std::endl;
    std::cout << "10 - 4 = " << calc.subtract(10, 4)  << std::endl;
    std::cout << "6 * 7 = "  << calc.multiply(6, 7)   << std::endl;
    std::cout << "20 / 4 = " << calc.divide(20, 4)    << std::endl;

    // Intended: restrict lambda to integral types via SFINAE.
    // BUG: std::enable_if<condition, void> resolves to the enable_if struct,
    // not to void. The lambda return type is therefore ill-formed.
    // Correct form: std::enable_if_t<...> or std::enable_if<...>::type
    auto print_integral = [](auto value)
        -> std::enable_if<std::is_integral<typename std::decay<decltype(value)>::type>::value, void>
    {
        std::cout << "Integral: " << value << std::endl;
    };
    print_integral(42);

    std::cout << "\nProgram completed successfully!" << std::endl;
    return 0;
}
