"""X language interpreter: cohesive builtin-family mixins split from the core Interpreter."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ._common import *  # noqa: F401,F403
from ._common import MAX_STRING_LENGTH, ComparatorItem, _is_class_method, _ARRAY_METHODS, _STRING_METHODS



class MathBuiltins:
    def _math_members(self) -> dict[str, Any]:
        return {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "inf": math.inf,
            "nan": math.nan,
            "abs": BuiltinFunction("Math.abs", lambda args: self._math_abs(args)),
            "sin": BuiltinFunction("Math.sin", lambda args: self._math_sin(args)),
            "cos": BuiltinFunction("Math.cos", lambda args: self._math_cos(args)),
            "tan": BuiltinFunction("Math.tan", lambda args: self._math_tan(args)),
            "asin": BuiltinFunction("Math.asin", lambda args: self._math_asin(args)),
            "acos": BuiltinFunction("Math.acos", lambda args: self._math_acos(args)),
            "atan": BuiltinFunction("Math.atan", lambda args: self._math_atan(args)),
            "atan2": BuiltinFunction("Math.atan2", lambda args: self._math_atan2(args)),
            "sinh": BuiltinFunction("Math.sinh", lambda args: self._math_sinh(args)),
            "cosh": BuiltinFunction("Math.cosh", lambda args: self._math_cosh(args)),
            "tanh": BuiltinFunction("Math.tanh", lambda args: self._math_tanh(args)),
            "exp": BuiltinFunction("Math.exp", lambda args: self._math_exp(args)),
            "log": BuiltinFunction("Math.log", lambda args: self._math_log(args)),
            "log2": BuiltinFunction("Math.log2", lambda args: self._math_log2(args)),
            "log10": BuiltinFunction("Math.log10", lambda args: self._math_log10(args)),
            "sqrt": BuiltinFunction("Math.sqrt", lambda args: self._math_sqrt(args)),
            "cbrt": BuiltinFunction("Math.cbrt", lambda args: self._math_cbrt(args)),
            "pow": BuiltinFunction("Math.pow", lambda args: self._math_pow(args)),
            "hypot": BuiltinFunction("Math.hypot", lambda args: self._math_hypot(args)),
            "floor": BuiltinFunction("Math.floor", lambda args: self._math_floor(args)),
            "ceil": BuiltinFunction("Math.ceil", lambda args: self._math_ceil(args)),
            "round": BuiltinFunction("Math.round", lambda args: self._math_round(args)),
            "trunc": BuiltinFunction("Math.trunc", lambda args: self._math_trunc(args)),
            "sign": BuiltinFunction("Math.sign", lambda args: self._math_sign(args)),
            "min": BuiltinFunction("Math.min", lambda args: self._math_min(args)),
            "max": BuiltinFunction("Math.max", lambda args: self._math_max(args)),
            "random": BuiltinFunction("Math.random", lambda args: self._math_random(args)),
            "randomInt": BuiltinFunction(
                "Math.randomInt", lambda args: self._math_random_int(args)
            ),
            "degrees": BuiltinFunction("Math.degrees", lambda args: self._math_degrees(args)),
            "radians": BuiltinFunction("Math.radians", lambda args: self._math_radians(args)),
            "isclose": BuiltinFunction("Math.isclose", lambda args: self._math_isclose(args)),
            "factorial": BuiltinFunction("Math.factorial", lambda args: self._math_factorial(args)),
            "gcd": BuiltinFunction("Math.gcd", lambda args: self._math_gcd(args)),
            "lcm": BuiltinFunction("Math.lcm", lambda args: self._math_lcm(args)),
            "perm": BuiltinFunction("Math.perm", lambda args: self._math_perm(args)),
            "comb": BuiltinFunction("Math.comb", lambda args: self._math_comb(args)),
        }

    def _math_unary(self, args: list[Any], func) -> float:
        if len(args) != 1:
            raise RuntimeErrorX(f"Expected 1 argument, got {len(args)}")
        val = args[0]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise RuntimeErrorX("Math functions expect a number")
        return func(val)

    def _math_binary(self, args: list[Any], func) -> float:
        if len(args) != 2:
            raise RuntimeErrorX(f"Expected 2 arguments, got {len(args)}")
        a, b = args[0], args[1]
        if isinstance(a, bool) or not isinstance(a, (int, float)):
            raise RuntimeErrorX("Math functions expect numbers")
        if isinstance(b, bool) or not isinstance(b, (int, float)):
            raise RuntimeErrorX("Math functions expect numbers")
        return func(a, b)

    def _math_variadic(self, args: list[Any], func) -> float:
        if len(args) == 0:
            raise RuntimeErrorX("Expected at least 1 argument")
        for val in args:
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise RuntimeErrorX("Math functions expect numbers")
        return func(*args)

    def _math_abs(self, args: list[Any]) -> float:
        return self._math_unary(args, abs)

    def _math_sin(self, args: list[Any]) -> float:
        return self._math_unary(args, math.sin)

    def _math_cos(self, args: list[Any]) -> float:
        return self._math_unary(args, math.cos)

    def _math_tan(self, args: list[Any]) -> float:
        return self._math_unary(args, math.tan)

    def _math_asin(self, args: list[Any]) -> float:
        return self._math_unary(args, math.asin)

    def _math_acos(self, args: list[Any]) -> float:
        return self._math_unary(args, math.acos)

    def _math_atan(self, args: list[Any]) -> float:
        return self._math_unary(args, math.atan)

    def _math_atan2(self, args: list[Any]) -> float:
        return self._math_binary(args, math.atan2)

    def _math_sinh(self, args: list[Any]) -> float:
        return self._math_unary(args, math.sinh)

    def _math_cosh(self, args: list[Any]) -> float:
        return self._math_unary(args, math.cosh)

    def _math_tanh(self, args: list[Any]) -> float:
        return self._math_unary(args, math.tanh)

    def _math_exp(self, args: list[Any]) -> float:
        return self._math_unary(args, math.exp)

    def _math_log(self, args: list[Any]) -> float:
        if len(args) not in (1, 2):
            raise RuntimeErrorX("Math.log expects 1 or 2 arguments")
        x = args[0]
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise RuntimeErrorX("Math.log expects a number")
        if len(args) == 2:
            base = args[1]
            if isinstance(base, bool) or not isinstance(base, (int, float)):
                raise RuntimeErrorX("Math.log expects a number as base")
            return math.log(x, base)
        return math.log(x)

    def _math_log2(self, args: list[Any]) -> float:
        return self._math_unary(args, math.log2)

    def _math_log10(self, args: list[Any]) -> float:
        return self._math_unary(args, math.log10)

    def _math_sqrt(self, args: list[Any]) -> float:
        return self._math_unary(args, math.sqrt)

    def _math_cbrt(self, args: list[Any]) -> float:
        return self._math_unary(args, math.cbrt)

    def _math_pow(self, args: list[Any]) -> float:
        return self._math_binary(args, math.pow)

    def _math_hypot(self, args: list[Any]) -> float:
        return self._math_variadic(args, math.hypot)

    def _math_floor(self, args: list[Any]) -> float:
        return self._math_unary(args, math.floor)

    def _math_ceil(self, args: list[Any]) -> float:
        return self._math_unary(args, math.ceil)

    def _math_round(self, args: list[Any]) -> float:
        if len(args) not in (1, 2):
            raise RuntimeErrorX("Math.round expects 1 or 2 arguments")
        x = args[0]
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise RuntimeErrorX("Math.round expects a number")
        if len(args) == 2:
            ndigits = args[1]
            if not isinstance(ndigits, int):
                raise RuntimeErrorX("Math.round ndigits must be an integer")
            return round(x, ndigits)
        return round(x)

    def _math_trunc(self, args: list[Any]) -> float:
        return self._math_unary(args, math.trunc)

    def _math_sign(self, args: list[Any]) -> float:
        return self._math_unary(args, lambda x: (x > 0) - (x < 0))

    def _math_min(self, args: list[Any]) -> float:
        return self._math_variadic(args, min)

    def _math_max(self, args: list[Any]) -> float:
        return self._math_variadic(args, max)

    def _math_random(self, args: list[Any]) -> float:
        if args:
            raise RuntimeErrorX("Math.random expects no arguments")
        return random.random()

    def _math_random_int(self, args: list[Any]) -> int:
        """``Math.randomInt(max)`` or ``Math.randomInt(min, max)``, both inclusive."""
        if len(args) == 1:
            low, high = 0, args[0]
        elif len(args) == 2:
            low, high = args[0], args[1]
        else:
            raise RuntimeErrorX("Math.randomInt expects 1 or 2 arguments")
        for value in (low, high):
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuntimeErrorX("Math.randomInt expects integer bounds")
        if low > high:
            raise RuntimeErrorX("Math.randomInt requires min <= max")
        return random.randint(low, high)

    def _math_degrees(self, args: list[Any]) -> float:
        return self._math_unary(args, math.degrees)

    def _math_radians(self, args: list[Any]) -> float:
        return self._math_unary(args, math.radians)

    def _math_isclose(self, args: list[Any]) -> bool:
        if len(args) not in (2, 4):
            raise RuntimeErrorX("Math.isclose expects 2 or 4 arguments")
        a, b = args[0], args[1]
        if isinstance(a, bool) or not isinstance(a, (int, float)):
            raise RuntimeErrorX("Math.isclose expects numbers")
        if isinstance(b, bool) or not isinstance(b, (int, float)):
            raise RuntimeErrorX("Math.isclose expects numbers")
        rel_tol = 1e-9
        abs_tol = 0.0
        if len(args) >= 3:
            rel_tol = args[2]
        if len(args) == 4:
            abs_tol = args[3]
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)

    def _math_factorial(self, args: list[Any]) -> int:
        return self._math_unary(args, math.factorial)

    def _math_gcd(self, args: list[Any]) -> int:
        return self._math_variadic(args, math.gcd)

    def _math_lcm(self, args: list[Any]) -> int:
        return self._math_variadic(args, math.lcm)

    def _math_perm(self, args: list[Any]) -> int:
        return self._math_binary(args, math.perm)

    def _math_comb(self, args: list[Any]) -> int:
        return self._math_binary(args, math.comb)

